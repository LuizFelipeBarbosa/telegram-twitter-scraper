from __future__ import annotations

from telegram_scraper.kg.config import KGSettings
from telegram_scraper.kg.embedder import OpenAIEmbedder
from telegram_scraper.kg.extraction import OpenAISemanticExtractor
from telegram_scraper.kg.repository import PostgresRepository
from telegram_scraper.kg.stream import RedisRawMessageStream
from telegram_scraper.kg.translation import OpenAIMessageTranslator
from telegram_scraper.kg.vector_store import PineconeVectorStore


def build_repository(settings: KGSettings) -> PostgresRepository:
    return PostgresRepository(settings.database_url)


def build_stream(settings: KGSettings) -> RedisRawMessageStream:
    return RedisRawMessageStream(
        settings.redis_url,
        stream_key=settings.stream_key,
        consumer_group=settings.consumer_group,
        retention_ms=settings.stream_retention_ms,
    )


def build_embedder(settings: KGSettings) -> OpenAIEmbedder:
    return OpenAIEmbedder(api_key=settings.openai_api_key, model=settings.embedding_model)


def build_semantic_extractor(settings: KGSettings) -> OpenAISemanticExtractor:
    return OpenAISemanticExtractor(
        api_key=settings.openai_api_key,
        model=settings.semantic_model,
        max_chars=settings.semantic_max_chars,
        batch_size=settings.semantic_batch_size,
    )


def build_message_translator(settings: KGSettings) -> OpenAIMessageTranslator:
    return OpenAIMessageTranslator(
        api_key=settings.openai_api_key,
        model=settings.translation_model,
        max_chars=settings.semantic_max_chars,
        batch_size=settings.semantic_batch_size,
    )


def build_vector_store(settings: KGSettings) -> PineconeVectorStore:
    return PineconeVectorStore(
        api_key=settings.pinecone_api_key,
        story_index=settings.pinecone_index_story,
        theme_index=settings.pinecone_index_theme,
        event_index=settings.pinecone_index_event,
    )
