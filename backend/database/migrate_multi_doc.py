"""
Migration: multi-doc support
============================

Renomeia tabelas antigas (fre_*) para nomes genéricos e adiciona
coluna tipo_doc onde necessário. Idempotente — pode ser executado
múltiplas vezes sem efeitos colaterais.

Executa automaticamente no startup via init_database().
"""

import logging
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

logger = logging.getLogger(__name__)


# (tabela_antiga, tabela_nova)
TABLE_RENAMES = [
    ("fre_documents",       "documents"),
    ("fre_items",           "document_items"),
    ("fre_evaluations",     "evaluations"),
    ("fre_item_evaluations","item_evaluations"),
]

# (tabela_nova, coluna, definição)
COLUMNS_TO_ADD = [
    ("documents",   "tipo_doc", "VARCHAR(10) DEFAULT 'FRE'"),
    ("evaluations", "tipo_doc", "VARCHAR(10) DEFAULT 'FRE'"),
    # token split columns (idempotente, já existiam antes)
    ("item_evaluations", "input_tokens",  "INTEGER DEFAULT 0"),
    ("item_evaluations", "output_tokens", "INTEGER DEFAULT 0"),
]


async def run_migration(conn: AsyncConnection) -> None:
    """Executa todas as migrations necessárias."""

    # 1. Renomear tabelas antigas se ainda existirem
    for old_name, new_name in TABLE_RENAMES:
        # Verifica se a tabela antiga existe
        result = await conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name=:n"),
            {"n": old_name},
        )
        if result.fetchone():
            # Verifica se a nova tabela ainda NÃO existe
            result2 = await conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='table' AND name=:n"),
                {"n": new_name},
            )
            if not result2.fetchone():
                logger.info(f"Migration: renomeando tabela {old_name} → {new_name}")
                await conn.execute(text(f"ALTER TABLE {old_name} RENAME TO {new_name}"))
            else:
                logger.info(f"Migration: tabela {old_name} existe mas {new_name} também — pulando rename")

    # 2. Adicionar colunas novas onde necessário (idempotente)
    for table, col, col_def in COLUMNS_TO_ADD:
        try:
            await conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {col_def}"))
            logger.info(f"Migration: adicionada coluna {table}.{col}")
        except Exception:
            pass  # Coluna já existe — normal
