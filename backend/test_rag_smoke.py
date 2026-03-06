"""
Smoke test para o pipeline RAG — end-to-end com OpenAI real.

Cria documentos de conteúdo 100% controlado, sobe num Vector Store
temporário, usa o RAGService do projeto para perguntas e verifica
as respostas. Faz cleanup completo ao final.

Uso:
    cd backend && source ../.venv/bin/activate && python test_rag_smoke.py
"""

import asyncio
import io
import sys
import logging

# Adiciona backend/ ao path para importar serviços do projeto
sys.path.insert(0, ".")

from openai import AsyncOpenAI
from config import get_settings
from services.rag_service import RAGService

# ---------------------------------------------------------------------------
# Documentos de teste (conteúdo 100% controlado)
# ---------------------------------------------------------------------------

DOCS = [
    (
        "FRE_2024-12-31.txt",
        """\
EMPRESA: ACME Tecnologia SA
CNPJ: 12.345.678/0001-90
TIPO: FRE
DT_REFER: 2024-12-31
============================================================

Receita líquida do exercício 2024: R$ 1,85 bilhões.
EBITDA 2024: R$ 420 milhões. Margem EBITDA: 22,7%.
CEO em 2024: João da Silva (nomeado em março de 2024).
Número de funcionários: 8.200 colaboradores.
Principal produto: plataforma SaaS de gestão empresarial.
Sede: São Paulo, SP. CNPJ: 12.345.678/0001-90.
Risco principal: concentração em 3 clientes que respondem por 45% da receita.
""",
    ),
    (
        "FRE_2023-12-31.txt",
        """\
EMPRESA: ACME Tecnologia SA
CNPJ: 12.345.678/0001-90
TIPO: FRE
DT_REFER: 2023-12-31
============================================================

Receita líquida do exercício 2023: R$ 1,50 bilhões.
EBITDA 2023: R$ 320 milhões. Margem EBITDA: 21,3%.
CEO em 2023: Maria Santos.
Número de funcionários: 7.100 colaboradores.
Evento relevante: aquisição da startup LogiAI por R$ 80 milhões em julho de 2023.
""",
    ),
    (
        "DFP_2024-12-31.txt",
        """\
EMPRESA: ACME Tecnologia SA
CNPJ: 12.345.678/0001-90
TIPO: DFP
DT_REFER: 2024-12-31
============================================================

Balanço Patrimonial em 31/12/2024:
Ativo total: R$ 5,2 bilhões.
Patrimônio líquido: R$ 2,8 bilhões.
Dívida bruta: R$ 1,1 bilhão. Dívida líquida: R$ 680 milhões.
Alavancagem (Dívida líquida/EBITDA): 1,6x.
Caixa e equivalentes: R$ 420 milhões.
""",
    ),
]

# ---------------------------------------------------------------------------
# Perguntas e termos esperados nas respostas
# ---------------------------------------------------------------------------

QUESTIONS = [
    ("Qual foi a receita líquida em 2024?", "1,85"),
    ("Como evoluiu o EBITDA de 2023 para 2024?", "320"),   # 320 → 420 (ambos devem aparecer)
    ("Quem era o CEO em 2023?", "maria santos"),
    ("Qual é a alavancagem da empresa?", "1,6"),
    ("Qual é o risco de concentração de clientes?", "45%"),
]

# ---------------------------------------------------------------------------
# Helpers de log
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.WARNING,  # silencia logs internos do projeto
    format="%(levelname)s %(name)s: %(message)s",
)

def header(text: str):
    print(f"\n{'=' * 60}")
    print(f"  {text}")
    print('=' * 60)

# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

async def main():
    settings = get_settings()
    if not settings.openai_api_key:
        print("ERRO: FRE_OPENAI_API_KEY não configurada. Crie um arquivo .env em backend/.")
        sys.exit(1)

    client = AsyncOpenAI(api_key=settings.openai_api_key)
    file_ids: list[str] = []
    vs_id: str | None = None

    try:
        # ------------------------------------------------------------------
        # 1. Upload dos 3 arquivos
        # ------------------------------------------------------------------
        header("1. Upload de arquivos")
        for name, content in DOCS:
            f = await client.files.create(
                file=(name, io.BytesIO(content.encode("utf-8")), "text/plain"),
                purpose="assistants",
            )
            file_ids.append(f.id)
            print(f"  Uploaded: {name} → {f.id}")

        # ------------------------------------------------------------------
        # 2. Cria Vector Store e adiciona arquivos em batch
        # ------------------------------------------------------------------
        header("2. Criando Vector Store")
        vs = await client.vector_stores.create(name="rag_smoke_test")
        vs_id = vs.id
        print(f"  VS criado: {vs_id}")

        batch = await client.vector_stores.file_batches.create(
            vector_store_id=vs_id,
            file_ids=file_ids,
        )
        batch_id = batch.id  # salva antes do loop (SDK bug: retrieve sobrescreve .id)
        print(f"  Batch {batch_id} — aguardando processamento...")

        # Polling até batch concluir (máx 60s)
        for attempt in range(20):
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
        # 3. Cria sessão RAG com o VS temporário
        # ------------------------------------------------------------------
        header("3. Criando sessão RAG")
        rag = RAGService()
        session = rag.create_session(
            vector_store_id=vs_id,
            company_name="ACME Tecnologia SA",
        )
        print(f"  Sessão: {session.session_id}")
        print(f"  Vector Store resolvido: {session.vector_store_id}")

        # ------------------------------------------------------------------
        # 4. Perguntas e verificação de respostas
        # ------------------------------------------------------------------
        header("4. Perguntas de smoke test")
        passed = 0
        for i, (question, expected) in enumerate(QUESTIONS, 1):
            print(f"\n[{i}/{len(QUESTIONS)}] {question}")
            print(f"  Esperado conter: '{expected}'")

            msg = await rag.chat(session.session_id, question)
            content_lower = msg.content.lower()
            ok = expected.lower() in content_lower

            status = "PASS" if ok else "FAIL"
            if ok:
                passed += 1

            print(f"  {status}")
            # Mostra primeiros 400 chars da resposta
            preview = msg.content[:400].replace("\n", " ")
            print(f"  Resposta: {preview}{'...' if len(msg.content) > 400 else ''}")

            if msg.sources:
                print(f"  Citacoes: {len(msg.sources)} file_citation(s)")

        # ------------------------------------------------------------------
        # 5. Resultado final
        # ------------------------------------------------------------------
        header("5. Resultado")
        print(f"  {passed}/{len(QUESTIONS)} testes passaram")
        if passed == len(QUESTIONS):
            print("  Pipeline RAG OK.")
        elif passed >= len(QUESTIONS) - 1:
            print("  Pipeline RAG funcionando com pequenas falhas.")
        else:
            print("  ATENCAO: multiplas falhas — verificar pipeline.")

    finally:
        # ------------------------------------------------------------------
        # Cleanup: deleta VS e arquivos da OpenAI
        # ------------------------------------------------------------------
        header("Cleanup")
        if vs_id:
            try:
                await client.vector_stores.delete(vs_id)
                print(f"  Vector Store {vs_id} deletado.")
            except Exception as e:
                print(f"  Erro ao deletar VS: {e}")

        for fid in file_ids:
            try:
                await client.files.delete(fid)
                print(f"  Arquivo {fid} deletado.")
            except Exception as e:
                print(f"  Erro ao deletar arquivo {fid}: {e}")

        print("  Cleanup concluido.")


if __name__ == "__main__":
    asyncio.run(main())
