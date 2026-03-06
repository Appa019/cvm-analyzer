#!/usr/bin/env bash
# ==============================================================================
# FRE Analyzer — Setup Script para Oracle Cloud Free Tier
# VM.Standard.E2.1.Micro (1 OCPU AMD, 1GB RAM, Ubuntu 22.04)
# ==============================================================================
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log()   { echo -e "${GREEN}[SETUP]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

# ── Verificações ─────────────────────────────────────────────────────────────
[[ $EUID -ne 0 ]] && error "Execute como root: sudo bash deploy/setup.sh"

REPO_DIR="${1:-/home/ubuntu/fre-analyzer}"
DOMAIN="${2:-}"
APP_USER="ubuntu"

log "Diretório do projeto: $REPO_DIR"
[[ -n "$DOMAIN" ]] && log "Domínio: $DOMAIN" || warn "Domínio não informado (SSL será configurado depois)"

# ── 1. Swap de 2GB ──────────────────────────────────────────────────────────
if [ ! -f /swapfile ]; then
    log "Configurando swap de 2GB..."
    fallocate -l 2G /swapfile
    chmod 600 /swapfile
    mkswap /swapfile
    swapon /swapfile
    echo '/swapfile none swap sw 0 0' >> /etc/fstab
    # Reduzir swappiness para priorizar RAM
    echo 'vm.swappiness=10' >> /etc/sysctl.conf
    sysctl vm.swappiness=10
    log "Swap configurado"
else
    log "Swap já existe, pulando..."
fi

# ── 2. Desabilitar serviços desnecessários ───────────────────────────────────
log "Desabilitando serviços desnecessários..."
for svc in snapd snapd.socket snapd.seeded.service unattended-upgrades; do
    if systemctl is-active --quiet "$svc" 2>/dev/null; then
        systemctl stop "$svc" 2>/dev/null || true
        systemctl disable "$svc" 2>/dev/null || true
        log "  Desabilitado: $svc"
    fi
done

# ── 3. Instalar dependências do sistema ──────────────────────────────────────
log "Atualizando pacotes..."
apt-get update -qq

log "Instalando dependências..."
apt-get install -y -qq \
    python3.11 python3.11-venv python3.11-dev \
    nginx certbot python3-certbot-nginx \
    fail2ban \
    git curl wget \
    build-essential

# Node.js 20.x (via NodeSource)
if ! command -v node &>/dev/null; then
    log "Instalando Node.js 20.x..."
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
    apt-get install -y -qq nodejs
fi
log "Node: $(node --version), npm: $(npm --version)"

# ── 4. Clonar ou verificar repositório ───────────────────────────────────────
if [ ! -d "$REPO_DIR" ]; then
    log "Clonando repositório..."
    git clone https://github.com/Appa019/fre-analyzer.git "$REPO_DIR"
    chown -R "$APP_USER:$APP_USER" "$REPO_DIR"
else
    log "Repositório já existe em $REPO_DIR"
fi

# ── 5. Python venv + dependências ───────────────────────────────────────────
log "Configurando Python venv..."
cd "$REPO_DIR"

if [ ! -d .venv ]; then
    python3.11 -m venv .venv
fi
source .venv/bin/activate
pip install --upgrade pip -q
pip install -r requirements-server.txt -q
log "Dependências Python instaladas"

# ── 6. Build frontend ───────────────────────────────────────────────────────
log "Construindo frontend..."
cd "$REPO_DIR/frontend"
npm ci --production=false 2>&1 | tail -3
npm run build 2>&1 | tail -3
cd "$REPO_DIR"
log "Frontend construído"

# ── 7. Diretórios de dados ──────────────────────────────────────────────────
DATA_DIR="/home/$APP_USER/.local/share/FREAnalyzer"
mkdir -p "$DATA_DIR"/{data,logs,cache,vector_stores}
chown -R "$APP_USER:$APP_USER" "$DATA_DIR"
log "Diretórios de dados criados em $DATA_DIR"

# ── 8. Verificar .env ───────────────────────────────────────────────────────
if [ ! -f "$REPO_DIR/.env" ]; then
    warn "Arquivo .env não encontrado!"
    warn "Crie $REPO_DIR/.env com pelo menos:"
    warn "  FRE_OPENAI_API_KEY=<sua-key>"
    warn "  FRE_OPENAI_API_KEY=<sua-key>"
    warn "  FRE_OPENAI_MODEL=gpt-4o-mini"
fi

# ── 9. Nginx ────────────────────────────────────────────────────────────────
log "Configurando Nginx..."
cp "$REPO_DIR/deploy/nginx-fre-analyzer.conf" /etc/nginx/sites-available/fre-analyzer

# Substituir DOMAIN se informado
if [[ -n "$DOMAIN" ]]; then
    sed -i "s/server_name _;/server_name $DOMAIN;/g" /etc/nginx/sites-available/fre-analyzer
    sed -i "s|DOMAIN|$DOMAIN|g" /etc/nginx/sites-available/fre-analyzer
fi

ln -sf /etc/nginx/sites-available/fre-analyzer /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default

# Testar config antes de recarregar
nginx -t && systemctl reload nginx
log "Nginx configurado"

# ── 10. SSL com Certbot ─────────────────────────────────────────────────────
if [[ -n "$DOMAIN" ]]; then
    log "Configurando SSL com Certbot..."
    mkdir -p /var/www/certbot
    certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos --email "admin@$DOMAIN" || {
        warn "Certbot falhou. Execute manualmente: certbot --nginx -d $DOMAIN"
    }
else
    warn "SSL não configurado (domínio não informado)"
    warn "Quando tiver o domínio, execute: certbot --nginx -d SEU_DOMINIO"
    # Usar config HTTP-only temporariamente
    cat > /etc/nginx/sites-available/fre-analyzer <<'NGINX'
server {
    listen 80;
    server_name _;
    client_max_body_size 50M;

    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;

    gzip on;
    gzip_vary on;
    gzip_types text/plain text/css application/json application/javascript;

    location /assets/ {
        proxy_pass http://127.0.0.1:8000;
        expires 1y;
        add_header Cache-Control "public, immutable";
    }

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
NGINX
    nginx -t && systemctl reload nginx
fi

# ── 11. Systemd service ─────────────────────────────────────────────────────
log "Instalando serviço systemd..."
cp "$REPO_DIR/deploy/fre-analyzer.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable fre-analyzer
systemctl restart fre-analyzer
log "Serviço fre-analyzer instalado e iniciado"

# ── 12. UFW Firewall ────────────────────────────────────────────────────────
log "Configurando firewall..."
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable
log "Firewall configurado (22, 80, 443)"

# ── 13. Fail2ban ─────────────────────────────────────────────────────────────
log "Configurando fail2ban..."
cat > /etc/fail2ban/jail.local <<'F2B'
[DEFAULT]
bantime = 3600
findtime = 600
maxretry = 5

[sshd]
enabled = true

[nginx-http-auth]
enabled = true

[nginx-limit-req]
enabled = true
logpath = /var/log/nginx/error.log
F2B
systemctl enable fail2ban
systemctl restart fail2ban
log "Fail2ban configurado"

# ── 14. Logrotate ────────────────────────────────────────────────────────────
log "Configurando logrotate..."
cp "$REPO_DIR/deploy/logrotate-fre-analyzer.conf" /etc/logrotate.d/fre-analyzer
log "Logrotate configurado"

# ── 15. Health monitor cron ──────────────────────────────────────────────────
log "Configurando health monitor..."
chmod +x "$REPO_DIR/deploy/health-monitor.sh"
(crontab -l 2>/dev/null || true; echo "*/5 * * * * $REPO_DIR/deploy/health-monitor.sh") | sort -u | crontab -
log "Health monitor no cron (a cada 5 minutos)"

# ── 16. Verificação final ───────────────────────────────────────────────────
log "Aguardando serviço iniciar..."
sleep 3

if curl -sf http://127.0.0.1:8000/api/settings/health > /dev/null 2>&1; then
    log "Health check: OK"
else
    warn "Health check falhou — verifique: journalctl -u fre-analyzer -n 50"
fi

echo ""
log "========================================="
log "  Setup concluído!"
log "========================================="
echo ""
echo "  Uso de RAM:"
free -h | head -2
echo ""
echo "  Serviços:"
systemctl is-active fre-analyzer nginx fail2ban | paste - - - <(echo -e "fre-analyzer\nnginx\nfail2ban")
echo ""
[[ -z "$DOMAIN" ]] && warn "Lembre de configurar SSL quando o domínio estiver pronto"
echo ""
log "Logs: journalctl -u fre-analyzer -f"
