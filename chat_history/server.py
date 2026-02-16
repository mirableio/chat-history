from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Query, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from chat_history.config import load_settings
from chat_history.services import ChatHistoryService


_STATIC_DIR = Path(__file__).resolve().parent / "static"


def _get_service(request: Request) -> ChatHistoryService:
    return request.app.state.chat_history_service


def create_app() -> FastAPI:
    settings = load_settings()
    service = ChatHistoryService(settings)
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

    @api_app.post("/toggle_favorite")
    def toggle_favorite(provider: str, conv_id: str, request: Request):
        is_favorite = _get_service(request).toggle_favorite(provider, conv_id)
        return {
            "provider": provider,
            "conversation_id": conv_id,
            "is_favorite": is_favorite,
        }

    app.mount("/api", api_app)
    app.mount("/", StaticFiles(directory=str(_STATIC_DIR), html=True), name="Static")
    return app
