"""
CVM Analyzer - Diff API Routes
===========================

FastAPI routes for document diff functionality.
"""

import tempfile
from pathlib import Path
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel
from datetime import datetime

from security import get_current_user
from services import get_diff_engine, get_pdf_extractor, get_cvm_service
from config import get_settings


router = APIRouter(prefix="/api/diff", tags=["Diff"])


# =============================================================================
# Request/Response Models
# =============================================================================

class DiffRequest(BaseModel):
    """Request to compare two documents."""
    doc_a_path: Optional[str] = None
    doc_b_path: Optional[str] = None
    doc_a_dt_refer: Optional[str] = None
    doc_b_dt_refer: Optional[str] = None
    doc_a_versao: Optional[int] = 1
    doc_b_versao: Optional[int] = 1
    include_semantic: bool = True
    download_from_cvm: bool = False


class SectionDiffResponse(BaseModel):
    """Response for a single section diff."""
    item_id: str
    titulo_a: str
    titulo_b: str
    change_type: str
    text_changes: List[dict]
    table_changes: List[dict]
    semantic_summary: str
    has_changes: bool


class DiffResponse(BaseModel):
    """Full diff response."""
    doc_a_id: str
    doc_b_id: str
    doc_a_dt_refer: str
    doc_b_dt_refer: str
    total_sections: int
    added_count: int
    removed_count: int
    modified_count: int
    moved_count: int
    unchanged_count: int
    summary: str
    created_at: str
    sections: List[SectionDiffResponse]


class WordDiffRequest(BaseModel):
    """Request for word-level diff."""
    text_a: str
    text_b: str
    show_formatting: bool = False


class WordDiffResponse(BaseModel):
    """Response with word-level diff."""
    diff_output: str
    changes: List[dict]


# =============================================================================
# Routes
# =============================================================================

@router.post("/compare", response_model=DiffResponse)
async def compare_documents(request: DiffRequest, current_user: dict = Depends(get_current_user)):
    """
    Compare two FRE documents.
    
    Returns section-by-section diff with semantic summaries.
    """
    try:
        diff_engine = get_diff_engine()
        pdf_extractor = get_pdf_extractor()
        cvm_service = get_cvm_service()

        # Resolve paths
        doc_a_path = request.doc_a_path
        doc_b_path = request.doc_b_path

        if request.download_from_cvm:
            if request.doc_a_dt_refer and getattr(request, 'doc_a_link', None):
                doc_a_path = str(cvm_service.download_pdf_sync(
                    request.doc_a_link,
                    request.doc_a_dt_refer,
                    request.doc_a_versao
                ))

            if request.doc_b_dt_refer and getattr(request, 'doc_b_link', None):
                doc_b_path = str(cvm_service.download_pdf_sync(
                    request.doc_b_link,
                    request.doc_b_dt_refer,
                    request.doc_b_versao
                ))
        
        if not doc_a_path or not doc_b_path:
            raise HTTPException(
                status_code=400,
                detail="Both document paths are required"
            )
        
        # Extract sections from both documents
        from pathlib import Path
        extraction_a = pdf_extractor.extract_full(Path(doc_a_path))
        extraction_b = pdf_extractor.extract_full(Path(doc_b_path))
        
        # Compare
        result = await diff_engine.compare_documents(
            sections_a=extraction_a.sections,
            sections_b=extraction_b.sections,
            doc_a_id=f"fre_{request.doc_a_dt_refer}_v{request.doc_a_versao}",
            doc_b_id=f"fre_{request.doc_b_dt_refer}_v{request.doc_b_versao}",
            doc_a_dt_refer=request.doc_a_dt_refer or "",
            doc_b_dt_refer=request.doc_b_dt_refer or "",
            include_semantic=request.include_semantic
        )
        
        # Convert to response
        sections = [
            SectionDiffResponse(
                item_id=s.item_id,
                titulo_a=s.titulo_a,
                titulo_b=s.titulo_b,
                change_type=s.change_type.value,
                text_changes=[c.to_dict() for c in s.text_changes[:10]],
                table_changes=[c.to_dict() for c in s.table_changes[:10]],
                semantic_summary=s.semantic_summary,
                has_changes=s.change_type.value != "unchanged"
            )
            for s in result.section_diffs
        ]
        
        return DiffResponse(
            doc_a_id=result.doc_a_id,
            doc_b_id=result.doc_b_id,
            doc_a_dt_refer=result.doc_a_dt_refer,
            doc_b_dt_refer=result.doc_b_dt_refer,
            total_sections=result.total_sections,
            added_count=result.added_count,
            removed_count=result.removed_count,
            modified_count=result.modified_count,
            moved_count=result.moved_count,
            unchanged_count=result.unchanged_count,
            summary=result.summary,
            created_at=result.created_at,
            sections=sections
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/word-diff", response_model=WordDiffResponse)
async def get_word_diff(request: WordDiffRequest, current_user: dict = Depends(get_current_user)):
    """
    Get word-level diff between two texts.
    
    Used for detailed view of changes.
    """
    try:
        diff_engine = get_diff_engine()
        
        diff_output, changes = diff_engine.get_word_diff(
            request.text_a,
            request.text_b,
            request.show_formatting
        )
        
        return WordDiffResponse(
            diff_output=diff_output,
            changes=[c.to_dict() for c in changes]
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


MAX_UPLOAD_SIZE = 50 * 1024 * 1024  # 50MB


@router.post("/compare-upload", response_model=DiffResponse)
async def compare_upload(
    file1: UploadFile = File(...),
    file2: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
):
    """
    Compare two uploaded PDF files.
    Returns section-by-section diff with semantic summaries.
    """
    for f in (file1, file2):
        if not f.filename or not f.filename.lower().endswith(".pdf"):
            raise HTTPException(status_code=400, detail="Apenas arquivos PDF são aceitos.")

    tmp_paths = []
    try:
        for f in (file1, file2):
            content = await f.read()
            if len(content) > MAX_UPLOAD_SIZE:
                raise HTTPException(status_code=413, detail="Arquivo muito grande. Limite: 50MB.")
            if not content.startswith(b"%PDF"):
                raise HTTPException(status_code=400, detail=f"O arquivo '{f.filename}' não é um PDF válido.")
            tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
            tmp.write(content)
            tmp.close()
            tmp_paths.append(tmp.name)

        diff_engine = get_diff_engine()
        pdf_extractor = get_pdf_extractor()

        extraction_a = pdf_extractor.extract_full(Path(tmp_paths[0]))
        extraction_b = pdf_extractor.extract_full(Path(tmp_paths[1]))

        result = await diff_engine.compare_documents(
            sections_a=extraction_a.sections,
            sections_b=extraction_b.sections,
            doc_a_id=f"upload_{file1.filename}",
            doc_b_id=f"upload_{file2.filename}",
            doc_a_dt_refer="",
            doc_b_dt_refer="",
            include_semantic=True,
        )

        sections = [
            SectionDiffResponse(
                item_id=s.item_id,
                titulo_a=s.titulo_a,
                titulo_b=s.titulo_b,
                change_type=s.change_type.value,
                text_changes=[c.to_dict() for c in s.text_changes[:10]],
                table_changes=[c.to_dict() for c in s.table_changes[:10]],
                semantic_summary=s.semantic_summary,
                has_changes=s.change_type.value != "unchanged",
            )
            for s in result.section_diffs
        ]

        return DiffResponse(
            doc_a_id=result.doc_a_id,
            doc_b_id=result.doc_b_id,
            doc_a_dt_refer=result.doc_a_dt_refer,
            doc_b_dt_refer=result.doc_b_dt_refer,
            total_sections=result.total_sections,
            added_count=result.added_count,
            removed_count=result.removed_count,
            modified_count=result.modified_count,
            moved_count=result.moved_count,
            unchanged_count=result.unchanged_count,
            summary=result.summary,
            created_at=result.created_at,
            sections=sections,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        for p in tmp_paths:
            Path(p).unlink(missing_ok=True)


class CompareLocalRequest(BaseModel):
    """Request to compare two locally-saved documents."""
    cnpj: str
    doc1_filename: str
    doc2_filename: str
    include_semantic: bool = True


@router.post("/compare-local", response_model=DiffResponse)
async def compare_local_docs(
    request: CompareLocalRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Compara dois documentos salvos localmente pelo enet_scraper.
    Resolve os caminhos via ~/.local/share/FREAnalyzer/enet_local/{cnpj_slug}/
    """
    settings = get_settings()
    cnpj_slug = request.cnpj.replace("/", "_").replace(".", "_").replace("-", "_").strip("_")
    base_dir = (settings.base_dir / "enet_local" / cnpj_slug).resolve()

    path1 = (base_dir / request.doc1_filename).resolve()
    path2 = (base_dir / request.doc2_filename).resolve()

    if not path1.is_relative_to(base_dir) or not path2.is_relative_to(base_dir):
        raise HTTPException(status_code=400, detail="Nome de arquivo inválido.")
    if not path1.exists():
        raise HTTPException(status_code=404, detail=f"Arquivo não encontrado: {request.doc1_filename}")
    if not path2.exists():
        raise HTTPException(status_code=404, detail=f"Arquivo não encontrado: {request.doc2_filename}")

    try:
        diff_engine = get_diff_engine()
        pdf_extractor = get_pdf_extractor()

        extraction_a = pdf_extractor.extract_full(path1)
        extraction_b = pdf_extractor.extract_full(path2)

        doc_a_id = request.doc1_filename.replace(".pdf", "")
        doc_b_id = request.doc2_filename.replace(".pdf", "")

        result = await diff_engine.compare_documents(
            sections_a=extraction_a.sections,
            sections_b=extraction_b.sections,
            doc_a_id=doc_a_id,
            doc_b_id=doc_b_id,
            doc_a_dt_refer=request.doc1_filename,
            doc_b_dt_refer=request.doc2_filename,
            include_semantic=request.include_semantic,
        )

        sections = [
            SectionDiffResponse(
                item_id=s.item_id,
                titulo_a=s.titulo_a,
                titulo_b=s.titulo_b,
                change_type=s.change_type.value,
                text_changes=[c.to_dict() for c in s.text_changes[:10]],
                table_changes=[c.to_dict() for c in s.table_changes[:10]],
                semantic_summary=s.semantic_summary,
                has_changes=s.change_type.value != "unchanged",
            )
            for s in result.section_diffs
        ]

        return DiffResponse(
            doc_a_id=result.doc_a_id,
            doc_b_id=result.doc_b_id,
            doc_a_dt_refer=result.doc_a_dt_refer,
            doc_b_dt_refer=result.doc_b_dt_refer,
            total_sections=result.total_sections,
            added_count=result.added_count,
            removed_count=result.removed_count,
            modified_count=result.modified_count,
            moved_count=result.moved_count,
            unchanged_count=result.unchanged_count,
            summary=result.summary,
            created_at=result.created_at,
            sections=sections,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history")
async def get_diff_history():
    """
    Get history of diff sessions.
    """
    # TODO: Implement database retrieval
    return {"sessions": []}
