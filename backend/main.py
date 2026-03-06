"""
CVM Analyzer - FastAPI Application
===============================

Main FastAPI application setup.
Serves API routes and static frontend files.
"""

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from rate_limit import limiter
from api import evaluation_router, diff_router, chat_router, settings_router, archive_router, cvm_router
from config import get_settings
from database import init_database
from utils import setup_logging, get_logger


async def _checklist_refresh_loop() -> None:
    """Background task: refresh CVM Anexo C checklist every 7 days."""
    from services.checklist_parser import get_checklist_parser
    logger = get_logger()
    parser = get_checklist_parser()

    # Pre-warm on startup (non-blocking: use existing cache if fresh)
    try:
        await parser.parse_anexo_c(force_refresh=False)
        logger.info("Checklist pre-warmed on startup")
    except Exception as exc:
        logger.warning(f"Checklist pre-warm failed: {exc}")

    REFRESH_INTERVAL = 7 * 24 * 3600  # 7 days in seconds
    while True:
        await asyncio.sleep(REFRESH_INTERVAL)
        logger.info("Running scheduled checklist refresh...")
        try:
            await parser.parse_anexo_c(force_refresh=True)
            logger.info("Checklist refreshed successfully")
        except Exception as exc:
            logger.error(f"Checklist refresh failed: {exc}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    # Startup
    setup_logging()
    logger = get_logger()
    logger.info("Starting CVM Analyzer application...")

    # Initialize database
    await init_database()
    logger.info("Database initialized")

    # Load company Vector Stores from DB
    try:
        from services import get_rag_service
        from database import get_async_engine, get_async_session_factory
        from config import get_settings as _get_settings
        _s = _get_settings()
        _engine = get_async_engine(str(_s.db_path))
        _factory = get_async_session_factory(_engine)
        async with _factory() as _db:
            await get_rag_service().load_company_stores_from_db(_db)
        logger.info("Company Vector Stores carregados do DB")
    except Exception as _exc:
        logger.warning(f"Não foi possível carregar company stores: {_exc}")

    # Start background checklist refresh loop
    refresh_task = asyncio.create_task(_checklist_refresh_loop())

    yield

    # Shutdown
    refresh_task.cancel()
    logger.info("Shutting down CVM Analyzer application...")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    
    app = FastAPI(
        title="CVM Analyzer API",
        description="API for FRE document analysis and evaluation",
        version="1.0.0",
        lifespan=lifespan
    )

    # Rate limiting
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    
    # CORS middleware - configurable origins
    settings = get_settings()
    origins = settings.cors_origins.split(",") if settings.cors_origins else ["*"]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include API routers
    app.include_router(evaluation_router)
    app.include_router(diff_router)
    app.include_router(chat_router)
    app.include_router(settings_router)
    app.include_router(archive_router)
    app.include_router(cvm_router)
    
    # Serve static frontend files in production
    frontend_dist = Path(__file__).parent.parent / "frontend" / "dist"
    if frontend_dist.exists():
        # Mount known static subdirectories from Vite build output
        for subdir in ("assets", "bg", "images"):
            subdir_path = frontend_dist / subdir
            if subdir_path.exists():
                app.mount(f"/{subdir}", StaticFiles(directory=subdir_path), name=subdir)

        @app.get("/{full_path:path}")
        async def serve_frontend(full_path: str):
            """Serve frontend for non-API routes (SPA fallback)."""
            if full_path.startswith("api/"):
                return {"error": "Not found"}

            # Serve loose static files from dist/ root (e.g. favicon, images)
            if full_path and full_path != "":
                file_path = (frontend_dist / full_path).resolve()
                if file_path.is_relative_to(frontend_dist.resolve()) and file_path.is_file():
                    return FileResponse(file_path)

            # SPA fallback — serve index.html for client-side routing
            index_path = frontend_dist / "index.html"
            if index_path.exists():
                return FileResponse(index_path)

            return {"error": "Frontend not built"}
    
    return app


# Create app instance
app = create_app()


if __name__ == "__main__":
    import uvicorn
    
    _settings = get_settings()
    uvicorn.run(
        "main:app",
        host=_settings.api_host,
        port=_settings.api_port,
        reload=_settings.debug
    )
