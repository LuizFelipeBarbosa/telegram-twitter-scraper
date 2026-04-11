from __future__ import annotations

from dataclasses import asdict
from typing import Literal, Sequence

from telegram_scraper.kg.repository import PostgresStoryRepository
from telegram_scraper.kg.services import KGQueryService


Window = Literal["1d", "3d", "5d", "7d", "14d", "31d"]

WINDOW_FIELD_MAP: dict[Window, str] = {
    "1d": "heat_1d",
    "3d": "heat_3d",
    "5d": "heat_5d",
    "7d": "heat_7d",
    "14d": "heat_14d",
    "31d": "heat_31d",
}


class VisualizationQueries:
    def __init__(self, database_url: str):
        self.repository = PostgresStoryRepository(database_url)
        self.service = KGQueryService(self.repository)

    def list_channels(self) -> dict[str, object]:
        return {"channels": [asdict(channel) for channel in self.service.channels()]}

    def list_kind_nodes(self, *, kind: str, limit: int = 50) -> dict[str, object]:
        return {
            "kind": kind,
            "nodes": [asdict(node) for node in self.service.list_nodes(kind=kind, limit=limit)],
        }

    def list_theme_heat(
        self,
        *,
        window: Window,
        phase: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, object]:
        field_name = WINDOW_FIELD_MAP[window]
        rows = self.repository.list_theme_heat(phase=phase)
        paged = rows[offset : offset + limit]
        themes = [
            {
                "node_id": row.node_id,
                "slug": row.slug,
                "display_name": row.display_name,
                "article_count": row.article_count,
                "heat": getattr(row, field_name),
                "phase": row.phase,
            }
            for row in paged
        ]
        return {
            "window": window,
            "total": len(rows),
            "themes": themes,
            "topics": themes,
        }

    def get_graph_snapshot(
        self,
        *,
        window: Window,
        kinds: Sequence[str] | None = None,
        phase: str | None = None,
        limit: int = 300,
    ) -> dict[str, object]:
        selected_kinds = tuple(kinds or ("event", "theme"))
        nodes: list[dict[str, object]] = []

        if "theme" in selected_kinds:
            theme_payload = self.list_theme_heat(window=window, phase=phase, limit=limit, offset=0)
            theme_rows = theme_payload["themes"]
            if theme_rows:
                for theme in theme_rows:
                    nodes.append(
                        {
                            "node_id": theme["node_id"],
                            "kind": "theme",
                            "slug": theme["slug"],
                            "display_name": theme["display_name"],
                            "summary": None,
                            "article_count": theme["article_count"],
                            "score": theme["heat"],
                            "heat": theme["heat"],
                            "phase": theme["phase"],
                        }
                    )
            else:
                for row in self.service.list_nodes(kind="theme", limit=limit):
                    nodes.append(
                        {
                            "node_id": row.node_id,
                            "kind": row.kind,
                            "slug": row.slug,
                            "display_name": row.display_name,
                            "summary": row.summary,
                            "article_count": row.article_count,
                            "score": float(row.article_count),
                            "heat": None,
                            "phase": None,
                        }
                    )

        for kind in selected_kinds:
            if kind == "theme":
                continue
            for row in self.service.list_nodes(kind=kind, limit=limit):
                nodes.append(
                    {
                        "node_id": row.node_id,
                        "kind": row.kind,
                        "slug": row.slug,
                        "display_name": row.display_name,
                        "summary": row.summary,
                        "article_count": row.article_count,
                        "score": float(row.article_count),
                        "heat": None,
                        "phase": None,
                    }
                )

        nodes.sort(key=lambda item: (-float(item["score"]), str(item["display_name"]).lower()))
        nodes = nodes[:limit]
        node_ids = {str(node["node_id"]) for node in nodes}

        relation_map: dict[tuple[str, str, str], dict[str, object]] = {}
        for node_id in node_ids:
            for relation in self.repository.list_node_relations(node_id):
                if relation.source_node_id not in node_ids or relation.target_node_id not in node_ids:
                    continue
                key = (relation.source_node_id, relation.target_node_id, relation.relation_type)
                relation_map[key] = {
                    "source": relation.source_node_id,
                    "target": relation.target_node_id,
                    "type": relation.relation_type,
                    "score": relation.score,
                }

        relations = sorted(relation_map.values(), key=lambda item: (-float(item["score"]), item["source"], item["target"]))
        return {"window": window, "nodes": nodes, "relations": relations}

    def get_theme_history(self, slug: str) -> dict[str, object]:
        history = self.service.theme_history(slug)
        if not history:
            raise KeyError(slug)
        first = history[0]
        return {
            "node_id": first.node_id,
            "slug": first.slug,
            "display_name": first.display_name,
            "history": [
                {
                    "date": point.date,
                    "article_count": point.article_count,
                    "centroid_drift": point.centroid_drift,
                }
                for point in history
            ],
        }

    def get_node_detail(self, *, kind: str, slug: str) -> dict[str, object]:
        detail = self.service.node_show(kind=kind, slug=slug)
        if detail is None:
            raise KeyError(slug)
        return asdict(detail)
