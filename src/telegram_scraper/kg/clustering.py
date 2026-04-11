from __future__ import annotations

from typing import Sequence


class HDBSCANTopicClusterer:
    def __init__(self, *, min_cluster_size: int = 2):
        self.min_cluster_size = max(min_cluster_size, 2)

    def cluster(self, embeddings: dict[str, list[float]]) -> dict[str, int]:
        story_ids = list(embeddings)
        if not story_ids:
            return {}
        if len(story_ids) == 1:
            return {story_ids[0]: 0}

        try:
            import numpy as np
            from sklearn.preprocessing import normalize
            from umap import UMAP
            import hdbscan
        except ImportError as exc:  # pragma: no cover - exercised only without runtime deps.
            raise RuntimeError(
                "umap-learn and hdbscan are not installed. Install project dependencies before using KG clustering."
            ) from exc

        matrix = np.array([embeddings[story_id] for story_id in story_ids], dtype=float)
        matrix = normalize(matrix)

        if len(story_ids) >= 3:
            reducer = UMAP(
                n_components=min(5, matrix.shape[1], len(story_ids) - 1),
                n_neighbors=max(2, min(15, len(story_ids) - 1)),
                metric="cosine",
                random_state=42,
            )
            reduced = reducer.fit_transform(matrix)
        else:
            reduced = matrix

        clusterer = hdbscan.HDBSCAN(
            min_cluster_size=min(self.min_cluster_size, len(story_ids)),
            metric="euclidean",
            cluster_selection_method="eom",
        )
        labels = clusterer.fit_predict(reduced)

        next_noise_label = (max(labels) + 1) if len(labels) else 0
        assignments: dict[str, int] = {}
        for story_id, label in zip(story_ids, labels):
            if int(label) == -1:
                assignments[story_id] = next_noise_label
                next_noise_label += 1
            else:
                assignments[story_id] = int(label)
        return assignments


def partition_embeddings(
    story_ids: Sequence[str],
    embeddings: dict[str, list[float]],
) -> tuple[list[str], list[str], float]:
    if len(story_ids) < 2:
        return list(story_ids), [], 0.0

    try:
        import numpy as np
        from sklearn.cluster import KMeans
        from sklearn.metrics import silhouette_score
        from sklearn.preprocessing import normalize
    except ImportError as exc:  # pragma: no cover - exercised only without runtime deps.
        raise RuntimeError("scikit-learn is not installed. Install project dependencies before using KG splitting.") from exc

    matrix = np.array([embeddings[story_id] for story_id in story_ids], dtype=float)
    matrix = normalize(matrix)
    kmeans = KMeans(n_clusters=2, n_init=10, random_state=42)
    labels = kmeans.fit_predict(matrix)
    silhouette = float(silhouette_score(matrix, labels)) if len(story_ids) > 2 else 0.0

    left = [story_id for story_id, label in zip(story_ids, labels) if int(label) == 0]
    right = [story_id for story_id, label in zip(story_ids, labels) if int(label) == 1]
    return left, right, silhouette
