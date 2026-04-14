from __future__ import annotations

from dataclasses import asdict
from typing import Any, Literal, Sequence

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

    def _visible_channel_ids(self) -> tuple[int, ...]:
        # Candidate assignments are the signature that a channel has been rebuilt
        # under the staged resolver instead of the legacy one-shot node generator.
        return tuple(self.repository.list_candidate_channel_ids())

    def _visible_node_ids(self, *, channel_ids: Sequence[int]) -> set[str]:
        if not channel_ids:
            return set()
        return set(self.repository.list_node_ids_for_channels(channel_ids=channel_ids, status="active"))

    def _visibility(self) -> tuple[tuple[int, ...], set[str]]:
        channel_ids = self._visible_channel_ids()
        return channel_ids, self._visible_node_ids(channel_ids=channel_ids)

    @staticmethod
    def _remap_related_node(item: dict[str, Any]) -> dict[str, Any]:
        """Map legacy story-count field names from the model layer to message-count API names."""
        if "shared_story_count" in item:
            item["shared_message_count"] = item.pop("shared_story_count")
        if "latest_story_at" in item:
            item["latest_message_at"] = item.pop("latest_story_at")
        return item

    def _filter_node_detail_payload(
        self,
        payload: dict[str, Any],
        *,
        visible_channel_ids: set[int],
        visible_node_ids: set[str],
    ) -> dict[str, Any]:
        parent_event = payload.get("parent_event")
        if parent_event and parent_event.get("node_id") not in visible_node_ids:
            payload["parent_event"] = None

        # Related-entity buckets: filter by visibility and remap field names.
        for bucket in ("events", "people", "nations", "orgs", "places", "themes"):
            payload[bucket] = [
                self._remap_related_node(item)
                for item in payload.get(bucket, [])
                if item.get("node_id") in visible_node_ids
            ]

        # child_events use EventChildSummary, not RelatedNode — no remap needed.
        payload["child_events"] = [
            item
            for item in payload.get("child_events", [])
            if item.get("node_id") in visible_node_ids
        ]

        payload["messages"] = [
            message
            for message in payload.get("messages", [])
            if message.get("channel_id") in visible_channel_ids
        ]
        # Drop the legacy stories field from the serialized dict if present.
        payload.pop("stories", None)
        return payload

    def thresholds_for(self, kind: str) -> HeatPhaseThresholds | None:
        if kind == "theme":
            return self.theme_heat_thresholds
        if kind == "event":
            return self.event_heat_thresholds
        return None

    def list_channels(self) -> dict[str, object]:
        visible_channel_ids, _visible_node_ids = self._visibility()
        visible_channel_id_set = set(visible_channel_ids)
        return {
            "channels": [
                asdict(channel)
                for channel in self.service.channels()
                if channel.channel_id in visible_channel_id_set
            ]
        }

    def list_kind_nodes(self, *, kind: str, limit: int = 50, include_children: bool = False) -> dict[str, object]:
        _visible_channel_ids, visible_node_ids = self._visibility()
        return {
            "kind": kind,
            "nodes": [
                asdict(node)
                for node in self.service.list_nodes(kind=kind, limit=limit, include_children=include_children)
                if node.node_id in visible_node_ids
            ],
        }

    def list_theme_heat(
        self,
        *,
        window: Window,
        phase: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, object]:
        raw = self.list_node_heat(kind="theme", window=window, phase=phase, limit=limit, offset=offset)
        themes = raw["nodes"]
        return {
            "window": raw["window"],
            "total": raw["total"],
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

        _visible_channel_ids, visible_node_ids = self._visibility()
        field_name = WINDOW_FIELD_MAP[window]
        rows = [row for row in self.repository.list_node_heat_rows(kind=kind) if row.node_id in visible_node_ids]
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

        visible_channel_ids, visible_node_ids = self._visibility()
        selected_kinds = tuple(kinds or ("event", "theme"))
        ranked_nodes: list[dict[str, object]] = []
        selected_entries: list[NodeListEntry] = []
        field_name = WINDOW_FIELD_MAP[window]

        for kind in selected_kinds:
            thresholds = self.thresholds_for(kind)
            if phase is not None and thresholds is None:
                continue  # non-phase kinds dropped when phase filter active

            rows = [
                row
                for row in self.repository.list_node_heat_rows(kind=kind)
                if row.node_id in visible_node_ids
            ]

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
            for relation in self.service.snapshot_relations(nodes=visible_entries, channel_ids=visible_channel_ids)
        ]
        return {"window": window, "nodes": ranked_nodes, "relations": relations}

    def get_theme_history(self, slug: str) -> dict[str, object]:
        _visible_channel_ids, visible_node_ids = self._visibility()
        node = self.repository.get_node_by_slug(kind="theme", slug=slug)
        if node is None or node.node_id not in visible_node_ids:
            raise KeyError(slug)
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
        visible_channel_ids, visible_node_ids = self._visibility()
        detail = self.service.node_show_messages(kind=kind, slug=slug)
        if detail is None or detail.node_id not in visible_node_ids:
            raise KeyError(slug)
        return self._filter_node_detail_payload(
            asdict(detail),
            visible_channel_ids=set(visible_channel_ids),
            visible_node_ids=visible_node_ids,
        )

    def get_grouped_messages(self, *, node_id: str, window: str = "1d") -> list[dict]:
        visible_channel_ids = set(self._visible_channel_ids())
        groups = self.service.grouped_messages(node_id=node_id, window=window)
        result = []
        for group in groups:
            filtered_messages = [
                msg
                for msg in group.messages
                if msg.channel_id in visible_channel_ids
            ]
            if not filtered_messages:
                continue
            result.append({
                "group_id": group.group_id,
                "dominant_node_id": group.dominant_node_id,
                "messages": [asdict(msg) for msg in filtered_messages],
                "timestamp_start": group.timestamp_start,
                "timestamp_end": group.timestamp_end,
            })
        return result
