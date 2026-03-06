"""
CVM Analyzer - Archive API Routes
====================================

Routes for the historical document archive:
- List FREs for a given CNPJ (via CVM service)
- Serve PDF files via streaming (for the in-browser PDF viewer)
- Trigger manual document sync
- Daily sync logs
"""

import asyncio
import json
import time
import httpx
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, Query, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from sqlalchemy import select, desc

from services import get_cvm_service
from database import DocumentSync, get_async_engine, get_async_session_factory
from security import get_current_user
from config import get_settings


def _cnpj_slug(cnpj: str) -> str:
    return cnpj.replace("/", "_").replace(".", "_").replace("-", "_").strip("_")


def _enet_local_dir(cnpj: str) -> Path:
    settings = get_settings()
    d = settings.base_dir / "enet_local" / _cnpj_slug(cnpj)
    d.mkdir(parents=True, exist_ok=True)
    return d


router = APIRouter(prefix="/api/archive", tags=["Archive"])


@router.get("/documents")
async def list_documents(
    cnpj: Optional[str] = Query(default=None, description="CNPJ da empresa"),
    years: Optional[str] = Query(default=None, description="Anos separados por vírgula"),
    tipos: Optional[str] = Query(default=None, description="Tipos separados por vírgula: FRE,DFP,FCA,IPE"),
    current_user: dict = Depends(get_current_user),
):
    """
    Lista documentos de uma empresa via CVM, filtrado por CNPJ.
    Retorna lista vazia se nenhum CNPJ for informado.
    """
    if not cnpj:
        return {"documents": [], "total": 0}
    try:
        year_list = None
        if years:
            try:
                year_list = [int(y.strip()) for y in years.split(",") if y.strip()]
            except ValueError:
                raise HTTPException(status_code=400, detail="Formato de anos inválido.")

        tipo_list = [t.strip().upper() for t in tipos.split(",") if t.strip()] if tipos else ["FRE"]

        svc = get_cvm_service()
        all_docs = []

        if "FRE" in tipo_list:
            df = await svc.get_company_fres(cnpj, year_list)
            if not df.empty:
                all_docs.extend(df.to_dict(orient="records"))

        for tipo in ("DFP", "FCA", "IPE"):
            if tipo in tipo_list and hasattr(svc, "get_company_documents"):
                try:
                    df2 = await svc.get_company_documents(cnpj, tipo, year_list)
                    if not df2.empty:
                        all_docs.extend(df2.to_dict(orient="records"))
                except Exception:
                    pass

        return {"documents": all_docs, "total": len(all_docs)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/documents/{doc_key}/pdf")
async def stream_pdf(
    doc_key: str,
    cnpj: Optional[str] = Query(default=None, description="CNPJ da empresa"),
    link_doc: Optional[str] = Query(default=None, description="URL do PDF no CVM"),
    current_user: dict = Depends(get_current_user),
):
    """
    Stream a PDF file for in-browser viewing.

    doc_key format: "{DT_REFER}_{VERSAO}" e.g. "2024-12-31_1"
    link_doc é a URL do PDF conforme retornado pelo endpoint de FREs.
    """
    try:
        parts = doc_key.rsplit("_", 1)
        if len(parts) != 2:
            raise HTTPException(status_code=400, detail="Formato inválido. Use DT_REFER_VERSAO.")
        dt_refer, versao_str = parts
        versao = int(versao_str)
    except (ValueError, IndexError):
        raise HTTPException(status_code=400, detail="Formato inválido. Use DT_REFER_VERSAO.")

    if not link_doc:
        raise HTTPException(status_code=400, detail="Parâmetro link_doc é obrigatório.")

    svc = get_cvm_service()
    try:
        pdf_path = await svc.download_pdf(link_doc, dt_refer, versao, cnpj=cnpj or "")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Erro ao baixar PDF: {str(e)}")

    def iterfile():
        with open(pdf_path, "rb") as f:
            while chunk := f.read(65536):
                yield chunk

    filename = f"fre_{dt_refer}_v{versao}.pdf"
    return StreamingResponse(
        iterfile(),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="{filename}"',
            "Cache-Control": "public, max-age=86400",
        },
    )


@router.post("/sync")
async def trigger_sync(
    cnpj: Optional[str] = Query(default=None),
    current_user: dict = Depends(get_current_user),
):
    """
    Manually trigger a document sync for a given company CNPJ.
    Records sync metadata in the database.
    """
    settings = get_settings()
    db_engine = get_async_engine(str(settings.db_path))
    factory = get_async_session_factory(db_engine)

    errors = []
    new_docs = 0
    total_checked = 0

    try:
        if cnpj:
            svc = get_cvm_service()
            df = await svc.get_company_fres(cnpj)
            total_checked = len(df)
            from utils import get_cache_manager
            cache = get_cache_manager()
            for _, row in df.iterrows():
                dt = str(row.get("DT_REFER", "")).strip()
                versao = str(row.get("VERSAO", "1")).strip()
                cnpj_slug = cnpj.replace("/", "_").replace(".", "_").replace("-", "_").strip("_")
                cache_key = f"pdfs/{cnpj_slug}/{dt}_v{versao}.pdf"
                if not cache.get(cache_key):
                    new_docs += 1

    except Exception as e:
        errors.append(str(e))
        total_checked = 0

    async with factory() as session:
        sync_log = DocumentSync(
            synced_at=datetime.now(timezone.utc),
            new_docs_found=new_docs,
            total_docs_checked=total_checked,
            errors=errors,
        )
        session.add(sync_log)
        await session.commit()

    return {
        "status": "ok",
        "synced_at": datetime.now(timezone.utc).isoformat(),
        "new_docs_found": new_docs,
        "total_docs_checked": total_checked,
        "errors": errors,
    }


@router.get("/sync/logs")
async def get_sync_logs(
    limit: int = 20,
    current_user: dict = Depends(get_current_user),
):
    """Get recent sync logs."""
    settings = get_settings()
    db_engine = get_async_engine(str(settings.db_path))
    factory = get_async_session_factory(db_engine)

    async with factory() as session:
        result = await session.execute(
            select(DocumentSync)
            .order_by(desc(DocumentSync.synced_at))
            .limit(limit)
        )
        rows = result.scalars().all()

    return {
        "logs": [
            {
                "id": r.id,
                "synced_at": r.synced_at.isoformat(),
                "new_docs_found": r.new_docs_found,
                "total_docs_checked": r.total_docs_checked,
                "errors": r.errors or [],
            }
            for r in rows
        ]
    }


# =============================================================================
# ENET Local Files
# =============================================================================

@router.get("/local-files")
async def list_local_files(
    cnpj: str = Query(..., description="CNPJ da empresa"),
    tipos: Optional[str] = Query(default=None, description="Tipos separados por vírgula: FRE,DFP,FCA,IPE"),
    current_user: dict = Depends(get_current_user),
):
    """
    Lista arquivos salvos localmente pelo endpoint save-to-local.

    Lê ~/.local/share/FREAnalyzer/enet_local/{cnpj_slug}/index.json
    Retorna: { files: [...metadados] }
    Filtra por tipo_doc se o parâmetro tipos for informado.
    """
    d = _enet_local_dir(cnpj)
    index_path = d / "index.json"
    if not index_path.exists():
        return {"files": []}
    try:
        files = json.loads(index_path.read_text(encoding="utf-8"))
    except Exception:
        return {"files": []}

    if tipos:
        tipo_list = {t.strip().upper() for t in tipos.split(",") if t.strip()}
        files = [f for f in files if (f.get("tipo_doc") or "FRE").upper() in tipo_list]

    return {"files": files}


@router.post("/local-files/upload")
async def upload_local_file(
    cnpj: str = Form(..., description="CNPJ da empresa"),
    tipo_doc: str = Form(..., description="FRE, DFP, FCA ou IPE"),
    dt_refer: str = Form(..., description="Data de referência (AAAA-MM-DD ou DD/MM/AAAA)"),
    versao: str = Form(default="1"),
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
):
    """
    Upload manual de PDF para armazenamento local de uma empresa.

    Salva em enet_local/{cnpj_slug}/ e registra no index.json com source='manual'.
    """
    tipo_doc = tipo_doc.upper()
    if tipo_doc not in ("FRE", "DFP", "FCA", "IPE"):
        raise HTTPException(status_code=400, detail="tipo_doc deve ser FRE, DFP, FCA ou IPE.")
    if not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Apenas arquivos PDF são aceitos.")

    content = await file.read()
    if len(content) < 4 or content[:4] != b"%PDF":
        raise HTTPException(status_code=400, detail="O arquivo enviado não é um PDF válido.")

    d = _enet_local_dir(cnpj)
    dt_safe = dt_refer.replace("/", "-").replace(" ", "_").replace(":", "-")
    ts = int(time.time())
    filename = f"MANUAL_{tipo_doc}_{dt_safe}_v{versao}_{ts}.pdf"

    target = (d / filename).resolve()
    if not target.is_relative_to(d.resolve()):
        raise HTTPException(status_code=400, detail="Nome de arquivo inválido.")

    await asyncio.to_thread(target.write_bytes, content)

    entry = {
        "filename": filename,
        "id_doc": f"manual_{ts}",
        "tipo_doc": tipo_doc,
        "dt_refer": dt_refer,
        "versao": versao,
        "categoria": "",
        "assunto": "",
        "empresa": "",
        "saved_at": datetime.now(timezone.utc).isoformat(),
        "size_bytes": len(content),
        "source": "manual",
    }

    def _update_index():
        index = []
        index_path = d / "index.json"
        if index_path.exists():
            try:
                index = json.loads(index_path.read_text(encoding="utf-8"))
            except Exception:
                index = []
        index.append(entry)
        index_path.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")

    await asyncio.to_thread(_update_index)

    return {"ok": True, "filename": filename, "entry": entry}


@router.get("/local-files/{filename}/pdf")
async def stream_local_file(
    filename: str,
    cnpj: str = Query(..., description="CNPJ da empresa"),
    current_user: dict = Depends(get_current_user),
):
    """
    Stream de PDF de arquivo local salvo pelo save-to-local.

    Valida que o arquivo está dentro do diretório correto (prevenção de path traversal).
    """
    d = _enet_local_dir(cnpj)
    # Prevenção de path traversal: resolve o caminho e garante que está dentro do dir
    target = (d / filename).resolve()
    if not target.is_relative_to(d.resolve()):
        raise HTTPException(status_code=400, detail="Nome de arquivo inválido.")
    if not target.exists():
        raise HTTPException(status_code=404, detail="Arquivo não encontrado.")
    if target.suffix.lower() != ".pdf":
        raise HTTPException(status_code=400, detail="Apenas arquivos PDF são suportados.")

    def iterfile():
        with open(target, "rb") as f:
            while chunk := f.read(65536):
                yield chunk

    return StreamingResponse(
        iterfile(),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="{filename}"',
            "Cache-Control": "public, max-age=86400",
        },
    )
