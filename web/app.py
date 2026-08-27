# -*- coding: utf-8 -*-
"""FastAPI entrypoint for the video production workbench."""
import sys
from contextlib import asynccontextmanager
from time import perf_counter
from pathlib import Path
from uuid import uuid4

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from web.api.routes import router
from web.core.logging import configure_logging, get_logger, log_request
from web.core.settings import APP_HOST, APP_PORT, APP_RELOAD, STATIC_DIR
from web.services.canvas_compose import recover_compose_jobs
from web.services.canvas_generation import recover_generation_jobs
from web.services.canvas_image_processing import recover_image_processing_jobs

configure_logging()
logger = get_logger(__name__)


def create_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        recovered_generation = recover_generation_jobs()
        recovered_image = recover_image_processing_jobs()
        recovered_compose = recover_compose_jobs()
        recovered = recovered_generation + recovered_image + recovered_compose
        if recovered:
            logger.info(
                "Recovered unfinished jobs: kling=%s image=%s compose=%s",
                recovered_generation,
                recovered_image,
                recovered_compose,
            )
        yield

    app = FastAPI(title="引流视频生产平台", version="0.2.0", lifespan=lifespan)
    app.include_router(router)
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR), check_dir=False), name="static")

    @app.middleware("http")
    async def request_logging(request: Request, call_next):
        request_id = request.headers.get("X-Request-ID", uuid4().hex[:8])
        started_at = perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            logger.exception(
                "HTTP failed request_id=%s method=%s path=%s",
                request_id,
                request.method,
                request.url.path,
            )
            raise

        response.headers["X-Request-ID"] = request_id
        log_request(
            logger,
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=(perf_counter() - started_at) * 1000,
            request_id=request_id,
        )
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(_request: Request, exc: RequestValidationError):
        logger.warning("Request validation failed: %s", exc)
        return JSONResponse(status_code=400, content={"error": "请求参数无效", "detail": exc.errors()})

    @app.exception_handler(Exception)
    async def general_exception_handler(_request: Request, exc: Exception):
        logger.exception("Unhandled request error")
        return JSONResponse(status_code=500, content={"error": str(exc)})

    def react_entry() -> FileResponse:
        entry = STATIC_DIR / "canvas-app" / "index.html"
        if not entry.exists():
            raise HTTPException(status_code=503, detail="React 前端尚未构建，请先运行 start_dev.bat")
        return FileResponse(str(entry), media_type="text/html")

    @app.get("/")
    async def index() -> FileResponse:
        return react_entry()

    @app.get("/canvas-mvp")
    async def canvas_mvp() -> FileResponse:
        """React Flow canvas; it does not trigger production jobs."""
        return react_entry()

    @app.get("/workflow/{step}")
    async def workflow_step(step: str) -> FileResponse:
        allowed_steps = {"assets", "image-processing", "prompts", "generator", "timeline", "compose", "sound", "output"}
        if step not in allowed_steps:
            raise HTTPException(status_code=404, detail="工作流页面不存在")
        return react_entry()

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    print("=" * 50)
    print("  引流视频生产平台")
    print(f"  http://localhost:{APP_PORT}")
    print("=" * 50)
    uvicorn.run(
        "web.app:app",
        host=APP_HOST,
        port=APP_PORT,
        reload=APP_RELOAD,
        use_colors=True,
        log_config=None,
        access_log=False,
    )
