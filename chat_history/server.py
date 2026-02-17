from __future__ import annotations

from contextlib import asynccontextmanager
from importlib.metadata import PackageNotFoundError, version as package_version
from pathlib import Path

from fastapi import FastAPI, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from chat_history import __version__
from chat_history.config import load_settings
from chat_history.services import ChatHistoryService


_STATIC_DIR = Path(__file__).resolve().parent / "static"
_INDEX_FILE = _STATIC_DIR / "index.html"


def _resolve_asset_version() -> str:
    try:
        return package_version("chat-history")
    except PackageNotFoundError:
        return __version__


def _render_index_html(asset_version: str) -> str:
    html = _INDEX_FILE.read_text(encoding="utf-8")
    return html.replace("__ASSET_VERSION__", asset_version)


def _get_service(request: Request) -> ChatHistoryService:
    return request.app.state.chat_history_service


def create_app() -> FastAPI:
    settings = load_settings()
    service = ChatHistoryService(settings)
    asset_version = _resolve_asset_version()
    index_html = _render_index_html(asset_version)
    api_app = FastAPI(title="API")
    api_app.state.chat_history_service = service

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        service.load()
        app.state.chat_history_service = service
        api_app.state.chat_history_service = service
        yield

    app = FastAPI(lifespan=lifespan)

    @api_app.get("/conversations")
    def get_conversations(request: Request):
        return JSONResponse(content=_get_service(request).list_conversations())

    @api_app.get("/conversations/{provider}/{conv_id}/messages")
    def get_messages(provider: str, conv_id: str, request: Request):
        data = _get_service(request).get_messages(provider, conv_id)
        if data is None:
            return JSONResponse(content={"error": "Invalid conversation ID"}, status_code=404)
        return JSONResponse(content=data)

    @api_app.get("/activity")
    def get_activity(request: Request):
        return JSONResponse(content=_get_service(request).get_activity())

    @api_app.get("/activity/day")
    def get_activity_day(
        request: Request,
        date: str = Query(..., pattern=r"^\d{4}-\d{2}-\d{2}$"),
        provider: str | None = Query(default=None),
    ):
        return JSONResponse(
            content=_get_service(request).get_activity_day(day=date, provider=provider)
        )

    @api_app.get("/statistics")
    def get_statistics(request: Request):
        return JSONResponse(content=_get_service(request).get_statistics())

    @api_app.get("/ai-cost")
    def get_token_statistics(request: Request):
        return JSONResponse(content=_get_service(request).get_token_statistics())

    @api_app.get("/search")
    def search_conversations(
        request: Request,
        query: str = Query(..., min_length=2, description="Search query"),
    ):
        return JSONResponse(content=_get_service(request).search(query))

    @api_app.get("/assets/{provider}/{asset_id}")
    def get_asset(provider: str, asset_id: str, request: Request):
        asset = _get_service(request).get_asset(provider, asset_id)
        if asset is None:
            return JSONResponse(content={"error": "Asset not found"}, status_code=404)
        response = FileResponse(path=str(asset.path), media_type=asset.media_type)
        response.headers["Cache-Control"] = "private, max-age=86400"
        return response

    @api_app.post("/toggle_favorite")
    def toggle_favorite(provider: str, conv_id: str, request: Request):
        is_favorite = _get_service(request).toggle_favorite(provider, conv_id)
        return {
            "provider": provider,
            "conversation_id": conv_id,
            "is_favorite": is_favorite,
        }

    @app.get("/", include_in_schema=False)
    def get_index():
        return HTMLResponse(content=index_html)

    @app.get("/favicon.ico", include_in_schema=False)
    def get_favicon():
        return FileResponse(path=str(_STATIC_DIR / "favicon.ico"))

    app.mount("/api", api_app)
    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")
    return app
