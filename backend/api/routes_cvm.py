"""
CVM Analyzer - CVM API Routes
==============================

Endpoints para busca de empresas e listagem de FREs via dados públicos da CVM,
além de busca e download de documentos via portal ENET (rad.cvm.gov.br).
"""

import asyncio
import json
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select, delete

from services import get_cvm_service, get_enet_scraper
from security import get_current_user
from config import get_settings
from database import (
    Document as FREDocument,
    Evaluation as FREEvaluation,
    ItemEvaluation as FREItemEvaluation,
    DocumentItem as FREItem,
    VectorStoreRef, ChatMessage, DiffSession, IssueResolution,
    get_async_engine, get_async_session_factory,
)


def _cnpj_slug(cnpj: str) -> str:
    return cnpj.replace("/", "_").replace(".", "_").replace("-", "_").strip("_")


def _enet_local_dir(cnpj: str) -> Path:
    settings = get_settings()
    d = settings.base_dir / "enet_local" / _cnpj_slug(cnpj)
    d.mkdir(parents=True, exist_ok=True)
    return d


def _safe_name(s: str) -> str:
    """Sanitiza string para uso em nomes de arquivo."""
    return s.replace("/", "-").replace("\\", "-").replace(" ", "_")


def _load_index(d: Path) -> list:
    index_path = d / "index.json"
    if not index_path.exists():
        return []
    try:
        return json.loads(index_path.read_text(encoding="utf-8"))
    except Exception:
        return []


def _save_index(d: Path, entries: list) -> None:
    (d / "index.json").write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")


router = APIRouter(prefix="/api/cvm", tags=["CVM"])


@router.get("/status")
async def get_cvm_status(current_user: dict = Depends(get_current_user)):
    """Retorna status de inicialização e lista de empresas locais."""
    settings = get_settings()
    csv_dir = settings.cache_dir / "cvm_csv"
    initialized = csv_dir.exists() and any(csv_dir.glob("*.csv"))

    local_companies = []
    enet_local = settings.base_dir / "enet_local"
    if enet_local.exists():
        for company_dir in sorted(enet_local.iterdir()):
            if company_dir.is_dir():
                company_json = company_dir / "company.json"
                if company_json.exists():
                    try:
                        data = json.loads(company_json.read_text(encoding="utf-8"))
                        local_companies.append(data)
                    except Exception:
                        pass

    return {"initialized": initialized, "local_companies": local_companies}


@router.post("/cache/warm")
async def warm_csv_cache(
    force: bool = Query(default=False),
    current_user: dict = Depends(get_current_user),
):
    """SSE stream: baixa CSVs de todos os tipos × últimos 5 anos."""
    TIPOS = ["FRE", "DFP", "FCA", "IPE"]
    current_year = datetime.now(timezone.utc).year
    years = list(range(current_year - 4, current_year + 1))
    total = len(TIPOS) * len(years)

    async def generate():
        svc = get_cvm_service()
        done = 0
        for tipo in TIPOS:
            for year in years:
                current_label = f"{tipo} {year}"
                try:
                    await svc._load_doc_csv(tipo, year, force=force)
                    ok = True
                except Exception:
                    ok = False
                done += 1
                event = json.dumps({"done": done, "total": total, "current": current_label, "ok": ok})
                yield f"data: {event}\n\n"
        final = json.dumps({"done": total, "total": total, "complete": True})
        yield f"data: {final}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


class AddCompanyRequest(BaseModel):
    cnpj: str
    name: str


@router.post("/companies/add")
async def add_company(
    body: AddCompanyRequest,
    current_user: dict = Depends(get_current_user),
):
    """Adiciona empresa ao índice local com contagem de documentos dos últimos 5 anos."""
    settings = get_settings()
    current_year = datetime.now(timezone.utc).year
    last_5 = list(range(current_year - 4, current_year + 1))

    svc = get_cvm_service()
    docs = await svc.get_company_documents(
        body.cnpj, tipos=["FRE", "DFP", "FCA", "IPE"], years=last_5
    )

    doc_counts = {"FRE": 0, "DFP": 0, "FCA": 0, "IPE": 0}
    for doc in docs:
        t = doc.get("tipo_doc", "")
        if t in doc_counts:
            doc_counts[t] += 1

    slug = _cnpj_slug(body.cnpj)
    company_dir = settings.base_dir / "enet_local" / slug
    company_dir.mkdir(parents=True, exist_ok=True)

    company_data = {
        "cnpj": body.cnpj,
        "name": body.name,
        "added_at": datetime.now(timezone.utc).isoformat(),
        "doc_counts": doc_counts,
    }
    (company_dir / "company.json").write_text(
        json.dumps(company_data, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    return {"ok": True, "cnpj": body.cnpj, "name": body.name, "doc_counts": doc_counts}


@router.post("/companies/sync")
async def sync_company_documents(
    body: AddCompanyRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    SSE stream: baixa todos os documentos de uma empresa.
    Filtra para a última versão por (tipo_doc, dt_refer) e pula os já baixados.
    Usa semáforos + queue para emitir progresso em tempo real conforme cada doc termina.
    """
    import logging as _logging
    current_year = datetime.now(timezone.utc).year
    last_5 = list(range(current_year - 4, current_year + 1))

    async def generate():
        logger = _logging.getLogger(__name__)
        svc = get_cvm_service()
        scraper = get_enet_scraper()

        # Busca todos os documentos via CSVs da CVM
        all_docs = await svc.get_company_documents(
            body.cnpj, tipos=["FRE", "DFP", "FCA", "IPE"], years=last_5
        )

        # Filtra: última versão por (tipo_doc, dt_refer)
        def _versao_int(v):
            try:
                return int(v)
            except Exception:
                return 0

        latest: dict = {}
        for doc in all_docs:
            key = (doc["tipo_doc"], doc["dt_refer"])
            if key not in latest or _versao_int(doc["versao"]) > _versao_int(latest[key]["versao"]):
                latest[key] = doc
        deduped = list(latest.values())

        # Pula os já baixados (presentes no index.json)
        company_dir = _enet_local_dir(body.cnpj)
        index = _load_index(company_dir)
        existing_ids = {e["id_doc"] for e in index}
        to_download = [doc for doc in deduped if doc["id_doc"] not in existing_ids]
        skipped_existing = len(deduped) - len(to_download)

        total = len(to_download)
        yield f"data: {json.dumps({'starting': True, 'total': total, 'skipped_existing': skipped_existing})}\n\n"

        if total == 0:
            yield f"data: {json.dumps({'complete': True, 'done': 0, 'total': 0, 'saved': 0, 'skipped': skipped_existing, 'errors': 0})}\n\n"
            return

        index_map = {e["id_doc"]: e for e in index}
        saved_at = datetime.now(timezone.utc).isoformat()
        done = 0
        saved = 0
        errors = 0

        # Semáforos por tipo: Playwright (pesado) → 2 paralelos; httpx (leve) → 5 paralelos
        sem_est = asyncio.Semaphore(2)
        sem_ipe = asyncio.Semaphore(5)
        result_queue: asyncio.Queue = asyncio.Queue()

        async def _download_one(doc):
            tipo = doc["tipo_doc"]
            sem = sem_ipe if tipo == "IPE" else sem_est
            dt_safe = _safe_name(doc["dt_refer"]) if doc["dt_refer"] else doc["id_doc"]
            filename = f"{tipo}_{doc['id_doc']}_{dt_safe}.pdf"
            filepath = company_dir / filename
            async with sem:
                try:
                    if tipo == "IPE":
                        pdf_bytes = await scraper.download_ipe_pdf(
                            doc["id_doc"], doc["num_versao"], doc["num_protocolo"]
                        )
                    else:
                        with tempfile.TemporaryDirectory() as tmpdir:
                            tmp_path = Path(tmpdir) / filename
                            await scraper.download_fre_pdf(doc["id_doc"], tmp_path)
                            pdf_bytes = tmp_path.read_bytes()
                    await asyncio.to_thread(filepath.write_bytes, pdf_bytes)
                    entry = {
                        "filename": filename,
                        "id_doc": doc["id_doc"],
                        "tipo_doc": tipo,
                        "dt_refer": doc["dt_refer"],
                        "versao": str(doc.get("versao", "1")),
                        "categoria": doc.get("categoria", ""),
                        "assunto": doc.get("assunto", ""),
                        "empresa": doc.get("nome_empresa", body.name),
                        "saved_at": saved_at,
                        "size_bytes": len(pdf_bytes),
                    }
                    await result_queue.put((doc, True, entry))
                except Exception as exc:
                    logger.error(f"Erro ao baixar {tipo} {doc.get('dt_refer','?')} id={doc.get('id_doc','?')}: {exc}")
                    await result_queue.put((doc, False, None))

        # Inicia todas as tasks (concorrência controlada pelos semáforos)
        tasks = [asyncio.ensure_future(_download_one(doc)) for doc in to_download]

        # Emite evento assim que cada documento termina (sem aguardar batch inteiro)
        for _ in range(total):
            doc, ok, entry = await result_queue.get()
            if ok and entry:
                index_map[doc["id_doc"]] = entry
                saved += 1
            else:
                errors += 1
            done += 1
            current_label = f"{doc['tipo_doc']} {doc['dt_refer']}"
            yield f"data: {json.dumps({'done': done, 'total': total, 'current': current_label, 'ok': ok, 'saved': saved, 'errors': errors})}\n\n"

        # Aguarda conclusão de todas as tasks e salva índice
        await asyncio.gather(*tasks, return_exceptions=True)
        await asyncio.to_thread(_save_index, company_dir, list(index_map.values()))

        yield f"data: {json.dumps({'complete': True, 'done': done, 'total': total, 'saved': saved, 'skipped': skipped_existing, 'errors': errors})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


@router.get("/companies/search")
async def search_companies(
    q: str = Query(default="", description="Nome ou CNPJ da empresa"),
    year: int = Query(default=2024, description="Ano do CSV CVM para busca"),
    current_user: dict = Depends(get_current_user),
):
    """
    Busca empresas abertas pelo nome (DENOM_CIA) ou CNPJ nos dados da CVM.

    Retorna: { results: [{ cnpj, name, cod_cvm }] }
    """
    try:
        svc = get_cvm_service()
        results = await svc.search_companies(q, year)
        return {"results": results}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/documents")
async def get_company_documents(
    cnpj: str = Query(..., description="CNPJ da empresa (ex: 33.000.167/0001-01)"),
    tipos: str = Query(
        default="FRE,DFP,FCA,IPE",
        description="Tipos de documento separados por vírgula",
    ),
    years: Optional[str] = Query(
        default=None,
        description="Anos separados por vírgula (ex: 2023,2024,2025)",
    ),
    current_user: dict = Depends(get_current_user),
):
    """
    Lista documentos de uma empresa a partir dos CSVs abertos da CVM.

    CNPJ passado como query param para evitar problemas com '/' no path.
    Suporta FRE, DFP, FCA e IPE.
    """
    try:
        tipos_list = [t.strip().upper() for t in tipos.split(",") if t.strip()]
        year_list: Optional[List[int]] = None
        if years:
            try:
                year_list = [int(y.strip()) for y in years.split(",") if y.strip()]
            except ValueError:
                raise HTTPException(status_code=400, detail="Formato de anos inválido. Use: 2023,2024,2025")

        svc = get_cvm_service()
        docs = await svc.get_company_documents(cnpj, tipos_list, year_list)
        return {"documents": docs, "total": len(docs)}

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/companies/{cnpj}/fres")
async def get_company_fres(
    cnpj: str,
    years: Optional[str] = Query(
        default=None,
        description="Anos separados por vírgula (ex: 2022,2023,2024,2025)",
    ),
    current_user: dict = Depends(get_current_user),
):
    """
    Lista os FREs de uma empresa a partir do CNPJ, para os anos indicados.

    Retorna: { documents: [{ DT_REFER, VERSAO, LINK_DOC, DENOM_CIA, TIPO_DOC }] }
    """
    try:
        year_list: Optional[List[int]] = None
        if years:
            try:
                year_list = [int(y.strip()) for y in years.split(",") if y.strip()]
            except ValueError:
                raise HTTPException(status_code=400, detail="Formato de anos inválido. Use: 2022,2023,2024")

        svc = get_cvm_service()
        df = await svc.get_company_fres(cnpj, year_list)

        if df.empty:
            return {"documents": [], "total": 0}

        cols = [c for c in ("DT_REFER", "VERSAO", "LINK_DOC", "DENOM_CIA", "TIPO_DOC") if c in df.columns]
        docs = df[cols].to_dict(orient="records")
        return {"documents": docs, "total": len(docs)}

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/companies/{cnpj}/documents")
async def get_company_documents(
    cnpj: str,
    tipos: Optional[str] = Query(
        default=None,
        description="Tipos separados por vírgula: FRE,DFP,FCA,IPE (padrão: todos)",
    ),
    years: Optional[str] = Query(
        default=None,
        description="Anos separados por vírgula (ex: 2022,2023,2024,2025)",
    ),
    current_user: dict = Depends(get_current_user),
):
    """
    Lista documentos de uma empresa (FRE, DFP, FCA, IPE) a partir do CNPJ.

    Retorna: { documents: [{ DT_REFER, VERSAO, LINK_DOC, DENOM_CIA, TIPO_DOC }] }
    """
    try:
        year_list: Optional[List[int]] = None
        if years:
            try:
                year_list = [int(y.strip()) for y in years.split(",") if y.strip()]
            except ValueError:
                raise HTTPException(status_code=400, detail="Formato de anos inválido. Use: 2022,2023,2024")

        tipo_list = [t.strip().upper() for t in tipos.split(",") if t.strip()] if tipos else ["FRE", "DFP", "FCA", "IPE"]

        svc = get_cvm_service()
        all_docs = []

        if "FRE" in tipo_list:
            df = await svc.get_company_fres(cnpj, year_list)
            if not df.empty:
                cols = [c for c in ("DT_REFER", "VERSAO", "LINK_DOC", "DENOM_CIA", "TIPO_DOC") if c in df.columns]
                all_docs.extend(df[cols].to_dict(orient="records"))

        for tipo in ("DFP", "FCA", "IPE"):
            if tipo in tipo_list and hasattr(svc, "get_company_documents"):
                try:
                    df2 = await svc.get_company_documents(cnpj, tipo, year_list)
                    if not df2.empty:
                        cols2 = [c for c in ("DT_REFER", "VERSAO", "LINK_DOC", "DENOM_CIA", "TIPO_DOC") if c in df2.columns]
                        all_docs.extend(df2[cols2].to_dict(orient="records"))
                except Exception:
                    pass

        return {"documents": all_docs, "total": len(all_docs)}

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


class FreDocItem(BaseModel):
    link_doc: str
    dt_refer: str
    versao: int
    cnpj: str = ""
    company_name: str = ""


class DownloadPdfsRequest(BaseModel):
    documents: List[FreDocItem]


@router.post("/download-pdfs")
async def download_pdfs(
    body: DownloadPdfsRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Baixa e cacheia os PDFs dos FREs selecionados.

    Retorna: { results: [{ dt_refer, versao, ok, size_bytes?, error? }] }
    """
    if not body.documents:
        raise HTTPException(status_code=400, detail="Selecione pelo menos um documento.")

    svc = get_cvm_service()
    results = []

    async def _download_one(doc: FreDocItem):
        try:
            path = await svc.download_pdf(
                link_doc=doc.link_doc,
                dt_refer=doc.dt_refer,
                versao=doc.versao,
                cnpj=doc.cnpj,
                company_name=doc.company_name,
                pin=True,
            )
            return {"dt_refer": doc.dt_refer, "versao": doc.versao, "ok": True, "size_bytes": path.stat().st_size}
        except Exception as exc:
            return {"dt_refer": doc.dt_refer, "versao": doc.versao, "ok": False, "error": str(exc)}

    results = await asyncio.gather(*[_download_one(d) for d in body.documents])
    ok_count = sum(1 for r in results if r["ok"])
    return {
        "ok": ok_count > 0,
        "message": f"{ok_count}/{len(results)} PDFs baixados com sucesso.",
        "results": list(results),
    }


# =============================================================================
# ENET Endpoints
# =============================================================================

_CATEGORIAS_DEFAULT = "EST_2,IPE_7_29_-1,IPE_7_43_-1,IPE_4_-1_-1"


@router.get("/companies/{cnpj}/enet-documents")
async def list_enet_documents(
    cnpj: str,
    categorias: str = Query(
        default=_CATEGORIAS_DEFAULT,
        description="Categorias ENET separadas por vírgula (ex: EST_2,IPE_7_29_-1)",
    ),
    current_user: dict = Depends(get_current_user),
):
    """
    Lista documentos disponíveis no portal ENET para a empresa identificada pelo CNPJ.

    Usa cvm_service para obter o cod_cvm a partir do CNPJ, depois consulta o ENET.

    Retorna: { documents: [{num_seq, num_versao, num_protocolo, tipo_doc,
                            categoria, cod_cvm, empresa, tipo,
                            data_ref, data_entrega, status, versao}] }
    """
    try:
        # Resolve cod_cvm a partir do CNPJ via busca no CSV da CVM
        cvm_svc = get_cvm_service()
        companies = await cvm_svc.search_companies(cnpj.strip())
        # Busca exata por CNPJ
        cnpj_norm = cnpj.strip().replace(".", "").replace("/", "").replace("-", "")
        cod_cvm = None
        for c in companies:
            c_norm = c["cnpj"].replace(".", "").replace("/", "").replace("-", "")
            if c_norm == cnpj_norm:
                cod_cvm = c["cod_cvm"]
                break
        if not cod_cvm:
            raise HTTPException(
                status_code=404,
                detail=f"Empresa com CNPJ {cnpj} não encontrada nos dados CVM.",
            )

        cat_list = [c.strip() for c in categorias.split(",") if c.strip()]
        if not cat_list:
            raise HTTPException(status_code=400, detail="Informe ao menos uma categoria.")

        scraper = get_enet_scraper()
        docs = await scraper.list_documents(cod_cvm, cat_list)
        return {"documents": docs, "total": len(docs), "cod_cvm": cod_cvm}

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


class DownloadFreRequest(BaseModel):
    num_seq: str
    cnpj: str = ""


@router.post("/enet/download-fre")
async def download_fre_pdf(
    body: DownloadFreRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Gera e retorna o PDF de um FRE via Playwright (portal ENET).

    Internamente navega para o viewer do FRE, clica em "Salvar em PDF" e "Gerar PDF",
    captura o download e devolve o arquivo como StreamingResponse.
    """
    try:
        scraper = get_enet_scraper()
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / f"fre_{body.num_seq}.pdf"
            await scraper.download_fre_pdf(body.num_seq, output_path)
            pdf_bytes = output_path.read_bytes()

        filename = f"FRE_{body.num_seq}.pdf"
        return StreamingResponse(
            iter([pdf_bytes]),
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/enet/download-ipe/{num_seq}")
async def download_ipe_pdf(
    num_seq: str,
    num_versao: str = Query(..., description="Versão do documento"),
    num_protocolo: str = Query(..., description="Número de protocolo do documento"),
    current_user: dict = Depends(get_current_user),
):
    """
    Retorna o PDF de um documento IPE diretamente via httpx (portal ENET).

    Parâmetros: num_seq (path), num_versao e num_protocolo (query).
    """
    try:
        scraper = get_enet_scraper()
        pdf_bytes = await scraper.download_ipe_pdf(num_seq, num_versao, num_protocolo)
        filename = f"IPE_{num_seq}.pdf"
        return StreamingResponse(
            iter([pdf_bytes]),
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# =============================================================================
# Save ENET documents to local storage
# =============================================================================

class EnetDocItem(BaseModel):
    id_doc: str           # ID_DOC para FRE/DFP/FCA; numSequencia para IPE
    tipo_doc: str         # "FRE" | "DFP" | "FCA" | "IPE"
    num_versao: str = ""  # extraído de Link_Download (IPE)
    num_protocolo: str = ""  # extraído de Link_Download (IPE)
    dt_refer: str = ""
    versao: str = "1"
    categoria: str = ""
    assunto: str = ""
    empresa: str = ""


class SaveToLocalRequest(BaseModel):
    cnpj: str
    company_name: str = ""
    documents: List[EnetDocItem]


@router.post("/enet/save-to-local")
async def save_enet_to_local(
    body: SaveToLocalRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Baixa documentos e os persiste localmente no servidor.

    Para cada documento:
      - IPE: httpx → download_ipe_pdf (id_doc = numSequencia)
      - FRE/DFP/FCA: Playwright → download_fre_pdf (id_doc = ID_DOC do CSV)

    Salva em: ~/.local/share/FREAnalyzer/enet_local/{cnpj_slug}/{tipo}_{id_doc}_{dt_refer}.pdf
    Atualiza: ~/.local/share/FREAnalyzer/enet_local/{cnpj_slug}/index.json
    """
    if not body.documents:
        raise HTTPException(status_code=400, detail="Selecione pelo menos um documento.")

    d = _enet_local_dir(body.cnpj)
    scraper = get_enet_scraper()
    index = _load_index(d)
    index_map = {e["id_doc"]: e for e in index}

    async def _save_one(doc: EnetDocItem):
        dt_safe = _safe_name(doc.dt_refer) if doc.dt_refer else doc.id_doc
        filename = f"{doc.tipo_doc}_{doc.id_doc}_{dt_safe}.pdf"
        filepath = d / filename

        try:
            if doc.tipo_doc == "IPE":
                pdf_bytes = await scraper.download_ipe_pdf(
                    doc.id_doc, doc.num_versao, doc.num_protocolo
                )
            else:
                # FRE, DFP, FCA — viewer ENET via Playwright
                with tempfile.TemporaryDirectory() as tmpdir:
                    tmp_path = Path(tmpdir) / filename
                    await scraper.download_fre_pdf(doc.id_doc, tmp_path)
                    pdf_bytes = tmp_path.read_bytes()

            filepath.write_bytes(pdf_bytes)
            return {"id_doc": doc.id_doc, "filename": filename, "ok": True, "size_bytes": len(pdf_bytes)}
        except Exception as exc:
            return {"id_doc": doc.id_doc, "filename": filename, "ok": False, "error": str(exc)}

    results = await asyncio.gather(*[_save_one(d_) for d_ in body.documents])

    saved_at = datetime.now(timezone.utc).isoformat()
    for res, doc in zip(results, body.documents):
        if res["ok"]:
            index_map[doc.id_doc] = {
                "filename": res["filename"],
                "id_doc": doc.id_doc,
                "tipo_doc": doc.tipo_doc,
                "dt_refer": doc.dt_refer,
                "versao": str(doc.versao or "1"),
                "categoria": doc.categoria,
                "assunto": doc.assunto,
                "empresa": doc.empresa or body.company_name,
                "saved_at": saved_at,
                "size_bytes": res["size_bytes"],
            }

    _save_index(d, list(index_map.values()))

    ok_count = sum(1 for r in results if r["ok"])
    return {
        "ok": ok_count > 0,
        "message": f"{ok_count}/{len(results)} arquivo(s) salvos com sucesso.",
        "results": list(results),
    }


# =============================================================================
# Delete company (streaming SSE)
# =============================================================================

class DeleteCompanyRequest(BaseModel):
    cnpj: str


@router.post("/companies/delete-stream")
async def delete_company_stream(
    body: DeleteCompanyRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    SSE stream: remove empresa e todos os seus dados com progresso por etapa.

    Eventos: { step, label, status: 'running'|'done'|'error', count?, detail? }
    Etapas: lookup → openai → db → local → complete
    """
    async def generate():
        cnpj = body.cnpj
        settings = get_settings()
        engine = get_async_engine(str(settings.db_path))
        factory = get_async_session_factory(engine)

        # ── Etapa 1: Lookup ────────────────────────────────────────────────
        yield f"data: {json.dumps({'step': 'lookup', 'label': 'Buscando registros...', 'status': 'running'})}\n\n"

        doc_ids: list = []
        eval_ids: list = []
        vs_list: list = []

        async with factory() as session:
            docs_result = await session.execute(
                select(FREDocument).where(FREDocument.cnpj_cia == cnpj)
            )
            docs = docs_result.scalars().all()
            doc_ids = [d.id for d in docs]

            if doc_ids:
                vs_result = await session.execute(
                    select(VectorStoreRef).where(VectorStoreRef.document_id.in_(doc_ids))
                )
                vs_list = vs_result.scalars().all()

                evals_result = await session.execute(
                    select(FREEvaluation.id).where(FREEvaluation.document_id.in_(doc_ids))
                )
                eval_ids = [r[0] for r in evals_result.all()]

        detail = f"{len(doc_ids)} doc(s) · {len(vs_list)} vector store(s) · {len(eval_ids)} avaliação(ões)"
        yield f"data: {json.dumps({'step': 'lookup', 'label': 'Registros encontrados', 'status': 'done', 'count': len(doc_ids), 'detail': detail})}\n\n"

        # ── Etapa 2: OpenAI ────────────────────────────────────────────────
        deleted_vs = 0
        deleted_files = 0
        if vs_list:
            yield f"data: {json.dumps({'step': 'openai', 'label': f'Removendo {len(vs_list)} vector store(s) OpenAI...', 'status': 'running'})}\n\n"
            try:
                from openai import AsyncOpenAI
                client = AsyncOpenAI(api_key=settings.openai_api_key)
                for vs in vs_list:
                    try:
                        files = await client.vector_stores.files.list(vector_store_id=vs.vector_store_id)
                        for f in files.data:
                            try:
                                await client.files.delete(f.id)
                                deleted_files += 1
                            except Exception:
                                pass
                        await client.vector_stores.delete(vs.vector_store_id)
                        deleted_vs += 1
                    except Exception:
                        pass
            except Exception:
                pass
            detail_openai = f"{deleted_vs} vector store(s) · {deleted_files} arquivo(s) OpenAI"
            yield f"data: {json.dumps({'step': 'openai', 'label': 'Dados OpenAI removidos', 'status': 'done', 'count': deleted_vs, 'detail': detail_openai})}\n\n"
        else:
            yield f"data: {json.dumps({'step': 'openai', 'label': 'Nenhum dado OpenAI para remover', 'status': 'done', 'count': 0, 'detail': ''})}\n\n"

        # ── Etapa 3: Banco de dados ────────────────────────────────────────
        deleted_docs = 0
        if doc_ids:
            yield f"data: {json.dumps({'step': 'db', 'label': 'Removendo registros do banco...', 'status': 'running'})}\n\n"
            async with factory() as session:
                if eval_ids:
                    await session.execute(
                        delete(IssueResolution).where(IssueResolution.evaluation_id.in_(eval_ids))
                    )
                    await session.execute(
                        delete(FREItemEvaluation).where(FREItemEvaluation.evaluation_id.in_(eval_ids))
                    )
                await session.execute(
                    delete(FREEvaluation).where(FREEvaluation.document_id.in_(doc_ids))
                )
                await session.execute(
                    delete(FREItem).where(FREItem.document_id.in_(doc_ids))
                )
                await session.execute(
                    delete(VectorStoreRef).where(VectorStoreRef.document_id.in_(doc_ids))
                )
                await session.execute(
                    delete(ChatMessage).where(ChatMessage.document_id.in_(doc_ids))
                )
                await session.execute(
                    delete(DiffSession).where(
                        DiffSession.doc_a_id.in_(doc_ids) | DiffSession.doc_b_id.in_(doc_ids)
                    )
                )
                await session.execute(
                    delete(FREDocument).where(FREDocument.id.in_(doc_ids))
                )
                await session.commit()
                deleted_docs = len(doc_ids)
            yield f"data: {json.dumps({'step': 'db', 'label': 'Banco de dados limpo', 'status': 'done', 'count': deleted_docs, 'detail': f'{deleted_docs} documento(s) removido(s)'})}\n\n"
        else:
            yield f"data: {json.dumps({'step': 'db', 'label': 'Nenhum registro no banco para remover', 'status': 'done', 'count': 0, 'detail': ''})}\n\n"

        # ── Etapa 4: Arquivos locais ───────────────────────────────────────
        yield f"data: {json.dumps({'step': 'local', 'label': 'Removendo arquivos locais...', 'status': 'running'})}\n\n"
        company_dir = settings.base_dir / "enet_local" / _cnpj_slug(cnpj)
        local_file_count = 0
        if company_dir.exists():
            local_file_count = sum(1 for f in company_dir.rglob("*") if f.is_file())
            await asyncio.to_thread(shutil.rmtree, company_dir)
            yield f"data: {json.dumps({'step': 'local', 'label': 'Arquivos locais removidos', 'status': 'done', 'count': local_file_count, 'detail': f'{local_file_count} arquivo(s) PDF e índice'})}\n\n"
        else:
            yield f"data: {json.dumps({'step': 'local', 'label': 'Nenhum arquivo local para remover', 'status': 'done', 'count': 0, 'detail': ''})}\n\n"

        # ── Conclusão ──────────────────────────────────────────────────────
        yield f"data: {json.dumps({'step': 'complete', 'label': 'Empresa removida com sucesso', 'status': 'done', 'deleted_docs': deleted_docs, 'deleted_vs': deleted_vs, 'deleted_files': deleted_files, 'deleted_local': local_file_count})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")
