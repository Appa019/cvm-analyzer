"""
CVM Analyzer - Database Models
===========================

SQLAlchemy models for SQLite database.
Stores document analyses, evaluations, and chat history.

Suporta múltiplos tipos de documento: FRE, DFP, FCA, IPE.
"""

from datetime import datetime, timezone
from typing import Optional, List
from sqlalchemy import (
    Column, Integer, String, Text, Float, Boolean,
    DateTime, ForeignKey, JSON, create_engine, Index
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker as async_sessionmaker

Base = declarative_base()


# =============================================================================
# Document Model (FRE, DFP, FCA, IPE)
# =============================================================================

class Document(Base):
    """
    Represents a single document downloaded from CVM (FRE, DFP, FCA or IPE).
    """
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, autoincrement=True)
    cnpj_cia = Column(String(20), nullable=False, index=True)
    dt_refer = Column(String(10), nullable=False)  # YYYY-MM-DD
    versao = Column(Integer, nullable=False)
    tipo_doc = Column(String(10), default="FRE")   # FRE, DFP, FCA, IPE
    link_doc = Column(Text, nullable=False)
    local_path = Column(Text, nullable=True)
    downloaded_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    index_extracted = Column(Boolean, default=False)
    total_items = Column(Integer, default=0)
    is_pinned = Column(Boolean, default=False)  # Keep in cache

    # Relationships
    items = relationship("DocumentItem", back_populates="document", cascade="all, delete-orphan")
    evaluations = relationship(
        "Evaluation",
        back_populates="document",
        cascade="all, delete-orphan",
        foreign_keys="[Evaluation.document_id]",
    )

    __table_args__ = (
        Index("idx_doc_cnpj_dt_versao", "cnpj_cia", "dt_refer", "versao", "tipo_doc"),
    )

    def __repr__(self):
        return f"<Document(cnpj={self.cnpj_cia}, tipo={self.tipo_doc}, dt_refer={self.dt_refer}, versao={self.versao})>"


# Backward-compat alias
FREDocument = Document


# =============================================================================
# DocumentItem Model (Index Items)
# =============================================================================

class DocumentItem(Base):
    """
    Represents an item from the document index (section/subsection).
    """
    __tablename__ = "document_items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=False)
    item_id = Column(String(20), nullable=False)
    titulo = Column(Text, nullable=False)
    nivel = Column(Integer, default=1)
    page_start = Column(Integer, nullable=True)
    page_end = Column(Integer, nullable=True)
    content_text = Column(Text, nullable=True)
    content_hash = Column(String(64), nullable=True)  # SHA256 for diff

    # Normative mapping
    normative_item_id = Column(String(20), nullable=True)
    mapping_confidence = Column(Float, default=1.0)
    mapping_needs_review = Column(Boolean, default=False)

    # Relationships
    document = relationship("Document", back_populates="items")
    evaluation = relationship("ItemEvaluation", back_populates="item", uselist=False)

    __table_args__ = (
        Index("idx_doc_items_doc_item", "document_id", "item_id"),
    )

    def __repr__(self):
        return f"<DocumentItem(item_id={self.item_id}, titulo={self.titulo[:30]}...)>"


# Backward-compat alias
FREItem = DocumentItem


# =============================================================================
# Evaluation Model (Analysis Session)
# =============================================================================

class Evaluation(Base):
    """
    Represents an evaluation session for a document (FRE, DFP, FCA or IPE).
    """
    __tablename__ = "evaluations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=True)
    document_id_str = Column(String(100), nullable=True, index=True)  # e.g., "fre_2024-12-31_v1"
    tipo_doc = Column(String(10), default="FRE")   # FRE, DFP, FCA, IPE
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    completed_at = Column(DateTime, nullable=True)
    status = Column(String(20), default="in_progress")  # in_progress, completed, failed

    # Summary scores
    total_score = Column(Float, default=0.0)  # None for qualitative (IPE)
    total_items = Column(Integer, default=0)
    complete_count = Column(Integer, default=0)
    partial_count = Column(Integer, default=0)
    absent_count = Column(Integer, default=0)
    critical_count = Column(Integer, default=0)

    # Metadata
    model_used = Column(String(50), nullable=True)
    is_uploaded = Column(Boolean, default=False)  # True = user uploaded unpublished doc
    original_filename = Column(String(255), nullable=True)
    dt_refer = Column(String(10), nullable=True)
    versao = Column(Integer, nullable=True)

    # Comparison reference
    compared_with_doc_id = Column(Integer, ForeignKey("documents.id"), nullable=True)

    # Relationships
    document = relationship("Document", back_populates="evaluations", foreign_keys=[document_id])
    item_evaluations = relationship("ItemEvaluation", back_populates="evaluation", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Evaluation(id={self.id}, tipo={self.tipo_doc}, score={self.total_score}, status={self.status})>"


# Backward-compat alias
FREEvaluation = Evaluation


# =============================================================================
# ItemEvaluation Model
# =============================================================================

class ItemEvaluation(Base):
    """
    Detailed evaluation for a single document item.
    """
    __tablename__ = "item_evaluations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    evaluation_id = Column(Integer, ForeignKey("evaluations.id"), nullable=False)
    item_id = Column(Integer, ForeignKey("document_items.id"), nullable=True)
    item_id_str = Column(String(20), nullable=True)  # e.g., "7.3" — for direct evaluations

    # Evaluation results
    status = Column(String(20), nullable=False)  # COMPLETO, PARCIAL, AUSENTE, CRITICO, QUALITATIVO
    score = Column(Float, default=0.0)
    peso = Column(Integer, default=1)  # Weight used
    titulo = Column(Text, nullable=True)

    # Issues and suggestions
    issues = Column(JSON, default=list)  # [{severity, description}, ...]
    missing_checklist = Column(JSON, default=list)  # [str, ...]
    suggestion = Column(Text, nullable=True)  # With {{placeholders}}
    reasoning = Column(Text, nullable=True)

    # AI metadata
    confidence = Column(Float, default=1.0)
    model_used = Column(String(50), nullable=True)
    tokens_used = Column(Integer, default=0)
    input_tokens = Column(Integer, default=0)
    output_tokens = Column(Integer, default=0)

    # Relationships
    evaluation = relationship("Evaluation", back_populates="item_evaluations")
    item = relationship("DocumentItem", back_populates="evaluation", foreign_keys=[item_id])

    def __repr__(self):
        return f"<ItemEvaluation(status={self.status}, score={self.score})>"


# Backward-compat alias
FREItemEvaluation = ItemEvaluation


# =============================================================================
# Diff Session Model
# =============================================================================

class DiffSession(Base):
    """
    Represents a diff comparison between two documents.
    """
    __tablename__ = "diff_sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    doc_a_id = Column(Integer, ForeignKey("documents.id"), nullable=False)
    doc_b_id = Column(Integer, ForeignKey("documents.id"), nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Summary
    total_changes = Column(Integer, default=0)
    added_count = Column(Integer, default=0)
    removed_count = Column(Integer, default=0)
    modified_count = Column(Integer, default=0)
    moved_count = Column(Integer, default=0)

    # Relationships
    doc_a = relationship("Document", foreign_keys=[doc_a_id])
    doc_b = relationship("Document", foreign_keys=[doc_b_id])
    changes = relationship("DiffChange", back_populates="session", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<DiffSession(doc_a={self.doc_a_id}, doc_b={self.doc_b_id}, changes={self.total_changes})>"


# =============================================================================
# Diff Change Model
# =============================================================================

class DiffChange(Base):
    """
    Represents a single change between two document items.
    """
    __tablename__ = "diff_changes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(Integer, ForeignKey("diff_sessions.id"), nullable=False)
    item_a_id = Column(Integer, ForeignKey("document_items.id"), nullable=True)
    item_b_id = Column(Integer, ForeignKey("document_items.id"), nullable=True)

    # Change info
    change_type = Column(String(20), nullable=False)  # added, removed, modified, moved
    item_id_str = Column(String(20), nullable=True)  # e.g., "7.3"

    # Content
    semantic_summary = Column(Text, nullable=True)
    technical_diff = Column(JSON, default=dict)  # {added: [], removed: [], ...}

    # Table changes
    has_table_changes = Column(Boolean, default=False)
    table_diff = Column(JSON, nullable=True)

    # Relationships
    session = relationship("DiffSession", back_populates="changes")
    item_a = relationship("DocumentItem", foreign_keys=[item_a_id])
    item_b = relationship("DocumentItem", foreign_keys=[item_b_id])

    def __repr__(self):
        return f"<DiffChange(type={self.change_type}, item={self.item_id_str})>"


# =============================================================================
# Chat Message Model
# =============================================================================

class ChatMessage(Base):
    """
    Stores chat messages for RAG conversations.
    """
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=True)
    session_id = Column(String(50), nullable=False)  # Group messages

    role = Column(String(20), nullable=False)  # user, assistant
    content = Column(Text, nullable=False)
    sources = Column(JSON, default=list)  # [{item_id, dt_refer, versao, text}, ...]

    # Web search results (if used)
    web_sources = Column(JSON, nullable=True)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    tokens_used = Column(Integer, default=0)
    input_tokens = Column(Integer, default=0)
    output_tokens = Column(Integer, default=0)
    model_used = Column(String(50), nullable=True)
    cnpj_cia = Column(String(20), nullable=True, index=True)

    def __repr__(self):
        return f"<ChatMessage(role={self.role}, session={self.session_id})>"


# =============================================================================
# Normative Checklist Model
# =============================================================================

class NormativeChecklist(Base):
    """
    Stores the parsed normative checklist from CVM regulations.
    """
    __tablename__ = "normative_checklist"

    id = Column(Integer, primary_key=True, autoincrement=True)
    item_id = Column(String(20), nullable=False, unique=True)
    titulo = Column(Text, nullable=False)
    nivel = Column(Integer, default=1)
    texto_normativo = Column(Text, nullable=True)
    peso = Column(Integer, default=1)
    tags = Column(JSON, default=list)

    parsed_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    source_url = Column(Text, nullable=True)
    is_facultativo = Column(Boolean, default=False)  # True = item is optional per Resolução 80

    def __repr__(self):
        return f"<NormativeChecklist(item_id={self.item_id}, peso={self.peso})>"


# =============================================================================
# Vector Store Reference Model
# =============================================================================

class VectorStoreRef(Base):
    """
    Tracks OpenAI Vector Stores created for documents.
    """
    __tablename__ = "vector_store_refs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=True)
    name = Column(String(100), nullable=False)
    vector_store_id = Column(String(100), nullable=False, unique=True)
    is_global = Column(Boolean, default=False)

    # Company-level VS fields
    cnpj_cia = Column(String(20), nullable=True, index=True)
    indexed_files = Column(JSON, default=list)  # list of indexed filenames

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    last_used_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    file_count = Column(Integer, default=0)
    status = Column(String(20), default="active")  # active, expired, deleted

    def __repr__(self):
        return f"<VectorStoreRef(name={self.name}, id={self.vector_store_id})>"


# =============================================================================
# User Model
# =============================================================================

class User(Base):
    """User account for authentication."""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String(255), nullable=False, unique=True, index=True)
    name = Column(String(255), nullable=False)
    hashed_password = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    last_login = Column(DateTime, nullable=True)

    def __repr__(self):
        return f"<User(email={self.email}, active={self.is_active})>"


# =============================================================================
# Password Recovery Code Model
# =============================================================================

class PasswordRecoveryCode(Base):
    """6-digit recovery code for password reset."""
    __tablename__ = "password_recovery_codes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String(255), nullable=False, index=True)
    code = Column(String(6), nullable=False)
    expires_at = Column(DateTime, nullable=False)
    used = Column(Boolean, default=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return f"<PasswordRecoveryCode(email={self.email}, used={self.used})>"


# =============================================================================
# Email Verification Code Model
# =============================================================================

class EmailVerificationCode(Base):
    """6-digit code sent on registration to verify email ownership."""
    __tablename__ = "email_verification_codes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String(255), nullable=False, index=True)
    code = Column(String(6), nullable=False)
    expires_at = Column(DateTime, nullable=False)
    used = Column(Boolean, default=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return f"<EmailVerificationCode(email={self.email}, used={self.used})>"


# =============================================================================
# Issue Resolution Model
# =============================================================================

class IssueResolution(Base):
    """
    Tracks which evaluation issues a user has marked as resolved.
    """
    __tablename__ = "issue_resolutions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    evaluation_id = Column(Integer, ForeignKey("evaluations.id"), nullable=False)
    item_id_str = Column(String(20), nullable=False)  # e.g., "7.3"
    issue_index = Column(Integer, nullable=False)  # Index in the issues array
    user_email = Column(String(255), nullable=False, index=True)
    resolved_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("idx_issue_resolution_eval_user", "evaluation_id", "user_email"),
    )

    def __repr__(self):
        return f"<IssueResolution(eval={self.evaluation_id}, item={self.item_id_str}, user={self.user_email})>"


# =============================================================================
# Document Sync Log Model
# =============================================================================

class DocumentSync(Base):
    """Log of automated syncs to check for new documents."""
    __tablename__ = "document_syncs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    synced_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    new_docs_found = Column(Integer, default=0)
    total_docs_checked = Column(Integer, default=0)
    errors = Column(JSON, default=list)  # List of error messages

    def __repr__(self):
        return f"<DocumentSync(at={self.synced_at}, new={self.new_docs_found})>"


# =============================================================================
# Database Session Factory
# =============================================================================

def get_engine(db_path: str):
    """Create SQLite engine (sync)."""
    return create_engine(f"sqlite:///{db_path}", echo=False)


_async_engines: dict = {}


def get_async_engine(db_path: str):
    """Create or return cached SQLite engine (async)."""
    if db_path not in _async_engines:
        _async_engines[db_path] = create_async_engine(
            f"sqlite+aiosqlite:///{db_path}",
            echo=False,
            pool_pre_ping=True,
        )
    return _async_engines[db_path]


def create_tables(engine):
    """Create all tables in database."""
    Base.metadata.create_all(engine)


def get_session_factory(engine):
    """Create session factory for sync operations."""
    return sessionmaker(bind=engine)


def get_async_session_factory(async_engine):
    """Create session factory for async operations."""
    return async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
