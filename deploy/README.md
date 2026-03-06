# Deploy — Oracle Cloud Free Tier (ARM/Ubuntu)

## Pré-requisitos
- Instância Oracle Cloud ARM (Ampere A1, 1 OCPU, 6 GB RAM)
- Ubuntu 22.04+
- Acesso SSH configurado

## Passo a passo

### 1. Instalar dependências do sistema
```bash
sudo apt update && sudo apt install -y python3.11 python3.11-venv python3-pip nginx nodejs npm
```

### 2. Clonar e configurar
```bash
cd /home/ubuntu
git clone https://github.com/Appa019/cvm-analyzer.git fre-analyzer
cd fre-analyzer

python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements-server.txt
```

### 3. Configurar variáveis de ambiente
```bash
cp .env.example .env
nano .env
# Preencher:
# - FRE_OPENAI_API_KEY
# - FRE_OPENAI_MODEL=gpt-4o-mini
```

### 4. Build do frontend
```bash
cd frontend
npm ci
npm run build
cd ..
```

### 5. Instalar serviço systemd
```bash
sudo cp deploy/fre-analyzer.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable fre-analyzer
sudo systemctl start fre-analyzer
```

### 6. Configurar nginx
```bash
sudo cp deploy/nginx-fre-analyzer.conf /etc/nginx/sites-available/fre-analyzer
sudo ln -sf /etc/nginx/sites-available/fre-analyzer /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl restart nginx
```

### 7. Abrir firewall (Oracle Cloud)

No Console Oracle Cloud:
- VCN > Security Lists > Add Ingress Rule: TCP porta 80 de 0.0.0.0/0

Na instância:
```bash
sudo iptables -I INPUT -p tcp --dport 80 -j ACCEPT
sudo netfilter-persistent save
```

### 8. Verificar
```bash
# Health check local
curl http://localhost:8000/api/settings/health

# Acesso externo
curl http://<SEU_IP_PUBLICO>/
```

## Comandos úteis

```bash
# Ver logs
sudo journalctl -u fre-analyzer -f

# Reiniciar
sudo systemctl restart fre-analyzer

# Status
sudo systemctl status fre-analyzer

# Rebuild frontend após atualização
cd /home/ubuntu/fre-analyzer/frontend && npm run build
sudo systemctl restart fre-analyzer
```

## Atualizar código
```bash
cd /home/ubuntu/fre-analyzer
git pull origin main
source .venv/bin/activate
pip install -r requirements-server.txt
cd frontend && npm ci && npm run build && cd ..
sudo systemctl restart fre-analyzer
```
