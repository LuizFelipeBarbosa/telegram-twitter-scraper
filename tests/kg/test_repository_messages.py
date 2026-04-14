from __future__ import annotations

import unittest
from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock, call, patch

from telegram_scraper.kg.models import (
    CrossChannelMessageMatch,
    MessageEmbeddingRecord,
    MessageMatch,
    MessageNodeAssignment,
    MessageSemanticRecord,
    RawMessage,
)
from telegram_scraper.kg.repository import (
    PostgresStoryRepository,
    _cross_channel_message_match_from_row,
    _message_node_assignment_from_row,
    _message_semantic_from_row,
)
from telegram_scraper.kg.vector_store import PineconeVectorStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOW = datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc)


def _make_repo() -> PostgresStoryRepository:
    return PostgresStoryRepository(database_url="postgresql://fake/db")


def _make_cursor(rows: list[Any] | None = None, fetchone_row: Any = None):
    cursor = MagicMock()
    cursor.__enter__ = lambda s: s
    cursor.__exit__ = MagicMock(return_value=False)
    cursor.fetchall.return_value = rows or []
    cursor.fetchone.return_value = fetchone_row
    return cursor


def _make_connection(cursor):
    conn = MagicMock()
    conn.__enter__ = lambda s: s
    conn.__exit__ = MagicMock(return_value=False)
    conn.cursor.return_value = cursor
    return conn


# ---------------------------------------------------------------------------
# Row-deserializer unit tests
# ---------------------------------------------------------------------------


class MessageSemanticFromRowTests(unittest.TestCase):
    def test_deserializes_full_row(self):
        row = (123, 456, {"key": "val"}, "uuid-node", _NOW, _NOW)
        record = _message_semantic_from_row(row)
        self.assertEqual(record.channel_id, 123)
        self.assertEqual(record.message_id, 456)
        self.assertEqual(record.extraction_payload, {"key": "val"})
        self.assertEqual(record.primary_event_node_id, "uuid-node")
        self.assertIsNotNone(record.extracted_at)
        self.assertIsNotNone(record.updated_at)

    def test_nullable_fields(self):
        row = (1, 2, {}, None, None, None)
        record = _message_semantic_from_row(row)
        self.assertIsNone(record.primary_event_node_id)
        self.assertIsNone(record.extracted_at)
        self.assertIsNone(record.updated_at)


class MessageNodeAssignmentFromRowTests(unittest.TestCase):
    def test_deserializes_full_row(self):
        row = (10, 20, "node-uuid", 0.95, _NOW, True)
        assignment = _message_node_assignment_from_row(row)
        self.assertEqual(assignment.channel_id, 10)
        self.assertEqual(assignment.message_id, 20)
        self.assertEqual(assignment.node_id, "node-uuid")
        self.assertAlmostEqual(assignment.confidence, 0.95)
        self.assertTrue(assignment.is_primary_event)

    def test_nullable_assigned_at(self):
        row = (1, 2, "n", 0.5, None, False)
        assignment = _message_node_assignment_from_row(row)
        self.assertIsNone(assignment.assigned_at)


class CrossChannelMessageMatchFromRowTests(unittest.TestCase):
    def test_deserializes_full_row(self):
        row = (1, 100, 2, 200, 0.88, 30, _NOW)
        match = _cross_channel_message_match_from_row(row)
        self.assertEqual(match.channel_id, 1)
        self.assertEqual(match.message_id, 100)
        self.assertEqual(match.matched_channel_id, 2)
        self.assertEqual(match.matched_message_id, 200)
        self.assertAlmostEqual(match.similarity_score, 0.88)
        self.assertEqual(match.timestamp_delta_seconds, 30)
        self.assertIsNotNone(match.created_at)

    def test_nullable_fields(self):
        row = (1, 1, 2, 2, 0.5, None, None)
        match = _cross_channel_message_match_from_row(row)
        self.assertIsNone(match.timestamp_delta_seconds)
        self.assertIsNone(match.created_at)


# ---------------------------------------------------------------------------
# Repository method tests (using mock connections)
# ---------------------------------------------------------------------------


class UpsertMessageSemanticsTests(unittest.TestCase):
    def test_skips_empty_sequence(self):
        repo = _make_repo()
        with patch.object(repo, "_connect") as mock_connect:
            repo.upsert_message_semantics([])
        mock_connect.assert_not_called()

    def test_executes_upsert_for_records(self):
        repo = _make_repo()
        cursor = _make_cursor()
        conn = _make_connection(cursor)
        with patch.object(repo, "_connect", return_value=conn):
            repo.upsert_message_semantics(
                [
                    MessageSemanticRecord(
                        channel_id=1,
                        message_id=10,
                        extraction_payload={"events": []},
                        primary_event_node_id=None,
                    )
                ]
            )
        cursor.executemany.assert_called_once()
        sql = cursor.executemany.call_args[0][0]
        self.assertIn("INSERT INTO message_semantics", sql)
        self.assertIn("ON CONFLICT (channel_id, message_id)", sql)
        conn.commit.assert_called_once()


class GetMessageSemanticRecordTests(unittest.TestCase):
    def test_returns_none_when_not_found(self):
        repo = _make_repo()
        cursor = _make_cursor(fetchone_row=None)
        conn = _make_connection(cursor)
        with patch.object(repo, "_connect", return_value=conn):
            result = repo.get_message_semantic_record(channel_id=1, message_id=99)
        self.assertIsNone(result)

    def test_returns_record_when_found(self):
        repo = _make_repo()
        row = (1, 10, {"k": "v"}, None, _NOW, _NOW)
        cursor = _make_cursor(fetchone_row=row)
        conn = _make_connection(cursor)
        with patch.object(repo, "_connect", return_value=conn):
            result = repo.get_message_semantic_record(channel_id=1, message_id=10)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.channel_id, 1)
        self.assertEqual(result.message_id, 10)

    def test_query_filters_by_channel_and_message(self):
        repo = _make_repo()
        cursor = _make_cursor(fetchone_row=None)
        conn = _make_connection(cursor)
        with patch.object(repo, "_connect", return_value=conn):
            repo.get_message_semantic_record(channel_id=5, message_id=7)
        cursor.execute.assert_called_once()
        executed_sql = cursor.execute.call_args[0][0]
        self.assertIn("message_semantics", executed_sql)
        args = cursor.execute.call_args[0][1]
        self.assertEqual(args, (5, 7))


class SaveMessageNodeAssignmentsTests(unittest.TestCase):
    def test_skips_empty(self):
        repo = _make_repo()
        with patch.object(repo, "_connect") as mock_connect:
            repo.save_message_node_assignments([])
        mock_connect.assert_not_called()

    def test_executes_upsert(self):
        repo = _make_repo()
        cursor = _make_cursor()
        conn = _make_connection(cursor)
        with patch.object(repo, "_connect", return_value=conn):
            repo.save_message_node_assignments(
                [MessageNodeAssignment(channel_id=1, message_id=5, node_id="n1", confidence=0.9)]
            )
        cursor.executemany.assert_called_once()
        sql = cursor.executemany.call_args[0][0]
        self.assertIn("INSERT INTO message_nodes", sql)
        self.assertIn("ON CONFLICT (channel_id, message_id, node_id)", sql)
        conn.commit.assert_called_once()


class ListMessageNodeAssignmentsTests(unittest.TestCase):
    def test_returns_empty_when_both_filters_none(self):
        repo = _make_repo()
        with patch.object(repo, "_connect") as mock_connect:
            result = repo.list_message_node_assignments(message_keys=None, node_ids=None)
        self.assertEqual(result, [])
        mock_connect.assert_not_called()

    def test_filters_by_node_ids(self):
        repo = _make_repo()
        row = (1, 10, "n1", 0.9, _NOW, False)
        cursor = _make_cursor(rows=[row])
        conn = _make_connection(cursor)
        with patch.object(repo, "_connect", return_value=conn):
            result = repo.list_message_node_assignments(node_ids=["n1"])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].node_id, "n1")
        executed_sql = cursor.execute.call_args[0][0]
        self.assertIn("node_id = ANY(%s)", executed_sql)

    def test_filters_by_message_keys(self):
        repo = _make_repo()
        cursor = _make_cursor(rows=[])
        conn = _make_connection(cursor)
        with patch.object(repo, "_connect", return_value=conn):
            repo.list_message_node_assignments(message_keys=[(1, 10), (2, 20)])
        executed_sql = cursor.execute.call_args[0][0]
        self.assertIn("(channel_id, message_id) = ANY(%s)", executed_sql)


class ListMessageKeysForNodeTests(unittest.TestCase):
    def test_returns_tuples(self):
        repo = _make_repo()
        cursor = _make_cursor(rows=[(1, 10), (2, 20)])
        conn = _make_connection(cursor)
        with patch.object(repo, "_connect", return_value=conn):
            result = repo.list_message_keys_for_node("node-uuid")
        self.assertEqual(result, [(1, 10), (2, 20)])
        executed_sql = cursor.execute.call_args[0][0]
        self.assertIn("message_nodes", executed_sql)
        self.assertIn("node_id = %s", executed_sql)


class SaveCrossChannelMessageMatchesTests(unittest.TestCase):
    def test_skips_empty(self):
        repo = _make_repo()
        with patch.object(repo, "_connect") as mock_connect:
            repo.save_cross_channel_message_matches([])
        mock_connect.assert_not_called()

    def test_executes_upsert(self):
        repo = _make_repo()
        cursor = _make_cursor()
        conn = _make_connection(cursor)
        with patch.object(repo, "_connect", return_value=conn):
            repo.save_cross_channel_message_matches(
                [CrossChannelMessageMatch(channel_id=1, message_id=5, matched_channel_id=2, matched_message_id=9, similarity_score=0.8)]
            )
        cursor.executemany.assert_called_once()
        sql = cursor.executemany.call_args[0][0]
        self.assertIn("INSERT INTO message_matches", sql)
        self.assertIn("ON CONFLICT (channel_id, message_id, matched_channel_id, matched_message_id)", sql)
        conn.commit.assert_called_once()


class ListCrossChannelMessageMatchesTests(unittest.TestCase):
    def test_no_filter(self):
        repo = _make_repo()
        cursor = _make_cursor(rows=[])
        conn = _make_connection(cursor)
        with patch.object(repo, "_connect", return_value=conn):
            result = repo.list_cross_channel_message_matches()
        self.assertEqual(result, [])
        executed_sql = cursor.execute.call_args[0][0]
        self.assertIn("message_matches", executed_sql)

    def test_channel_filter(self):
        repo = _make_repo()
        cursor = _make_cursor(rows=[])
        conn = _make_connection(cursor)
        with patch.object(repo, "_connect", return_value=conn):
            repo.list_cross_channel_message_matches(channel_id=7)
        executed_sql, params = cursor.execute.call_args[0]
        self.assertIn("channel_id = %s", executed_sql)
        self.assertIn(7, params)


class MarkMessageEmbeddedTests(unittest.TestCase):
    def test_updates_raw_messages_and_inserts_embedding_record(self):
        repo = _make_repo()
        cursor = _make_cursor()
        conn = _make_connection(cursor)
        with patch.object(repo, "_connect", return_value=conn):
            repo.mark_message_embedded(channel_id=1, message_id=10, version="text-embedding-3-small")
        self.assertEqual(cursor.execute.call_count, 2)
        first_sql = cursor.execute.call_args_list[0][0][0]
        second_sql = cursor.execute.call_args_list[1][0][0]
        self.assertIn("UPDATE raw_messages", first_sql)
        self.assertIn("is_embedded = TRUE", first_sql)
        self.assertIn("INSERT INTO message_embeddings", second_sql)
        conn.commit.assert_called_once()


class MarkMessagesExtractedTests(unittest.TestCase):
    def test_skips_empty(self):
        repo = _make_repo()
        with patch.object(repo, "_connect") as mock_connect:
            repo.mark_messages_extracted([])
        mock_connect.assert_not_called()

    def test_updates_is_extracted(self):
        repo = _make_repo()
        cursor = _make_cursor()
        conn = _make_connection(cursor)
        with patch.object(repo, "_connect", return_value=conn):
            repo.mark_messages_extracted([(1, 10), (2, 20)])
        cursor.execute.assert_called_once()
        sql = cursor.execute.call_args[0][0]
        self.assertIn("UPDATE raw_messages", sql)
        self.assertIn("is_extracted = TRUE", sql)
        conn.commit.assert_called_once()


class ListMessagesWithoutEmbeddingsTests(unittest.TestCase):
    def test_basic_query_no_filter(self):
        repo = _make_repo()
        cursor = _make_cursor(rows=[])
        conn = _make_connection(cursor)
        with patch.object(repo, "_connect", return_value=conn):
            result = repo.list_messages_without_embeddings()
        self.assertEqual(result, [])
        executed_sql = cursor.execute.call_args[0][0]
        self.assertIn("is_embedded = FALSE", executed_sql)

    def test_with_channel_and_limit(self):
        repo = _make_repo()
        cursor = _make_cursor(rows=[])
        conn = _make_connection(cursor)
        with patch.object(repo, "_connect", return_value=conn):
            repo.list_messages_without_embeddings(channel_id=3, limit=50)
        executed_sql, params = cursor.execute.call_args[0]
        self.assertIn("channel_id = %s", executed_sql)
        self.assertIn("LIMIT %s", executed_sql)
        self.assertIn(3, params)
        self.assertIn(50, params)


class ListMessagesWithoutSemanticsTests(unittest.TestCase):
    def test_basic_query_no_filter(self):
        repo = _make_repo()
        cursor = _make_cursor(rows=[])
        conn = _make_connection(cursor)
        with patch.object(repo, "_connect", return_value=conn):
            result = repo.list_messages_without_semantics()
        self.assertEqual(result, [])
        executed_sql = cursor.execute.call_args[0][0]
        self.assertIn("is_extracted = FALSE", executed_sql)

    def test_with_channel_and_limit(self):
        repo = _make_repo()
        cursor = _make_cursor(rows=[])
        conn = _make_connection(cursor)
        with patch.object(repo, "_connect", return_value=conn):
            repo.list_messages_without_semantics(channel_id=5, limit=10)
        executed_sql, params = cursor.execute.call_args[0]
        self.assertIn("channel_id = %s", executed_sql)
        self.assertIn("LIMIT %s", executed_sql)


class RefreshMessageHeatViewTests(unittest.TestCase):
    def test_tries_concurrent_refresh(self):
        repo = _make_repo()
        cursor = _make_cursor()
        conn = _make_connection(cursor)
        with patch.object(repo, "_connect", return_value=conn):
            repo.refresh_message_heat_view()
        sql = cursor.execute.call_args[0][0]
        self.assertIn("message_heat_view", sql)
        conn.commit.assert_called_once()

    def test_falls_back_to_non_concurrent_on_error(self):
        repo = _make_repo()
        cursor = _make_cursor()
        conn = _make_connection(cursor)
        # First execute raises (simulating view not yet populated), second succeeds.
        cursor.execute.side_effect = [Exception("not populated"), None]
        with patch.object(repo, "_connect", return_value=conn):
            repo.refresh_message_heat_view()
        # Should have called execute twice (CONCURRENTLY then without)
        self.assertEqual(cursor.execute.call_count, 2)
        fallback_sql = cursor.execute.call_args_list[1][0][0]
        self.assertIn("REFRESH MATERIALIZED VIEW", fallback_sql)
        self.assertNotIn("CONCURRENTLY", fallback_sql)
        conn.commit.assert_called_once()


class ListMessageHeatRowsTests(unittest.TestCase):
    def test_filters_by_kind(self):
        repo = _make_repo()
        cursor = _make_cursor(rows=[])
        conn = _make_connection(cursor)
        with patch.object(repo, "_connect", return_value=conn):
            result = repo.list_message_heat_rows(kind="event")
        self.assertEqual(result, [])
        executed_sql, params = cursor.execute.call_args[0]
        self.assertIn("message_heat_view", executed_sql)
        self.assertIn("kind = %s", executed_sql)
        self.assertEqual(params, ("event",))


# ---------------------------------------------------------------------------
# VectorStore method tests
# ---------------------------------------------------------------------------


def _make_vector_store() -> PineconeVectorStore:
    return PineconeVectorStore(
        api_key="fake-key",
        story_index="story-embeddings",
        theme_index="theme-centroids",
        event_index="event-centroids",
    )


class UpsertMessageEmbeddingsTests(unittest.TestCase):
    def test_skips_empty(self):
        vs = _make_vector_store()
        mock_index = MagicMock()
        with patch.object(vs, "_story_index", return_value=mock_index):
            vs.upsert_message_embeddings([])
        mock_index.upsert.assert_not_called()

    def test_upserts_with_composite_id(self):
        vs = _make_vector_store()
        mock_index = MagicMock()
        records = [
            MessageEmbeddingRecord(
                channel_id=1,
                message_id=42,
                embedding=[0.1, 0.2, 0.3],
                timestamp=_NOW,
                node_ids=("n1",),
            )
        ]
        with patch.object(vs, "_story_index", return_value=mock_index):
            vs.upsert_message_embeddings(records)
        mock_index.upsert.assert_called_once()
        vectors = mock_index.upsert.call_args[1]["vectors"]
        self.assertEqual(len(vectors), 1)
        self.assertEqual(vectors[0]["id"], "1:42")
        self.assertEqual(vectors[0]["metadata"]["channel_id"], 1)
        self.assertEqual(vectors[0]["metadata"]["message_id"], 42)
        self.assertIn("timestamp", vectors[0]["metadata"])
        self.assertEqual(vectors[0]["metadata"]["node_ids"], ["n1"])


class FetchMessageEmbeddingsTests(unittest.TestCase):
    def test_returns_empty_for_no_keys(self):
        vs = _make_vector_store()
        result = vs.fetch_message_embeddings([])
        self.assertEqual(result, {})

    def test_parses_composite_key_from_response(self):
        vs = _make_vector_store()
        mock_index = MagicMock()
        # Use MagicMock for the vector object so _field uses getattr (not dict.get)
        # since _field checks hasattr first and dict.values returns the method.
        mock_vector = MagicMock()
        mock_vector.values = [0.1, 0.2]
        mock_response = MagicMock()
        mock_response.vectors = {"3:7": mock_vector}
        mock_index.fetch.return_value = mock_response
        with patch.object(vs, "_story_index", return_value=mock_index):
            result = vs.fetch_message_embeddings([(3, 7)])
        self.assertIn((3, 7), result)
        self.assertEqual(result[(3, 7)], [0.1, 0.2])


class QueryMessageEmbeddingsTests(unittest.TestCase):
    def test_parses_composite_id_into_message_match(self):
        vs = _make_vector_store()
        mock_index = MagicMock()
        mock_response = {
            "matches": [
                {"id": "5:99", "score": 0.92, "metadata": {"channel_id": 5, "message_id": 99}},
            ]
        }
        mock_index.query.return_value = mock_response
        with patch.object(vs, "_story_index", return_value=mock_index):
            results = vs.query_message_embeddings([0.1, 0.2], top_k=5)
        self.assertEqual(len(results), 1)
        self.assertIsInstance(results[0], MessageMatch)
        self.assertEqual(results[0].channel_id, 5)
        self.assertEqual(results[0].message_id, 99)
        self.assertAlmostEqual(results[0].similarity_score, 0.92)

    def test_skips_non_composite_ids(self):
        vs = _make_vector_store()
        mock_index = MagicMock()
        mock_response = {
            "matches": [
                {"id": "story-uuid-without-colon", "score": 0.9, "metadata": {}},
            ]
        }
        mock_index.query.return_value = mock_response
        with patch.object(vs, "_story_index", return_value=mock_index):
            results = vs.query_message_embeddings([0.1], top_k=5)
        # UUID story IDs don't have format "channel_id:message_id" with integer parts,
        # so they should be skipped (ValueError on int conversion).
        self.assertEqual(results, [])

    def test_applies_filters(self):
        vs = _make_vector_store()
        mock_index = MagicMock()
        mock_index.query.return_value = {"matches": []}
        with patch.object(vs, "_story_index", return_value=mock_index):
            vs.query_message_embeddings(
                [0.1],
                top_k=3,
                exclude_channel_id=2,
                timestamp_gte=_NOW,
            )
        call_kwargs = mock_index.query.call_args[1]
        self.assertIsNotNone(call_kwargs["filter"])
        self.assertIn("channel_id", call_kwargs["filter"])
        self.assertIn("timestamp", call_kwargs["filter"])


class DeleteMessageEmbeddingsTests(unittest.TestCase):
    def test_skips_empty(self):
        vs = _make_vector_store()
        mock_index = MagicMock()
        with patch.object(vs, "_story_index", return_value=mock_index):
            vs.delete_message_embeddings([])
        mock_index.delete.assert_not_called()

    def test_deletes_by_composite_id(self):
        vs = _make_vector_store()
        mock_index = MagicMock()
        with patch.object(vs, "_story_index", return_value=mock_index):
            vs.delete_message_embeddings([(1, 10), (2, 20)])
        mock_index.delete.assert_called_once()
        ids = mock_index.delete.call_args[1]["ids"]
        self.assertIn("1:10", ids)
        self.assertIn("2:20", ids)


class UpdateMessageNodeIdsTests(unittest.TestCase):
    def test_calls_update_with_composite_id(self):
        vs = _make_vector_store()
        mock_index = MagicMock()
        with patch.object(vs, "_story_index", return_value=mock_index):
            vs.update_message_node_ids(channel_id=3, message_id=7, node_ids=["n1", "n2"])
        mock_index.update.assert_called_once_with(
            id="3:7",
            set_metadata={"node_ids": ["n1", "n2"]},
        )


if __name__ == "__main__":
    unittest.main()
