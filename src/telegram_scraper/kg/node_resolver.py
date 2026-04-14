from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime
import hashlib
import re
from typing import Callable, Iterable, Iterator, Sequence
from uuid import uuid4

from telegram_scraper.kg.config import KGSettings
from telegram_scraper.kg.math_utils import cosine_similarity
from telegram_scraper.kg.models import (
    ExtractedSemanticNode,
    Node,
    NodeCentroidRecord,
    NodeKind,
    NodeSupportRecord,
    StorySemanticExtraction,
)
from telegram_scraper.utils import ensure_utc


NODE_KINDS: tuple[NodeKind, ...] = ("event", "person", "nation", "org", "place", "theme")


def _normalize_name(value: str) -> str:
    lowered = value.lower().strip()
    normalized = re.sub(r"[^a-z0-9]+", " ", lowered)
    return re.sub(r"\s+", " ", normalized).strip()


def _slugify(value: str) -> str:
    normalized = _normalize_name(value)
    if not normalized:
        return "node"
    return normalized.replace(" ", "-")


def _stable_hash(*parts: object) -> str:
    raw = "||".join(str(part or "") for part in parts)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:8]


def _person_middle_initial_variants(value: str) -> set[str]:
    normalized = _normalize_name(value)
    if not normalized:
        return set()
    tokens = normalized.split()
    if len(tokens) < 3:
        return set()
    middle = tokens[1:-1]
    if not middle or all(len(token) > 1 for token in middle):
        return set()
    collapsed = [tokens[0], *[token for token in middle if len(token) > 1], tokens[-1]]
    collapsed = [token for token in collapsed if token]
    if len(collapsed) < 2:
        return set()
    return {" ".join(collapsed)}


def _match_keys_for_text(kind: NodeKind, value: str) -> set[str]:
    normalized = _normalize_name(value)
    if not normalized:
        return set()
    keys = {normalized}
    if kind == "person":
        keys.update(_person_middle_initial_variants(normalized))
    return keys


def _candidate_match_keys(kind: NodeKind, candidate: ExtractedSemanticNode) -> set[str]:
    keys: set[str] = set()
    for value in (candidate.name, *candidate.aliases):
        keys.update(_match_keys_for_text(kind, value))
    return keys


def _node_match_keys(kind: NodeKind, node: Node) -> set[str]:
    keys = _match_keys_for_text(kind, node.normalized_name)
    for alias in node.aliases:
        keys.update(_match_keys_for_text(kind, alias))
    return keys


def _kind_candidates(extraction: StorySemanticExtraction) -> dict[NodeKind, tuple[ExtractedSemanticNode, ...]]:
    return {
        "event": extraction.events,
        "person": extraction.people,
        "nation": extraction.nations,
        "org": extraction.orgs,
        "place": extraction.places,
        "theme": extraction.themes,
    }


def _dedupe_candidates(kind: NodeKind, candidates: Iterable[ExtractedSemanticNode]) -> tuple[ExtractedSemanticNode, ...]:
    seen: set[str] = set()
    ordered: list[ExtractedSemanticNode] = []
    for candidate in candidates:
        if kind == "person":
            keys = _candidate_match_keys(kind, candidate)
            if not keys or keys & seen:
                continue
            seen.update(keys)
        else:
            key = _normalize_name(candidate.name)
            if not key or key in seen:
                continue
            seen.add(key)
        ordered.append(candidate)
    return tuple(ordered)


def iter_extraction_candidates(extraction: StorySemanticExtraction) -> Iterator[tuple[NodeKind, ExtractedSemanticNode]]:
    for kind in NODE_KINDS:
        for candidate in _dedupe_candidates(kind, _kind_candidates(extraction)[kind]):
            yield kind, candidate


def serialize_extraction(extraction: StorySemanticExtraction) -> dict[str, object]:
    def _payload(items: Sequence[ExtractedSemanticNode]) -> list[dict[str, object]]:
        return [
            {
                "name": item.name,
                "summary": item.summary,
                "aliases": list(item.aliases),
                "start_at": item.start_at.isoformat() if item.start_at is not None else None,
                "end_at": item.end_at.isoformat() if item.end_at is not None else None,
            }
            for item in items
        ]

    return {
        "events": _payload(extraction.events),
        "people": _payload(extraction.people),
        "nations": _payload(extraction.nations),
        "orgs": _payload(extraction.orgs),
        "places": _payload(extraction.places),
        "themes": _payload(extraction.themes),
        "primary_event": extraction.primary_event,
    }


@dataclass(frozen=True)
class ResolvedNode:
    node: Node
    confidence: float
    created: bool


@dataclass
class _NodeSupportState:
    story_count: int
    channel_ids: set[int] = field(default_factory=set)
    has_cross_channel_match: bool = False
    pending_story_ids: set[str] = field(default_factory=set)

    @classmethod
    def from_node(cls, node: Node, record: NodeSupportRecord | None) -> "_NodeSupportState":
        if record is None:
            return cls(story_count=max(node.article_count, 0))
        return cls(
            story_count=max(record.story_count, 0),
            channel_ids=set(record.channel_ids),
            has_cross_channel_match=record.has_cross_channel_match,
        )

    @property
    def channel_count(self) -> int:
        return len(self.channel_ids)

    def register_story(self, *, story_id: str, channel_id: int) -> bool:
        is_new_story = story_id not in self.pending_story_ids
        if is_new_story:
            self.pending_story_ids.add(story_id)
            self.story_count += 1
        self.channel_ids.add(channel_id)
        return is_new_story


class NodeResolver:
    def __init__(
        self,
        *,
        settings: KGSettings,
        node_cache: dict[NodeKind, dict[str, Node]],
        support_records: dict[str, NodeSupportRecord],
        theme_centroids: dict[str, list[float]],
        event_centroids: dict[str, list[float]],
        pending_theme_centroids: dict[str, NodeCentroidRecord],
        pending_event_centroids: dict[str, NodeCentroidRecord],
        utc_now: Callable[[], datetime],
    ):
        self.settings = settings
        self.node_cache = node_cache
        self.theme_centroids = theme_centroids
        self.event_centroids = event_centroids
        self.pending_theme_centroids = pending_theme_centroids
        self.pending_event_centroids = pending_event_centroids
        self.utc_now = utc_now
        self.nodes_by_id: dict[str, Node] = {}
        self.node_support: dict[str, _NodeSupportState] = {}
        for nodes in self.node_cache.values():
            for node in nodes.values():
                self.nodes_by_id[node.node_id] = node
                self.node_support[node.node_id] = _NodeSupportState.from_node(node, support_records.get(node.node_id))

    def resolve(
        self,
        *,
        kind: NodeKind,
        candidate: ExtractedSemanticNode,
        embedding: list[float],
        story_id: str,
        channel_id: int,
        story_timestamp: datetime,
        activate_immediately: bool,
    ) -> ResolvedNode:
        existing = self._match_existing_node(kind=kind, candidate=candidate, embedding=embedding)
        if existing is not None:
            support = self._support_state(existing)
            previous_story_count = support.story_count
            is_new_story = support.register_story(story_id=story_id, channel_id=channel_id)
            updated = self._apply_candidate(
                existing,
                candidate=candidate,
                last_updated=story_timestamp,
                article_count=support.story_count if is_new_story else existing.article_count,
            )
            updated = self._maybe_promote(updated, support=support, activate_immediately=activate_immediately)
            self._store_node(updated)
            if is_new_story:
                self._upsert_centroid(updated, embedding=embedding, previous_count=max(previous_story_count, 0))
            confidence = 0.99 if existing.normalized_name == _normalize_name(candidate.name) else 0.95
            if kind in {"theme", "event"} and embedding:
                confidence = max(confidence, self._similarity_for_node(updated, embedding=embedding))
            return ResolvedNode(node=updated, confidence=confidence, created=False)

        created = self._create_node(
            kind=kind,
            candidate=candidate,
            story_timestamp=story_timestamp,
            activate_immediately=activate_immediately,
        )
        support = self._support_state(created)
        support.register_story(story_id=story_id, channel_id=channel_id)
        created = replace(created, article_count=support.story_count)
        created = self._maybe_promote(created, support=support, activate_immediately=activate_immediately)
        self._store_node(created)
        self._upsert_centroid(created, embedding=embedding, previous_count=0)
        return ResolvedNode(node=created, confidence=1.0, created=True)

    def register_cross_channel_support(
        self,
        *,
        node_ids: Sequence[str],
    ) -> list[Node]:
        updated_nodes: list[Node] = []
        for node_id in dict.fromkeys(node_ids):
            node = self.nodes_by_id.get(node_id)
            if node is None or node.kind not in {"event", "theme"}:
                continue
            support = self._support_state(node)
            if support.has_cross_channel_match and node.status == "active":
                continue
            support.has_cross_channel_match = True
            updated = self._maybe_promote(node, support=support, activate_immediately=False)
            if updated != node:
                self._store_node(updated)
                updated_nodes.append(updated)
        return updated_nodes

    def _match_existing_node(
        self,
        *,
        kind: NodeKind,
        candidate: ExtractedSemanticNode,
        embedding: list[float],
    ) -> Node | None:
        normalized_name = _normalize_name(candidate.name)
        nodes = self._ordered_nodes(kind)
        if kind == "person":
            candidate_keys = _candidate_match_keys(kind, candidate)
            for node in nodes:
                if candidate_keys & _node_match_keys(kind, node):
                    return node

        event_parent_ids = {
            node.parent_node_id
            for node in nodes
            if kind == "event" and node.parent_node_id is not None
        }
        for node in nodes:
            if node.normalized_name == normalized_name:
                if kind != "event" or self._event_within_window(node=node, candidate=candidate):
                    return node
        for node in nodes:
            aliases = {_normalize_name(alias) for alias in node.aliases}
            if normalized_name in aliases:
                if kind != "event" or self._event_within_window(node=node, candidate=candidate):
                    return node
        if kind == "theme" and embedding:
            return self._best_centroid_match(
                self.theme_centroids,
                {node.node_id: node for node in nodes},
                embedding=embedding,
                threshold=self.settings.theme_match_threshold,
            )
        if kind == "event" and embedding:
            eligible_nodes = {
                node_id: node
                for node_id, node in self.node_cache[kind].items()
                if node.label_source != "hierarchy_group" and node_id not in event_parent_ids
            }
            matched_node = self._best_centroid_match(
                self.event_centroids,
                eligible_nodes,
                embedding=embedding,
                threshold=self.settings.event_match_threshold,
                event_candidate=candidate,
            )
            if (
                matched_node is not None
                and self._event_within_window(node=matched_node, candidate=candidate)
                and _name_overlap(matched_node.normalized_name, normalized_name) >= 0.35
            ):
                return matched_node
        return None

    def _event_within_window(self, *, node: Node, candidate: ExtractedSemanticNode) -> bool:
        if candidate.start_at is None or node.event_start_at is None:
            return True
        return abs((candidate.start_at.date() - node.event_start_at.date()).days) <= self.settings.event_match_window_days

    def _apply_candidate(
        self,
        node: Node,
        *,
        candidate: ExtractedSemanticNode,
        last_updated: datetime,
        article_count: int,
    ) -> Node:
        aliases = list(node.aliases)
        existing_aliases = {_normalize_name(alias) for alias in aliases}
        candidate_name = candidate.name.strip()
        normalized_candidate_name = _normalize_name(candidate_name)
        if (
            candidate_name
            and normalized_candidate_name
            and normalized_candidate_name != node.normalized_name
            and normalized_candidate_name not in existing_aliases
        ):
            aliases.append(candidate_name)
            existing_aliases.add(normalized_candidate_name)
        for alias in candidate.aliases:
            normalized_alias = _normalize_name(alias)
            if normalized_alias not in existing_aliases and alias.strip():
                aliases.append(alias.strip())
                existing_aliases.add(normalized_alias)
        event_start = node.event_start_at
        if candidate.start_at is not None:
            candidate_start = ensure_utc(candidate.start_at) or candidate.start_at
            event_start = candidate_start if event_start is None else min(event_start, candidate_start)
        event_end = node.event_end_at
        if candidate.end_at is not None:
            candidate_end = ensure_utc(candidate.end_at) or candidate.end_at
            event_end = candidate_end if event_end is None else max(event_end, candidate_end)
        return replace(
            node,
            summary=node.summary or candidate.summary,
            aliases=tuple(aliases),
            article_count=article_count,
            last_updated=max(node.last_updated or last_updated, last_updated),
            event_start_at=event_start,
            event_end_at=event_end,
        )

    def _create_node(
        self,
        *,
        kind: NodeKind,
        candidate: ExtractedSemanticNode,
        story_timestamp: datetime,
        activate_immediately: bool,
    ) -> Node:
        slug = self._unique_slug(kind=kind, display_name=candidate.name, event_start_at=candidate.start_at)
        return Node(
            node_id=str(uuid4()),
            kind=kind,
            slug=slug,
            display_name=candidate.name.strip(),
            canonical_name=candidate.name.strip(),
            normalized_name=_normalize_name(candidate.name),
            summary=candidate.summary,
            aliases=tuple(dict.fromkeys(alias.strip() for alias in candidate.aliases if alias.strip())),
            status=self._initial_status(kind=kind, activate_immediately=activate_immediately),
            article_count=0,
            created_at=self.utc_now(),
            last_updated=story_timestamp,
            event_start_at=ensure_utc(candidate.start_at) if candidate.start_at is not None else None,
            event_end_at=ensure_utc(candidate.end_at) if candidate.end_at is not None else None,
        )

    def _unique_slug(
        self,
        *,
        kind: NodeKind,
        display_name: str,
        event_start_at: datetime | None,
    ) -> str:
        base = _slugify(display_name)
        existing = {node.slug for node in self.node_cache[kind].values()}
        if base not in existing:
            return base
        if kind == "event" and event_start_at is not None:
            dated = f"{base}-{event_start_at.date().isoformat()}"
            if dated not in existing:
                return dated
        suffix = event_start_at.isoformat() if event_start_at is not None else ""
        return f"{base}-{_stable_hash(kind, display_name, suffix)}"

    def _best_centroid_match(
        self,
        centroids: dict[str, list[float]],
        nodes: dict[str, Node],
        *,
        embedding: list[float],
        threshold: float,
        event_candidate: ExtractedSemanticNode | None = None,
    ) -> Node | None:
        best_node: Node | None = None
        best_score = threshold
        for node_id, centroid in centroids.items():
            if not centroid:
                continue
            node = nodes.get(node_id)
            if node is None:
                continue
            if event_candidate is not None and not self._event_within_window(node=node, candidate=event_candidate):
                continue
            similarity = cosine_similarity(centroid, embedding)
            if similarity > best_score or (
                best_node is None and similarity >= best_score
            ) or (
                similarity == best_score
                and best_node is not None
                and best_node.status != "active"
                and node.status == "active"
            ):
                best_score = similarity
                best_node = node
        return best_node

    def _similarity_for_node(self, node: Node, *, embedding: list[float]) -> float:
        if node.kind == "theme":
            return cosine_similarity(self.theme_centroids.get(node.node_id, []), embedding)
        if node.kind == "event":
            return cosine_similarity(self.event_centroids.get(node.node_id, []), embedding)
        return 0.0

    def _upsert_centroid(self, node: Node, *, embedding: list[float], previous_count: int) -> None:
        if not embedding or node.kind not in {"theme", "event"}:
            return
        centroid_store = self.theme_centroids if node.kind == "theme" else self.event_centroids
        current = centroid_store.get(node.node_id, [])
        if current and previous_count > 0:
            updated = [
                (current[index] * previous_count + embedding[index]) / (previous_count + 1)
                for index in range(len(current))
            ]
        else:
            updated = embedding
        record = NodeCentroidRecord(
            node_id=node.node_id,
            kind=node.kind,
            embedding=updated,
            display_name=node.display_name,
            normalized_name=node.normalized_name,
            event_start_at=node.event_start_at,
            event_end_at=node.event_end_at,
        )
        centroid_store[node.node_id] = updated
        if node.kind == "theme":
            self.pending_theme_centroids[node.node_id] = record
        else:
            self.pending_event_centroids[node.node_id] = record

    def _ordered_nodes(self, kind: NodeKind) -> list[Node]:
        return sorted(
            self.node_cache[kind].values(),
            key=lambda node: (
                node.status != "active",
                -node.article_count,
                -(node.last_updated.timestamp() if node.last_updated is not None else 0.0),
                node.slug,
            ),
        )

    def _support_state(self, node: Node) -> _NodeSupportState:
        support = self.node_support.get(node.node_id)
        if support is None:
            support = _NodeSupportState.from_node(node, None)
            self.node_support[node.node_id] = support
        return support

    def _store_node(self, node: Node) -> None:
        self.node_cache[node.kind][node.node_id] = node
        self.nodes_by_id[node.node_id] = node

    def _initial_status(self, *, kind: NodeKind, activate_immediately: bool) -> str:
        if kind not in {"event", "theme"} or activate_immediately:
            return "active"
        return "candidate"

    def _maybe_promote(self, node: Node, *, support: _NodeSupportState, activate_immediately: bool) -> Node:
        if node.kind not in {"event", "theme"} or node.status == "active":
            return node
        if activate_immediately or support.story_count >= 2 or support.channel_count >= 2 or support.has_cross_channel_match:
            return replace(node, status="active")
        return node


def _name_overlap(left: str, right: str) -> float:
    left_tokens = set(left.split())
    right_tokens = set(right.split())
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / max(len(left_tokens), len(right_tokens))
