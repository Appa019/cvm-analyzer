"""
CVM Analyzer - API Package
==========================

Exporta todos os routers de API.
"""

from .routes_evaluation import router as evaluation_router
from .routes_diff import router as diff_router
from .routes_chat import router as chat_router
from .routes_settings import router as settings_router
from .routes_archive import router as archive_router
from .routes_cvm import router as cvm_router

__all__ = [
    "evaluation_router",
    "diff_router",
    "chat_router",
    "settings_router",
    "archive_router",
    "cvm_router",
]
