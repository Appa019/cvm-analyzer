"""
CVM Analyzer - Services Package
================================

Exporta todos os serviços.
"""

from .pdf_extractor import PDFExtractorService, get_pdf_extractor, PDFSection, PDFExtractionResult
from .checklist_parser import ChecklistParserService, get_checklist_parser, ChecklistItem, NormativeChecklist
from .evaluation_engine import EvaluationEngineService, get_evaluation_engine, ItemEvaluationResult, EvaluationSummary
from .diff_engine import DiffEngineService, get_diff_engine, DiffResult, SectionDiff, ChangeType
from .rag_service import RAGService, get_rag_service, ChatSession, ChatMessage
from .cvm_service import CVMService, get_cvm_service
from .enet_scraper import ENETScraper, get_enet_scraper

__all__ = [
    # CVM Service
    "CVMService",
    "get_cvm_service",

    # ENET Scraper
    "ENETScraper",
    "get_enet_scraper",

    # PDF Extractor
    "PDFExtractorService",
    "get_pdf_extractor",
    "PDFSection",
    "PDFExtractionResult",

    # Checklist Parser
    "ChecklistParserService",
    "get_checklist_parser",
    "ChecklistItem",
    "NormativeChecklist",

    # Evaluation Engine
    "EvaluationEngineService",
    "get_evaluation_engine",
    "ItemEvaluationResult",
    "EvaluationSummary",

    # Diff Engine
    "DiffEngineService",
    "get_diff_engine",
    "DiffResult",
    "SectionDiff",
    "ChangeType",

    # RAG Service
    "RAGService",
    "get_rag_service",
    "ChatSession",
    "ChatMessage"
]
