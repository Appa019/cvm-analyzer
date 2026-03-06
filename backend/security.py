async def get_current_user() -> dict:
    """FastAPI dependency — auth desabilitada para uso local."""
    return {"email": "local", "name": "Local"}
