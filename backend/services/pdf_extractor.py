"""
CVM Analyzer - PDF Extractor Service
=================================

Extracts text, tables, and structure from FRE PDFs.
Uses PyMuPDF for text and pdfplumber/Camelot for tables.
"""

import re
import hashlib
from pathlib import Path
from typing import Optional, List, Dict, Tuple, Any
from dataclasses import dataclass, asdict
import logging

import fitz  # PyMuPDF
import pdfplumber


@dataclass
class PDFPage:
    """Represents a single PDF page with extracted content."""
    page_num: int
    text: str
    tables: List[List[List[str]]]  # List of tables, each table is rows of cells
    has_images: bool = False


@dataclass
class PDFSection:
    """Represents a section identified in the PDF index."""
    item_id: str
    titulo: str
    nivel: int
    page_start: int
    page_end: Optional[int] = None
    content_text: str = ""
    content_hash: str = ""
    tables: List[List[List[str]]] = None
    
    def __post_init__(self):
        if self.tables is None:
            self.tables = []


@dataclass
class PDFExtractionResult:
    """Result of PDF extraction."""
    total_pages: int
    total_chars: int
    is_text_native: bool
    sections: List[PDFSection]
    full_text: str
    index_items: List[Dict[str, Any]]
    warnings: List[str]


class PDFExtractorService:
    """
    Service for extracting content from FRE PDFs.
    
    Features:
    - Text extraction with PyMuPDF
    - Table extraction with pdfplumber
    - Index/TOC detection and parsing
    - Section boundary detection
    - Text-native vs scan detection
    """
    
    # Regex for detecting index items (e.g., "1.", "1.1", "1.1.1")
    INDEX_PATTERN = re.compile(
        r"^(\d+(?:\.\d+)*\.?)\s+(.+?)(?:\s*\.{2,}\s*|\s+)(\d+)\s*$",
        re.MULTILINE
    )
    
    # Pattern for section headers in content
    SECTION_HEADER_PATTERN = re.compile(
        r"^(\d+(?:\.\d+)*\.?)\s+(.+?)$",
        re.MULTILINE
    )
    
    # Minimum text per page to consider it text-native
    MIN_TEXT_CHARS_PER_PAGE = 100
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        """
        Initialize PDF extractor.
        
        Args:
            logger: Logger instance
        """
        self.logger = logger or logging.getLogger(__name__)
    
    def extract_text(self, pdf_path: Path) -> Tuple[str, int, bool]:
        """
        Extract all text from PDF.
        
        Args:
            pdf_path: Path to PDF file
            
        Returns:
            Tuple of (full_text, total_pages, is_text_native)
        """
        self.logger.info(f"Extracting text from: {pdf_path}")
        
        doc = fitz.open(pdf_path)
        total_pages = len(doc)
        texts = []
        chars_per_page = []
        
        for page_num in range(total_pages):
            page = doc[page_num]
            text = page.get_text("text")
            texts.append(text)
            chars_per_page.append(len(text))
        
        doc.close()
        
        full_text = "\n\n".join(texts)
        avg_chars = sum(chars_per_page) / max(len(chars_per_page), 1)
        is_text_native = avg_chars >= self.MIN_TEXT_CHARS_PER_PAGE
        
        if not is_text_native:
            self.logger.warning(
                f"PDF appears to be scanned (avg {avg_chars:.0f} chars/page). "
                "OCR not available - manual review needed."
            )
        
        self.logger.info(
            f"Extracted {len(full_text)} chars from {total_pages} pages "
            f"(text-native: {is_text_native})"
        )
        
        return full_text, total_pages, is_text_native
    
    def extract_tables(self, pdf_path: Path) -> Dict[int, List[List[List[str]]]]:
        """
        Extract tables from PDF using pdfplumber.
        
        Args:
            pdf_path: Path to PDF file
            
        Returns:
            Dict mapping page number to list of tables
        """
        self.logger.info(f"Extracting tables from: {pdf_path}")
        
        tables_by_page = {}
        
        with pdfplumber.open(pdf_path) as pdf:
            for page_num, page in enumerate(pdf.pages):
                tables = page.extract_tables()
                if tables:
                    # Clean up table data
                    cleaned_tables = []
                    for table in tables:
                        cleaned_rows = []
                        for row in table:
                            cleaned_row = [
                                cell.strip() if cell else "" 
                                for cell in row
                            ]
                            cleaned_rows.append(cleaned_row)
                        cleaned_tables.append(cleaned_rows)
                    tables_by_page[page_num] = cleaned_tables
        
        total_tables = sum(len(t) for t in tables_by_page.values())
        self.logger.info(f"Extracted {total_tables} tables from {len(tables_by_page)} pages")
        
        return tables_by_page
    
    def extract_index(self, full_text: str) -> List[Dict[str, Any]]:
        """
        Extract index/TOC items from PDF text.
        
        Args:
            full_text: Full PDF text
            
        Returns:
            List of index items with item_id, titulo, page, nivel
        """
        self.logger.info("Extracting index from PDF text")
        
        # Look for index section
        index_start_patterns = [
            r"ÍNDICE",
            r"SUMÁRIO",
            r"TABELA\s+DE\s+CONTEÚDO",
            r"CONTEÚDO"
        ]
        
        index_text = ""
        for pattern in index_start_patterns:
            match = re.search(pattern, full_text, re.IGNORECASE)
            if match:
                # Get text from index start to first major section
                start = match.end()
                # Look for "1." or "1 " as first content item
                content_start = re.search(r"\n\s*1[\.\s]", full_text[start:])
                if content_start:
                    end = start + content_start.start() + 5000  # Get ~5000 chars of index
                    index_text = full_text[start:min(end, len(full_text))]
                    break
        
        if not index_text:
            # Try to find index pattern anywhere in first 20% of document
            search_range = full_text[:len(full_text)//5]
            index_text = search_range
        
        # Extract items using pattern
        items = []
        for match in self.INDEX_PATTERN.finditer(index_text):
            item_id = match.group(1).rstrip(".")
            titulo = match.group(2).strip()
            page = int(match.group(3))
            
            # Calculate nesting level
            nivel = len(item_id.split("."))
            
            items.append({
                "item_id": item_id,
                "titulo": titulo,
                "page": page,
                "nivel": nivel
            })
        
        # Sort by item_id
        items.sort(key=lambda x: [int(n) for n in x["item_id"].split(".")])
        
        self.logger.info(f"Extracted {len(items)} index items")
        return items
    
    def identify_sections(
        self,
        full_text: str,
        index_items: List[Dict[str, Any]],
        total_pages: int
    ) -> List[PDFSection]:
        """
        Identify and extract section content based on index.
        
        Args:
            full_text: Full PDF text
            index_items: List of index items
            total_pages: Total pages in PDF
            
        Returns:
            List of PDFSection objects with content
        """
        self.logger.info("Identifying sections from index")
        
        sections = []
        
        for i, item in enumerate(index_items):
            # Determine page range
            page_start = item["page"]
            page_end = (
                index_items[i + 1]["page"] - 1 
                if i + 1 < len(index_items) 
                else total_pages
            )
            
            # Build regex to find this section's header
            item_id_escaped = re.escape(item["item_id"])
            titulo_words = item["titulo"].split()[:3]  # First 3 words
            titulo_pattern = r"\s+".join(re.escape(w) for w in titulo_words)
            
            pattern = rf"{item_id_escaped}\.?\s+{titulo_pattern}"
            
            # Find section start in text
            match = re.search(pattern, full_text, re.IGNORECASE)
            
            if match:
                # Find next section start
                next_section_start = len(full_text)
                if i + 1 < len(index_items):
                    next_id = re.escape(index_items[i + 1]["item_id"])
                    next_match = re.search(
                        rf"\n\s*{next_id}\.?\s+", 
                        full_text[match.end():]
                    )
                    if next_match:
                        next_section_start = match.end() + next_match.start()
                
                content = full_text[match.start():next_section_start].strip()
            else:
                content = ""
                self.logger.warning(f"Could not locate content for item {item['item_id']}")
            
            # Calculate content hash
            content_hash = hashlib.sha256(content.encode()).hexdigest()[:16]
            
            section = PDFSection(
                item_id=item["item_id"],
                titulo=item["titulo"],
                nivel=item["nivel"],
                page_start=page_start,
                page_end=page_end,
                content_text=content,
                content_hash=content_hash
            )
            sections.append(section)
        
        self.logger.info(f"Identified {len(sections)} sections")
        return sections
    
    def extract_full(self, pdf_path: Path) -> PDFExtractionResult:
        """
        Perform full extraction of PDF.
        
        Args:
            pdf_path: Path to PDF file
            
        Returns:
            PDFExtractionResult with all extracted data
        """
        warnings = []
        
        # Extract text
        full_text, total_pages, is_text_native = self.extract_text(pdf_path)
        
        if not is_text_native:
            warnings.append("PDF parece ser digitalizado (scan). Revisão manual necessária.")
        
        # Extract index
        index_items = self.extract_index(full_text)
        
        if not index_items:
            warnings.append("Não foi possível extrair o índice automaticamente.")
        
        # Extract tables
        tables_by_page = self.extract_tables(pdf_path)
        
        # Identify sections
        sections = self.identify_sections(full_text, index_items, total_pages)
        
        # Assign tables to sections based on page range
        for section in sections:
            section_tables = []
            for page_num in range(section.page_start - 1, (section.page_end or section.page_start)):
                if page_num in tables_by_page:
                    section_tables.extend(tables_by_page[page_num])
            section.tables = section_tables
        
        return PDFExtractionResult(
            total_pages=total_pages,
            total_chars=len(full_text),
            is_text_native=is_text_native,
            sections=sections,
            full_text=full_text,
            index_items=index_items,
            warnings=warnings
        )
    
    def normalize_text(self, text: str) -> str:
        """
        Normalize text for comparison (used in diff).
        
        Args:
            text: Raw text
            
        Returns:
            Normalized text
        """
        # Replace non-breaking spaces
        text = text.replace("\u00a0", " ")
        # Collapse whitespace
        text = re.sub(r"\s+", " ", text)
        # Strip
        text = text.strip()
        return text
    
    def compare_content_hash(self, hash_a: str, hash_b: str) -> bool:
        """Check if two content hashes are identical."""
        return hash_a == hash_b


# =============================================================================
# Singleton Instance
# =============================================================================

_pdf_extractor: Optional[PDFExtractorService] = None


def get_pdf_extractor() -> PDFExtractorService:
    """Get or create the PDF extractor singleton."""
    global _pdf_extractor
    if _pdf_extractor is None:
        from utils import get_logger
        _pdf_extractor = PDFExtractorService(logger=get_logger())
    return _pdf_extractor
