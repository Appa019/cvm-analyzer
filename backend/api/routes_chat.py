"""
CVM Analyzer - Chat API Routes
===========================

FastAPI routes for RAG chat functionality.
"""

from pathlib import Path
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Depends, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from services import get_rag_service
from security import get_current_user
from config import get_settings
from database import get_async_engine, get_async_session_factory


router = APIRouter(prefix="/api/chat", tags=["Chat"])


# =============================================================================
# Request/Response Models
# =============================================================================

class CreateSessionRequest(BaseModel):
    cnpj_cia: Optional[str] = None
    document_id: Optional[str] = None
    dt_refer: Optional[str] = None
    versao: Optional[int] = None
    vector_store_id: Optional[str] = None
    company_name: Optional[str] = None


class SessionResponse(BaseModel):
    session_id: str
    document_id: Optional[str]
    dt_refer: Optional[str]
    versao: Optional[int]
    cnpj_cia: Optional[str]
    company_name: Optional[str]
    created_at: str


class ChatRequest(BaseModel):
    message: str


class SourceResponse(BaseModel):
    item_id: str
    dt_refer: str
    versao: int
    text_snippet: str
    is_historical: bool


class MessageResponse(BaseModel):
    role: str
    content: str
    sources: List[SourceResponse]
    web_sources: List[dict]
    created_at: str


class ChatHistoryResponse(BaseModel):
    session_id: str
    messages: List[MessageResponse]


class IndexCompanyRequest(BaseModel):
    cnpj_cia: str
    company_name: str
    new_only: bool = False


# =============================================================================
# Routes
# =============================================================================

@router.get("/company-status")
async def company_status(
    cnpj: str = Query(...),
    current_user: dict = Depends(get_current_user),
):
    """Retorna status de indexação de documentos para uma empresa."""
    settings = get_settings()
    enet_path = settings.base_dir / "enet_local"
    engine = get_async_engine(str(settings.db_path))
    factory = get_async_session_factory(engine)

    async with factory() as session:
        result = await get_rag_service().check_new_docs(cnpj, enet_path, session)

    return result


@router.post("/index-company")
async def index_company(
    request: IndexCompanyRequest,
    current_user: dict = Depends(get_current_user),
):
    """SSE stream: indexa PDFs de uma empresa no Vector Store da OpenAI."""
    settings = get_settings()
    enet_path = settings.base_dir / "enet_local"

    return StreamingResponse(
        get_rag_service().index_company_documents(
            request.cnpj_cia,
            request.company_name,
            enet_path,
            request.new_only,
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/sessions", response_model=SessionResponse)
async def create_session(
    request: CreateSessionRequest,
    current_user: dict = Depends(get_current_user)
):
    """Create a new chat session."""
    try:
        rag_service = get_rag_service()
        session = rag_service.create_session(
            cnpj_cia=request.cnpj_cia,
            document_id=request.document_id,
            dt_refer=request.dt_refer,
            versao=request.versao,
            vector_store_id=request.vector_store_id,
            company_name=request.company_name,
        )
        return SessionResponse(
            session_id=session.session_id,
            document_id=session.document_id,
            dt_refer=session.dt_refer,
            versao=session.versao,
            cnpj_cia=session.cnpj_cia,
            company_name=session.company_name,
            created_at=session.created_at
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sessions/{session_id}/messages", response_model=MessageResponse)
async def send_message(
    session_id: str,
    request: ChatRequest,
    current_user: dict = Depends(get_current_user)
):
    """Send a message to the chat. Returns the assistant response."""
    try:
        rag_service = get_rag_service()
        session = rag_service.get_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")

        response = await rag_service.chat(session_id, request.message)

        return MessageResponse(
            role=response.role,
            content=response.content,
            sources=[
                SourceResponse(
                    item_id=s.item_id,
                    dt_refer=s.dt_refer,
                    versao=s.versao,
                    text_snippet=s.text_snippet,
                    is_historical=s.is_historical
                )
                for s in response.sources
            ],
            web_sources=response.web_sources,
            created_at=response.created_at
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sessions/{session_id}", response_model=ChatHistoryResponse)
async def get_session_history(
    session_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Get chat history for a session."""
    try:
        rag_service = get_rag_service()
        session = rag_service.get_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")

        messages = [
            MessageResponse(
                role=m.role,
                content=m.content,
                sources=[
                    SourceResponse(
                        item_id=s.item_id,
                        dt_refer=s.dt_refer,
                        versao=s.versao,
                        text_snippet=s.text_snippet,
                        is_historical=s.is_historical
                    )
                    for s in m.sources
                ],
                web_sources=m.web_sources,
                created_at=m.created_at
            )
            for m in session.messages
        ]
        return ChatHistoryResponse(session_id=session_id, messages=messages)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/sessions/{session_id}")
async def delete_session(
    session_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Delete a chat session."""
    try:
        rag_service = get_rag_service()
        rag_service.clear_session(session_id)
        return {"status": "deleted", "session_id": session_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sessions")
async def list_sessions(current_user: dict = Depends(get_current_user)):
    """List all active chat sessions."""
    try:
        rag_service = get_rag_service()
        sessions = [
            {
                "session_id": s.session_id,
                "document_id": s.document_id,
                "dt_refer": s.dt_refer,
                "cnpj_cia": s.cnpj_cia,
                "company_name": s.company_name,
                "message_count": len(s.messages),
                "created_at": s.created_at
            }
            for s in rag_service.sessions.values()
        ]
        return {"sessions": sessions}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
