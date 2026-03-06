# CVM Analyzer

**Link Landing Page: https://landing-sage-iota-51.vercel.app/**

Ferramenta local para análise, avaliação de conformidade e comparação de documentos CVM — **FRE, DFP, FCA e IPE** — com base na **Resolução CVM nº 80**.

Sem autenticação, sem dados em nuvem. Tudo roda localmente na sua máquina.

---

## Funcionalidades

### Avaliação de Documentos
- Upload de PDF ou seleção de documento já baixado para análise completa
- Conformidade item a item com a **Resolução CVM 80 Anexo C** (21 seções, 156 itens)
- **Avaliação 3D**: combina o checklist normativo + seção atual do documento + até 5 versões históricas anteriores do mesmo tipo (detecção de padrões ao longo do tempo)
- Avaliação paralela de até 15 itens simultâneos via OpenAI Responses API
- Distinção entre itens **obrigatórios** e **facultativos** para emissores Categoria B
- Score por seção: `COMPLETO` · `PARCIAL` · `AUSENTE`
- Filtro por tipo de documento: FRE, DFP, FCA, IPE
- Exportação do relatório em **PDF** e **Excel (.xlsx)**

### Comparador de Versões (Diff)
- Comparação semântica entre dois documentos (modo local ou upload de PDFs)
- Diff textual por seção com destaque visual (adicionado / removido / modificado)
- Análise de impacto regulatório e de negócio gerada por IA
- Filtro por tipo de documento para selecionar apenas os documentos relevantes

### Chat RAG Multi-agêntico
- Chatbot fundamentado nos documentos baixados localmente por empresa
- **Vector Stores OpenAI por empresa** — busca semântica precisa, isolada por CNPJ
- Respostas com citação da fonte e data do documento
- Contexto de conversa persistido via `previous_response_id` (OpenAI Responses API)
- Seleção de modelo diretamente no chat

### Inicialização de Empresas
- Busca de companhias abertas via **CSVs de dados abertos da CVM** (zero dependência de scraping)
- Suporte a múltiplos tipos de documento: FRE, DFP, FCA, IPE
- Download automático de documentos via **Playwright (ENET)**
- Progresso em tempo real via **Server-Sent Events (SSE)**
- Seletor global de empresa no painel lateral — compartilhado em todas as páginas

### Arquivo Local
- Lista de todos os documentos baixados com visualização inline de PDF
- Metadados locais: tipo, data de referência, versão, tamanho
- Filtro por tipo de documento

### Custos
- Acompanhamento de uso de tokens e custo estimado por modelo, empresa e mês

---

## Stack Técnica

| Camada | Tecnologia |
|--------|-----------|
| Frontend | React 18 + Vite + Tailwind CSS v4 + Zustand + TanStack Query |
| Backend | FastAPI + SQLAlchemy 2.0 async (aiosqlite) + SQLite |
| IA | OpenAI Responses API — avaliação, diff semântico e RAG |
| RAG | OpenAI Vector Stores + File Search |
| PDF | PyMuPDF (fitz) + pdfplumber |
| DOCX | python-docx (parsing do checklist Anexo C) |
| Browser | Playwright (download de documentos ENET) |
| DB | SQLite local (zero configuração) |

---

## Estrutura do Projeto

```
cvm-analyser/
├── backend/
│   ├── api/
│   │   ├── routes_evaluation.py    # Avaliação de documentos (upload + IA)
│   │   ├── routes_diff.py          # Comparação semântica de versões
│   │   ├── routes_chat.py          # Chat RAG (Responses API + Vector Stores)
│   │   ├── routes_archive.py       # Arquivo local de documentos
│   │   ├── routes_settings.py      # Health check e configurações
│   │   └── routes_cvm.py           # Empresas, sync, download (CVM/ENET)
│   ├── database/
│   │   └── models.py               # SQLAlchemy async models
│   ├── services/
│   │   ├── checklist_parser.py     # Parser Anexo C (DOCX → 156 itens)
│   │   ├── evaluation_engine.py    # Motor de avaliação 3D (norma + histórico)
│   │   ├── rag_service.py          # Vector Store + chat com contexto persistido
│   │   ├── diff_engine.py          # Diff semântico com análise de impacto por IA
│   │   ├── cvm_service.py          # CSVs de dados abertos CVM (FRE/DFP/FCA/IPE)
│   │   ├── enet_scraper.py         # Playwright: download de documentos via ENET
│   │   └── pdf_extractor.py        # Extração de texto de PDFs
│   ├── utils/
│   │   ├── cache.py                # Cache de arquivos com TTL
│   │   ├── logger.py               # Logging centralizado
│   │   └── retry.py                # Retry com backoff exponencial
│   ├── config.py                   # Settings (pydantic-settings, prefixo FRE_)
│   ├── security.py                 # Usuário local fixo (sem autenticação)
│   ├── main.py                     # FastAPI app + startup
│   └── requirements.txt
├── frontend/
│   └── src/
│       ├── pages/
│       │   ├── EvaluationPage.jsx      # Avaliação de documentos
│       │   ├── DiffPage.jsx            # Comparador de versões
│       │   ├── ChatPage.jsx            # Chat RAG
│       │   ├── ArchivePage.jsx         # Arquivo de documentos
│       │   ├── InitializationPage.jsx  # Busca e download de empresas
│       │   ├── SettingsPage.jsx        # Configurações e health check
│       │   └── CostsPage.jsx           # Acompanhamento de custos
│       ├── components/
│       │   ├── Layout.jsx              # Sidebar + header
│       │   └── CompanySelector.jsx     # Seletor de empresa (dropdown global)
│       ├── store/
│       │   └── companyStore.js         # Estado global Zustand (empresa selecionada)
│       ├── context/
│       │   └── AuthContext.jsx         # Contexto de usuário local
│       ├── utils/
│       │   └── api.js                  # Wrapper apiFetch com tratamento de erros
│       ├── App.jsx
│       └── index.css                   # Design system (variáveis CSS + classes)
├── landing/                            # Landing page (React + Vite)
├── resol080consolid.docx               # Resolução CVM 80 consolidada (fonte do checklist)
├── Relação de itens facultativos - Categoria B.docx
├── start.sh                            # Script de produção (build + uvicorn)
└── .gitignore
```

---

## Instalação e Execução

### Pré-requisitos

- Python 3.11+
- Node.js 18+
- Chave de API OpenAI com acesso às APIs de **Responses**, **Files** e **Vector Stores**
- Playwright (para download de documentos via ENET)

### 1. Clone o repositório

```bash
git clone https://github.com/Appa019/cvm-analyser.git
cd cvm-analyser
```

### 2. Configure as variáveis de ambiente

Crie um arquivo `.env` na raiz do projeto:

```bash
# .env
FRE_OPENAI_API_KEY=sk-...
FRE_OPENAI_MODEL=gpt-4o-mini
```

### 3. Backend

```bash
# Criar virtualenv
python -m venv .venv
source .venv/bin/activate       # Linux/macOS
# .venv\Scripts\activate        # Windows

# Instalar dependências
pip install -r backend/requirements.txt

# Instalar browser para Playwright
playwright install chromium

# Iniciar servidor
cd backend
uvicorn main:app --reload --port 8000
```

Backend disponível em `http://localhost:8000`.
Documentação interativa: `http://localhost:8000/docs`

### 4. Frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend disponível em `http://localhost:5173` (proxy configurado para `:8000`).

### 5. Landing page (opcional)

```bash
cd landing
npm install
npm run dev
```

---

## Variáveis de Ambiente

Todas as variáveis usam o prefixo `FRE_` (lidas automaticamente por pydantic-settings).

| Variável | Obrigatório | Padrão | Descrição |
|----------|-------------|--------|-----------|
| `FRE_OPENAI_API_KEY` | ✅ | — | Chave de API OpenAI |
| `FRE_OPENAI_MODEL` | — | `gpt-4o-mini` | Modelo de linguagem padrão |
| `FRE_OPENAI_EMBEDDING_MODEL` | — | `text-embedding-3-large` | Modelo de embedding para RAG |
| `FRE_API_HOST` | — | `0.0.0.0` | Host do servidor FastAPI |
| `FRE_API_PORT` | — | `8000` | Porta do servidor FastAPI |
| `FRE_CACHE_MAX_SIZE_GB` | — | `5.0` | Tamanho máximo do cache de PDFs (GB) |
| `FRE_DEBUG` | — | `false` | Modo debug |
| `FRE_LOG_LEVEL` | — | `INFO` | Nível de log |

**Onde os dados ficam armazenados:**

| Sistema | Caminho |
|---------|---------|
| Linux/macOS | `~/.local/share/FREAnalyzer/` |
| Windows | `%LOCALAPPDATA%\FREAnalyzer\` |

Dentro desse diretório:

```
FREAnalyzer/
├── data/
│   └── fre_analyzer.db      # Banco SQLite (avaliações, histórico de chat, custos)
├── cache/                   # Cache de PDFs e CSVs da CVM
├── logs/                    # Logs da aplicação
└── enet_local/              # Documentos baixados por empresa
    └── {cnpj_slug}/
        ├── company.json     # Metadados da empresa
        ├── index.json       # Índice de documentos baixados
        └── *.pdf            # PDFs organizados por tipo e data
```

---

## Como Usar

### 1. Adicionar uma empresa

Acesse **Inicialização** na barra lateral:
1. Busque a empresa pelo nome (busca nos CSVs abertos da CVM)
2. Selecione os tipos de documento desejados (FRE, DFP, FCA, IPE)
3. Clique em **Sincronizar** — o progresso aparece em tempo real via SSE
4. Os PDFs são baixados e indexados localmente

### 2. Avaliar conformidade

Acesse **Avaliação** na barra lateral:
1. Selecione a empresa no dropdown do painel lateral
2. Escolha um documento local ou faça upload de um PDF
3. Filtre por tipo (FRE/DFP/FCA/IPE) se necessário
4. Clique em **Avaliar** — a IA analisa os 156 itens do Anexo C em paralelo
5. Exporte o resultado em PDF ou Excel

### 3. Comparar versões

Acesse **Comparação** na barra lateral:
1. Selecione dois documentos locais (ou faça upload de dois PDFs)
2. Use o filtro de tipo para focar em FRE, DFP, FCA ou IPE
3. Clique em **Comparar** — o diff semântico é gerado com análise de impacto

### 4. Conversar com os documentos

Acesse **Chat** na barra lateral:
1. Selecione a empresa no dropdown
2. Faça perguntas em linguagem natural sobre os documentos da empresa
3. O sistema responde com base nos PDFs indexados, citando a fonte

---

## Checklist Resolução CVM 80

O arquivo `resol080consolid.docx` contém a Resolução CVM nº 80 consolidada, que é a base para toda a avaliação de conformidade.

O `checklist_parser.py` extrai automaticamente os **156 itens do Anexo C**, identificando:
- Seção e subseção de cada item
- Texto do requisito normativo
- Se o item é **facultativo** para emissores Categoria B (com base no arquivo `Relação de itens facultativos - Categoria B.docx`)

O checklist é **recarregado automaticamente a cada 7 dias** por uma task assíncrona em background.

---

## Desenvolvimento

```bash
# Terminal 1 — Backend com hot reload
cd backend && source ../.venv/bin/activate
uvicorn main:app --reload --port 8000

# Terminal 2 — Frontend com HMR
cd frontend && npm run dev
```

### Health check

```bash
curl http://localhost:8000/api/settings/health
# {"status": "ok", "api_key_configured": true, "version": "1.0.0"}
```

### Verificar configuração

```bash
cd backend && source ../.venv/bin/activate
python -c "from config import get_settings; s = get_settings(); print(s.base_dir, s.openai_model)"
```

---

## Dados CVM — Fontes

Os CSVs de documentos são baixados automaticamente dos dados abertos da CVM:

```
https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/{TIPO}/DADOS/{tipo_lower}_cia_aberta_{ano}.zip
```

Suporte a: **FRE**, **DFP**, **FCA**, **IPE** — atualizados semanalmente pela CVM.

---

## Licença

MIT
