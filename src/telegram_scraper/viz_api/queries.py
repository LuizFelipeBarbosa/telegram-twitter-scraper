from __future__ import annotations

from dataclasses import asdict
from typing import Literal, Sequence

from telegram_scraper.kg.heat_phase import HeatPhaseThresholds
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
    def __init__(
        self,
        database_url: str,
        *,
        theme_heat_thresholds: HeatPhaseThresholds | None = None,
        event_heat_thresholds: HeatPhaseThresholds | None = None,
    ):
        self.repository = PostgresStoryRepository(database_url)
        self.repository.ensure_schema()
        self.service = KGQueryService(self.repository)
        self.theme_heat_thresholds = theme_heat_thresholds
        self.event_heat_thresholds = event_heat_thresholds

    def thresholds_for(self, kind: str) -> HeatPhaseThresholds | None:
        if kind == "theme":
            return self.theme_heat_thresholds
        if kind == "event":
            return self.event_heat_thresholds
        return None

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

    def list_node_heat(
        self,
        *,
        kind: str,
        window: Window,
        phase: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, object]:
        from dataclasses import replace
        from telegram_scraper.kg.heat_phase import PhaseNotSupported, classify_phase

        field_name = WINDOW_FIELD_MAP[window]
        rows = self.repository.list_node_heat_rows(kind=kind)
        thresholds = self.thresholds_for(kind)
        classified = [
            replace(row, phase=classify_phase(row, thresholds))
            for row in rows
        ]
        if phase is not None:
            if thresholds is None:
                raise PhaseNotSupported(kind)
            classified = [r for r in classified if r.phase == phase]
        classified.sort(key=lambda r: (-r.heat_1d, -r.heat_3d, r.display_name))
        total = len(classified)
        paged = classified[offset : offset + limit]
        nodes = [
            {
                "node_id": row.node_id,
                "kind": row.kind,
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
            "kind": kind,
            "total": total,
            "nodes": nodes,
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
        from telegram_scraper.kg.heat_phase import classify_phase

        selected_kinds = tuple(kinds or ("event", "theme"))
        ranked_nodes: list[dict[str, object]] = []
        selected_entries: list[NodeListEntry] = []
        field_name = WINDOW_FIELD_MAP[window]

        for kind in selected_kinds:
            thresholds = self.thresholds_for(kind)
            if phase is not None and thresholds is None:
                continue  # non-phase kinds dropped when phase filter active

            rows = self.repository.list_node_heat_rows(kind=kind)

            for row in rows:
                classified_phase = classify_phase(row, thresholds)
                if phase is not None and classified_phase != phase:
                    continue
                heat_value = getattr(row, field_name)
                entry = NodeListEntry(
                    node_id=row.node_id,
                    kind=row.kind,
                    slug=row.slug,
                    display_name=row.display_name,
                    summary=None,
                    article_count=row.article_count,
                    last_updated=None,
                    child_count=0,
                    parent_event=None,
                )
                selected_entries.append(entry)
                ranked_nodes.append(
                    {
                        "node_id": row.node_id,
                        "kind": row.kind,
                        "slug": row.slug,
                        "display_name": row.display_name,
                        "summary": None,
                        "article_count": row.article_count,
                        "score": heat_value,
                        "heat": heat_value,
                        "phase": classified_phase,
                        "child_count": 0,
                        "parent_event": None,
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
