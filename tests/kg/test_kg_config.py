from __future__ import annotations

import tempfile
import unittest
from os import environ
from pathlib import Path
from unittest.mock import patch

from telegram_scraper.kg.config import KGSettings


_BASE_VALUES = {
    "DATABASE_URL": "postgresql://postgres:postgres@localhost:5432/telegram_kg",
    "REDIS_URL": "redis://localhost:6379/0",
    "PINECONE_API_KEY": "pc-test",
    "OPENAI_API_KEY": "sk-test",
}


def build_settings(**overrides: str) -> KGSettings:
    return KGSettings.from_mapping({**_BASE_VALUES, **overrides})


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
        self.assertEqual(settings.consumer_group, "kg-workers")
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


class KGSettingsHeatThresholdTests(unittest.TestCase):
    def test_defaults_populated(self):
        from telegram_scraper.kg.heat_phase import DEFAULT_THEME_HEAT_THRESHOLDS, DEFAULT_EVENT_HEAT_THRESHOLDS

        settings = build_settings()
        self.assertEqual(settings.theme_heat_thresholds, DEFAULT_THEME_HEAT_THRESHOLDS)
        self.assertEqual(settings.event_heat_thresholds, DEFAULT_EVENT_HEAT_THRESHOLDS)

    def test_theme_phase_disabled(self):
        from telegram_scraper.kg.heat_phase import DEFAULT_EVENT_HEAT_THRESHOLDS

        settings = build_settings(KG_THEME_HEAT_PHASE_ENABLED="0")
        self.assertIsNone(settings.theme_heat_thresholds)
        self.assertEqual(settings.event_heat_thresholds, DEFAULT_EVENT_HEAT_THRESHOLDS)

    def test_event_phase_disabled(self):
        from telegram_scraper.kg.heat_phase import DEFAULT_THEME_HEAT_THRESHOLDS

        settings = build_settings(KG_EVENT_HEAT_PHASE_ENABLED="0")
        self.assertEqual(settings.theme_heat_thresholds, DEFAULT_THEME_HEAT_THRESHOLDS)
        self.assertIsNone(settings.event_heat_thresholds)

    def test_theme_thresholds_json_override(self):
        import json

        custom = {
            "emerging_1d_min": 0.20,
            "emerging_31d_max": 0.03,
            "fading_31d_min": 0.08,
            "fading_1d_max": 0.02,
            "sustained_delta_max": 0.03,
            "flash_3d_min": 0.20,
            "flash_7d_max": 0.03,
        }
        settings = build_settings(KG_THEME_HEAT_THRESHOLDS_JSON=json.dumps(custom))
        self.assertEqual(settings.theme_heat_thresholds.emerging_1d_min, 0.20)
        self.assertEqual(settings.theme_heat_thresholds.flash_3d_min, 0.20)


if __name__ == "__main__":
    unittest.main()
