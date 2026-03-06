#!/usr/bin/env bash
# ==============================================================================
# FRE Analyzer — Health Monitor (cron: */5 * * * *)
# Verifica RAM, swap, e se o serviço está respondendo.
# Reinicia automaticamente se não responder após 3 tentativas.
# ==============================================================================
set -uo pipefail

LOG="/var/log/fre-analyzer-health.log"
SERVICE="fre-analyzer"
HEALTH_URL="http://127.0.0.1:8000/api/settings/health"
MAX_RETRIES=3
RETRY_DELAY=5

timestamp() { date '+%Y-%m-%d %H:%M:%S'; }

log()  { echo "[$(timestamp)] [INFO] $*" >> "$LOG"; }
warn() { echo "[$(timestamp)] [WARN] $*" >> "$LOG"; }

# ── Verificar RAM ────────────────────────────────────────────────────────────
RAM_USED_PCT=$(free | awk '/Mem:/ {printf "%.0f", $3/$2*100}')
if [ "$RAM_USED_PCT" -gt 85 ]; then
    warn "RAM usage alta: ${RAM_USED_PCT}%"
fi

# ── Verificar Swap ───────────────────────────────────────────────────────────
SWAP_TOTAL=$(free | awk '/Swap:/ {print $2}')
if [ "$SWAP_TOTAL" -gt 0 ]; then
    SWAP_USED_PCT=$(free | awk '/Swap:/ {printf "%.0f", $3/$2*100}')
    if [ "$SWAP_USED_PCT" -gt 50 ]; then
        warn "Swap usage alta: ${SWAP_USED_PCT}%"
    fi
fi

# ── Verificar serviço ────────────────────────────────────────────────────────
healthy=false
for i in $(seq 1 $MAX_RETRIES); do
    if curl -sf --max-time 10 "$HEALTH_URL" > /dev/null 2>&1; then
        healthy=true
        break
    fi
    sleep "$RETRY_DELAY"
done

if $healthy; then
    log "OK — RAM: ${RAM_USED_PCT}%"
else
    warn "Serviço não respondeu após $MAX_RETRIES tentativas. Reiniciando..."
    systemctl restart "$SERVICE"
    sleep 5
    if curl -sf --max-time 10 "$HEALTH_URL" > /dev/null 2>&1; then
        log "Serviço reiniciado com sucesso"
    else
        warn "Serviço não respondeu mesmo após restart"
    fi
fi
