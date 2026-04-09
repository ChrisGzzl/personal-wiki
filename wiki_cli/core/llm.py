"""LLM client wrapper - supports Anthropic and OpenAI-compatible providers."""
from collections.abc import Generator
from typing import Optional

from .config import Config


class LLMClient:
    def __init__(self, config: Config):
        self.config = config
        self._client = None

    @property
    def provider(self) -> str:
        return self.config.get("llm.provider", "anthropic")

    @property
    def client(self):
        if self._client is None:
            if self.provider == "anthropic":
                import anthropic
                self._client = anthropic.Anthropic(api_key=self.config.api_key)
            else:
                # openai-compatible (openai, azure, local, etc.)
                from openai import OpenAI
                self._client = OpenAI(
                    api_key=self.config.api_key,
                    base_url=self.config.get("llm.base_url"),
                )
        return self._client

    def complete(self, system: str, user: str, operation: Optional[str] = None) -> str:
        """Non-streaming completion, returns full text.

        Args:
            operation: If given, uses config.model_for(operation) instead of default model.
                       e.g. "ingest", "query", "lint"
        """
        model = self.config.model_for(operation) if operation else self.config.model
        if self.provider == "anthropic":
            response = self.client.messages.create(
                model=model,
                max_tokens=self.config.max_tokens,
                temperature=self.config.temperature,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
            return response.content[0].text
        else:
            response = self.client.chat.completions.create(
                model=model,
                max_tokens=self.config.max_tokens,
                temperature=self.config.temperature,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            )
            content = response.choices[0].message.content
            if not content:
                finish = response.choices[0].finish_reason
                raise RuntimeError(
                    f"LLM returned empty content (finish_reason={finish}). "
                    f"usage={response.usage}. "
                    f"Possible cause: prompt too long or content filtered."
                )
            return content

    def stream(self, system: str, user: str, operation: Optional[str] = None) -> Generator[str, None, None]:
        """Streaming completion, yields text chunks.

        Args:
            operation: If given, uses config.model_for(operation) instead of default model.
        """
        model = self.config.model_for(operation) if operation else self.config.model
        if self.provider == "anthropic":
            with self.client.messages.stream(
                model=model,
                max_tokens=self.config.max_tokens,
                temperature=self.config.temperature,
                system=system,
                messages=[{"role": "user", "content": user}],
            ) as s:
                for text in s.text_stream:
                    yield text
        else:
            stream = self.client.chat.completions.create(
                model=model,
                max_tokens=self.config.max_tokens,
                temperature=self.config.temperature,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                stream=True,
            )
            for chunk in stream:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta.content
                if delta:
                    yield delta

    def complete_streaming(self, system: str, user: str) -> str:
        """Streams to stdout via rich, returns full text."""
        from rich.console import Console
        from rich.live import Live
        from rich.text import Text

        console = Console()
        full_text = ""
        buffer = ""

        with Live(console=console, refresh_per_second=10) as live:
            for chunk in self.stream(system, user):
                full_text += chunk
                buffer += chunk
                live.update(Text(buffer))

        return full_text
