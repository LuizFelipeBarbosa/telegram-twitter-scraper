from __future__ import annotations

from dataclasses import asdict
from typing import Literal, Sequence

from telegram_scraper.kg.models import NodeListEntry
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
        self.repository.ensure_schema()
        self.service = KGQueryService(self.repository)

    def list_channels(self) -> dict[str, object]:
        return {"channels": [asdict(channel) for channel in self.service.channels()]}

    def list_kind_nodes(self, *, kind: str, limit: int = 50, include_children: bool = False) -> dict[str, object]:
        return {
            "kind": kind,
            "nodes": [asdict(node) for node in self.service.list_nodes(kind=kind, limit=limit, include_children=include_children)],
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
        include_children: bool = False,
    ) -> dict[str, object]:
        selected_kinds = tuple(kinds or ("event", "theme"))
        ranked_nodes: list[dict[str, object]] = []
        selected_entries: list[NodeListEntry] = []

        if "theme" in selected_kinds:
            theme_payload = self.list_theme_heat(window=window, phase=phase, limit=limit, offset=0)
            theme_rows = theme_payload["themes"]
            if theme_rows:
                for theme in theme_rows:
                    selected_entries.append(
                        NodeListEntry(
                            node_id=str(theme["node_id"]),
                            kind="theme",
                            slug=str(theme["slug"]),
                            display_name=str(theme["display_name"]),
                            summary=None,
                            article_count=int(theme["article_count"]),
                            last_updated=None,
                            child_count=0,
                            parent_event=None,
                        )
                    )
                    ranked_nodes.append(
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
                            "child_count": 0,
                            "parent_event": None,
                        }
                    )
            else:
                for row in self.service.list_nodes(kind="theme", limit=limit):
                    selected_entries.append(row)
                    ranked_nodes.append(
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
                            "child_count": row.child_count,
                            "parent_event": asdict(row.parent_event) if row.parent_event is not None else None,
                        }
                    )

        for kind in selected_kinds:
            if kind == "theme":
                continue
            for row in self.service.list_nodes(kind=kind, limit=limit, include_children=include_children):
                selected_entries.append(row)
                ranked_nodes.append(
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
                        "child_count": row.child_count,
                        "parent_event": asdict(row.parent_event) if row.parent_event is not None else None,
                    }
                )

        ranked_nodes.sort(key=lambda item: (-float(item["score"]), str(item["display_name"]).lower()))
        ranked_nodes = ranked_nodes[:limit]
        selected_entry_lookup = {row.node_id: row for row in selected_entries}
        visible_entries = [selected_entry_lookup[str(node["node_id"])] for node in ranked_nodes if str(node["node_id"]) in selected_entry_lookup]
        relations = [
            {
                "source": relation.source_node_id,
                "target": relation.target_node_id,
                "type": relation.relation_type,
                "score": relation.score,
            }
            for relation in self.service.snapshot_relations(nodes=visible_entries)
        ]
        return {"window": window, "nodes": ranked_nodes, "relations": relations}

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
