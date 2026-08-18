# -*- coding: utf-8 -*-
"""FastAPI entrypoint for the video production workbench."""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from web.api.routes import router
from web.core.logging import configure_logging, get_logger
from web.core.settings import APP_HOST, APP_PORT, STATIC_DIR, TEMPLATE_DIR

configure_logging()
logger = get_logger(__name__)


def create_app() -> FastAPI:
    app = FastAPI(title="引流视频生产平台", version="0.2.0")
    app.include_router(router)
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR), check_dir=False), name="static")

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(_request: Request, exc: RequestValidationError):
        logger.warning("Request validation failed: %s", exc)
        return JSONResponse(status_code=400, content={"error": "请求参数无效", "detail": exc.errors()})

    @app.exception_handler(Exception)
    async def general_exception_handler(_request: Request, exc: Exception):
        logger.exception("Unhandled request error")
        return JSONResponse(status_code=500, content={"error": str(exc)})

    @app.get("/")
    async def index() -> FileResponse:
        return FileResponse(str(TEMPLATE_DIR / "index.html"), media_type="text/html")

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    print("=" * 50)
    print("  引流视频生产平台")
    print(f"  http://localhost:{APP_PORT}")
    print("=" * 50)
    uvicorn.run("web.app:app", host=APP_HOST, port=APP_PORT, reload=False, log_config=None)