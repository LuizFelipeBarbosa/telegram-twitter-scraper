from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import re
from typing import Iterable, Sequence
from uuid import uuid4

from telegram_scraper.kg.interfaces import StoryRepository
from telegram_scraper.kg.models import EventHierarchyRef, Node, NodeKind, NodeListEntry, StoryNodeAssignment


SCOPING_ACTOR_KINDS: tuple[NodeKind, ...] = ("nation", "org")
FAMILY_ORDER: tuple[str, ...] = ("operation", "airstrike", "strike", "launch", "talks")
GENERIC_PARENT_MIN_CHILDREN = 2
ACTOR_ADJECTIVES = {
    "iran": "Iranian",
    "israel": "Israeli",
    "united states": "US",
    "u s": "US",
    "us": "US",
    "america": "US",
}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_name(value: str) -> str:
    lowered = value.lower().strip()
    normalized = re.sub(r"[^a-z0-9]+", " ", lowered)
    return re.sub(r"\s+", " ", normalized).strip()


def _slugify(value: str) -> str:
    normalized = _normalize_name(value)
    return normalized.replace(" ", "-") or "event"


def _stable_hash(*parts: object) -> str:
    raw = "||".join(str(part or "") for part in parts)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:8]


def _pick_latest(values: Iterable[datetime | None]) -> datetime | None:
    filtered = [value for value in values if value is not None]
    return max(filtered) if filtered else None


def _pick_earliest(values: Iterable[datetime | None]) -> datetime | None:
    filtered = [value for value in values if value is not None]
    return min(filtered) if filtered else None


def _extract_operation_parent_display(name: str) -> str | None:
    lowered = name.lower()
    true_promise = re.search(r"\b(true promise \d+)\b", lowered)
    if true_promise:
        return f"Operation {true_promise.group(1).title()}"

    operation_match = re.search(r"\b(operation|campaign)\b", name, flags=re.IGNORECASE)
    if operation_match is None:
        return None

    suffix = name[operation_match.start() :]
    suffix = re.split(r"[:(]", suffix, maxsplit=1)[0]
    tokens = suffix.split()
    if not tokens:
        return None

    stop_words = {
        "wave",
        "waves",
        "day",
        "days",
        "retaliatory",
        "regional",
        "targeting",
        "targets",
        "against",
        "on",
        "strike",
        "strikes",
        "operations",
        "ops",
        "mission",
        "missions",
        "missile",
        "missiles",
        "drone",
        "drones",
    }
    kept: list[str] = []
    for index, token in enumerate(tokens):
        cleaned = re.sub(r"[^A-Za-z0-9'-]+", "", token)
        if not cleaned:
            continue
        if index > 0 and cleaned.lower() in stop_words:
            break
        kept.append(cleaned.strip("'\""))
    if len(kept) < 2:
        return None
    if kept[0].lower() not in {"operation", "campaign"}:
        kept.insert(0, "Operation")
    return " ".join(kept)


def _detect_generic_family(name: str) -> str | None:
    lowered = name.lower()
    if re.search(r"\bairstrikes?\b", lowered):
        return "airstrike"
    if re.search(r"\blaunch(?:es)?\b", lowered):
        return "launch"
    if re.search(r"\btalks?\b|\bmeetings?\b|\bconversation\b", lowered):
        return "talks"
    if re.search(r"\bstrikes?\b", lowered):
        return "strike"
    return None


def _extract_label_actor(name: str) -> tuple[str, str] | None:
    patterns = (
        (r"\bus[- ]israeli\b", ("us israeli", "US-Israeli")),
        (r"\biranian\b", ("iran", "Iranian")),
        (r"\bisraeli\b", ("israel", "Israeli")),
        (r"\bidf\b", ("idf", "IDF")),
        (r"\bhezbollah\b", ("hezbollah", "Hezbollah")),
        (r"\birgc\b", ("irgc", "IRGC")),
        (r"\bus\b|\bu\.s\.\b|\bamerican\b", ("united states", "US")),
    )
    lowered = name.lower()
    for pattern, payload in patterns:
        if re.search(pattern, lowered):
            return payload
    return None


def _parse_launch_scope(name: str) -> tuple[str | None, str | None]:
    lowered = name.lower()
    match = re.search(r"launch(?:es)?\s+from\s+(.+?)(?:\s+toward(?:s)?\s+|\s+to\s+)(.+)$", lowered)
    if match is not None:
        return (match.group(1).strip(" ,."), match.group(2).strip(" ,."))  # source, target
    match = re.search(r"launch(?:es)?\s+(?:toward(?:s)?|to)\s+(.+)$", lowered)
    if match is not None:
        return (None, match.group(1).strip(" ,."))
    return (None, None)


def _parse_place_scope(name: str) -> str | None:
    lowered = name.lower()
    matches = list(re.finditer(r"\b(?:in|on|at|near|across|against|toward(?:s)?|to)\s+(.+?)(?:$|\(|,)", lowered))
    if not matches:
        return None
    candidate = matches[-1].group(1).strip(" ,.")
    candidate = re.split(
        r"\b(?:during|after|following|amid|causing|killing|destroying|where|which|that|as|while)\b",
        candidate,
        maxsplit=1,
    )[0].strip(" ,.")
    return candidate or None


def _normalize_place_scope(text: str) -> tuple[str, str] | None:
    normalized = _normalize_name(text)
    if not normalized:
        return None

    if "southern lebanon" in normalized:
        return ("southern lebanon", "Southern Lebanon")
    if "beirut" in normalized:
        return ("beirut", "Beirut")
    if "tehran" in normalized:
        return ("tehran", "Tehran")
    if "tel aviv" in normalized:
        return ("tel aviv", "Tel Aviv")
    if "haifa" in normalized:
        return ("haifa", "Haifa")
    if "central israel" in normalized:
        return ("central israel", "Central Israel")
    if "northern israel" in normalized:
        return ("northern israel", "Northern Israel")
    if "southern israel" in normalized:
        return ("southern israel", "Southern Israel")
    if "occupied palestine" in normalized:
        return ("occupied palestine", "Occupied Palestine")
    if "occupied territories" in normalized:
        return ("occupied territories", "Occupied Territories")
    if normalized.endswith(" lebanon") or normalized == "lebanon":
        return ("lebanon", "Lebanon")
    if normalized.endswith(" israel") or normalized == "israel":
        return ("israel", "Israel")
    if normalized.endswith(" iran") or normalized == "iran":
        return ("iran", "Iran")
    if "," in text:
        trailing = text.split(",")[-1].strip()
        trailing_scope = _normalize_place_scope(trailing)
        if trailing_scope is not None:
            return trailing_scope
    return (normalized, _titleish(text))


def _extract_story_scoping_actor(
    *,
    node: Node,
    story_ids: set[str],
    story_assignments: dict[str, list[StoryNodeAssignment]],
    nodes_by_id: dict[str, Node],
) -> tuple[str, str] | None:
    actor_counts: Counter[str] = Counter()
    actor_labels: dict[str, str] = {}
    normalized_label = node.normalized_name

    for story_id in story_ids:
        for assignment in story_assignments.get(story_id, []):
            related = nodes_by_id.get(assignment.node_id)
            if related is None or related.node_id == node.node_id or related.kind not in SCOPING_ACTOR_KINDS:
                continue
            if related.normalized_name and related.normalized_name not in normalized_label:
                continue
            actor_key, actor_label = _actor_label(related)
            actor_counts[actor_key] += 1
            actor_labels[actor_key] = actor_label

    if not actor_counts:
        return None
    actor_key, _count = actor_counts.most_common(1)[0]
    return actor_key, actor_labels[actor_key]


def _extract_story_scoping_place(
    *,
    node: Node,
    story_ids: set[str],
    story_assignments: dict[str, list[StoryNodeAssignment]],
    nodes_by_id: dict[str, Node],
) -> tuple[str, str] | None:
    place_counts: Counter[str] = Counter()
    place_labels: dict[str, str] = {}
    normalized_label = node.normalized_name

    for story_id in story_ids:
        for assignment in story_assignments.get(story_id, []):
            related = nodes_by_id.get(assignment.node_id)
            if related is None or related.node_id == node.node_id or related.kind != "place":
                continue
            if related.normalized_name and related.normalized_name not in normalized_label:
                continue
            scope = _normalize_place_scope(related.display_name)
            if scope is None:
                continue
            place_key, place_label = scope
            place_counts[place_key] += 1
            place_labels[place_key] = place_label

    if not place_counts:
        return None
    place_key, _count = place_counts.most_common(1)[0]
    return place_key, place_labels[place_key]


def _titleish(text: str) -> str:
    words = [part for part in re.split(r"\s+", text.strip()) if part]
    return " ".join(word.upper() if word.upper() in {"US", "IDF", "IRGC"} else word.capitalize() for word in words)


def _actor_label(node: Node) -> tuple[str, str]:
    key = node.normalized_name
    if node.kind == "nation":
        return key, ACTOR_ADJECTIVES.get(key, node.display_name)
    return key, node.display_name


def _family_display(
    *,
    family: str,
    actor_label: str | None,
    place_label: str | None,
    source_label: str | None = None,
) -> str | None:
    if family == "launch":
        if source_label and place_label:
            return f"Launches from {source_label} toward {place_label}"
        if actor_label and place_label:
            return f"{actor_label} launches toward {place_label}"
        if place_label:
            return f"Launches toward {place_label}"
        return None
    if family == "talks":
        if actor_label and place_label:
            return f"{place_label} talks involving {actor_label}"
        if actor_label:
            return f"{actor_label} talks"
        return None
    if family == "airstrike":
        if actor_label:
            return f"{actor_label} airstrikes"
        if place_label:
            return f"Airstrikes in {place_label}"
        return None
    if family == "strike":
        if actor_label:
            return f"{actor_label} strikes"
        if place_label:
            return f"Strikes in {place_label}"
        return None
    return None


def _generic_group(
    *,
    node: Node,
    story_ids: set[str],
    story_assignments: dict[str, list[StoryNodeAssignment]],
    nodes_by_id: dict[str, Node],
) -> GenericGroupMatch | None:
    family = _detect_generic_family(node.display_name)
    if family is None:
        return None

    actor_key: str | None = None
    actor_label: str | None = None
    parsed_actor = _extract_label_actor(node.display_name)
    if parsed_actor is not None:
        actor_key, actor_label = parsed_actor
    else:
        story_actor = _extract_story_scoping_actor(
            node=node,
            story_ids=story_ids,
            story_assignments=story_assignments,
            nodes_by_id=nodes_by_id,
        )
        if story_actor is not None:
            actor_key, actor_label = story_actor

    if family in {"airstrike", "strike"}:
        if actor_key is None or actor_label is None:
            return None
        display_name = _family_display(
            family=family,
            actor_label=actor_label,
            place_label=None,
        )
        if not display_name:
            return None
        return GenericGroupMatch(
            primary_key=f"{family}|{actor_key}",
            primary_display_name=display_name,
        )

    place_key: str | None = None
    place_label: str | None = None
    source_label: str | None = None
    if family == "launch":
        source_scope, target_scope = _parse_launch_scope(node.display_name)
        if source_scope:
            source_label = _titleish(source_scope)
        if target_scope:
            normalized_target = _normalize_place_scope(target_scope)
            if normalized_target is not None:
                place_key, place_label = normalized_target
    if place_key is None:
        parsed_place = _parse_place_scope(node.display_name)
        if parsed_place:
            normalized_place = _normalize_place_scope(parsed_place)
            if normalized_place is not None:
                place_key, place_label = normalized_place
    if place_key is None:
        story_place = _extract_story_scoping_place(
            node=node,
            story_ids=story_ids,
            story_assignments=story_assignments,
            nodes_by_id=nodes_by_id,
        )
        if story_place is not None:
            place_key, place_label = story_place

    display_name = _family_display(
        family=family,
        actor_label=actor_label,
        place_label=place_label,
        source_label=source_label,
    )
    if not display_name:
        return None
    actor_scope = actor_key or "unknown"
    place_scope = place_key or _normalize_name(source_label or "unknown")
    return GenericGroupMatch(
        primary_key=f"{family}|{actor_scope}|{place_scope}",
        primary_display_name=display_name,
    )


def _synthetic_summary(display_name: str) -> str:
    return f"Parent event grouping related sub-events for {display_name}."


@dataclass(frozen=True)
class GenericGroupMatch:
    primary_key: str
    primary_display_name: str
    fallback_key: str | None = None
    fallback_display_name: str | None = None


@dataclass(frozen=True)
class EventHierarchyRebuildResult:
    parents_created: int
    parents_deleted: int
    child_links_updated: int
    top_level_events: int


@dataclass(frozen=True)
class EventHierarchySnapshot:
    nodes_by_id: dict[str, Node]
    direct_story_ids_by_node: dict[str, set[str]]
    children_by_parent: dict[str, tuple[str, ...]]
    rollup_story_ids_by_node: dict[str, set[str]]
    rollup_last_updated_by_node: dict[str, datetime | None]

    def node(self, node_id: str) -> Node:
        return self.nodes_by_id[node_id]

    def is_parent(self, node_id: str) -> bool:
        return bool(self.children_by_parent.get(node_id))

    def parent_id(self, node_id: str) -> str | None:
        return self.nodes_by_id[node_id].parent_node_id

    def top_level_ids(self) -> tuple[str, ...]:
        return tuple(node_id for node_id, node in self.nodes_by_id.items() if node.parent_node_id is None)

    def descendant_ids(self, node_id: str) -> tuple[str, ...]:
        return (node_id,) + self.children_by_parent.get(node_id, ())

    def ref_for(self, node_id: str) -> EventHierarchyRef:
        node = self.nodes_by_id[node_id]
        return EventHierarchyRef(
            node_id=node.node_id,
            slug=node.slug,
            display_name=node.display_name,
            summary=node.summary,
            article_count=len(self.rollup_story_ids_by_node.get(node_id, set())),
            child_count=len(self.children_by_parent.get(node_id, ())),
            last_updated=self.rollup_last_updated_by_node.get(node_id),
        )

    def entry_for(self, node_id: str) -> NodeListEntry:
        node = self.nodes_by_id[node_id]
        parent_ref = self.ref_for(node.parent_node_id) if node.parent_node_id else None
        return NodeListEntry(
            node_id=node.node_id,
            kind=node.kind,
            slug=node.slug,
            display_name=node.display_name,
            summary=node.summary,
            article_count=len(self.rollup_story_ids_by_node.get(node_id, set())),
            last_updated=self.rollup_last_updated_by_node.get(node_id),
            child_count=len(self.children_by_parent.get(node_id, ())),
            parent_event=parent_ref,
        )


def build_event_hierarchy_snapshot(repository: StoryRepository) -> EventHierarchySnapshot:
    nodes = {node.node_id: node for node in repository.list_nodes(kind="event")}
    assignments = repository.list_story_node_assignments(node_ids=tuple(nodes))
    direct_story_ids_by_node: dict[str, set[str]] = defaultdict(set)
    for assignment in assignments:
        direct_story_ids_by_node[assignment.node_id].add(assignment.story_id)

    children_by_parent: dict[str, list[str]] = defaultdict(list)
    for node in nodes.values():
        if node.parent_node_id and node.parent_node_id in nodes:
            children_by_parent[node.parent_node_id].append(node.node_id)

    child_map = {parent_id: tuple(sorted(child_ids)) for parent_id, child_ids in children_by_parent.items()}
    rollup_story_ids_by_node: dict[str, set[str]] = {}
    rollup_last_updated_by_node: dict[str, datetime | None] = {}
    for node_id, node in nodes.items():
        story_ids = set(direct_story_ids_by_node.get(node_id, set()))
        children = child_map.get(node_id, ())
        for child_id in children:
            story_ids.update(direct_story_ids_by_node.get(child_id, set()))
        rollup_story_ids_by_node[node_id] = story_ids
        rollup_last_updated_by_node[node_id] = _pick_latest(
            [node.last_updated] + [nodes[child_id].last_updated for child_id in children]
        )

    return EventHierarchySnapshot(
        nodes_by_id=nodes,
        direct_story_ids_by_node={node_id: set(story_ids) for node_id, story_ids in direct_story_ids_by_node.items()},
        children_by_parent=child_map,
        rollup_story_ids_by_node=rollup_story_ids_by_node,
        rollup_last_updated_by_node=rollup_last_updated_by_node,
    )


class KGEventHierarchyService:
    def __init__(self, repository: StoryRepository):
        self.repository = repository

    def rebuild(self) -> EventHierarchyRebuildResult:
        all_nodes = {node.node_id: node for node in self.repository.list_nodes()}
        event_nodes = {node.node_id: node for node in all_nodes.values() if node.kind == "event" and node.status == "active"}
        real_events = {node_id: node for node_id, node in event_nodes.items() if node.label_source != "hierarchy_group"}
        synthetic_events = {node_id: node for node_id, node in event_nodes.items() if node.label_source == "hierarchy_group"}

        assignments = self.repository.list_story_node_assignments()
        story_assignments: dict[str, list[StoryNodeAssignment]] = defaultdict(list)
        direct_story_ids_by_event: dict[str, set[str]] = defaultdict(set)
        for assignment in assignments:
            story_assignments[assignment.story_id].append(assignment)
            if assignment.node_id in real_events:
                direct_story_ids_by_event[assignment.node_id].add(assignment.story_id)

        desired_parent_key_by_child: dict[str, str] = {}
        desired_parent_display_by_key: dict[str, str] = {}
        explicit_parent_candidates: dict[str, set[str]] = defaultdict(set)
        generic_groups: dict[str, set[str]] = defaultdict(set)
        generic_fallback_groups: dict[str, set[str]] = defaultdict(set)
        generic_fallback_display_by_key: dict[str, str] = {}

        for node_id, node in real_events.items():
            operation_parent = _extract_operation_parent_display(node.display_name)
            if operation_parent:
                operation_key = f"operation|{_normalize_name(operation_parent)}"
                desired_parent_display_by_key.setdefault(operation_key, operation_parent)
                if _normalize_name(operation_parent) == node.normalized_name:
                    explicit_parent_candidates[operation_key].add(node_id)
                    continue
                desired_parent_key_by_child[node_id] = operation_key
                continue

            generic_group = _generic_group(
                node=node,
                story_ids=direct_story_ids_by_event.get(node_id, set()),
                story_assignments=story_assignments,
                nodes_by_id=all_nodes,
            )
            if generic_group is None:
                continue
            desired_parent_display_by_key.setdefault(generic_group.primary_key, generic_group.primary_display_name)
            generic_groups[generic_group.primary_key].add(node_id)
            if generic_group.fallback_key and generic_group.fallback_display_name:
                generic_fallback_groups[generic_group.fallback_key].add(node_id)
                generic_fallback_display_by_key.setdefault(
                    generic_group.fallback_key,
                    generic_group.fallback_display_name,
                )

        real_by_normalized: dict[str, list[Node]] = defaultdict(list)
        for node in real_events.values():
            real_by_normalized[node.normalized_name].append(node)
        synthetic_by_normalized: dict[str, list[Node]] = defaultdict(list)
        for node in synthetic_events.values():
            synthetic_by_normalized[node.normalized_name].append(node)

        desired_children_by_parent_id: dict[str, set[str]] = defaultdict(set)
        synthetic_parents: dict[str, Node] = {}
        parents_created = 0
        assigned_generic_children: set[str] = set()

        for group_key, child_ids in list(generic_groups.items()):
            if len(child_ids) < GENERIC_PARENT_MIN_CHILDREN:
                continue
            display_name = desired_parent_display_by_key[group_key]
            parent_id, created_node = self._resolve_parent_node(
                group_key=group_key,
                display_name=display_name,
                real_by_normalized=real_by_normalized,
                synthetic_by_normalized=synthetic_by_normalized,
                child_ids=child_ids,
                nodes_by_id=real_events | synthetic_events | synthetic_parents,
            )
            if created_node is not None:
                synthetic_parents[parent_id] = created_node
                parents_created += 1
                synthetic_by_normalized[created_node.normalized_name].append(created_node)
            for child_id in child_ids:
                if child_id != parent_id:
                    desired_children_by_parent_id[parent_id].add(child_id)
                    assigned_generic_children.add(child_id)

        for group_key, child_ids in list(generic_fallback_groups.items()):
            eligible_child_ids = {child_id for child_id in child_ids if child_id not in assigned_generic_children}
            if len(eligible_child_ids) < GENERIC_PARENT_MIN_CHILDREN:
                continue
            display_name = generic_fallback_display_by_key[group_key]
            parent_id, created_node = self._resolve_parent_node(
                group_key=group_key,
                display_name=display_name,
                real_by_normalized=real_by_normalized,
                synthetic_by_normalized=synthetic_by_normalized,
                child_ids=eligible_child_ids,
                nodes_by_id=real_events | synthetic_events | synthetic_parents,
            )
            if created_node is not None:
                synthetic_parents[parent_id] = created_node
                parents_created += 1
                synthetic_by_normalized[created_node.normalized_name].append(created_node)
            for child_id in eligible_child_ids:
                if child_id != parent_id:
                    desired_children_by_parent_id[parent_id].add(child_id)
                    assigned_generic_children.add(child_id)

        for child_id, group_key in desired_parent_key_by_child.items():
            display_name = desired_parent_display_by_key[group_key]
            parent_id, created_node = self._resolve_parent_node(
                group_key=group_key,
                display_name=display_name,
                real_by_normalized=real_by_normalized,
                synthetic_by_normalized=synthetic_by_normalized,
                child_ids={child_id},
                explicit_parent_ids=explicit_parent_candidates.get(group_key, set()),
                nodes_by_id=real_events | synthetic_events | synthetic_parents,
            )
            if created_node is not None:
                synthetic_parents[parent_id] = created_node
                parents_created += 1
                synthetic_by_normalized[created_node.normalized_name].append(created_node)
            if child_id != parent_id:
                desired_children_by_parent_id[parent_id].add(child_id)

        nodes_to_save: list[Node] = []
        desired_parent_id_by_child: dict[str, str] = {}
        for parent_id, child_ids in desired_children_by_parent_id.items():
            for child_id in child_ids:
                desired_parent_id_by_child[child_id] = parent_id

        all_active_event_nodes = event_nodes | synthetic_parents
        child_links_updated = 0
        for node_id, node in real_events.items():
            next_parent_id = desired_parent_id_by_child.get(node_id)
            if node.parent_node_id != next_parent_id:
                child_links_updated += 1
            if node.parent_node_id != next_parent_id:
                nodes_to_save.append(
                    Node(
                        **{**node.__dict__, "parent_node_id": next_parent_id},
                    )
                )

        for parent_id, child_ids in desired_children_by_parent_id.items():
            base_node = synthetic_parents.get(parent_id) or all_active_event_nodes.get(parent_id)
            if base_node is None:
                continue
            is_new_synthetic_parent = parent_id in synthetic_parents
            child_nodes = [real_events[child_id] for child_id in child_ids if child_id in real_events]
            if not child_nodes and base_node.label_source == "hierarchy_group":
                continue
            merged_last_updated = _pick_latest([base_node.last_updated] + [child.last_updated for child in child_nodes])
            merged_start = _pick_earliest([base_node.event_start_at] + [child.event_start_at for child in child_nodes])
            merged_end = _pick_latest([base_node.event_end_at] + [child.event_end_at for child in child_nodes])
            next_summary = base_node.summary if base_node.label_source != "hierarchy_group" else _synthetic_summary(base_node.display_name)
            if (
                is_new_synthetic_parent
                or base_node.parent_node_id is not None
                or base_node.last_updated != merged_last_updated
                or base_node.event_start_at != merged_start
                or base_node.event_end_at != merged_end
                or base_node.summary != next_summary
            ):
                nodes_to_save.append(
                    Node(
                        **{
                            **base_node.__dict__,
                            "parent_node_id": None,
                            "summary": next_summary,
                            "last_updated": merged_last_updated,
                            "event_start_at": merged_start,
                            "event_end_at": merged_end,
                        },
                    )
                )

        stale_synthetic_ids = [
            node_id
            for node_id, node in synthetic_events.items()
            if node_id not in desired_children_by_parent_id and node_id not in synthetic_parents
        ]

        if nodes_to_save:
            deduped = {node.node_id: node for node in nodes_to_save}
            parent_ids = set(desired_children_by_parent_id)
            parents_first = [node for node in deduped.values() if node.node_id in parent_ids]
            remaining = [node for node in deduped.values() if node.node_id not in parent_ids]
            if parents_first:
                self.repository.save_nodes(parents_first)
            if remaining:
                self.repository.save_nodes(remaining)
        if stale_synthetic_ids:
            self.repository.delete_nodes(stale_synthetic_ids)

        top_level_event_ids = {
            node_id
            for node_id in real_events
            if desired_parent_id_by_child.get(node_id) is None
        } | set(desired_children_by_parent_id)
        return EventHierarchyRebuildResult(
            parents_created=parents_created,
            parents_deleted=len(stale_synthetic_ids),
            child_links_updated=child_links_updated,
            top_level_events=len(top_level_event_ids),
        )

    def _resolve_parent_node(
        self,
        *,
        group_key: str,
        display_name: str,
        real_by_normalized: dict[str, list[Node]],
        synthetic_by_normalized: dict[str, list[Node]],
        child_ids: set[str],
        nodes_by_id: dict[str, Node],
        explicit_parent_ids: set[str] | None = None,
    ) -> tuple[str, Node | None]:
        normalized = _normalize_name(display_name)
        explicit_parent_ids = explicit_parent_ids or set()
        if explicit_parent_ids:
            parent_id = sorted(
                explicit_parent_ids,
                key=lambda node_id: (
                    -nodes_by_id[node_id].article_count,
                    -(nodes_by_id[node_id].last_updated.timestamp() if nodes_by_id[node_id].last_updated is not None else 0.0),
                    nodes_by_id[node_id].slug,
                ),
            )[0]
            return parent_id, None

        matching_real = real_by_normalized.get(normalized, [])
        preferred_real = [node for node in matching_real if node.node_id not in child_ids] or matching_real
        if preferred_real:
            chosen = sorted(
                preferred_real,
                key=lambda node: (
                    -node.article_count,
                    -(node.last_updated.timestamp() if node.last_updated is not None else 0.0),
                    node.slug,
                ),
            )[0]
            return chosen.node_id, None

        matching_synthetic = synthetic_by_normalized.get(normalized, [])
        if matching_synthetic:
            chosen = sorted(
                matching_synthetic,
                key=lambda node: (
                    -(node.last_updated.timestamp() if node.last_updated is not None else 0.0),
                    node.slug,
                ),
            )[0]
            return chosen.node_id, None

        existing_slugs = {node.slug for node in nodes_by_id.values()}
        base_slug = _slugify(display_name)
        slug = base_slug if base_slug not in existing_slugs else f"{base_slug}-group-{_stable_hash(group_key)}"
        created = Node(
            node_id=str(uuid4()),
            kind="event",
            slug=slug,
            display_name=display_name,
            canonical_name=display_name,
            normalized_name=normalized,
            summary=_synthetic_summary(display_name),
            aliases=(),
            status="active",
            label_source="hierarchy_group",
            article_count=0,
            created_at=_utc_now(),
            last_updated=_utc_now(),
            event_start_at=None,
            event_end_at=None,
            parent_node_id=None,
        )
        return created.node_id, created
