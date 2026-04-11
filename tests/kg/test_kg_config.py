from __future__ import annotations

import tempfile
import unittest
from os import environ
from pathlib import Path
from unittest.mock import patch

from telegram_scraper.kg.config import KGSettings


class KGSettingsTests(unittest.TestCase):
    def test_defaults_from_mapping(self):
        settings = KGSettings.from_mapping(
            {
                "DATABASE_URL": "postgresql://postgres:postgres@localhost:5432/telegram_kg",
                "REDIS_URL": "redis://localhost:6379/0",
                "PINECONE_API_KEY": "pc-test",
                "OPENAI_API_KEY": "sk-test",
            }
        )

        self.assertEqual(settings.pinecone_index_story, "story-embeddings")
        self.assertEqual(settings.pinecone_index_theme, "theme-centroids")
        self.assertEqual(settings.pinecone_index_event, "event-centroids")
        self.assertEqual(settings.embedding_model, "text-embedding-3-small")
        self.assertEqual(settings.semantic_model, "gpt-5-mini")
        self.assertEqual(settings.stream_key, "telegram:raw")
        self.assertEqual(settings.consumer_group, "segmentation-workers")
        self.assertEqual(settings.vector_dimension, 1536)
        self.assertEqual(settings.semantic_max_chars, 12000)
        self.assertEqual(settings.semantic_batch_size, 8)
        self.assertEqual(settings.historical_extraction_workers, 4)
        self.assertEqual(settings.theme_match_threshold, 0.78)
        self.assertEqual(settings.event_match_threshold, 0.80)
        self.assertEqual(settings.event_match_window_days, 14)

    def test_load_prefers_env_file_over_process_environment(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            env_file = Path(tmpdir) / ".env"
            env_file.write_text(
                "\n".join(
                    [
                        "DATABASE_URL=postgresql://file",
                        "REDIS_URL=redis://file",
                        "PINECONE_API_KEY=file-pinecone",
                        "OPENAI_API_KEY=file-openai",
                    ]
                ),
                encoding="utf-8",
            )

            with patch.dict(environ, {"OPENAI_API_KEY": "process-openai"}, clear=False):
                settings = KGSettings.load(env_file)

            self.assertEqual(settings.openai_api_key, "file-openai")


if __name__ == "__main__":
    unittest.main()
