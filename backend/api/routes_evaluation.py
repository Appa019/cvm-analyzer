"""
CVM Analyzer - Evaluation API Routes
=================================

Routes for FRE evaluation: download from published source, upload unpublished PDF,
3D analysis (vs CVM 80 + historical + facultativos), history, resolve issues, export.
"""

import io
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List

from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select, desc

from services import get_evaluation_engine, get_cvm_service, EvaluationSummary
from database import (
    Evaluation as FREEvaluation,
    ItemEvaluation as FREItemEvaluation,
    IssueResolution,
    get_async_engine, get_async_session_factory,
)
from security import get_current_user
from config import get_settings


router = APIRouter(prefix="/api/evaluation", tags=["Evaluation"])


# =============================================================================
# DB helpers
# =============================================================================

async def get_db_session():
    settings = get_settings()
    engine = get_async_engine(str(settings.db_path))
    factory = get_async_session_factory(engine)
    async with factory() as session:
        yield session


async def save_evaluation_to_db(session, summary: EvaluationSummary, is_uploaded: bool = False, filename: str = None):
    """Persist an EvaluationSummary to the database and return the DB record id."""
    eval_record = FREEvaluation(
        document_id_str=summary.document_id,
        dt_refer=summary.dt_refer,
        versao=summary.versao,
        tipo_doc=getattr(summary, "tipo_doc", "FRE"),
        status="completed",
        total_score=summary.total_score,
        total_items=summary.total_items,
        complete_count=summary.complete_count,
        partial_count=summary.partial_count,
        absent_count=summary.absent_count,
        critical_count=summary.critical_count,
        model_used=summary.model_used,
        is_uploaded=is_uploaded,
        original_filename=filename,
        completed_at=datetime.now(timezone.utc),
    )
    session.add(eval_record)
    await session.flush()  # get eval_record.id

    for r in summary.item_results:
        item_eval = FREItemEvaluation(
            evaluation_id=eval_record.id,
            item_id_str=r.item_id,
            titulo=r.titulo,
            status=r.status,
            score=r.score,
            peso=r.peso,
            issues=[{"severity": i.severity, "description": i.description} for i in r.issues],
            missing_checklist=r.missing_checklist,
            suggestion=r.suggestion,
            reasoning=r.reasoning,
            confidence=r.confidence,
            tokens_used=r.tokens_used,
            input_tokens=r.input_tokens,
            output_tokens=r.output_tokens,
            model_used=summary.model_used,
        )
        session.add(item_eval)

    await session.commit()
    return eval_record.id


# =============================================================================
# Request / Response Models
# =============================================================================

class EvaluateRequest(BaseModel):
    dt_refer: str
    versao: Optional[int] = 1
    cnpj: Optional[str] = None
    link_doc: Optional[str] = None
    tipo_doc: str = "FRE"  # FRE, DFP, FCA, IPE
    local_filename: Optional[str] = None  # arquivo já baixado em enet_local/


class ItemEvaluationResponse(BaseModel):
    item_id: str
    titulo: str
    status: str
    score: float
    peso: int
    issues: List[dict]
    missing_checklist: List[str]
    suggestion: str
    confidence: float
    reasoning: str


class EvaluationResponse(BaseModel):
    evaluation_id: int
    document_id: str
    dt_refer: str
    versao: int
    tipo_doc: str = "FRE"
    total_score: Optional[float]  # None para avaliações qualitativas (IPE)
    total_items: int
    complete_count: int
    partial_count: int
    absent_count: int
    critical_count: int
    evaluated_at: str
    model_used: str
    is_uploaded: bool
    items: List[ItemEvaluationResponse]


class ResolveIssueRequest(BaseModel):
    item_id_str: str
    issue_index: int


# =============================================================================
# Routes
# =============================================================================

@router.get("/documents")
async def get_company_documents(
    cnpj: Optional[str] = None,
    years: Optional[str] = None,
    tipos: Optional[str] = None,
):
    """Lista documentos disponíveis de uma empresa (via CVM) filtrado por CNPJ e tipos."""
    if not cnpj:
        return {"documents": []}
    try:
        year_list = None
        if years:
            try:
                year_list = [int(y.strip()) for y in years.split(",") if y.strip()]
            except ValueError:
                raise HTTPException(status_code=400, detail="Formato de anos inválido.")
        tipo_list = [t.strip().upper() for t in tipos.split(",") if t.strip()] if tipos else ["FRE", "DFP", "FCA", "IPE"]
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
        return {"documents": all_docs}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/evaluate", response_model=EvaluationResponse)
async def evaluate_document(
    request: EvaluateRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Evaluate a published CVM Analyzer (downloaded from website).
    Checks DB cache first — re-evaluates only if not found.
    """
    engine_svc = get_evaluation_engine()
    settings = get_settings()
    db_engine = get_async_engine(str(settings.db_path))
    factory = get_async_session_factory(db_engine)

    tipo_doc = request.tipo_doc.upper()
    document_id = f"{tipo_doc.lower()}_{request.dt_refer}_v{request.versao}"

    async with factory() as session:
        # Cache check
        result = await session.execute(
            select(FREEvaluation)
            .where(FREEvaluation.document_id_str == document_id)
            .where(FREEvaluation.status == "completed")
            .order_by(desc(FREEvaluation.completed_at))
        )
        cached = result.scalars().first()

    if cached:
        # Load item evaluations
        async with factory() as session:
            items_result = await session.execute(
                select(FREItemEvaluation).where(FREItemEvaluation.evaluation_id == cached.id)
            )
            item_rows = items_result.scalars().all()

        items = [
            ItemEvaluationResponse(
                item_id=r.item_id_str or "",
                titulo=r.titulo or "",
                status=r.status,
                score=r.score,
                peso=r.peso,
                issues=r.issues or [],
                missing_checklist=r.missing_checklist or [],
                suggestion=r.suggestion or "",
                confidence=r.confidence,
                reasoning=r.reasoning or "",
            )
            for r in item_rows
        ]

        return EvaluationResponse(
            evaluation_id=cached.id,
            document_id=cached.document_id_str or document_id,
            dt_refer=cached.dt_refer or request.dt_refer,
            versao=cached.versao or request.versao,
            tipo_doc=getattr(cached, "tipo_doc", None) or tipo_doc,
            total_score=cached.total_score,
            total_items=cached.total_items,
            complete_count=cached.complete_count,
            partial_count=cached.partial_count,
            absent_count=cached.absent_count,
            critical_count=cached.critical_count,
            evaluated_at=cached.completed_at.isoformat() if cached.completed_at else "",
            model_used=cached.model_used or "",
            is_uploaded=cached.is_uploaded,
            items=items,
        )

    # Usa arquivo local se informado (já baixado via sync)
    if request.local_filename and request.cnpj:
        from config import get_settings as _get_settings
        def _cnpj_slug(c): return c.replace("/","_").replace(".","_").replace("-","_").strip("_")
        _base = _get_settings().base_dir / "enet_local" / _cnpj_slug(request.cnpj)
        _local = (_base / request.local_filename).resolve()
        if not str(_local).startswith(str(_base.resolve())):
            raise HTTPException(status_code=400, detail="Nome de arquivo inválido.")
        if not _local.exists():
            raise HTTPException(status_code=404, detail=f"Arquivo local não encontrado: {request.local_filename}")
        pdf_path = _local
        versao = request.versao or 1
    else:
        # Download PDF via CVM service
        if not request.link_doc:
            if not request.cnpj:
                raise HTTPException(status_code=400, detail="Informe cnpj e link_doc para avaliar um documento publicado.")
            svc = get_cvm_service()
            df = await svc.get_company_fres(request.cnpj)
            row = df[df["DT_REFER"] == request.dt_refer]
            if row.empty:
                raise HTTPException(status_code=404, detail=f"Documento não encontrado: DT_REFER={request.dt_refer}, CNPJ={request.cnpj}")
            link_doc = str(row.iloc[0]["LINK_DOC"])
            versao = int(str(row.iloc[0].get("VERSAO", request.versao)))
        else:
            svc = get_cvm_service()
            link_doc = request.link_doc
            versao = request.versao or 1
        pdf_path = await svc.download_pdf(link_doc, request.dt_refer, versao, cnpj=request.cnpj or "")

    # Run evaluation (roteado por tipo_doc)
    # Passa cnpj e filename para carregar histórico de documentos anteriores
    summary = await engine_svc.evaluate_document(
        str(pdf_path),
        request.dt_refer,
        versao,
        tipo_doc,
        cnpj=request.cnpj or None,
        current_filename=request.local_filename or None,
    )

    # Persist to DB
    async with factory() as session:
        eval_id = await save_evaluation_to_db(session, summary)

    items = [
        ItemEvaluationResponse(
            item_id=r.item_id,
            titulo=r.titulo,
            status=r.status,
            score=r.score,
            peso=r.peso,
            issues=[{"severity": i.severity, "description": i.description} for i in r.issues],
            missing_checklist=r.missing_checklist,
            suggestion=r.suggestion,
            confidence=r.confidence,
            reasoning=r.reasoning,
        )
        for r in summary.item_results
    ]

    return EvaluationResponse(
        evaluation_id=eval_id,
        document_id=summary.document_id,
        dt_refer=summary.dt_refer,
        versao=summary.versao,
        tipo_doc=getattr(summary, "tipo_doc", tipo_doc),
        total_score=summary.total_score,
        total_items=summary.total_items,
        complete_count=summary.complete_count,
        partial_count=summary.partial_count,
        absent_count=summary.absent_count,
        critical_count=summary.critical_count,
        evaluated_at=summary.evaluated_at,
        model_used=summary.model_used,
        is_uploaded=False,
        items=items,
    )


@router.post("/upload", response_model=EvaluationResponse)
async def upload_and_evaluate(
    file: UploadFile = File(...),
    dt_refer: str = Form(default=datetime.now(timezone.utc).strftime("%Y-%m-%d")),
    versao: int = Form(default=1),
    tipo_doc: str = Form(default="FRE"),
    current_user: dict = Depends(get_current_user),
):
    """
    Upload an unpublished FRE PDF and run 3D analysis:
    1. vs Resolução CVM 80 (item-by-item conformance)
    2. vs all historical CVM Analyzers (regression detection)
    3. Alert for missing itens facultativos
    """
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Apenas arquivos PDF são aceitos.")

    MAX_UPLOAD_SIZE = 50 * 1024 * 1024  # 50MB

    engine_svc = get_evaluation_engine()
    settings = get_settings()

    # Save uploaded file to a temp path
    content = await file.read()
    if len(content) > MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=413, detail="Arquivo muito grande. Limite: 50MB.")
    if not content.startswith(b"%PDF"):
        raise HTTPException(status_code=400, detail="O arquivo enviado não é um PDF válido.")

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        summary = await engine_svc.evaluate_document(tmp_path, dt_refer, versao, tipo_doc.upper())
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    # Historical comparison: get latest published evaluation from DB
    db_engine = get_async_engine(str(settings.db_path))
    factory = get_async_session_factory(db_engine)
    async with factory() as session:
        hist_result = await session.execute(
            select(FREEvaluation)
            .where(FREEvaluation.is_uploaded == False)
            .where(FREEvaluation.status == "completed")
            .order_by(desc(FREEvaluation.completed_at))
        )
        historical = hist_result.scalars().first()
        hist_score = historical.total_score if historical else None

    # Attach historical context to summary document_id
    doc_id = f"upload_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{file.filename}"
    summary.document_id = doc_id

    # Persist
    async with factory() as session:
        eval_id = await save_evaluation_to_db(session, summary, is_uploaded=True, filename=file.filename)

    items = [
        ItemEvaluationResponse(
            item_id=r.item_id,
            titulo=r.titulo,
            status=r.status,
            score=r.score,
            peso=r.peso,
            issues=[{"severity": i.severity, "description": i.description} for i in r.issues],
            missing_checklist=r.missing_checklist,
            suggestion=r.suggestion,
            confidence=r.confidence,
            reasoning=r.reasoning,
        )
        for r in summary.item_results
    ]

    response = EvaluationResponse(
        evaluation_id=eval_id,
        document_id=doc_id,
        dt_refer=summary.dt_refer,
        versao=summary.versao,
        tipo_doc=getattr(summary, "tipo_doc", "FRE"),
        total_score=summary.total_score,
        total_items=summary.total_items,
        complete_count=summary.complete_count,
        partial_count=summary.partial_count,
        absent_count=summary.absent_count,
        critical_count=summary.critical_count,
        evaluated_at=summary.evaluated_at,
        model_used=summary.model_used,
        is_uploaded=True,
        items=items,
    )
    return response


@router.get("/history")
async def get_evaluation_history(current_user: dict = Depends(get_current_user)):
    """List all evaluations ordered by most recent."""
    settings = get_settings()
    db_engine = get_async_engine(str(settings.db_path))
    factory = get_async_session_factory(db_engine)

    async with factory() as session:
        result = await session.execute(
            select(FREEvaluation)
            .where(FREEvaluation.status == "completed")
            .order_by(desc(FREEvaluation.completed_at))
        )
        rows = result.scalars().all()

    evaluations = [
        {
            "id": r.id,
            "document_id": r.document_id_str,
            "dt_refer": r.dt_refer,
            "versao": r.versao,
            "tipo_doc": getattr(r, "tipo_doc", None) or "FRE",
            "total_score": r.total_score,
            "total_items": r.total_items,
            "complete_count": r.complete_count,
            "partial_count": r.partial_count,
            "absent_count": r.absent_count,
            "critical_count": r.critical_count,
            "model_used": r.model_used,
            "is_uploaded": r.is_uploaded,
            "original_filename": r.original_filename,
            "evaluated_at": r.completed_at.isoformat() if r.completed_at else None,
        }
        for r in rows
    ]
    return {"evaluations": evaluations}


@router.get("/{evaluation_id}", response_model=EvaluationResponse)
async def get_evaluation(
    evaluation_id: int,
    current_user: dict = Depends(get_current_user),
):
    """Get a specific evaluation with all item results."""
    settings = get_settings()
    db_engine = get_async_engine(str(settings.db_path))
    factory = get_async_session_factory(db_engine)

    async with factory() as session:
        result = await session.execute(
            select(FREEvaluation).where(FREEvaluation.id == evaluation_id)
        )
        eval_row = result.scalars().first()

    if not eval_row:
        raise HTTPException(status_code=404, detail="Avaliação não encontrada.")

    async with factory() as session:
        items_result = await session.execute(
            select(FREItemEvaluation).where(FREItemEvaluation.evaluation_id == evaluation_id)
        )
        item_rows = items_result.scalars().all()

    items = [
        ItemEvaluationResponse(
            item_id=r.item_id_str or "",
            titulo=r.titulo or "",
            status=r.status,
            score=r.score,
            peso=r.peso,
            issues=r.issues or [],
            missing_checklist=r.missing_checklist or [],
            suggestion=r.suggestion or "",
            confidence=r.confidence,
            reasoning=r.reasoning or "",
        )
        for r in item_rows
    ]

    return EvaluationResponse(
        evaluation_id=eval_row.id,
        document_id=eval_row.document_id_str or "",
        dt_refer=eval_row.dt_refer or "",
        versao=eval_row.versao or 1,
        tipo_doc=getattr(eval_row, "tipo_doc", None) or "FRE",
        total_score=eval_row.total_score,
        total_items=eval_row.total_items,
        complete_count=eval_row.complete_count,
        partial_count=eval_row.partial_count,
        absent_count=eval_row.absent_count,
        critical_count=eval_row.critical_count,
        evaluated_at=eval_row.completed_at.isoformat() if eval_row.completed_at else "",
        model_used=eval_row.model_used or "",
        is_uploaded=eval_row.is_uploaded,
        items=items,
    )


@router.post("/{evaluation_id}/issues/resolve")
async def resolve_issue(
    evaluation_id: int,
    request: ResolveIssueRequest,
    current_user: dict = Depends(get_current_user),
):
    """Mark an issue as resolved by the current user (persisted per-user)."""
    settings = get_settings()
    db_engine = get_async_engine(str(settings.db_path))
    factory = get_async_session_factory(db_engine)

    async with factory() as session:
        # Check evaluation exists
        result = await session.execute(
            select(FREEvaluation).where(FREEvaluation.id == evaluation_id)
        )
        if not result.scalars().first():
            raise HTTPException(status_code=404, detail="Avaliação não encontrada.")

        # Check if already resolved by this user
        existing = await session.execute(
            select(IssueResolution).where(
                IssueResolution.evaluation_id == evaluation_id,
                IssueResolution.item_id_str == request.item_id_str,
                IssueResolution.issue_index == request.issue_index,
                IssueResolution.user_email == current_user["email"],
            )
        )
        if existing.scalars().first():
            return {"status": "already_resolved"}

        resolution = IssueResolution(
            evaluation_id=evaluation_id,
            item_id_str=request.item_id_str,
            issue_index=request.issue_index,
            user_email=current_user["email"],
        )
        session.add(resolution)
        await session.commit()

    return {"status": "resolved", "item_id_str": request.item_id_str, "issue_index": request.issue_index}


@router.get("/{evaluation_id}/issues/resolved")
async def get_resolved_issues(
    evaluation_id: int,
    current_user: dict = Depends(get_current_user),
):
    """Get list of issues the current user has marked as resolved."""
    settings = get_settings()
    db_engine = get_async_engine(str(settings.db_path))
    factory = get_async_session_factory(db_engine)

    async with factory() as session:
        result = await session.execute(
            select(IssueResolution).where(
                IssueResolution.evaluation_id == evaluation_id,
                IssueResolution.user_email == current_user["email"],
            )
        )
        rows = result.scalars().all()

    return {
        "resolved": [
            {"item_id_str": r.item_id_str, "issue_index": r.issue_index, "resolved_at": r.resolved_at.isoformat()}
            for r in rows
        ]
    }


@router.get("/{evaluation_id}/export/xlsx")
async def export_xlsx(
    evaluation_id: int,
    current_user: dict = Depends(get_current_user),
):
    """Export evaluation results as Excel (.xlsx)."""
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment
    from openpyxl.utils import get_column_letter

    settings = get_settings()
    db_engine = get_async_engine(str(settings.db_path))
    factory = get_async_session_factory(db_engine)

    async with factory() as session:
        eval_result = await session.execute(
            select(FREEvaluation).where(FREEvaluation.id == evaluation_id)
        )
        eval_row = eval_result.scalars().first()
        if not eval_row:
            raise HTTPException(status_code=404, detail="Avaliação não encontrada.")

        items_result = await session.execute(
            select(FREItemEvaluation).where(FREItemEvaluation.evaluation_id == evaluation_id)
        )
        item_rows = items_result.scalars().all()

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Avaliação FRE"

    # Header
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill("solid", fgColor="1a365d")
    headers = ["Item", "Título", "Status", "Score", "Peso", "Problemas", "Itens Faltantes", "Sugestão", "Confiança"]
    for col_idx, h in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col_idx, value=h)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center", wrap_text=True)

    STATUS_COLORS = {
        "COMPLETO": "48bb78",
        "PARCIAL": "ed8936",
        "AUSENTE": "e53e3e",
        "CRITICO": "c53030",
    }

    for row_idx, item in enumerate(item_rows, 2):
        issues_text = "; ".join(
            f"[{i.get('severity','?').upper()}] {i.get('description','')}"
            for i in (item.issues or [])
        )
        missing_text = "; ".join(item.missing_checklist or [])
        row_data = [
            item.item_id_str,
            item.titulo,
            item.status,
            item.score,
            item.peso,
            issues_text,
            missing_text,
            item.suggestion,
            f"{int(item.confidence * 100)}%",
        ]
        for col_idx, val in enumerate(row_data, 1):
            cell = ws.cell(row=row_idx, column=col_idx, value=val)
            if col_idx == 3:  # Status column
                color = STATUS_COLORS.get(item.status, "718096")
                cell.fill = PatternFill("solid", fgColor=color)
                cell.font = Font(color="FFFFFF", bold=True)
            cell.alignment = Alignment(wrap_text=True, vertical="top")

    # Column widths
    col_widths = [10, 40, 12, 8, 6, 60, 40, 60, 10]
    for i, w in enumerate(col_widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w

    # Summary sheet
    ws2 = wb.create_sheet("Resumo")
    ws2["A1"] = "Relatório de Avaliação FRE"
    ws2["A1"].font = Font(bold=True, size=14, color="1a365d")
    summary_data = [
        ("Documento", eval_row.document_id_str),
        ("DT_REFER", eval_row.dt_refer),
        ("Versão", eval_row.versao),
        ("Score Total", f"{eval_row.total_score:.1f}/100"),
        ("Itens Avaliados", eval_row.total_items),
        ("Completo", eval_row.complete_count),
        ("Parcial", eval_row.partial_count),
        ("Ausente", eval_row.absent_count),
        ("Crítico", eval_row.critical_count),
        ("Modelo IA", eval_row.model_used),
        ("Avaliado em", eval_row.completed_at.strftime("%d/%m/%Y %H:%M") if eval_row.completed_at else ""),
    ]
    for row_idx, (label, value) in enumerate(summary_data, 3):
        ws2.cell(row=row_idx, column=1, value=label).font = Font(bold=True)
        ws2.cell(row=row_idx, column=2, value=value)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    filename = f"avaliacao_fre_{eval_row.dt_refer or evaluation_id}.xlsx"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{evaluation_id}/export/pdf")
async def export_pdf(
    evaluation_id: int,
    current_user: dict = Depends(get_current_user),
):
    """Export evaluation results as a formatted PDF report."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib.enums import TA_CENTER, TA_LEFT

    settings = get_settings()
    db_engine = get_async_engine(str(settings.db_path))
    factory = get_async_session_factory(db_engine)

    async with factory() as session:
        eval_result = await session.execute(
            select(FREEvaluation).where(FREEvaluation.id == evaluation_id)
        )
        eval_row = eval_result.scalars().first()
        if not eval_row:
            raise HTTPException(status_code=404, detail="Avaliação não encontrada.")

        items_result = await session.execute(
            select(FREItemEvaluation).where(FREItemEvaluation.evaluation_id == evaluation_id)
        )
        item_rows = items_result.scalars().all()

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=2*cm, bottomMargin=2*cm)
    styles = getSampleStyleSheet()

    primary_blue = colors.HexColor("#1a365d")
    primary_green = colors.HexColor("#48bb78")

    title_style = ParagraphStyle("Title", parent=styles["Title"], textColor=primary_blue, fontSize=18, spaceAfter=6)
    heading_style = ParagraphStyle("Heading", parent=styles["Heading2"], textColor=primary_blue, fontSize=12, spaceBefore=12)
    normal_style = styles["Normal"]

    STATUS_COLORS_RL = {
        "COMPLETO": colors.HexColor("#48bb78"),
        "PARCIAL": colors.HexColor("#ed8936"),
        "AUSENTE": colors.HexColor("#e53e3e"),
        "CRITICO": colors.HexColor("#c53030"),
    }

    story = []
    story.append(Paragraph("CVM Analyzer — Relatório de Avaliação", title_style))
    story.append(Spacer(1, 0.3*cm))

    meta = [
        ["Documento:", eval_row.document_id_str or ""],
        ["DT_REFER:", eval_row.dt_refer or ""],
        ["Versão:", str(eval_row.versao or "")],
        ["Score Total:", f"{eval_row.total_score:.1f} / 100"],
        ["Itens Avaliados:", str(eval_row.total_items)],
        ["Modelo IA:", eval_row.model_used or ""],
        ["Avaliado em:", eval_row.completed_at.strftime("%d/%m/%Y %H:%M") if eval_row.completed_at else ""],
    ]
    meta_table = Table(meta, colWidths=[4*cm, 12*cm])
    meta_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("TEXTCOLOR", (0, 0), (0, -1), primary_blue),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.whitesmoke, colors.white]),
    ]))
    story.append(meta_table)
    story.append(Spacer(1, 0.5*cm))

    story.append(Paragraph("Resultados por Item", heading_style))
    story.append(Spacer(1, 0.2*cm))

    table_data = [["Item", "Título", "Status", "Score", "Problemas"]]
    for item in item_rows:
        issues_text = "; ".join(i.get("description", "") for i in (item.issues or [])[:2])
        if len(item.issues or []) > 2:
            issues_text += f" (+{len(item.issues)-2})"
        table_data.append([
            item.item_id_str or "",
            (item.titulo or "")[:40],
            item.status,
            f"{item.score:.0f}",
            issues_text[:80],
        ])

    col_widths = [2*cm, 6*cm, 2.5*cm, 1.5*cm, 6*cm]
    t = Table(table_data, colWidths=col_widths, repeatRows=1)
    style_cmds = [
        ("BACKGROUND", (0, 0), (-1, 0), primary_blue),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.whitesmoke]),
        ("ALIGN", (3, 0), (3, -1), "CENTER"),
    ]
    for row_idx, item in enumerate(item_rows, 1):
        status_color = STATUS_COLORS_RL.get(item.status, colors.grey)
        style_cmds.append(("BACKGROUND", (2, row_idx), (2, row_idx), status_color))
        style_cmds.append(("TEXTCOLOR", (2, row_idx), (2, row_idx), colors.white))
    t.setStyle(TableStyle(style_cmds))
    story.append(t)

    doc.build(story)
    buf.seek(0)

    filename = f"avaliacao_fre_{eval_row.dt_refer or evaluation_id}.pdf"
    return StreamingResponse(
        buf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
