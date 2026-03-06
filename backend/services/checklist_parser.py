"""
CVM Analyzer - Checklist Parser Service
====================================

Parses Resolução CVM 80 Anexo C to extract a normative checklist with
facultative item flags for Categoria B emitters.

Sources (in priority order):
  1. Local resol080consolid.docx  — Table 1, structured, includes "X" flags
  2. PDF from CVM direct URL      — fallback when DOCX is absent
  3. Hardcoded skeleton            — last resort

Cache: 7-day TTL stored via CacheManager.
"""

import re
import json
import asyncio
from io import BytesIO
from pathlib import Path
from typing import Optional, List, Dict
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
import logging

import httpx
from docx import Document as DocxDocument
import fitz  # PyMuPDF

from config import get_settings
from utils import get_cache_manager, get_logger


# ─── Data models ──────────────────────────────────────────────────────────────

@dataclass
class ChecklistItem:
    """Represents a single normative item from Anexo C."""
    item_id: str
    titulo: str
    nivel: int
    texto_normativo: str
    peso: int              # 1 = baixo | 2 = médio | 3 = alto
    tags: List[str]
    is_facultativo: bool = False   # facultative for Categoria B
    parent_id: Optional[str] = None

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class NormativeChecklist:
    """Complete Resolução CVM 80 Anexo C checklist."""
    items: List[ChecklistItem]
    source_url: str
    parsed_at: str
    version: str = "2.0"

    def to_dict(self) -> Dict:
        return {
            "items": [item.to_dict() for item in self.items],
            "source_url": self.source_url,
            "parsed_at": self.parsed_at,
            "version": self.version,
        }

    def get_item(self, item_id: str) -> Optional[ChecklistItem]:
        for item in self.items:
            if item.item_id == item_id:
                return item
        return None

    def get_by_nivel(self, nivel: int) -> List[ChecklistItem]:
        return [item for item in self.items if item.nivel == nivel]


# ─── Parser service ───────────────────────────────────────────────────────────

class ChecklistParserService:
    """
    Parses Resolução CVM 80 Anexo C.

    Strategy:
    1. Use local resol080consolid.docx (Table 1) — primary, structured, reliable
    2. Download PDF from CVM direct URL if DOCX is missing
    3. Use hardcoded fallback skeleton as last resort

    Cache: 7-day TTL with file-mtime age check.
    """

    # Direct PDF URL (bypasses CVM HTML navigation)
    CVM_PDF_URL = (
        "https://conteudo.cvm.gov.br/export/sites/cvm/legislacao"
        "/resolucoes/anexos/001/resol080consolid.pdf"
    )

    # Candidate paths for the local DOCX (searched in order)
    LOCAL_DOCX_CANDIDATES = [
        # Project root (3 levels up from backend/services/)
        Path(__file__).resolve().parent.parent.parent / "resol080consolid.docx",
        # Placed inside backend/ directory
        Path(__file__).resolve().parent.parent / "resol080consolid.docx",
        # Placed alongside this file
        Path(__file__).resolve().parent / "resol080consolid.docx",
    ]

    CACHE_KEY = "normative/fre_checklist_v2.json"
    CACHE_TTL_DAYS = 7

    # Cache keys por tipo de documento
    CACHE_KEYS = {
        "FRE": "normative/fre_checklist_v2.json",
        "DFP": "normative/dfp_checklist_v1.json",
        "FCA": "normative/fca_checklist_v1.json",
    }

    # Nomes dos arquivos DOCX por tipo
    DOCX_FILENAMES = {
        "FRE": "resol080consolid.docx",
        "DFP": "checklist_dfp_rcvm80.docx",
        "FCA": "checklist_fca_rcvm80.docx",
    }

    # Matches item IDs like "1", "1.1", "10.5", etc. at the start of a line
    ITEM_RE = re.compile(r"^(\d+(?:\.\d+)*)\.?\s*[\t ]*(.{0,300})", re.DOTALL)

    HIGH_CRITICALITY = [
        "risco", "riscos", "contingência", "contingências",
        "litígio", "litígios", "relacionada", "relacionadas",
        "controladora", "controlada", "governança", "compliance",
        "auditoria", "controle", "controles", "capital",
        "remuneração", "administrador", "administradores",
    ]
    MEDIUM_CRITICALITY = [
        "atividade", "atividades", "negócio", "negócios",
        "econômico", "grupo", "assembleia", "valores",
        "mobiliário", "mobiliários", "comentário", "comentários",
    ]

    def __init__(self, logger: Optional[logging.Logger] = None):
        self.logger = logger or get_logger()
        self.cache = get_cache_manager()
        self.settings = get_settings()

    # ─── Weight / tag helpers ─────────────────────────────────────────────────

    def _weight(self, titulo: str, texto: str) -> int:
        combined = (titulo + " " + texto).lower()
        for kw in self.HIGH_CRITICALITY:
            if kw in combined:
                return 3
        for kw in self.MEDIUM_CRITICALITY:
            if kw in combined:
                return 2
        return 1

    def _tags(self, titulo: str, texto: str) -> List[str]:
        combined = (titulo + " " + texto).lower()
        mapping = {
            "risco": ["risco", "riscos"],
            "disclosure": ["divulgação", "disclosure"],
            "governança": ["governança", "conselho"],
            "financeiro": ["financeiro", "financeira", "capital"],
            "relacionadas": ["relacionada", "vinculada"],
            "controle": ["controle", "auditoria"],
            "remuneração": ["remuneração", "compensação"],
        }
        tags = []
        for tag, kws in mapping.items():
            if any(kw in combined for kw in kws):
                tags.append(tag)
        return tags

    def _parent_id(self, item_id: str) -> Optional[str]:
        parts = item_id.split(".")
        return ".".join(parts[:-1]) if len(parts) > 1 else None

    # ─── Local DOCX parsing ───────────────────────────────────────────────────

    def _find_local_docx(self) -> Optional[Path]:
        for path in self.LOCAL_DOCX_CANDIDATES:
            if path.exists():
                self.logger.info(f"Local DOCX found: {path}")
                return path
        return None

    def _parse_docx_table(self, docx_path: Path) -> List[ChecklistItem]:
        """
        Parse Anexo C from Table 1 of resol080consolid.docx.

        Table 1 structure:
          Row 0 (header): ["EMISSORES REGISTRADOS NAS CATEGORIAS 'A' E 'B'",
                           "Os campos assinalados com 'X' são facultativos..."]
          Subsequent rows:
            Col 0: item-ID + description (may be multi-line or span sub-items)
            Col 1: "X" when the item is optional for Categoria B
        """
        self.logger.info(f"Parsing DOCX table from {docx_path}")
        try:
            doc = DocxDocument(str(docx_path))
        except Exception as exc:
            self.logger.error(f"Cannot open DOCX: {exc}")
            return []

        if not doc.tables:
            self.logger.warning("No tables found in DOCX")
            return []

        table = doc.tables[0]  # Table 1 = Anexo C
        items: List[ChecklistItem] = []
        seen_ids: set = set()
        current: Optional[ChecklistItem] = None
        extra: List[str] = []

        def flush():
            nonlocal current, extra
            if current is None:
                return
            if extra:
                current.texto_normativo = " ".join(extra).strip()
                current.peso = self._weight(current.titulo, current.texto_normativo)
                current.tags = self._tags(current.titulo, current.texto_normativo)
            items.append(current)
            current = None
            extra = []

        def make_item(item_id: str, titulo: str, is_fac: bool) -> ChecklistItem:
            nivel = len(item_id.split("."))
            return ChecklistItem(
                item_id=item_id,
                titulo=titulo[:300].strip(),
                nivel=nivel,
                texto_normativo="",
                peso=self._weight(titulo, ""),
                tags=self._tags(titulo, ""),
                is_facultativo=is_fac,
                parent_id=self._parent_id(item_id),
            )

        for row in table.rows[1:]:  # skip header row
            col0 = row.cells[0].text.strip() if row.cells else ""
            col1 = row.cells[1].text.strip() if len(row.cells) > 1 else ""
            row_is_fac = col1.upper() == "X"

            if not col0:
                continue

            # A cell may contain multiple lines; some cells embed two items
            # (e.g. "20.\n20.1. Description...")
            lines = [l.strip() for l in col0.split("\n") if l.strip()]
            for line in lines:
                m = self.ITEM_RE.match(line)
                if m and m.group(1).replace(".", "").isdigit():
                    item_id = m.group(1).rstrip(".")
                    titulo_raw = m.group(2).strip()

                    if item_id in seen_ids:
                        # Duplicate ID (formatting artifact) — skip
                        continue

                    flush()
                    seen_ids.add(item_id)
                    # Only the first line of a multi-item cell carries the X flag
                    current = make_item(item_id, titulo_raw, row_is_fac)
                elif current is not None and line:
                    extra.append(line)

        flush()
        self.logger.info(f"Parsed {len(items)} items from DOCX table")
        return items

    # ─── PDF parsing ──────────────────────────────────────────────────────────

    async def _fetch_and_parse_pdf(self) -> List[ChecklistItem]:
        """Download PDF from CVM and extract Anexo C items."""
        self.logger.info(f"Downloading PDF: {self.CVM_PDF_URL}")
        try:
            async with httpx.AsyncClient(timeout=90, follow_redirects=True) as client:
                resp = await client.get(self.CVM_PDF_URL)
                resp.raise_for_status()
                pdf_bytes = resp.content
        except Exception as exc:
            self.logger.error(f"PDF download failed: {exc}")
            return []

        return self._parse_pdf_bytes(pdf_bytes)

    def _parse_pdf_bytes(self, pdf_bytes: bytes) -> List[ChecklistItem]:
        """Extract Anexo C items from raw PDF bytes using PyMuPDF."""
        try:
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            full_text = "\n".join(page.get_text("text") for page in doc)
            doc.close()
        except Exception as exc:
            self.logger.error(f"PDF text extraction failed: {exc}")
            return []

        # Isolate Anexo C section
        start_m = re.search(r"ANEXO\s+C\b", full_text, re.IGNORECASE)
        if not start_m:
            self.logger.warning("'ANEXO C' not found in PDF text")
            return []
        text = full_text[start_m.start():]
        stop_m = re.search(r"ANEXO\s+D\b", text, re.IGNORECASE)
        if stop_m:
            text = text[: stop_m.start()]

        # Noise lines to skip (page numbers, headers, etc.)
        NOISE = re.compile(
            r"^(\d{1,3}|CVM.*|Formulário de Referência.*|ANEXO C.*)$",
            re.IGNORECASE,
        )

        items: List[ChecklistItem] = []
        seen_ids: set = set()
        current: Optional[ChecklistItem] = None
        extra: List[str] = []

        def flush():
            nonlocal current, extra
            if current is None:
                return
            if extra:
                current.texto_normativo = " ".join(extra).strip()
                current.peso = self._weight(current.titulo, current.texto_normativo)
                current.tags = self._tags(current.titulo, current.texto_normativo)
            items.append(current)
            current = None
            extra = []

        for raw_line in text.split("\n"):
            line = raw_line.strip()
            if not line or NOISE.match(line):
                continue
            m = self.ITEM_RE.match(line)
            if m and m.group(1).replace(".", "").isdigit():
                item_id = m.group(1).rstrip(".")
                if item_id in seen_ids:
                    continue
                flush()
                seen_ids.add(item_id)
                titulo = m.group(2).strip()
                nivel = len(item_id.split("."))
                current = ChecklistItem(
                    item_id=item_id,
                    titulo=titulo[:300],
                    nivel=nivel,
                    texto_normativo="",
                    peso=1,
                    tags=[],
                    is_facultativo=False,  # PDF has no X column; use DOCX for flags
                    parent_id=self._parent_id(item_id),
                )
            elif current is not None and line:
                extra.append(line)

        flush()
        self.logger.info(f"Parsed {len(items)} items from PDF")
        return items

    # ─── Cache helpers ────────────────────────────────────────────────────────

    def _cache_is_stale(self, cached_path: str) -> bool:
        try:
            mtime = datetime.fromtimestamp(Path(cached_path).stat().st_mtime)
            return datetime.utcnow() - mtime > timedelta(days=self.CACHE_TTL_DAYS)
        except Exception:
            return True

    def _load_cache(self, cached_path: str) -> Optional[NormativeChecklist]:
        try:
            with open(cached_path, encoding="utf-8") as f:
                data = json.load(f)
            items = [ChecklistItem(**it) for it in data["items"]]
            return NormativeChecklist(
                items=items,
                source_url=data["source_url"],
                parsed_at=data["parsed_at"],
                version=data.get("version", "2.0"),
            )
        except Exception as exc:
            self.logger.warning(f"Cache read failed: {exc}")
            return None

    def _save_cache(self, checklist: NormativeChecklist) -> None:
        try:
            payload = json.dumps(checklist.to_dict(), ensure_ascii=False, indent=2)
            self.cache.put(self.CACHE_KEY, payload.encode("utf-8"), pinned=True)
            self.logger.info(f"Checklist cached ({len(checklist.items)} items)")
        except Exception as exc:
            self.logger.error(f"Failed to cache checklist: {exc}")

    # ─── Multi-doc helpers ────────────────────────────────────────────────────

    def _find_docx_by_filename(self, filename: str) -> Optional[Path]:
        """Procura arquivo DOCX nos candidatos padrão."""
        candidates = [
            Path(__file__).resolve().parent.parent.parent / filename,
            Path(__file__).resolve().parent.parent / filename,
            Path(__file__).resolve().parent / filename,
        ]
        for path in candidates:
            if path.exists():
                self.logger.info(f"DOCX encontrado: {path}")
                return path
        return None

    async def _parse_docx_by_filename(self, filename: str, tipo_doc: str) -> NormativeChecklist:
        """
        Carrega e parseia um DOCX genérico de checklist (DFP ou FCA).
        Se o DOCX não existir, usa fallback hardcoded por tipo.
        """
        cache_key = self.CACHE_KEYS.get(tipo_doc, f"normative/{tipo_doc.lower()}_checklist_v1.json")

        if not hasattr(self, '_force_refresh') or not self._force_refresh:
            cached_path = self.cache.get(cache_key)
            if cached_path and not self._cache_is_stale(cached_path):
                result = self._load_cache(cached_path)
                if result:
                    return result

        docx_path = self._find_docx_by_filename(filename)
        items: List[ChecklistItem] = []
        source_url = "fallback"

        if docx_path:
            items = self._parse_docx_table(docx_path)
            source_url = str(docx_path)
            self.logger.info(f"{tipo_doc}: {len(items)} itens do DOCX")
        else:
            self.logger.warning(f"DOCX não encontrado: {filename} — usando fallback hardcoded")
            if tipo_doc == "DFP":
                items = self._fallback_dfp_checklist()
            elif tipo_doc == "FCA":
                items = self._fallback_fca_checklist()
            source_url = "fallback"

        checklist = NormativeChecklist(
            items=items,
            source_url=source_url,
            parsed_at=datetime.utcnow().isoformat(),
        )

        try:
            payload = json.dumps(checklist.to_dict(), ensure_ascii=False, indent=2)
            self.cache.put(cache_key, payload.encode("utf-8"), pinned=True)
        except Exception as exc:
            self.logger.error(f"Falha ao salvar cache {tipo_doc}: {exc}")

        return checklist

    def _fallback_dfp_checklist(self) -> List[ChecklistItem]:
        """
        Checklist hardcoded para DFP (Demonstrações Financeiras Padronizadas)
        baseado na RCVM 80 e ITR/DFP CVM. Usado quando o DOCX não está disponível.
        """
        sections = [
            # (item_id, titulo, peso, is_facultativo)
            ("1",    "Balanço Patrimonial Ativo", 3, False),
            ("1.1",  "Ativo Circulante", 3, False),
            ("1.2",  "Ativo Não Circulante", 3, False),
            ("2",    "Balanço Patrimonial Passivo", 3, False),
            ("2.1",  "Passivo Circulante", 3, False),
            ("2.2",  "Passivo Não Circulante", 3, False),
            ("2.3",  "Patrimônio Líquido", 3, False),
            ("3",    "Demonstração do Resultado", 3, False),
            ("3.1",  "Receita de Venda de Bens e/ou Serviços", 3, False),
            ("3.2",  "Resultado Bruto", 3, False),
            ("3.3",  "Resultado Antes do Resultado Financeiro e dos Tributos", 3, False),
            ("3.4",  "Resultado Financeiro", 3, False),
            ("3.5",  "Resultado Antes dos Tributos sobre o Lucro", 3, False),
            ("3.6",  "Lucro/Prejuízo do Período", 3, False),
            ("4",    "Demonstração do Resultado Abrangente", 2, False),
            ("4.1",  "Lucro/Prejuízo Consolidado do Período", 2, False),
            ("4.2",  "Componentes dos Outros Resultados Abrangentes", 2, False),
            ("5",    "Demonstração do Fluxo de Caixa", 3, False),
            ("5.1",  "Caixa Líquido de Atividades Operacionais", 3, False),
            ("5.2",  "Caixa Líquido de Atividades de Investimento", 3, False),
            ("5.3",  "Caixa Líquido de Atividades de Financiamento", 3, False),
            ("5.4",  "Variação Cambial sobre Caixa e Equivalentes de Caixa", 2, False),
            ("5.5",  "Aumento/Redução de Caixa e Equivalentes", 3, False),
            ("6",    "Demonstração das Mutações do Patrimônio Líquido", 2, False),
            ("6.1",  "Capital Social Integralizado", 2, False),
            ("6.2",  "Reservas de Capital", 2, False),
            ("6.3",  "Reservas de Lucros", 2, False),
            ("6.4",  "Outros Resultados Abrangentes", 2, False),
            ("7",    "Demonstração do Valor Adicionado", 2, True),
            ("7.1",  "Receitas", 2, True),
            ("7.2",  "Insumos Adquiridos de Terceiros", 2, True),
            ("7.3",  "Valor Adicionado Bruto", 2, True),
            ("7.4",  "Distribuição do Valor Adicionado", 2, True),
            ("8",    "Notas Explicativas", 3, False),
            ("8.1",  "Contexto operacional e principais atividades", 3, False),
            ("8.2",  "Principais práticas contábeis adotadas", 3, False),
            ("8.3",  "Instrumentos financeiros e gestão de riscos", 3, False),
            ("8.4",  "Partes relacionadas — transações e saldos", 3, False),
            ("8.5",  "Contingências e provisões relevantes", 3, False),
            ("8.6",  "Composição do endividamento e covenants", 3, False),
            ("8.7",  "Eventos subsequentes relevantes", 2, False),
            ("8.8",  "Outras divulgações obrigatórias", 2, False),
            ("9",    "Relatório dos Auditores Independentes", 3, False),
            ("9.1",  "Opinião dos auditores (sem modificações ou qualificações)", 3, False),
            ("9.2",  "Parágrafo de ênfase ou outros assuntos", 2, False),
            ("9.3",  "Principais assuntos de auditoria (PAA)", 2, False),
        ]
        items = []
        for item_id, titulo, peso, is_fac in sections:
            nivel = len(item_id.split("."))
            items.append(ChecklistItem(
                item_id=item_id,
                titulo=titulo,
                nivel=nivel,
                texto_normativo=f"Conforme RCVM 80 e normas IASB/CPC, DFP item {item_id}.",
                peso=peso,
                tags=self._tags(titulo, ""),
                is_facultativo=is_fac,
                parent_id=self._parent_id(item_id),
            ))
        return items

    def _fallback_fca_checklist(self) -> List[ChecklistItem]:
        """
        Checklist hardcoded para FCA (Formulário Cadastral) conforme RCVM 80.
        Usado quando o DOCX não está disponível.
        """
        sections = [
            ("1",    "Identificação do Emissor", 2, False),
            ("1.1",  "Razão social e CNPJ", 2, False),
            ("1.2",  "Data de constituição e registro CVM", 2, False),
            ("1.3",  "Sede e endereço para correspondência", 2, False),
            ("1.4",  "Contatos do Diretor de Relações com Investidores (DRI)", 2, False),
            ("1.5",  "Auditor independente cadastrado na CVM", 2, False),
            ("2",    "Características da Emissão e dos Valores Mobiliários", 2, False),
            ("2.1",  "Espécie e quantidade de valores mobiliários", 2, False),
            ("2.2",  "Mercados onde os valores mobiliários são admitidos à negociação", 2, False),
            ("2.3",  "Código de negociação (ticker)", 2, False),
            ("3",    "Dados do Estatuto Social", 2, False),
            ("3.1",  "Objeto social", 2, False),
            ("3.2",  "Prazo de duração", 1, False),
            ("3.3",  "Data do último estatuto social arquivado", 2, False),
            ("4",    "Composição do Capital Social", 3, False),
            ("4.1",  "Quantidade de ações ordinárias", 3, False),
            ("4.2",  "Quantidade de ações preferenciais", 3, False),
            ("4.3",  "Percentual de free float", 3, False),
            ("5",    "Acionistas e Grupo de Controle", 3, False),
            ("5.1",  "Acionistas com participação superior a 5%", 3, False),
            ("5.2",  "Identificação do controlador ou grupo controlador", 3, False),
            ("6",    "Administradores e Conselho Fiscal", 2, False),
            ("6.1",  "Membros do Conselho de Administração", 2, False),
            ("6.2",  "Membros da Diretoria Executiva", 2, False),
            ("6.3",  "Membros do Conselho Fiscal (se instalado)", 2, True),
            ("7",    "Informações sobre Segmentos de Listagem", 2, False),
            ("7.1",  "Segmento de listagem (Novo Mercado, Nível 1, 2, etc.)", 2, False),
            ("7.2",  "Adesão a câmaras de arbitragem", 2, True),
            ("8",    "Declarações e Responsabilidades", 2, False),
            ("8.1",  "Declaração de veracidade e completude das informações", 2, False),
            ("8.2",  "Assinaturas dos responsáveis (Presidente e DRI)", 2, False),
        ]
        items = []
        for item_id, titulo, peso, is_fac in sections:
            nivel = len(item_id.split("."))
            items.append(ChecklistItem(
                item_id=item_id,
                titulo=titulo,
                nivel=nivel,
                texto_normativo=f"Conforme RCVM 80, Formulário Cadastral, item {item_id}.",
                peso=peso,
                tags=self._tags(titulo, ""),
                is_facultativo=is_fac,
                parent_id=self._parent_id(item_id),
            ))
        return items

    async def parse_checklist(self, tipo_doc: str, force_refresh: bool = False) -> NormativeChecklist:
        """
        Retorna checklist normativo para o tipo de documento informado.

        - FRE → Anexo C da RCVM 80 (resol080consolid.docx)
        - DFP → checklist_dfp_rcvm80.docx
        - FCA → checklist_fca_rcvm80.docx
        - IPE → checklist vazio (avaliação qualitativa livre)
        """
        if tipo_doc == "FRE":
            return await self.parse_anexo_c(force_refresh)
        elif tipo_doc in ("DFP", "FCA"):
            filename = self.DOCX_FILENAMES[tipo_doc]
            return await self._parse_docx_by_filename(filename, tipo_doc)
        else:
            # IPE e tipos desconhecidos: sem checklist fixo
            return NormativeChecklist(
                items=[],
                source_url="qualitative",
                parsed_at=datetime.utcnow().isoformat(),
            )

    # ─── Public API ───────────────────────────────────────────────────────────

    async def parse_anexo_c(self, force_refresh: bool = False) -> NormativeChecklist:
        """
        Return Anexo C checklist.

        Uses cached version when it is ≤ 7 days old.
        Re-parses on expiry or when force_refresh=True.
        """
        if not force_refresh:
            cached_path = self.cache.get(self.CACHE_KEY)
            if cached_path and not self._cache_is_stale(cached_path):
                self.logger.info("Returning cached Anexo C checklist")
                result = self._load_cache(cached_path)
                if result:
                    return result

        items: List[ChecklistItem] = []
        source_url = "fallback"

        # 1. Local DOCX — best source (includes facultative flags)
        docx_path = self._find_local_docx()
        if docx_path:
            items = self._parse_docx_table(docx_path)
            source_url = str(docx_path)

        # 2. CVM PDF — if DOCX unavailable
        if not items:
            self.logger.warning("Local DOCX not found. Trying CVM PDF...")
            items = await self._fetch_and_parse_pdf()
            source_url = self.CVM_PDF_URL

        # 3. Hardcoded skeleton — last resort
        if not items:
            self.logger.warning("All live sources failed. Using fallback skeleton.")
            items = self._fallback_checklist()
            source_url = "fallback"

        checklist = NormativeChecklist(
            items=items,
            source_url=source_url,
            parsed_at=datetime.utcnow().isoformat(),
        )
        self._save_cache(checklist)
        return checklist

    def parse_anexo_c_sync(self, force_refresh: bool = False) -> NormativeChecklist:
        """Synchronous wrapper for parse_anexo_c."""
        return asyncio.run(self.parse_anexo_c(force_refresh))

    def _fallback_checklist(self) -> List[ChecklistItem]:
        """
        Hardcoded skeleton derived from Resolução CVM 80 Anexo C.
        Used only when DOCX and PDF are both unavailable.
        """
        sections = [
            # (item_id, titulo, peso, is_facultativo)
            ("1",    "Identificação das pessoas responsáveis", 1, False),
            ("1.1",  "Declarações individuais do Presidente e DRI", 1, False),
            ("1.2",  "Declaração individual de novo ocupante do cargo", 1, False),
            ("2",    "Auditores", 1, False),
            ("2.1",  "Informações sobre auditores independentes", 1, False),
            ("2.2",  "Remuneração dos auditores", 1, False),
            ("2.3",  "Outras informações sobre auditores", 1, False),
            ("3",    "Informações financeiras selecionadas", 2, False),
            ("3.1",  "Demonstrações financeiras selecionadas", 2, True),
            ("3.2",  "Informações proforma", 2, True),
            ("3.3",  "Eventos subsequentes às demonstrações financeiras", 2, True),
            ("3.4",  "Política de destinação dos resultados", 2, False),
            ("3.5",  "Distribuição de dividendos e retenção de lucro líquido", 2, True),
            ("3.6",  "Declaração de dividendos nos últimos 3 exercícios", 2, True),
            ("3.7",  "Endividamento do emissor", 2, False),
            ("3.8",  "Obrigações do emissor", 2, False),
            ("3.9",  "Outras informações financeiras", 1, False),
            ("4",    "Fatores de risco", 3, False),
            ("4.1",  "Fatores de risco que influenciam a decisão de investimento", 3, False),
            ("4.2",  "Riscos de mercado", 3, False),
            ("4.3",  "Processos judiciais do emissor", 3, False),
            ("4.4",  "Processos judiciais de controladas", 3, True),
            ("4.5",  "Processos sigilosos relevantes", 3, False),
            ("4.6",  "Processos de autoridades governamentais", 3, False),
            ("4.7",  "Outras contingências relevantes", 3, False),
            ("4.8",  "Regras do país de origem (emissor estrangeiro)", 3, False),
            ("5",    "Política de gerenciamento de riscos e controles internos", 3, False),
            ("5.1",  "Riscos indicados no item 4.1", 3, True),
            ("5.2",  "Riscos de mercado do item 4.2", 3, True),
            ("5.3",  "Controles adotados para garantir elaboração adequada", 3, False),
            ("5.4",  "Mecanismos e procedimentos de integridade", 3, False),
            ("5.5",  "Alterações significativas nos controles internos", 3, True),
            ("5.6",  "Outras informações sobre gestão de riscos", 1, False),
            ("6",    "Histórico do emissor", 1, False),
            ("6.1",  "Constituição do emissor", 1, False),
            ("6.2",  "Prazo de duração", 1, False),
            ("6.3",  "Breve histórico do emissor", 1, False),
            ("6.4",  "Data de registro na CVM", 1, False),
            ("6.5",  "Pedido de falência", 1, False),
            ("6.6",  "Outras informações históricas", 1, False),
            ("7",    "Atividades do emissor", 2, False),
            ("7.1",  "Atividades principais desenvolvidas", 2, False),
            ("7.2",  "Segmentos operacionais", 2, True),
            ("7.3",  "Produtos e serviços", 2, True),
            ("7.4",  "Clientes responsáveis por mais de 10% da receita", 2, True),
            ("7.5",  "Regulação estatal sobre as atividades", 2, True),
            ("7.6",  "Países de receita relevante", 2, True),
            ("7.7",  "Atividades no exterior", 2, True),
            ("7.8",  "Políticas socioambientais", 2, True),
            ("7.9",  "Outras informações sobre atividades", 1, False),
            ("8",    "Negócios extraordinários", 2, False),
            ("8.1",  "Aquisição ou alienação de ativo relevante", 2, False),
            ("8.2",  "Alterações na forma de condução dos negócios", 2, False),
            ("8.3",  "Contratos relevantes fora do curso ordinário", 2, False),
            ("8.4",  "Outras informações sobre negócios extraordinários", 1, False),
            ("9",    "Ativos relevantes", 2, False),
            ("9.1",  "Bens do ativo não-circulante relevantes", 2, True),
            ("9.2",  "Outras informações sobre ativos", 1, False),
            ("10",   "Comentários dos diretores", 2, False),
            ("10.1", "Condições financeiras e patrimoniais gerais", 2, False),
            ("10.2", "Estrutura de capital e endividamento", 2, False),
            ("10.3", "Eventos com efeitos relevantes", 2, False),
            ("10.4", "Mudanças significativas nas práticas contábeis", 2, False),
            ("10.5", "Políticas contábeis críticas", 2, True),
            ("10.6", "Itens não evidenciados nas demonstrações financeiras", 2, False),
            ("10.7", "Obrigações não evidenciadas nos balanços", 2, False),
            ("10.8", "Alocação de recursos para capital de giro", 2, False),
            ("10.9", "Outros fatores que influenciaram o desempenho", 1, False),
            ("11",   "Projeções", 2, False),
            ("11.1", "Identificação das projeções", 2, False),
            ("11.2", "Comparação de projeções divulgadas x realizadas", 2, False),
            ("12",   "Assembleia geral e administração", 2, False),
            ("12.1", "Estrutura administrativa", 2, False),
            ("12.2", "Regras sobre assembleias gerais", 2, True),
            ("12.3", "Regras sobre o conselho de administração", 2, True),
            ("12.4", "Cláusula compromissória no estatuto social", 2, True),
            ("12.5", "Informações sobre administradores e conselheiros fiscais", 2, False),
            ("12.6", "Membros do conselho fiscal", 2, False),
            ("12.7", "Administradores de sociedades controladas", 2, False),
            ("12.8", "Membros de comitês estatutários", 2, False),
            ("12.9", "Relação conjugal/união estável entre administradores", 2, True),
            ("12.10","Relações de subordinação entre administradores", 2, True),
            ("12.11","Acordos entre administradores e o emissor", 2, True),
            ("12.13","Outras informações sobre administração", 1, False),
            ("13",   "Remuneração dos administradores", 3, False),
            ("13.1", "Política de remuneração do conselho e diretoria", 3, True),
            ("13.2", "Remuneração reconhecida no resultado", 3, False),
            ("13.3", "Remuneração variável", 3, True),
            ("13.4", "Plano de remuneração baseado em ações", 3, True),
            ("13.5", "Remuneração baseada em ações reconhecida no resultado", 3, True),
            ("13.6", "Opções em aberto do conselho e diretoria", 3, True),
            ("13.7", "Opções exercidas e ações entregues", 3, True),
            ("13.8", "Informações para compreensão dos planos de ações", 3, True),
            ("13.9", "Ações direta ou indiretamente detidas", 3, True),
            ("13.10","Planos de previdência em vigor", 3, True),
            ("13.11","Remuneração máxima, mínima e média dos administradores", 3, True),
            ("13.12","Arranjos contratuais e apólices de seguro", 3, True),
            ("13.13","Percentual da remuneração de cada órgão", 3, False),
            ("13.14","Remuneração de administradores por razão diferente do cargo", 3, True),
            ("13.15","Remuneração de administradores de controladas", 3, False),
            ("13.16","Outras informações sobre remuneração", 1, False),
            ("14",   "Recursos humanos", 2, False),
            ("14.1", "Recursos humanos do emissor", 2, True),
            ("14.2", "Alterações relevantes nos recursos humanos", 2, True),
            ("14.3", "Políticas de remuneração dos empregados", 2, True),
            ("14.4", "Relações com sindicatos", 2, True),
            ("14.5", "Outras informações sobre recursos humanos", 1, False),
            ("15",   "Controle e grupo econômico", 3, False),
            ("15.1", "Acionista ou grupo controlador", 3, False),
            ("15.2", "Organograma dos acionistas", 3, True),
            ("15.3", "Distribuição do capital", 3, False),
            ("15.4", "Organograma dos acionistas e grupo econômico", 3, False),
            ("15.5", "Acordo de acionistas arquivado na sede", 3, True),
            ("15.6", "Alterações nas participações dos membros do controle", 3, True),
            ("15.7", "Principais operações societárias no grupo", 3, False),
            ("15.8", "Outras informações sobre controle", 1, False),
            ("16",   "Transações com partes relacionadas", 3, False),
            ("16.1", "Regras e políticas de partes relacionadas", 3, True),
            ("16.2", "Transações com partes relacionadas", 3, False),
            ("16.3", "Identificação de cada transação com parte relacionada", 3, False),
            ("16.4", "Outras informações sobre partes relacionadas", 1, False),
            ("17",   "Capital social", 2, False),
            ("17.1", "Informações sobre o capital social", 2, False),
            ("17.2", "Aumentos de capital", 2, True),
            ("17.3", "Desdobramentos, grupamentos e bonificações", 2, True),
            ("17.4", "Reduções de capital", 2, True),
            ("17.5", "Outras informações sobre capital", 1, False),
            ("18",   "Valores mobiliários", 2, False),
            ("18.1", "Direitos das ações emitidas", 2, True),
            ("18.2", "Regras estatutárias que limitam direitos de acionistas", 2, True),
            ("18.3", "Exceções e cláusulas suspensivas de direitos", 2, True),
            ("18.4", "Volume de negociações dos valores mobiliários", 2, True),
            ("18.5", "Outros valores mobiliários emitidos no Brasil", 2, False),
            ("18.6", "Mercados brasileiros onde os valores são negociados", 2, False),
            ("18.7", "Valores admitidos à negociação em mercado estrangeiro", 2, False),
            ("18.8", "Títulos emitidos no exterior", 2, False),
            ("18.9", "Ofertas públicas de distribuição", 2, False),
            ("18.10","Plano de distribuição de oferta pública", 2, True),
            ("18.11","Ofertas públicas de aquisição feitas pelo emissor", 2, True),
            ("18.12","Outras informações sobre valores mobiliários", 1, False),
            ("19",   "Planos de recompra e valores mobiliários em tesouraria", 2, False),
            ("19.1", "Planos de recompra de ações", 2, True),
            ("19.2", "Valores mobiliários em tesouraria", 2, True),
            ("19.3", "Outras informações sobre recompra", 1, False),
            ("20",   "Política de negociação de valores mobiliários", 2, False),
            ("20.1", "Adoção de política de negociação", 2, True),
            ("20.2", "Outras informações sobre política de negociação", 1, False),
            ("21",   "Política de divulgação de informações", 2, False),
            ("21.1", "Normas e procedimentos internos de divulgação", 2, True),
            ("21.2", "Política de divulgação de ato ou fato relevante", 2, True),
            ("21.3", "Administradores responsáveis pela política de divulgação", 2, True),
            ("21.4", "Outras informações sobre política de divulgação", 1, False),
        ]

        items = []
        for item_id, titulo, peso, is_fac in sections:
            nivel = len(item_id.split("."))
            items.append(ChecklistItem(
                item_id=item_id,
                titulo=titulo,
                nivel=nivel,
                texto_normativo=f"Conforme Resolução CVM 80, Anexo C, item {item_id}.",
                peso=peso,
                tags=self._tags(titulo, ""),
                is_facultativo=is_fac,
                parent_id=self._parent_id(item_id),
            ))
        return items


# ─── Singleton ────────────────────────────────────────────────────────────────

_checklist_parser: Optional[ChecklistParserService] = None


def get_checklist_parser() -> ChecklistParserService:
    """Return the singleton ChecklistParserService instance."""
    global _checklist_parser
    if _checklist_parser is None:
        _checklist_parser = ChecklistParserService()
    return _checklist_parser
