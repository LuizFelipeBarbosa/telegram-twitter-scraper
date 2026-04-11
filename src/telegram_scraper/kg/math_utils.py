from __future__ import annotations

import math
from collections import Counter
from typing import Iterable, Sequence


STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "has",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "that",
    "the",
    "to",
    "was",
    "were",
    "will",
    "with",
}


def cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    numerator = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return numerator / (left_norm * right_norm)


def average_vectors(vectors: Iterable[Sequence[float]]) -> list[float]:
    rows = [list(vector) for vector in vectors if vector]
    if not rows:
        return []
    length = len(rows[0])
    total = [0.0] * length
    for row in rows:
        for index, value in enumerate(row):
            total[index] += value
    return [value / len(rows) for value in total]


def tokenize(text: str) -> list[str]:
    tokens: list[str] = []
    for raw in text.lower().split():
        token = "".join(char for char in raw if char.isalnum() or char in {"-", "#"})
        token = token.strip("-#")
        if len(token) < 3 or token in STOPWORDS:
            continue
        tokens.append(token)
    return tokens


def extract_keywords(texts: Iterable[str], *, limit: int = 5) -> tuple[str, ...]:
    counts: Counter[str] = Counter()
    for text in texts:
        counts.update(tokenize(text))
    return tuple(word for word, _ in counts.most_common(limit))


def compute_class_tfidf_keywords(cluster_texts: dict[str, Sequence[str]], *, limit: int = 5) -> dict[str, tuple[str, ...]]:
    class_term_counts: dict[str, Counter[str]] = {}
    document_frequency: Counter[str] = Counter()
    total_classes = max(len(cluster_texts), 1)

    for cluster_id, texts in cluster_texts.items():
        counts: Counter[str] = Counter()
        seen: set[str] = set()
        for text in texts:
            tokens = tokenize(text)
            counts.update(tokens)
            seen.update(tokens)
        class_term_counts[cluster_id] = counts
        document_frequency.update(seen)

    keywords: dict[str, tuple[str, ...]] = {}
    for cluster_id, counts in class_term_counts.items():
        total_terms = sum(counts.values()) or 1
        scored: list[tuple[str, float]] = []
        for token, count in counts.items():
            tf = count / total_terms
            idf = math.log((1 + total_classes) / (1 + document_frequency[token])) + 1.0
            scored.append((token, tf * idf))
        scored.sort(key=lambda item: item[1], reverse=True)
        keywords[cluster_id] = tuple(token for token, _ in scored[:limit])
    return keywords


def build_topic_label(keywords: Sequence[str], *, fallback: str) -> str:
    normalized = [word.replace("-", " ").title() for word in keywords if word]
    if not normalized:
        return fallback
    return " / ".join(normalized[:3])
