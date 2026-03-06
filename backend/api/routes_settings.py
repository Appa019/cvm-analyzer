"""
CVM Analyzer - Settings API Routes
===================================

FastAPI routes for app settings and health check.
API key is configured exclusively via .env file (FRE_OPENAI_API_KEY).
"""

import asyncio
import re
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, func, text

from config import get_settings
from security import get_current_user
import config as config_module
from services import get_checklist_parser, get_cvm_service
from utils import get_cache_manager
from database import (
    ItemEvaluation as FREItemEvaluation,
    Evaluation as FREEvaluation,
    Document as FREDocument,
    get_async_engine, get_async_session_factory,
)


router = APIRouter(prefix="/api/settings", tags=["Settings"])

ENV_PATH = Path(__file__).resolve().parent.parent.parent / ".env"


# =============================================================================
# Response Models
# =============================================================================

class AppSettingsResponse(BaseModel):
    """Response with app settings."""
    openai_model: str
    embedding_model: str
    max_cache_size_gb: float
    default_cnpj: str
    version: str


class EnvSettingsResponse(BaseModel):
    openai_api_key_masked: str   # "sk-...XXXX" ou "" se não configurada
    openai_model: str


class EnvSettingsUpdate(BaseModel):
    openai_api_key: Optional[str] = None
    openai_model: Optional[str] = None


# =============================================================================
# Helper Functions
# =============================================================================

def _read_env_file() -> dict:
    """Lê o .env e retorna dict {KEY: VALUE}."""
    result = {}
    if not ENV_PATH.exists():
        return result
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            result[k.strip()] = v.strip()
    return result


def _write_env_var(key: str, value: str) -> None:
    """Atualiza ou insere KEY=VALUE no .env sem apagar outras linhas."""
    if "\n" in value or "\r" in value:
        raise ValueError(f"Valor inválido para {key}: não pode conter quebras de linha.")
    content = ENV_PATH.read_text(encoding="utf-8") if ENV_PATH.exists() else ""
    pattern = rf"^({re.escape(key)}\s*=).*$"
    new_line = f"{key}={value}"
    if re.search(pattern, content, flags=re.MULTILINE):
        content = re.sub(pattern, new_line, content, flags=re.MULTILINE)
    else:
        content = content.rstrip("\n") + f"\n{new_line}\n"
    ENV_PATH.write_text(content, encoding="utf-8")


# =============================================================================
# Routes
# =============================================================================

@router.get("/app", response_model=AppSettingsResponse)
async def get_app_settings():
    """Get current app settings (read-only)."""
    settings = get_settings()
    return AppSettingsResponse(
        openai_model=settings.openai_model,
        embedding_model=settings.openai_embedding_model,
        max_cache_size_gb=settings.cache_max_size_gb,
        default_cnpj=settings.default_cnpj,
        version=settings.app_version
    )


@router.get("/health")
async def health_check():
    """Health check endpoint."""
    settings = get_settings()
    return {
        "status": "ok",
        "version": settings.app_version,
        "api_key_configured": bool(settings.openai_api_key)
    }


@router.get("/env", response_model=EnvSettingsResponse)
async def get_env_settings(current_user: dict = Depends(get_current_user)):
    """Retorna configurações editáveis (chave mascarada)."""
    env = await asyncio.to_thread(_read_env_file)
    raw_key = env.get("FRE_OPENAI_API_KEY", "")
    masked = f"sk-...{raw_key[-4:]}" if len(raw_key) > 4 else ("configurada" if raw_key else "")
    return EnvSettingsResponse(
        openai_api_key_masked=masked,
        openai_model=env.get("FRE_OPENAI_MODEL", get_settings().openai_model),
    )


@router.post("/env")
async def update_env_settings(body: EnvSettingsUpdate, current_user: dict = Depends(get_current_user)):
    """Salva chave/modelo no .env e invalida o singleton de configurações."""
    try:
        if body.openai_api_key is not None:
            await asyncio.to_thread(_write_env_var, "FRE_OPENAI_API_KEY", body.openai_api_key)
        if body.openai_model is not None:
            await asyncio.to_thread(_write_env_var, "FRE_OPENAI_MODEL", body.openai_model)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    config_module._settings = None
    return {"ok": True, "message": "Configurações salvas com sucesso."}


@router.post("/refresh-checklist")
async def refresh_checklist(current_user: dict = Depends(get_current_user)):
    """Força re-parse do checklist da Resolução CVM 80 (Anexo C)."""
    try:
        parser = get_checklist_parser()
        checklist = await parser.parse_anexo_c(force_refresh=True)
        total = len(checklist.items)
        return {
            "ok": True,
            "message": f"Checklist atualizado: {total} itens carregados.",
            "total_items": total,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Erro ao atualizar checklist: {exc}")


# Preços por 1M tokens (input, output) — fonte: developers.openai.com/api/docs/models (março 2026)
_PRICING: dict[str, tuple[float, float]] = {
    "gpt-5-mini":        (0.250,  2.000),
    "gpt-5.4:xhigh":     (2.500, 60.000),  # reasoning xhigh: output ~4x por reasoning tokens
    "gpt-5.4:high":      (2.500, 30.000),  # reasoning high: output ~2x por reasoning tokens
    "gpt-5.4:medium":    (2.500, 22.500),  # reasoning medium: output ~1.5x
    "gpt-5.4:low":       (2.500, 15.000),  # reasoning low: output base
    "gpt-5.4":           (2.500, 15.000),
    "gpt-5.1":           (1.250, 10.000),
    "gpt-5":             (1.250, 10.000),
    "gpt-4.1-nano":      (0.100,  0.400),
    "gpt-4.1-mini":      (0.400,  1.600),
    "gpt-4.1":           (2.000,  8.000),
    "gpt-4o-mini":       (0.150,  0.600),
    "gpt-4o":            (2.500, 10.000),
    "o4-mini":           (1.100,  4.400),
    "o3-mini":           (1.100,  4.400),
    "o3":                (2.000,  8.000),
    "o1":               (15.000, 60.000),
}
_DEFAULT_PRICING = (0.250, 2.000)  # gpt-5-mini como fallback


def _cost_usd(model: str, input_tok: int, output_tok: int, total_tok: int) -> float:
    """Calcula custo exato se tiver split, ou estimativa com 75/25 se só tiver total."""
    # Normaliza nome do modelo (remove datas e sufixos)
    model_key = (model or "").lower()
    for key in _PRICING:
        if key in model_key:
            price_in, price_out = _PRICING[key]
            break
    else:
        price_in, price_out = _DEFAULT_PRICING

    if input_tok > 0 or output_tok > 0:
        return (input_tok * price_in + output_tok * price_out) / 1_000_000
    # Fallback para registros antigos sem split: assume 75% input / 25% output
    return total_tok * (0.75 * price_in + 0.25 * price_out) / 1_000_000


@router.get("/costs")
async def get_costs(current_user: dict = Depends(get_current_user)):
    """Retorna uso de tokens e custo estimado por modelo, empresa e mês."""
    settings = get_settings()
    engine = get_async_engine(str(settings.db_path))
    factory = get_async_session_factory(engine)

    async with factory() as session:
        # ── Avaliações: totais por modelo ─────────────────────────────────────
        model_rows = await session.execute(text("""
            SELECT
                ie.model_used,
                SUM(ie.input_tokens)  AS input_tok,
                SUM(ie.output_tokens) AS output_tok,
                SUM(ie.tokens_used)   AS total_tok,
                COUNT(ie.id)          AS item_count
            FROM item_evaluations ie
            GROUP BY ie.model_used
        """))
        model_data = model_rows.fetchall()

        # ── RAG: totais por modelo ────────────────────────────────────────────
        rag_model_rows = await session.execute(text("""
            SELECT
                cm.model_used,
                SUM(cm.input_tokens)  AS input_tok,
                SUM(cm.output_tokens) AS output_tok,
                SUM(cm.tokens_used)   AS total_tok,
                COUNT(cm.id)          AS item_count
            FROM chat_messages cm
            WHERE cm.role = 'assistant' AND cm.model_used IS NOT NULL
            GROUP BY cm.model_used
        """))
        rag_model_data = rag_model_rows.fetchall()

        # ── Avaliações: por empresa ───────────────────────────────────────────
        company_rows = await session.execute(text("""
            SELECT
                d.cnpj_cia,
                ie.model_used,
                SUM(ie.input_tokens)  AS input_tok,
                SUM(ie.output_tokens) AS output_tok,
                SUM(ie.tokens_used)   AS total_tok,
                COUNT(DISTINCT e.id)  AS eval_count,
                COUNT(ie.id)          AS item_count
            FROM item_evaluations ie
            JOIN evaluations e ON ie.evaluation_id = e.id
            JOIN documents d   ON e.document_id   = d.id
            GROUP BY d.cnpj_cia, ie.model_used
        """))
        company_data = company_rows.fetchall()

        # ── RAG: por empresa ──────────────────────────────────────────────────
        rag_company_rows = await session.execute(text("""
            SELECT
                cm.cnpj_cia,
                cm.model_used,
                SUM(cm.input_tokens)  AS input_tok,
                SUM(cm.output_tokens) AS output_tok,
                SUM(cm.tokens_used)   AS total_tok,
                COUNT(cm.id)          AS item_count
            FROM chat_messages cm
            WHERE cm.role = 'assistant' AND cm.cnpj_cia IS NOT NULL
            GROUP BY cm.cnpj_cia, cm.model_used
        """))
        rag_company_data = rag_company_rows.fetchall()

        # ── Avaliações: por mês ───────────────────────────────────────────────
        month_rows = await session.execute(text("""
            SELECT
                strftime('%Y-%m', e.completed_at) AS month,
                ie.model_used,
                SUM(ie.input_tokens)  AS input_tok,
                SUM(ie.output_tokens) AS output_tok,
                SUM(ie.tokens_used)   AS total_tok
            FROM item_evaluations ie
            JOIN evaluations e ON ie.evaluation_id = e.id
            WHERE e.completed_at IS NOT NULL
            GROUP BY month, ie.model_used
            ORDER BY month DESC
        """))
        month_data = month_rows.fetchall()

        # ── RAG: por mês ──────────────────────────────────────────────────────
        rag_month_rows = await session.execute(text("""
            SELECT
                strftime('%Y-%m', cm.created_at) AS month,
                cm.model_used,
                SUM(cm.input_tokens)  AS input_tok,
                SUM(cm.output_tokens) AS output_tok,
                SUM(cm.tokens_used)   AS total_tok
            FROM chat_messages cm
            WHERE cm.role = 'assistant' AND cm.model_used IS NOT NULL
            GROUP BY month, cm.model_used
            ORDER BY month DESC
        """))
        rag_month_data = rag_month_rows.fetchall()

    # ── Agrega por modelo (avaliação + RAG combinados) ───────────────────────
    model_map: dict = {}
    for row in list(model_data) + list(rag_model_data):
        key = row.model_used or "desconhecido"
        if key not in model_map:
            model_map[key] = {"model": key, "input_tokens": 0, "output_tokens": 0,
                              "total_tokens": 0, "cost_usd": 0.0, "item_count": 0}
        m = model_map[key]
        m["input_tokens"]  += row.input_tok or 0
        m["output_tokens"] += row.output_tok or 0
        m["total_tokens"]  += row.total_tok or 0
        m["item_count"]    += row.item_count or 0
        m["cost_usd"]      += _cost_usd(key, row.input_tok or 0, row.output_tok or 0, row.total_tok or 0)
    for v in model_map.values():
        v["cost_usd"] = round(v["cost_usd"], 6)
    by_model = sorted(model_map.values(), key=lambda x: x["cost_usd"], reverse=True)

    # ── Agrega por empresa (avaliação + RAG combinados) ───────────────────────
    company_map: dict = {}
    for row in company_data:
        cnpj = row.cnpj_cia
        if cnpj not in company_map:
            company_map[cnpj] = {"cnpj": cnpj, "input_tokens": 0, "output_tokens": 0,
                                  "total_tokens": 0, "cost_usd": 0.0, "eval_count": 0, "item_count": 0}
        e = company_map[cnpj]
        e["input_tokens"]  += row.input_tok or 0
        e["output_tokens"] += row.output_tok or 0
        e["total_tokens"]  += row.total_tok or 0
        e["eval_count"]    += row.eval_count or 0
        e["item_count"]    += row.item_count or 0
        e["cost_usd"]      += _cost_usd(row.model_used, row.input_tok or 0, row.output_tok or 0, row.total_tok or 0)

    for row in rag_company_data:
        cnpj = row.cnpj_cia or "desconhecido"
        if cnpj not in company_map:
            company_map[cnpj] = {"cnpj": cnpj, "input_tokens": 0, "output_tokens": 0,
                                  "total_tokens": 0, "cost_usd": 0.0, "eval_count": 0, "item_count": 0}
        e = company_map[cnpj]
        e["input_tokens"]  += row.input_tok or 0
        e["output_tokens"] += row.output_tok or 0
        e["total_tokens"]  += row.total_tok or 0
        e["item_count"]    += row.item_count or 0
        e["cost_usd"]      += _cost_usd(row.model_used, row.input_tok or 0, row.output_tok or 0, row.total_tok or 0)

    by_company = sorted(company_map.values(), key=lambda x: x["cost_usd"], reverse=True)

    # ── Agrega por mês (avaliação + RAG combinados) ───────────────────────────
    month_map: dict = {}
    for row in list(month_data) + list(rag_month_data):
        m = row.month or "desconhecido"
        if m not in month_map:
            month_map[m] = {"month": m, "input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "cost_usd": 0.0}
        month_map[m]["input_tokens"]  += row.input_tok or 0
        month_map[m]["output_tokens"] += row.output_tok or 0
        month_map[m]["total_tokens"]  += row.total_tok or 0
        month_map[m]["cost_usd"]      += _cost_usd(row.model_used, row.input_tok or 0, row.output_tok or 0, row.total_tok or 0)

    by_month = sorted(month_map.values(), key=lambda x: x["month"], reverse=True)

    # ── Summary global ────────────────────────────────────────────────────────
    all_model_rows = list(model_data) + list(rag_model_data)
    total_input  = sum(r.input_tok or 0 for r in all_model_rows)
    total_output = sum(r.output_tok or 0 for r in all_model_rows)
    total_tok    = sum(r.total_tok or 0 for r in all_model_rows)
    total_cost   = sum(v["cost_usd"] for v in model_map.values())
    has_exact = total_input > 0 or total_output > 0

    return {
        "summary": {
            "total_tokens":    total_tok,
            "input_tokens":    total_input,
            "output_tokens":   total_output,
            "total_cost_usd":  round(total_cost, 6),
            "has_exact_split": has_exact,
        },
        "by_model":   by_model,
        "by_company": by_company,
        "by_month":   by_month,
        "pricing":    {k: {"input_per_1m": v[0], "output_per_1m": v[1]} for k, v in _PRICING.items()},
    }


@router.post("/refresh-cvm")
async def refresh_cvm(current_user: dict = Depends(get_current_user)):
    """Limpa o cache dos CSVs da CVM (memória + disco) para forçar novo download."""
    svc = get_cvm_service()
    cache = get_cache_manager()

    cleared_years = list(svc._csv_cache.keys())
    svc._csv_cache.clear()

    for year in cleared_years:
        cache.delete(f"cvm_csv/fre_cia_aberta_{year}.csv")

    return {
        "ok": True,
        "message": "Cache CVM limpo. Os dados serão baixados novamente na próxima busca." if cleared_years else "Cache CVM já estava vazio. Os dados serão baixados na próxima busca.",
        "cleared_years": cleared_years,
    }


