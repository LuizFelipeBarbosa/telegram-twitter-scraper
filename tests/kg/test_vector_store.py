from __future__ import annotations

import unittest

from telegram_scraper.kg.vector_store import _chunk_vectors_by_bytes


class VectorStoreTests(unittest.TestCase):
    def test_chunk_vectors_by_bytes_splits_large_payloads(self):
        vectors = [
            {"id": "a", "values": [0.1] * 128, "metadata": {"channel_id": 1, "node_ids": ["x"]}},
            {"id": "b", "values": [0.2] * 128, "metadata": {"channel_id": 1, "node_ids": ["y"]}},
            {"id": "c", "values": [0.3] * 128, "metadata": {"channel_id": 1, "node_ids": ["z"]}},
        ]

        batches = _chunk_vectors_by_bytes(vectors, max_bytes=2500)

        self.assertGreater(len(batches), 1)
        self.assertEqual(sum(len(batch) for batch in batches), 3)
        self.assertEqual([vector["id"] for batch in batches for vector in batch], ["a", "b", "c"])


if __name__ == "__main__":
    unittest.main()
