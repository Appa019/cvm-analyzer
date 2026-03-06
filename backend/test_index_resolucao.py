"""
Indexação e smoke test da Resolução CVM 80 (resol080consolid.docx).

Fluxo:
  1. Extrai texto do DOCX (todos os parágrafos + tabelas)
  2. Sobe o conteúdo como arquivo texto no OpenAI
  3. Cria Vector Store temporário e adiciona o arquivo
  4. Usa o RAGService para fazer perguntas sobre a resolução
  5. Cleanup (deleta VS e arquivo da OpenAI)

Uso:
    cd backend && source ../.venv/bin/activate && python test_index_resolucao.py
"""

import asyncio
import io
import sys
import logging
from pathlib import Path

sys.path.insert(0, ".")

from docx import Document as DocxDocument
from openai import AsyncOpenAI
from config import get_settings
from services.rag_service import RAGService

# ---------------------------------------------------------------------------
# Caminho do DOCX
# ---------------------------------------------------------------------------

DOCX_PATH = Path(__file__).resolve().parent.parent / "resol080consolid.docx"

# ---------------------------------------------------------------------------
# Perguntas sobre a Resolução CVM 80
# ---------------------------------------------------------------------------

QUESTIONS = [
    (
        "Qual é o número desta resolução e qual órgão a emitiu?",
        "80",
    ),
    (
        "O que é o Formulário de Referência (FRE) e qual seu objetivo?",
        "formulário",
    ),
    (
        "Quais são as informações obrigatórias sobre remuneração dos administradores no FRE?",
        "remuneração",
    ),
    (
        "O que deve constar sobre fatores de risco no FRE?",
        "risco",
    ),
    (
        "Quais itens são facultativos para emissores registrados na Categoria B?",
        "categoria b",
    ),
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")


def header(text: str):
    print(f"\n{'=' * 60}")
    print(f"  {text}")
    print("=" * 60)


def extract_docx_text(path: Path) -> str:
    """Extrai todo o texto do DOCX: parágrafos + conteúdo das tabelas."""
    doc = DocxDocument(str(path))
    parts = []

    # Parágrafos normais
    for para in doc.paragraphs:
        txt = para.text.strip()
        if txt:
            parts.append(txt)

    # Conteúdo das tabelas
    for table in doc.tables:
        for row in table.rows:
            row_cells = [c.text.strip() for c in row.cells if c.text.strip()]
            if row_cells:
                parts.append(" | ".join(row_cells))

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

async def main():
    if not DOCX_PATH.exists():
        print(f"ERRO: Arquivo não encontrado: {DOCX_PATH}")
        sys.exit(1)

    settings = get_settings()
    if not settings.openai_api_key:
        print("ERRO: FRE_OPENAI_API_KEY não configurada.")
        sys.exit(1)

    client = AsyncOpenAI(api_key=settings.openai_api_key)
    file_id: str | None = None
    vs_id: str | None = None

    try:
        # ------------------------------------------------------------------
        # 1. Extrai texto do DOCX
        # ------------------------------------------------------------------
        header("1. Extraindo texto do DOCX")
        print(f"  Arquivo: {DOCX_PATH}")
        text = await asyncio.to_thread(extract_docx_text, DOCX_PATH)
        print(f"  Texto extraído: {len(text):,} caracteres")
        print(f"  Preview (primeiros 300 chars):")
        print(f"  {text[:300].replace(chr(10), ' ')}")

        # Prepend cabeçalho para contextualizar o documento
        content = (
            "DOCUMENTO: Resolução CVM nº 80\n"
            "TIPO: Resolução normativa — Formulário de Referência (FRE)\n"
            "ÓRGÃO: Comissão de Valores Mobiliários (CVM)\n"
            "CONTEÚDO: Anexo C — itens obrigatórios e facultativos do FRE\n"
            f"{'=' * 60}\n\n"
        ) + text

        # ------------------------------------------------------------------
        # 2. Upload do arquivo
        # ------------------------------------------------------------------
        header("2. Upload para OpenAI Files")
        f = await client.files.create(
            file=("resol080consolid.txt", io.BytesIO(content.encode("utf-8")), "text/plain"),
            purpose="assistants",
        )
        file_id = f.id
        print(f"  File ID: {file_id}")
        print(f"  Tamanho: {len(content):,} bytes")

        # ------------------------------------------------------------------
        # 3. Cria Vector Store e aguarda indexação
        # ------------------------------------------------------------------
        header("3. Criando Vector Store")
        vs = await client.vector_stores.create(
            name="resol080_smoke_test",
            metadata={"source": "resol080consolid.docx", "tipo": "normativo"},
        )
        vs_id = vs.id
        print(f"  VS ID: {vs_id}")

        batch = await client.vector_stores.file_batches.create(
            vector_store_id=vs_id,
            file_ids=[file_id],
        )
        batch_id = batch.id  # salva antes do loop (SDK bug: retrieve sobrescreve .id)
        print(f"  Batch {batch_id} — aguardando indexação...")

        for _ in range(20):
            batch = await client.vector_stores.file_batches.retrieve(
                batch_id,
                vector_store_id=vs_id,
            )
            if batch.status in ("completed", "failed", "cancelled"):
                break
            await asyncio.sleep(3)

        print(f"  Batch status: {batch.status}")
        if batch.status != "completed":
            print(f"ERRO: batch terminou com status '{batch.status}'. Abortando.")
            return

        # ------------------------------------------------------------------
        # 4. Sessão RAG e perguntas
        # ------------------------------------------------------------------
        header("4. Sessão RAG — perguntas sobre a Resolução CVM 80")
        rag = RAGService()
        session = rag.create_session(
            vector_store_id=vs_id,
            company_name="Resolução CVM nº 80",
        )
        print(f"  Session: {session.session_id}")

        passed = 0
        for i, (question, expected) in enumerate(QUESTIONS, 1):
            print(f"\n[{i}/{len(QUESTIONS)}] {question}")
            print(f"  Esperado conter: '{expected}'")

            msg = await rag.chat(session.session_id, question)
            ok = expected.lower() in msg.content.lower()

            if ok:
                passed += 1
                print(f"  PASS")
            else:
                print(f"  FAIL")

            preview = msg.content[:500].replace("\n", " ")
            print(f"  Resposta: {preview}{'...' if len(msg.content) > 500 else ''}")

            if msg.sources:
                print(f"  Citacoes: {len(msg.sources)} file_citation(s)")

        # ------------------------------------------------------------------
        # 5. Resultado
        # ------------------------------------------------------------------
        header("5. Resultado")
        print(f"  {passed}/{len(QUESTIONS)} testes passaram")
        if passed == len(QUESTIONS):
            print("  Indexação da Resolução CVM 80 OK.")
        elif passed >= len(QUESTIONS) - 1:
            print("  Indexação funcionando — pequenas variações de linguagem.")
        else:
            print("  ATENCAO: múltiplas falhas — verificar conteúdo indexado.")

    finally:
        # ------------------------------------------------------------------
        # Cleanup
        # ------------------------------------------------------------------
        header("Cleanup")
        if vs_id:
            try:
                await client.vector_stores.delete(vs_id)
                print(f"  Vector Store {vs_id} deletado.")
            except Exception as e:
                print(f"  Erro ao deletar VS: {e}")
        if file_id:
            try:
                await client.files.delete(file_id)
                print(f"  Arquivo {file_id} deletado.")
            except Exception as e:
                print(f"  Erro ao deletar arquivo: {e}")
        print("  Cleanup concluído.")


if __name__ == "__main__":
    asyncio.run(main())
