from __future__ import annotations

from typing import Annotated, List, Optional

from fastapi import FastAPI, HTTPException, Query

from telegram_scraper.kg.config import KGSettings
from telegram_scraper.viz_api.cache import RedisResponseCache
from telegram_scraper.viz_api.queries import VisualizationQueries
from telegram_scraper.viz_api.schemas import (
    ChannelsResponse,
    GraphSnapshotResponse,
    HealthResponse,
    NodeDetailResponse,
    NodeListResponse,
    ThemesHeatResponse,
    ThemeHistoryResponse,
    Window,
)


def create_app(settings: KGSettings) -> FastAPI:
    app = FastAPI(title="Telegram KG Visualization API", version="0.2.0")
    queries = VisualizationQueries(
        settings.database_url,
        theme_heat_thresholds=settings.theme_heat_thresholds,
        event_heat_thresholds=settings.event_heat_thresholds,
    )
    cache = RedisResponseCache(settings.redis_url)

    @app.get("/api/health", response_model=HealthResponse)
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/channels", response_model=ChannelsResponse)
    def channels() -> dict:
        return cache.get_or_set("channels", {}, ttl_seconds=60 * 60, loader=queries.list_channels)

    @app.get("/api/themes/heat", response_model=ThemesHeatResponse)
    def themes_heat(
        window: Window = Query(default="7d"),
        phase: Optional[str] = Query(default=None),
        limit: int = Query(default=50, ge=1, le=300),
        offset: int = Query(default=0, ge=0),
    ) -> dict:
        params = {"window": window, "phase": phase, "limit": limit, "offset": offset}
        return cache.get_or_set(
            "themes_heat",
            params,
            ttl_seconds=15 * 60,
            loader=lambda: queries.list_theme_heat(window=window, phase=phase, limit=limit, offset=offset),
        )

    @app.get("/api/topics/heat", response_model=ThemesHeatResponse)
    def topics_heat_alias(
        window: Window = Query(default="7d"),
        phase: Optional[str] = Query(default=None),
        limit: int = Query(default=50, ge=1, le=300),
        offset: int = Query(default=0, ge=0),
    ) -> dict:
        return themes_heat(window=window, phase=phase, limit=limit, offset=offset)

    @app.get("/api/graph/snapshot", response_model=GraphSnapshotResponse)
    def graph_snapshot(
        window: Window = Query(default="7d"),
        phase: Optional[str] = Query(default=None),
        limit: int = Query(default=300, ge=1, le=300),
        kind: Annotated[Optional[List[str]], Query()] = None,
    ) -> dict:
        params = {"window": window, "phase": phase, "limit": limit, "kind": kind or []}
        return cache.get_or_set(
            "graph_snapshot",
            params,
            ttl_seconds=15 * 60,
            loader=lambda: queries.get_graph_snapshot(window=window, phase=phase, limit=limit, kinds=kind),
        )

    def _list_nodes(kind: str, limit: int) -> dict:
        return cache.get_or_set(
            "node_list",
            {"kind": kind, "limit": limit},
            ttl_seconds=15 * 60,
            loader=lambda: queries.list_kind_nodes(kind=kind, limit=limit),
        )

    @app.get("/api/events", response_model=NodeListResponse)
    def events(limit: int = Query(default=50, ge=1, le=500)) -> dict:
        return _list_nodes("event", limit)

    @app.get("/api/people", response_model=NodeListResponse)
    def people(limit: int = Query(default=50, ge=1, le=500)) -> dict:
        return _list_nodes("person", limit)

    @app.get("/api/nations", response_model=NodeListResponse)
    def nations(limit: int = Query(default=50, ge=1, le=500)) -> dict:
        return _list_nodes("nation", limit)

    @app.get("/api/orgs", response_model=NodeListResponse)
    def orgs(limit: int = Query(default=50, ge=1, le=500)) -> dict:
        return _list_nodes("org", limit)

    @app.get("/api/places", response_model=NodeListResponse)
    def places(limit: int = Query(default=50, ge=1, le=500)) -> dict:
        return _list_nodes("place", limit)

    @app.get("/api/themes", response_model=NodeListResponse)
    def themes(limit: int = Query(default=50, ge=1, le=500)) -> dict:
        return _list_nodes("theme", limit)

    @app.get("/api/themes/{slug}/history", response_model=ThemeHistoryResponse)
    def theme_history(slug: str) -> dict:
        try:
            return cache.get_or_set(
                "theme_history",
                {"slug": slug},
                ttl_seconds=60 * 60,
                loader=lambda: queries.get_theme_history(slug),
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Theme not found") from exc

    @app.get("/api/topics/{slug}/timeline")
    def topic_timeline_alias(slug: str) -> dict:
        history = theme_history(slug)
        return {
            "topic_id": history["slug"],
            "timeline": history["history"],
            "events": [],
        }

    @app.get("/api/nodes/{kind}/{slug}", response_model=NodeDetailResponse)
    def node_detail(kind: str, slug: str) -> dict:
        try:
            return cache.get_or_set(
                "node_detail",
                {"kind": kind, "slug": slug},
                ttl_seconds=60 * 60,
                loader=lambda: queries.get_node_detail(kind=kind, slug=slug),
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Node not found") from exc

    @app.get("/api/topics/{slug}/related", response_model=NodeDetailResponse)
    def topic_related_alias(slug: str) -> dict:
        try:
            return node_detail("theme", slug)
        except HTTPException as exc:
            raise HTTPException(status_code=404, detail="Theme not found") from exc

    @app.get("/api/topics/{slug}/stories")
    def topic_stories_alias(
        slug: str,
        limit: int = Query(default=20, ge=1, le=100),
        offset: int = Query(default=0, ge=0),
    ) -> dict:
        try:
            detail = queries.get_node_detail(kind="theme", slug=slug)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Theme not found") from exc
        stories = detail["stories"][offset : offset + limit]
        return {
            "topic_id": slug,
            "limit": limit,
            "offset": offset,
            "total": len(detail["stories"]),
            "stories": stories,
        }

    return app
