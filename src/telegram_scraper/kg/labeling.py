from __future__ import annotations

from typing import Sequence


class OpenAITopicLabelRefiner:
    def __init__(self, *, api_key: str, model: str):
        self.api_key = api_key
        self.model = model

    def _client(self):
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover - exercised only without runtime deps.
            raise RuntimeError("openai is not installed. Install project dependencies before using KG commands.") from exc
        return OpenAI(api_key=self.api_key)

    def refine_label(self, *, current_label: str, story_texts: Sequence[str]) -> str:
        if not story_texts:
            return current_label

        prompt = "\n\n".join(story_texts[:10])
        client = self._client()
        response = client.responses.create(
            model=self.model,
            input=[
                {
                    "role": "system",
                    "content": "Generate a concise 3-5 word topic label for a cluster of news/story texts. Return label only.",
                },
                {
                    "role": "user",
                    "content": f"Current label: {current_label}\n\nStory texts:\n{prompt}",
                },
            ],
        )
        label = (response.output_text or "").strip()
        return label or current_label
