"""
CVM Analyzer - Configuration Module
=====================================

Gerencia configurações da aplicação, caminhos e constantes.
Usa pydantic-settings para configuração tipada via variáveis de ambiente (prefixo FRE_).
"""

import os
from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """
    Application settings loaded from environment or defaults.
    
    Settings are read in order of priority:
    1. Environment variables (FRE_*)
    2. .env file (if exists)
    3. Default values
    """
    
    # ==========================================================================
    # Application Info
    # ==========================================================================
    app_name: str = "CVM Analyzer"
    app_version: str = "1.0.0"
    debug: bool = False
    
    # ==========================================================================
    # Paths - Windows Local App Data
    # ==========================================================================
    @property
    def base_dir(self) -> Path:
        """Base directory for all app data (Windows: %LOCALAPPDATA%/FREAnalyzer)"""
        local_app_data = os.environ.get("LOCALAPPDATA", str(Path.home() / ".local" / "share"))
        return Path(local_app_data) / "FREAnalyzer"
    
    @property
    def cache_dir(self) -> Path:
        """Directory for cached PDFs and CSVs"""
        path = self.base_dir / "cache"
        path.mkdir(parents=True, exist_ok=True)
        return path
    
    @property
    def db_path(self) -> Path:
        """SQLite database file path"""
        path = self.base_dir / "data"
        path.mkdir(parents=True, exist_ok=True)
        return path / "fre_analyzer.db"
    
    @property
    def logs_dir(self) -> Path:
        """Directory for log files"""
        path = self.base_dir / "logs"
        path.mkdir(parents=True, exist_ok=True)
        return path
    
    @property
    def vector_stores_dir(self) -> Path:
        """Directory for vector store metadata"""
        path = self.base_dir / "vector_stores"
        path.mkdir(parents=True, exist_ok=True)
        return path
    
    # ==========================================================================
    # Cache Settings
    # ==========================================================================
    cache_max_size_gb: float = Field(default=5.0, description="Maximum cache size in GB")
    cache_pin_years: int = Field(default=3, description="Number of recent years to always keep")
    
    # ==========================================================================
    # CVM Data Source
    # ==========================================================================
    # CNPJ padrão para pré-preencher o seletor de empresa
    default_cnpj: str = ""
    
    # ==========================================================================
    # OpenAI API Settings
    # ==========================================================================
    openai_api_key: Optional[str] = Field(default=None, description="OpenAI API key (memory-only at runtime)")
    openai_model: str = Field(default="gpt-5-mini", description="Model for evaluation and RAG")
    openai_embedding_model: str = Field(default="text-embedding-3-large", description="Model for embeddings")
    openai_timeout: int = Field(default=180, description="API timeout in seconds")
    openai_max_retries: int = Field(default=3, description="Max retries for API calls")
    
    # ==========================================================================
    # Download Settings
    # ==========================================================================
    download_timeout: int = Field(default=180, description="Download timeout in seconds")
    download_max_retries: int = Field(default=3, description="Max retries for downloads")
    
    # ==========================================================================
    # Logging Settings
    # ==========================================================================
    log_max_bytes: int = Field(default=10 * 1024 * 1024, description="Max log file size (10MB)")
    log_backup_count: int = Field(default=5, description="Number of log backups to keep")
    log_level: str = Field(default="INFO", description="Logging level")
    
    # ==========================================================================
    # Server Settings
    # ==========================================================================
    api_host: str = Field(default="0.0.0.0")
    api_port: int = Field(default=8000)
    cors_origins: Optional[str] = Field(default=None, description="Comma-separated allowed origins, or None for *")
    
    class Config:
        env_prefix = "FRE_"
        env_file = str(Path(__file__).resolve().parent.parent / ".env")
        env_file_encoding = "utf-8"
        extra = "ignore"  # Ignore extra environment variables


# =============================================================================
# Status Icons/Labels
# =============================================================================

STATUS_CONFIG = {
    "COMPLETO": {
        "icon": "✅",
        "label": "Completo",
        "color": "#48bb78",
        "score_base": 1.0
    },
    "PARCIAL": {
        "icon": "⚠️",
        "label": "Parcial",
        "color": "#ed8936",
        "score_base": 0.6
    },
    "AUSENTE": {
        "icon": "❌",
        "label": "Ausente",
        "color": "#e53e3e",
        "score_base": 0.0
    },
    "CRITICO": {
        "icon": "⛔",
        "label": "Crítico",
        "color": "#c53030",
        "score_base": 0.0
    }
}

SEVERITY_PENALTIES = {
    "low": 0.05,
    "medium": 0.10,
    "high": 0.20,
    "critical": 0.35
}


# =============================================================================
# Singleton Settings Instance
# =============================================================================

_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """Retorna a instância singleton de Settings."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
