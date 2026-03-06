"""
CVM Analyzer - RAG Service
=======================

RAG (Retrieval-Augmented Generation) service for chat about all company documents.
Uses OpenAI Responses API with Vector Store (file_search) and web_search tools.
Implements previous_response_id for stateful multi-turn conversation.

RAG Agêntico por Empresa:
- Vector Store por empresa (cnpj_cia) contendo todos os PDFs baixados
- Attribute filtering por tipo/data via file_search nativo
- Multi-step reasoning via Responses API
- Persistência do VS ID no DB, carregado ao iniciar
"""

import asyncio
import io
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any, AsyncGenerator
from dataclasses import dataclass, asdict, field
import logging
import re

from openai import AsyncOpenAI

from config import get_settings


def _cnpj_slug(cnpj: str) -> str:
    return cnpj.replace("/", "_").replace(".", "_").replace("-", "_").strip("_")


@dataclass
class Source:
    """Represents a source citation."""
    item_id: str
    dt_refer: str
    versao: int
    text_snippet: str
    is_historical: bool = False

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class ChatMessage:
    """Represents a chat message."""
    role: str  # user, assistant
    content: str
    sources: List[Source] = field(default_factory=list)
    web_sources: List[Dict] = field(default_factory=list)
    created_at: str = ""

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.utcnow().isoformat()

    def to_dict(self) -> Dict:
        return {
            **asdict(self),
            "sources": [s.to_dict() for s in self.sources]
        }


@dataclass
class ChatSession:
    """Represents a chat session."""
    session_id: str
    document_id: Optional[str]
    dt_refer: Optional[str]
    versao: Optional[int]
    messages: List[ChatMessage] = field(default_factory=list)
    vector_store_id: Optional[str] = None
    previous_response_id: Optional[str] = None  # For stateful multi-turn
    company_name: Optional[str] = None
    cnpj_cia: Optional[str] = None
    doc_list: str = "(nenhum documento indexado)"
    created_at: str = ""

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.utcnow().isoformat()


class RAGService:
    """
    Service for RAG-based chat about ALL company documents.

    Features:
    - Vector Store por empresa (cnpj_cia) — PDFs indexados com atributos por arquivo
    - file_search com max_num_results=20 para raciocínio multi-step
    - web_search para consultas regulatórias externas
    - Temporal awareness: DT_REFER citado em cada resposta, alertas históricos
    - Stateful multi-turn context via previous_response_id
    - System prompt com lista de documentos disponíveis por empresa
    """

    SYSTEM_PROMPT_TEMPLATE = """Você é um assistente especializado em documentos de {company_name}.

Data de hoje: {today}

Documentos disponíveis:
{doc_list}

RACIOCÍNIO MULTI-ETAPA (OBRIGATÓRIO):
1. Para perguntas sobre evolução ou comparação entre períodos: realize buscas SEPARADAS para cada período relevante antes de sintetizar.
2. Priorize o documento mais recente, mas sempre cite o DT_REFER de cada informação.
3. Se não encontrar a informação em uma busca, tente reformular a query e buscar novamente.

REGRAS INEGOCIÁVEIS:
1. Responda SEMPRE em português brasileiro (PT-BR).
2. NUNCA invente dados. Se não estiver nos documentos: "Não encontrei essa informação nos documentos disponíveis."
3. Cite sempre: tipo do documento, DT_REFER e versão. Ex: "FRE 2024-12-31 v1, Item 7.3"
4. Documentos com mais de 12 meses: avise "⚠️ Esta informação é de [ano] — verifique se há versão mais recente."
5. Use file_search para documentos internos. Use web_search APENAS para normas regulatórias externas (Resolução CVM, normas IASB, etc.) ou quando não encontrar nos documentos.
6. Seja objetivo e preciso. Não especule além do que está nos documentos.

Ao citar trechos, reproduza com fidelidade e indique claramente que é uma citação."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        logger: Optional[logging.Logger] = None
    ):
        self.settings = get_settings()
        self.api_key = api_key or self.settings.openai_api_key
        self.logger = logger or logging.getLogger(__name__)
        self._client: Optional[AsyncOpenAI] = None

        # In-memory session store (sessions are ephemeral)
        self.sessions: Dict[str, ChatSession] = {}

        # document_id → vector_store_id mapping (legacy)
        self.vector_stores: Dict[str, str] = {}

        # cnpj_cia → vector_store_id mapping (carregado do DB ao iniciar)
        self.company_stores: Dict[str, str] = {}

        # Consolidated vector store (legacy fallback)
        self.consolidated_vector_store_id: Optional[str] = None

    def set_api_key(self, api_key: str):
        """Set API key."""
        self.api_key = api_key
        self._client = None

    @property
    def client(self) -> AsyncOpenAI:
        """Get AsyncOpenAI client."""
        if not self.api_key:
            raise ValueError("API key not set. Configure FRE_OPENAI_API_KEY em .env")

        if self._client is None:
            self._client = AsyncOpenAI(api_key=self.api_key)

        return self._client

    # =========================================================================
    # Startup: carregar VS do DB
    # =========================================================================

    async def load_company_stores_from_db(self, db_session) -> None:
        """Carrega mapeamento cnpj_cia → vs_id do DB ao iniciar."""
        from database.models import VectorStoreRef
        from sqlalchemy import select

        try:
            result = await db_session.execute(
                select(VectorStoreRef).where(
                    VectorStoreRef.cnpj_cia.isnot(None),
                    VectorStoreRef.status == "active"
                )
            )
            for ref in result.scalars().all():
                self.company_stores[ref.cnpj_cia] = ref.vector_store_id
            self.logger.info(f"Loaded {len(self.company_stores)} company VS from DB")
        except Exception as e:
            self.logger.warning(f"Could not load company stores from DB: {e}")

    # =========================================================================
    # Status: verificar novos docs
    # =========================================================================

    async def check_new_docs(
        self,
        cnpj_cia: str,
        enet_local_path: Path,
        db_session
    ) -> Dict:
        """Verifica quantos arquivos locais ainda não foram indexados."""
        from database.models import VectorStoreRef
        from sqlalchemy import select

        cnpj_slug_val = _cnpj_slug(cnpj_cia)
        index_path = Path(enet_local_path) / cnpj_slug_val / "index.json"

        if not index_path.exists():
            return {"has_vs": False, "indexed_count": 0, "new_count": 0}

        try:
            index_data = json.loads(index_path.read_text(encoding="utf-8"))
        except Exception:
            return {"has_vs": False, "indexed_count": 0, "new_count": 0}

        available = {f["filename"] for f in index_data}

        ref = (await db_session.execute(
            select(VectorStoreRef).where(VectorStoreRef.cnpj_cia == cnpj_cia)
        )).scalar_one_or_none()

        if not ref:
            return {"has_vs": False, "indexed_count": 0, "new_count": len(available)}

        indexed = set(ref.indexed_files or [])
        new_files = available - indexed

        return {
            "has_vs": True,
            "vs_id": ref.vector_store_id,
            "indexed_count": len(indexed),
            "new_count": len(new_files),
        }

    # =========================================================================
    # Indexação: index_company_documents (SSE async generator)
    # =========================================================================

    async def index_company_documents(
        self,
        cnpj_cia: str,
        company_name: str,
        enet_local_path: Path,
        new_only: bool = False
    ) -> AsyncGenerator[str, None]:
        """
        Indexa PDFs de uma empresa no Vector Store da OpenAI.
        Usa atributos por arquivo para filtros por tipo/data.
        Yields SSE events de progresso.
        """
        from database.models import VectorStoreRef
        from database import get_async_engine, get_async_session_factory
        from sqlalchemy import select

        settings = get_settings()
        engine = get_async_engine(str(settings.db_path))
        factory = get_async_session_factory(engine)

        cnpj_slug_val = _cnpj_slug(cnpj_cia)
        company_path = Path(enet_local_path) / cnpj_slug_val
        index_path = company_path / "index.json"

        if not index_path.exists():
            yield f"data: {json.dumps({'status': 'error', 'detail': 'index.json não encontrado para esta empresa'})}\n\n"
            return

        try:
            index_data = json.loads(index_path.read_text(encoding="utf-8"))
        except Exception as e:
            yield f"data: {json.dumps({'status': 'error', 'detail': f'Erro ao ler index.json: {e}'})}\n\n"
            return

        # Carrega ref existente do DB
        already_indexed: set = set()
        vs_id: Optional[str] = None

        async with factory() as session:
            result = await session.execute(
                select(VectorStoreRef).where(VectorStoreRef.cnpj_cia == cnpj_cia)
            )
            existing_ref = result.scalar_one_or_none()
            if existing_ref:
                already_indexed = set(existing_ref.indexed_files or [])
                vs_id = existing_ref.vector_store_id

        # Filtra arquivos a indexar
        if new_only:
            to_index = [f for f in index_data if f.get("filename") not in already_indexed]
        else:
            to_index = list(index_data)

        total = len(to_index)
        yield f"data: {json.dumps({'status': 'start', 'total': total})}\n\n"

        if total == 0:
            yield f"data: {json.dumps({'status': 'done', 'vs_id': vs_id, 'indexed': 0})}\n\n"
            return

        # Cria VS se não existe
        if not vs_id:
            try:
                store = await self.client.vector_stores.create(
                    name=f"company_{cnpj_slug_val}",
                    metadata={
                        "cnpj_cia": cnpj_cia,
                        "company_name": company_name,
                        "embedding_model": self.settings.openai_embedding_model,
                    }
                )
                vs_id = store.id
                self.logger.info(f"Vector store criado: {vs_id} para {cnpj_cia}")
            except Exception as e:
                yield f"data: {json.dumps({'status': 'error', 'detail': f'Erro ao criar Vector Store: {e}'})}\n\n"
                return

        newly_indexed: List[str] = []

        for i, doc in enumerate(to_index):
            filename = doc.get("filename", "")
            pdf_path = company_path / filename

            if not pdf_path.exists():
                yield f"data: {json.dumps({'done': i + 1, 'total': total, 'file': filename, 'skipped': True})}\n\n"
                continue

            try:
                text = await self._extract_pdf_text(pdf_path)

                dt_refer = doc.get("dt_refer", "")
                tipo_doc = doc.get("tipo_doc", "")
                header = (
                    f"EMPRESA: {company_name}\n"
                    f"CNPJ: {cnpj_cia}\n"
                    f"TIPO: {tipo_doc}\n"
                    f"DT_REFER: {dt_refer}\n"
                    f"ARQUIVO: {filename}\n"
                    f"{'=' * 60}\n\n"
                )
                content = (header + text).encode("utf-8")

                uploaded = await self.client.files.create(
                    file=(filename.replace(".pdf", ".txt"), io.BytesIO(content), "text/plain"),
                    purpose="assistants"
                )

                dt_ts = float(self._dt_to_timestamp(dt_refer))
                await self.client.vector_stores.files.create(
                    vector_store_id=vs_id,
                    file_id=uploaded.id,
                    attributes={
                        "tipo_doc": tipo_doc,
                        "dt_refer": dt_refer,
                        "dt_refer_ts": dt_ts,
                        "cnpj_cia": cnpj_cia,
                    }
                )

                newly_indexed.append(filename)

            except Exception as e:
                self.logger.error(f"Erro ao indexar {filename}: {e}")

            yield f"data: {json.dumps({'done': i + 1, 'total': total, 'file': filename})}\n\n"

        # Persiste no DB
        all_indexed = list(already_indexed | set(newly_indexed))
        async with factory() as session:
            result = await session.execute(
                select(VectorStoreRef).where(VectorStoreRef.cnpj_cia == cnpj_cia)
            )
            ref = result.scalar_one_or_none()

            if ref:
                ref.indexed_files = all_indexed
                ref.file_count = len(all_indexed)
                ref.last_used_at = datetime.utcnow()
            else:
                session.add(VectorStoreRef(
                    cnpj_cia=cnpj_cia,
                    name=f"company_{cnpj_slug_val}",
                    vector_store_id=vs_id,
                    indexed_files=all_indexed,
                    file_count=len(all_indexed),
                    status="active",
                ))
            await session.commit()

        self.company_stores[cnpj_cia] = vs_id
        self.logger.info(f"Indexação concluída para {cnpj_cia}: {len(newly_indexed)} novos arquivos")

        yield f"data: {json.dumps({'status': 'done', 'vs_id': vs_id, 'indexed': len(newly_indexed)})}\n\n"

    # =========================================================================
    # Helpers
    # =========================================================================

    async def _extract_pdf_text(self, path: Path) -> str:
        """Extrai texto de um PDF usando PyMuPDF."""
        def _read():
            import fitz
            doc = fitz.open(str(path))
            text = "\n\n".join(page.get_text() for page in doc)
            doc.close()
            return text[:400_000]  # ~400KB limit

        return await asyncio.to_thread(_read)

    def _dt_to_timestamp(self, dt_str: str) -> int:
        """Converte 'YYYY-MM-DD' para unix timestamp."""
        try:
            return int(datetime.strptime(dt_str, "%Y-%m-%d").timestamp())
        except Exception:
            return 0

    def _is_historical(self, dt_refer: str) -> bool:
        """Check if a date is historical (older than 1 year)."""
        try:
            ref_date = datetime.strptime(dt_refer, "%Y-%m-%d")
            return (datetime.utcnow() - ref_date).days > 365
        except Exception:
            return False

    # =========================================================================
    # Session management
    # =========================================================================

    def create_session(
        self,
        cnpj_cia: Optional[str] = None,
        document_id: Optional[str] = None,
        dt_refer: Optional[str] = None,
        versao: Optional[int] = None,
        vector_store_id: Optional[str] = None,
        company_name: Optional[str] = None,
    ) -> ChatSession:
        """Create a new chat session."""
        session_id = str(uuid.uuid4())

        # Resolve VS: empresa > documento específico > legacy
        resolved_store = (
            self.company_stores.get(cnpj_cia or "")
            or vector_store_id
            or self.vector_stores.get(document_id or "")
            or self.consolidated_vector_store_id
        )

        # Monta lista de docs disponíveis para o system prompt
        doc_list = "(nenhum documento indexado)"
        if cnpj_cia:
            try:
                cnpj_slug_val = _cnpj_slug(cnpj_cia)
                index_path = self.settings.base_dir / "enet_local" / cnpj_slug_val / "index.json"
                if index_path.exists():
                    index_data = json.loads(index_path.read_text(encoding="utf-8"))
                    doc_list = "\n".join(
                        f"- {d.get('tipo_doc', '?')} {d.get('dt_refer', '?')} ({d.get('filename', '?')})"
                        for d in sorted(index_data, key=lambda x: x.get("dt_refer", ""), reverse=True)
                    ) or doc_list
            except Exception as e:
                self.logger.debug(f"Não foi possível carregar index.json para {cnpj_cia}: {e}")

        session = ChatSession(
            session_id=session_id,
            cnpj_cia=cnpj_cia,
            document_id=document_id,
            dt_refer=dt_refer,
            versao=versao,
            vector_store_id=resolved_store,
            company_name=company_name,
            doc_list=doc_list,
        )

        self.sessions[session_id] = session
        self.logger.info(
            f"Chat session criada: {session_id} (store={resolved_store}, cnpj={cnpj_cia})"
        )
        return session

    def get_session(self, session_id: str) -> Optional[ChatSession]:
        """Get a chat session by ID."""
        return self.sessions.get(session_id)

    def _build_tools(self, session: ChatSession) -> List[Dict]:
        """Build tools list for the Responses API call."""
        tools: List[Dict] = []

        if session.vector_store_id:
            tools.append({
                "type": "file_search",
                "vector_store_ids": [session.vector_store_id],
                "max_num_results": 20,
            })

        tools.append({
            "type": "web_search_preview",
            "user_location": {"type": "approximate", "country": "BR"}
        })

        return tools

    def _system_prompt(self, session: ChatSession) -> str:
        return self.SYSTEM_PROMPT_TEMPLATE.format(
            company_name=session.company_name or "empresas abertas brasileiras",
            today=datetime.utcnow().strftime("%Y-%m-%d"),
            doc_list=session.doc_list,
        )

    def _extract_sources(
        self,
        response: Any,
        dt_refer: str,
        versao: int
    ) -> List[Source]:
        """Extract file citations from the response output."""
        sources: List[Source] = []

        try:
            for item in getattr(response, "output", []):
                for content in getattr(item, "content", []):
                    for annotation in getattr(content, "annotations", []):
                        if getattr(annotation, "type", "") == "file_citation":
                            cite = annotation.file_citation
                            quote = getattr(cite, "quote", "")
                            match = re.search(r"#\s*([\d.]+)", quote)
                            item_id = match.group(1) if match else "N/A"
                            sources.append(Source(
                                item_id=item_id,
                                dt_refer=dt_refer,
                                versao=versao,
                                text_snippet=quote[:200],
                                is_historical=self._is_historical(dt_refer)
                            ))
        except Exception as e:
            self.logger.debug(f"Source extraction error: {e}")

        return sources

    def _extract_web_sources(self, response: Any) -> List[Dict]:
        """Extract URL citations from the response output."""
        web_sources: List[Dict] = []

        try:
            for item in getattr(response, "output", []):
                for content in getattr(item, "content", []):
                    for annotation in getattr(content, "annotations", []):
                        if getattr(annotation, "type", "") == "url_citation":
                            cite = annotation.url_citation
                            web_sources.append({
                                "url": getattr(cite, "url", ""),
                                "title": getattr(cite, "title", ""),
                                "snippet": getattr(cite, "snippet", "")[:200]
                            })
        except Exception as e:
            self.logger.debug(f"Web source extraction error: {e}")

        return web_sources

    # =========================================================================
    # Chat
    # =========================================================================

    async def chat(
        self,
        session_id: str,
        user_message: str
    ) -> ChatMessage:
        """
        Send a message and get a grounded response.

        Uses previous_response_id for stateful multi-turn context.
        """
        session = self.get_session(session_id)
        if not session:
            raise ValueError(f"Session not found: {session_id}")

        user_msg = ChatMessage(role="user", content=user_message)
        session.messages.append(user_msg)

        tools = self._build_tools(session)
        system_prompt = self._system_prompt(session)

        try:
            from services.evaluation_engine import _parse_model
            base_model, reasoning = _parse_model(self.settings.openai_model)
            call_kwargs: Dict[str, Any] = {
                "model": base_model,
                "input": [{"role": "user", "content": user_message}],
                "instructions": system_prompt,
            }

            if reasoning:
                call_kwargs["reasoning"] = reasoning

            if tools:
                call_kwargs["tools"] = tools

            if session.previous_response_id:
                call_kwargs["previous_response_id"] = session.previous_response_id

            response = await self.client.responses.create(**call_kwargs)

            session.previous_response_id = response.id
            response_text = response.output_text

            # Extrai uso de tokens
            usage = getattr(response, "usage", None)
            input_tok = getattr(usage, "input_tokens", 0) or 0
            output_tok = getattr(usage, "output_tokens", 0) or 0

            sources = self._extract_sources(
                response,
                session.dt_refer or "",
                session.versao or 0
            )
            web_sources = self._extract_web_sources(response)

            historical = [s for s in sources if s.is_historical]
            if historical:
                years = ", ".join(sorted({s.dt_refer[:4] for s in historical}))
                response_text += (
                    f"\n\n⚠️ **Nota:** Esta resposta inclui informações de documentos "
                    f"históricos ({years}). Verifique se há versões mais recentes."
                )

            assistant_msg = ChatMessage(
                role="assistant",
                content=response_text,
                sources=sources,
                web_sources=web_sources
            )

            session.messages.append(assistant_msg)

            # Persiste uso de tokens no DB (fire-and-forget)
            asyncio.create_task(self._save_chat_usage(
                session_id=session_id,
                cnpj_cia=session.cnpj_cia,
                model=base_model,
                input_tokens=input_tok,
                output_tokens=output_tok,
                content=response_text,
                sources=[s.to_dict() for s in sources],
            ))

            self.logger.info(
                f"Chat [{session_id}]: {len(response_text)} chars, "
                f"{len(sources)} doc sources, {len(web_sources)} web sources, "
                f"tokens={input_tok}in/{output_tok}out"
            )

            return assistant_msg

        except Exception as e:
            self.logger.error(f"Chat error [{session_id}]: {e}")
            error_msg = ChatMessage(
                role="assistant",
                content=f"Desculpe, ocorreu um erro ao processar sua pergunta: {str(e)}"
            )
            session.messages.append(error_msg)
            return error_msg

    async def _save_chat_usage(
        self,
        session_id: str,
        cnpj_cia: Optional[str],
        model: str,
        input_tokens: int,
        output_tokens: int,
        content: str,
        sources: List[Dict],
    ) -> None:
        """Persiste uso de tokens da resposta RAG no banco de dados."""
        try:
            from database.models import ChatMessage as ChatMessageDB
            from database import get_async_engine, get_async_session_factory

            settings = get_settings()
            engine = get_async_engine(str(settings.db_path))
            factory = get_async_session_factory(engine)

            async with factory() as db:
                db.add(ChatMessageDB(
                    session_id=session_id,
                    role="assistant",
                    content=content[:4000],  # trunca para não inflar o DB
                    sources=sources,
                    tokens_used=input_tokens + output_tokens,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    model_used=model,
                    cnpj_cia=cnpj_cia,
                ))
                await db.commit()
        except Exception as e:
            self.logger.warning(f"Não foi possível salvar uso de tokens RAG: {e}")

    def get_chat_history(self, session_id: str) -> List[Dict]:
        """Get formatted chat history for a session."""
        session = self.get_session(session_id)
        if not session:
            return []
        return [msg.to_dict() for msg in session.messages]

    def clear_session(self, session_id: str):
        """Remove a chat session."""
        if session_id in self.sessions:
            del self.sessions[session_id]
            self.logger.info(f"Session cleared: {session_id}")

    # =========================================================================
    # Legacy: create_vector_store (mantido para compatibilidade)
    # =========================================================================

    async def create_vector_store(
        self,
        document_id: str,
        dt_refer: str,
        versao: int,
        tipo_doc: str,
        content_chunks: List[Dict[str, str]]
    ) -> str:
        """Create or update a Vector Store for a document (legacy)."""
        self.logger.info(f"Creating Vector Store for {document_id} ({tipo_doc} {dt_refer} v{versao})")

        store = await self.client.vector_stores.create(
            name=f"{tipo_doc} {dt_refer} v{versao}",
            metadata={
                "document_id": document_id,
                "dt_refer": dt_refer,
                "versao": str(versao),
                "tipo_doc": tipo_doc,
            }
        )

        file_ids: List[str] = []
        for chunk in content_chunks:
            header = (
                f"# {chunk.get('item_id', 'N/A')} - {chunk.get('titulo', 'Sem título')}\n"
                f"**Tipo:** {tipo_doc}\n"
                f"**DT_REFER:** {dt_refer}\n"
                f"**Versão:** {versao}\n"
                f"**document_id:** {document_id}\n\n"
                "---\n\n"
            )
            body = chunk.get("content", "")
            file_bytes = (header + body).encode("utf-8")
            filename = f"{document_id}_{chunk.get('item_id', 'chunk')}.txt"
            uploaded = await self.client.files.create(
                file=(filename, io.BytesIO(file_bytes), "text/plain"),
                purpose="assistants"
            )
            file_ids.append(uploaded.id)

        if file_ids:
            batch = await self.client.vector_stores.file_batches.create(
                vector_store_id=store.id,
                file_ids=file_ids
            )
            batch_id = batch.id  # salva antes do loop (SDK bug: retrieve sobrescreve .id)
            for _ in range(60):
                batch = await self.client.vector_stores.file_batches.retrieve(
                    batch_id,
                    vector_store_id=store.id,
                )
                if batch.status in ("completed", "failed", "cancelled"):
                    break
                await asyncio.sleep(3)
            if batch.status == "failed":
                raise RuntimeError(f"Vector store batch failed for {document_id}.")

        self.vector_stores[document_id] = store.id
        return store.id


# =============================================================================
# Singleton Instance
# =============================================================================

_rag_service: Optional[RAGService] = None


def get_rag_service() -> RAGService:
    """Get or create the RAG service singleton."""
    global _rag_service
    if _rag_service is None:
        from utils import get_logger
        _rag_service = RAGService(logger=get_logger())
    return _rag_service
