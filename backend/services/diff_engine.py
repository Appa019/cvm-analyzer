"""
CVM Analyzer - Diff Engine Service
===============================

Document comparison engine for FRE analysis.
Supports section, paragraph, word-level and table diffs.
"""

import re
import json
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass, asdict, field
from enum import Enum
import logging
import difflib

from openai import AsyncOpenAI

from config import get_settings
from services.pdf_extractor import PDFSection, get_pdf_extractor


class ChangeType(str, Enum):
    """Types of changes between documents."""
    ADDED = "added"
    REMOVED = "removed"
    MODIFIED = "modified"
    MOVED = "moved"
    UNCHANGED = "unchanged"


@dataclass
class TextChange:
    """Represents a text change within a section."""
    type: ChangeType
    old_text: str = ""
    new_text: str = ""
    position: int = 0  # Character or line position
    
    def to_dict(self) -> Dict:
        return {
            "type": self.type.value,
            "old_text": self.old_text,
            "new_text": self.new_text,
            "position": self.position
        }


@dataclass
class TableChange:
    """Represents changes in a table."""
    row: int
    col: int
    old_value: str
    new_value: str
    delta_numeric: Optional[float] = None
    
    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class SectionDiff:
    """Diff result for a single section."""
    item_id: str
    titulo_a: str
    titulo_b: str
    change_type: ChangeType
    text_changes: List[TextChange]
    table_changes: List[TableChange]
    semantic_summary: str = ""
    technical_diff: str = ""
    confidence: float = 1.0
    moved_from: Optional[str] = None  # If section was moved
    
    def to_dict(self) -> Dict:
        return {
            **asdict(self),
            "change_type": self.change_type.value,
            "text_changes": [c.to_dict() for c in self.text_changes],
            "table_changes": [c.to_dict() for c in self.table_changes]
        }


@dataclass
class DiffResult:
    """Complete diff result between two documents."""
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
    section_diffs: List[SectionDiff]
    summary: str
    created_at: str
    
    def to_dict(self) -> Dict:
        return {
            **asdict(self),
            "section_diffs": [s.to_dict() for s in self.section_diffs]
        }


class DiffEngineService:
    """
    Service for comparing FRE documents.
    
    Features:
    - Text normalization for ignoring formatting changes
    - Section-level alignment by item_id
    - Paragraph and word-level diffs
    - Table comparison with numeric deltas
    - Semantic explanations via AI
    """
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        logger: Optional[logging.Logger] = None
    ):
        """
        Initialize diff engine.
        
        Args:
            api_key: OpenAI API key for semantic summaries
            logger: Logger instance
        """
        self.settings = get_settings()
        self.api_key = api_key or self.settings.openai_api_key
        self.logger = logger or logging.getLogger(__name__)
        self._client: Optional[AsyncOpenAI] = None
    
    def set_api_key(self, api_key: str):
        """Set API key for semantic analysis."""
        self.api_key = api_key
        self._client = None
    
    @property
    def client(self) -> Optional[AsyncOpenAI]:
        """Get AsyncOpenAI client if API key is set."""
        if not self.api_key:
            return None

        if self._client is None:
            self._client = AsyncOpenAI(api_key=self.api_key)

        return self._client
    
    def normalize_text(self, text: str) -> str:
        """
        Normalize text for comparison.
        
        - Replaces non-breaking spaces
        - Collapses whitespace
        - Strips leading/trailing whitespace
        
        Args:
            text: Raw text
            
        Returns:
            Normalized text
        """
        if not text:
            return ""
        
        # Replace non-breaking spaces
        text = text.replace("\u00a0", " ")
        
        # Collapse multiple whitespaces to single space
        text = re.sub(r"\s+", " ", text)
        
        # Strip
        text = text.strip()
        
        return text
    
    def split_into_paragraphs(self, text: str) -> List[str]:
        """Split text into paragraphs."""
        # Split on double newlines or similar
        paragraphs = re.split(r"\n\s*\n|\r\n\s*\r\n", text)
        return [p.strip() for p in paragraphs if p.strip()]
    
    def get_word_diff(
        self,
        text_a: str,
        text_b: str,
        show_formatting: bool = False
    ) -> Tuple[str, List[TextChange]]:
        """
        Get word-level diff between two texts.
        
        Args:
            text_a: Original text
            text_b: Modified text
            show_formatting: If True, include formatting changes
            
        Returns:
            Tuple of (unified diff string, list of changes)
        """
        if not show_formatting:
            text_a = self.normalize_text(text_a)
            text_b = self.normalize_text(text_b)
        
        # Split into words
        words_a = text_a.split()
        words_b = text_b.split()
        
        # Get diff
        differ = difflib.unified_diff(
            words_a, 
            words_b, 
            lineterm=""
        )
        
        diff_output = "\n".join(differ)
        
        # Extract changes
        changes = []
        matcher = difflib.SequenceMatcher(None, words_a, words_b)
        
        pos = 0
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == "replace":
                changes.append(TextChange(
                    type=ChangeType.MODIFIED,
                    old_text=" ".join(words_a[i1:i2]),
                    new_text=" ".join(words_b[j1:j2]),
                    position=pos
                ))
            elif tag == "delete":
                changes.append(TextChange(
                    type=ChangeType.REMOVED,
                    old_text=" ".join(words_a[i1:i2]),
                    position=pos
                ))
            elif tag == "insert":
                changes.append(TextChange(
                    type=ChangeType.ADDED,
                    new_text=" ".join(words_b[j1:j2]),
                    position=pos
                ))
            pos = i2
        
        return diff_output, changes
    
    def get_paragraph_diff(
        self,
        text_a: str,
        text_b: str,
        show_formatting: bool = False
    ) -> List[TextChange]:
        """
        Get paragraph-level diff.
        
        Args:
            text_a: Original text
            text_b: Modified text
            show_formatting: If True, include formatting changes
            
        Returns:
            List of paragraph changes
        """
        if not show_formatting:
            text_a = self.normalize_text(text_a)
            text_b = self.normalize_text(text_b)
        
        paras_a = self.split_into_paragraphs(text_a)
        paras_b = self.split_into_paragraphs(text_b)
        
        changes = []
        matcher = difflib.SequenceMatcher(None, paras_a, paras_b)
        
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == "replace":
                # Modified paragraphs
                for i, j in zip(range(i1, i2), range(j1, j2)):
                    changes.append(TextChange(
                        type=ChangeType.MODIFIED,
                        old_text=paras_a[i] if i < len(paras_a) else "",
                        new_text=paras_b[j] if j < len(paras_b) else "",
                        position=i
                    ))
            elif tag == "delete":
                for i in range(i1, i2):
                    changes.append(TextChange(
                        type=ChangeType.REMOVED,
                        old_text=paras_a[i],
                        position=i
                    ))
            elif tag == "insert":
                for j in range(j1, j2):
                    changes.append(TextChange(
                        type=ChangeType.ADDED,
                        new_text=paras_b[j],
                        position=j
                    ))
        
        return changes
    
    def compare_tables(
        self,
        tables_a: List[List[List[str]]],
        tables_b: List[List[List[str]]]
    ) -> List[TableChange]:
        """
        Compare tables and find changes.
        
        Args:
            tables_a: Tables from document A
            tables_b: Tables from document B
            
        Returns:
            List of table changes
        """
        changes = []
        
        # Compare tables pairwise (assuming same order)
        for t_idx, (table_a, table_b) in enumerate(zip(tables_a, tables_b)):
            max_rows = max(len(table_a), len(table_b))
            max_cols = max(
                max(len(row) for row in table_a) if table_a else 0,
                max(len(row) for row in table_b) if table_b else 0
            )
            
            for row_idx in range(max_rows):
                for col_idx in range(max_cols):
                    val_a = ""
                    val_b = ""
                    
                    if row_idx < len(table_a) and col_idx < len(table_a[row_idx]):
                        val_a = table_a[row_idx][col_idx]
                    
                    if row_idx < len(table_b) and col_idx < len(table_b[row_idx]):
                        val_b = table_b[row_idx][col_idx]
                    
                    # Normalize for comparison
                    norm_a = self.normalize_text(val_a)
                    norm_b = self.normalize_text(val_b)
                    
                    if norm_a != norm_b:
                        # Try to calculate numeric delta
                        delta = None
                        try:
                            num_a = float(re.sub(r"[^\d.,\-]", "", val_a).replace(",", "."))
                            num_b = float(re.sub(r"[^\d.,\-]", "", val_b).replace(",", "."))
                            delta = num_b - num_a
                        except (ValueError, AttributeError):
                            pass
                        
                        changes.append(TableChange(
                            row=row_idx,
                            col=col_idx,
                            old_value=val_a,
                            new_value=val_b,
                            delta_numeric=delta
                        ))
        
        return changes
    
    def align_sections(
        self,
        sections_a: List[PDFSection],
        sections_b: List[PDFSection]
    ) -> List[Tuple[Optional[PDFSection], Optional[PDFSection], ChangeType]]:
        """
        Align sections from two documents by item_id.
        
        Args:
            sections_a: Sections from document A
            sections_b: Sections from document B
            
        Returns:
            List of aligned pairs with change type
        """
        map_a = {s.item_id: s for s in sections_a}
        map_b = {s.item_id: s for s in sections_b}
        
        all_ids = sorted(
            set(map_a.keys()) | set(map_b.keys()),
            key=lambda x: [int(n) for n in x.split(".")]
        )
        
        aligned = []
        
        for item_id in all_ids:
            sec_a = map_a.get(item_id)
            sec_b = map_b.get(item_id)
            
            if sec_a and sec_b:
                # Both exist - check if content changed
                norm_a = self.normalize_text(sec_a.content_text)
                norm_b = self.normalize_text(sec_b.content_text)
                
                if norm_a == norm_b:
                    change_type = ChangeType.UNCHANGED
                else:
                    change_type = ChangeType.MODIFIED
                    
            elif sec_a and not sec_b:
                change_type = ChangeType.REMOVED
            else:
                change_type = ChangeType.ADDED
            
            aligned.append((sec_a, sec_b, change_type))
        
        # Check for moved sections (same content, different item_id)
        content_to_id_a = {self.normalize_text(s.content_text)[:500]: s.item_id for s in sections_a}
        content_to_id_b = {self.normalize_text(s.content_text)[:500]: s.item_id for s in sections_b}
        
        for i, (sec_a, sec_b, change_type) in enumerate(aligned):
            if change_type == ChangeType.REMOVED and sec_a:
                content = self.normalize_text(sec_a.content_text)[:500]
                if content in content_to_id_b:
                    aligned[i] = (sec_a, sec_b, ChangeType.MOVED)
            elif change_type == ChangeType.ADDED and sec_b:
                content = self.normalize_text(sec_b.content_text)[:500]
                if content in content_to_id_a:
                    aligned[i] = (sec_a, sec_b, ChangeType.MOVED)
        
        return aligned
    
    SEMANTIC_IMPACT_SCHEMA = {
        "type": "object",
        "properties": {
            "resumo_mudancas": {
                "type": "string",
                "description": "Resumo objetivo do que mudou nesta seção"
            },
            "impacto_regulatorio": {
                "type": "string",
                "description": "Impacto regulatório da mudança (CVM, normas, compliance)"
            },
            "impacto_negocio": {
                "type": "string",
                "description": "Impacto no negócio (risco, financeiro, operacional)"
            },
            "severidade": {
                "type": "string",
                "enum": ["baixa", "media", "alta", "critica"],
                "description": "Severidade do impacto da mudança"
            }
        },
        "required": ["resumo_mudancas", "impacto_regulatorio", "impacto_negocio", "severidade"],
        "additionalProperties": False
    }

    async def generate_semantic_summary(
        self,
        item_id: str,
        titulo: str,
        old_text: str,
        new_text: str
    ) -> str:
        """
        Generate semantic summary and impact analysis of changes using AI.

        Args:
            item_id: Section ID
            titulo: Section title
            old_text: Original text
            new_text: Modified text

        Returns:
            Formatted semantic summary with impact analysis
        """
        if not self.client:
            return "Resumo semântico não disponível (API key não configurada)"

        try:
            from services.evaluation_engine import _parse_model
            base_model, reasoning = _parse_model(self.settings.openai_model)
            diff_kwargs: Dict[str, Any] = {
                "model": base_model,
                "instructions": (
                    "Você é um analista especializado em documentos regulatórios brasileiros (FRE/CVM).\n"
                    "Analise as diferenças entre duas versões de uma seção e retorne um JSON estruturado "
                    "com o resumo das mudanças e seus impactos regulatórios e de negócio.\n"
                    "Seja objetivo e preciso. Responda em português."
                ),
                "input": (
                    f"Seção: {item_id} — {titulo}\n\n"
                    f"**VERSÃO ANTERIOR:**\n{old_text[:3000]}\n\n"
                    f"**VERSÃO ATUAL:**\n{new_text[:3000]}\n\n"
                    "Analise as mudanças e retorne no formato JSON solicitado."
                ),
                "text": {
                    "format": {
                        "type": "json_schema",
                        "name": "semantic_impact",
                        "strict": True,
                        "schema": self.SEMANTIC_IMPACT_SCHEMA
                    }
                },
            }
            if reasoning:
                diff_kwargs["reasoning"] = reasoning
            response = await self.client.responses.create(**diff_kwargs)

            data = json.loads(response.output_text)
            severity_labels = {
                "baixa": "🟢 Baixa",
                "media": "🟡 Média",
                "alta": "🟠 Alta",
                "critica": "🔴 Crítica"
            }
            sev_label = severity_labels.get(data.get("severidade", "media"), "🟡 Média")

            return (
                f"**{sev_label} — {data.get('resumo_mudancas', '')}**\n\n"
                f"**Impacto Regulatório:** {data.get('impacto_regulatorio', 'N/A')}\n\n"
                f"**Impacto no Negócio:** {data.get('impacto_negocio', 'N/A')}"
            )

        except Exception as e:
            self.logger.error(f"Error generating semantic summary for {item_id}: {e}")
            return f"Erro ao gerar análise de impacto: {str(e)}"
    
    async def compare_documents(
        self,
        sections_a: List[PDFSection],
        sections_b: List[PDFSection],
        doc_a_id: str,
        doc_b_id: str,
        doc_a_dt_refer: str,
        doc_b_dt_refer: str,
        include_semantic: bool = True
    ) -> DiffResult:
        """
        Compare two FRE documents.
        
        Args:
            sections_a: Sections from document A (older)
            sections_b: Sections from document B (newer)
            doc_a_id: Document A identifier
            doc_b_id: Document B identifier
            doc_a_dt_refer: Document A reference date
            doc_b_dt_refer: Document B reference date
            include_semantic: If True, generate semantic summaries
            
        Returns:
            DiffResult with complete comparison
        """
        from datetime import datetime
        
        self.logger.info(f"Comparing documents: {doc_a_id} vs {doc_b_id}")
        
        # Align sections
        aligned = self.align_sections(sections_a, sections_b)
        
        section_diffs = []
        counts = {t: 0 for t in ChangeType}
        
        for sec_a, sec_b, change_type in aligned:
            counts[change_type] += 1
            
            # Get item info
            item_id = sec_a.item_id if sec_a else sec_b.item_id
            titulo_a = sec_a.titulo if sec_a else ""
            titulo_b = sec_b.titulo if sec_b else ""
            
            text_a = sec_a.content_text if sec_a else ""
            text_b = sec_b.content_text if sec_b else ""
            tables_a = sec_a.tables if sec_a else []
            tables_b = sec_b.tables if sec_b else []
            
            # Get text changes
            if change_type == ChangeType.MODIFIED:
                text_changes = self.get_paragraph_diff(text_a, text_b)
            elif change_type == ChangeType.REMOVED:
                text_changes = [TextChange(
                    type=ChangeType.REMOVED,
                    old_text=text_a
                )]
            elif change_type == ChangeType.ADDED:
                text_changes = [TextChange(
                    type=ChangeType.ADDED,
                    new_text=text_b
                )]
            else:
                text_changes = []
            
            # Get table changes
            table_changes = self.compare_tables(tables_a, tables_b)
            
            # Generate technical diff
            _, word_changes = self.get_word_diff(text_a, text_b)
            technical_diff = json.dumps([c.to_dict() for c in word_changes[:20]], ensure_ascii=False)
            
            # Generate semantic summary (only for modified sections)
            semantic_summary = ""
            if change_type == ChangeType.MODIFIED and include_semantic:
                semantic_summary = await self.generate_semantic_summary(
                    item_id,
                    titulo_b or titulo_a,
                    text_a,
                    text_b
                )
            
            section_diff = SectionDiff(
                item_id=item_id,
                titulo_a=titulo_a,
                titulo_b=titulo_b,
                change_type=change_type,
                text_changes=text_changes,
                table_changes=table_changes,
                semantic_summary=semantic_summary,
                technical_diff=technical_diff
            )
            section_diffs.append(section_diff)
        
        # Generate overall summary
        summary_parts = []
        if counts[ChangeType.ADDED]:
            summary_parts.append(f"{counts[ChangeType.ADDED]} seção(ões) adicionada(s)")
        if counts[ChangeType.REMOVED]:
            summary_parts.append(f"{counts[ChangeType.REMOVED]} seção(ões) removida(s)")
        if counts[ChangeType.MODIFIED]:
            summary_parts.append(f"{counts[ChangeType.MODIFIED]} seção(ões) modificada(s)")
        if counts[ChangeType.MOVED]:
            summary_parts.append(f"{counts[ChangeType.MOVED]} seção(ões) movida(s)")
        
        summary = "; ".join(summary_parts) if summary_parts else "Nenhuma alteração encontrada"
        
        result = DiffResult(
            doc_a_id=doc_a_id,
            doc_b_id=doc_b_id,
            doc_a_dt_refer=doc_a_dt_refer,
            doc_b_dt_refer=doc_b_dt_refer,
            total_sections=len(aligned),
            added_count=counts[ChangeType.ADDED],
            removed_count=counts[ChangeType.REMOVED],
            modified_count=counts[ChangeType.MODIFIED],
            moved_count=counts[ChangeType.MOVED],
            unchanged_count=counts[ChangeType.UNCHANGED],
            section_diffs=section_diffs,
            summary=summary,
            created_at=datetime.utcnow().isoformat()
        )
        
        self.logger.info(f"Diff complete: {summary}")
        return result
    
    def compare_documents_sync(
        self,
        sections_a: List[PDFSection],
        sections_b: List[PDFSection],
        doc_a_id: str,
        doc_b_id: str,
        doc_a_dt_refer: str,
        doc_b_dt_refer: str,
        include_semantic: bool = True
    ) -> DiffResult:
        """Synchronous version of compare_documents."""
        import asyncio
        return asyncio.run(self.compare_documents(
            sections_a, sections_b,
            doc_a_id, doc_b_id,
            doc_a_dt_refer, doc_b_dt_refer,
            include_semantic
        ))


# =============================================================================
# Singleton Instance
# =============================================================================

_diff_engine: Optional[DiffEngineService] = None


def get_diff_engine() -> DiffEngineService:
    """Get or create the diff engine singleton."""
    global _diff_engine
    if _diff_engine is None:
        from utils import get_logger
        _diff_engine = DiffEngineService(logger=get_logger())
    return _diff_engine
