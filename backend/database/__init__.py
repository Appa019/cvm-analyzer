"""
CVM Analyzer - Database Initialization
===================================

Cria e inicializa o banco SQLite. Executa migration de renomeação
das tabelas fre_* → nomes genéricos (multi-doc support).
"""

from .models import (
    Base,
    get_engine,
    get_async_engine,
    create_tables,
    get_session_factory,
    get_async_session_factory,
    # Novos nomes genéricos
    Document,
    DocumentItem,
    Evaluation,
    ItemEvaluation,
    # Aliases backward-compat
    FREDocument,
    FREItem,
    FREEvaluation,
    FREItemEvaluation,
    # Outros modelos
    DiffSession,
    DiffChange,
    ChatMessage,
    NormativeChecklist,
    VectorStoreRef,
    User,
    PasswordRecoveryCode,
    EmailVerificationCode,
    IssueResolution,
    DocumentSync,
)


async def _run_rag_migrations(conn) -> None:
    """Adiciona colunas novas ao vector_store_refs e chat_messages (idempotente)."""
    from sqlalchemy import text
    for table, col, typedef in [
        ("vector_store_refs", "cnpj_cia", "TEXT"),
        ("vector_store_refs", "indexed_files", "TEXT DEFAULT '[]'"),
        ("chat_messages", "input_tokens", "INTEGER DEFAULT 0"),
        ("chat_messages", "output_tokens", "INTEGER DEFAULT 0"),
        ("chat_messages", "model_used", "TEXT"),
        ("chat_messages", "cnpj_cia", "TEXT"),
    ]:
        try:
            await conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {typedef}"))
        except Exception:
            pass  # coluna já existe


async def init_database():
    """Initialize the database asynchronously."""
    from config import get_settings
    from .migrate_multi_doc import run_migration

    settings = get_settings()
    engine = get_async_engine(str(settings.db_path))

    async with engine.begin() as conn:
        # 1. Executar migration antes de criar tabelas (rename fre_* → generic)
        await run_migration(conn)

        # 2. Criar tabelas novas (idempotente — ignora as que já existem)
        await conn.run_sync(Base.metadata.create_all)

        # 3. Adicionar colunas novas ao vector_store_refs
        await _run_rag_migrations(conn)


__all__ = [
    "Base",
    "get_engine",
    "get_async_engine",
    "create_tables",
    "init_database",
    "get_session_factory",
    "get_async_session_factory",
    # Novos nomes
    "Document",
    "DocumentItem",
    "Evaluation",
    "ItemEvaluation",
    # Backward-compat
    "FREDocument",
    "FREItem",
    "FREEvaluation",
    "FREItemEvaluation",
    # Outros
    "DiffSession",
    "DiffChange",
    "ChatMessage",
    "NormativeChecklist",
    "VectorStoreRef",
    "User",
    "PasswordRecoveryCode",
    "EmailVerificationCode",
    "IssueResolution",
    "DocumentSync",
]
