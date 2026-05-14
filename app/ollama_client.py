from __future__ import annotations

from typing import Any

import requests

from app.config import settings


class OllamaClient:
    def __init__(self, host: str | None = None, timeout: int = 120) -> None:
        self.host = (host or settings.ollama_host).rstrip("/")
        self.timeout = timeout

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.host}{path}"
        response = requests.post(url, json=payload, timeout=self.timeout)
        try:
            response.raise_for_status()
        except requests.exceptions.HTTPError as e:
            raise RuntimeError(f"Ollama API Error: {response.status_code} - {response.text}") from e
        return response.json()

    def embed(self, texts: list[str], model: str | None = None) -> list[list[float]]:
        model_name = model or settings.embed_model
        vectors: list[list[float]] = []
        for text in texts:
            data = self._post(
                "/api/embed",
                {
                    "model": model_name, 
                    "input": text,
                    "truncate": True,
                    "options": {"num_ctx": settings.num_ctx}
                },
            )
            embeddings = data.get("embeddings") or []
            if not embeddings:
                raise RuntimeError("Ollama /api/embed returned no embeddings.")
            vectors.append(embeddings[0])
        return vectors

    def chat(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float | None = None,
        top_p: float | None = None,
        num_ctx: int | None = None,
    ) -> str:
        model_name = model or settings.chat_model
        if model_name.startswith("deepseek-"):
            return self._deepseek_chat(
                messages=messages,
                model=model_name,
                temperature=temperature,
                top_p=top_p,
            )

        data = self._post(
            "/api/chat",
            {
                "model": model_name,
                "messages": messages,
                "stream": False,
                "options": {
                    "temperature": settings.temperature if temperature is None else temperature,
                    "top_p": settings.top_p if top_p is None else top_p,
                    "num_ctx": settings.num_ctx if num_ctx is None else num_ctx,
                },
            },
        )
        message = data.get("message", {})
        content = message.get("content", "")
        return content.strip()

    def _deepseek_chat(
        self,
        messages: list[dict[str, str]],
        model: str,
        temperature: float | None = None,
        top_p: float | None = None,
    ) -> str:
        if not settings.deepseek_api_key:
            raise RuntimeError("DEEPSEEK_API_KEY is not configured.")

        try:
            from openai import OpenAI
        except ImportError as e:
            raise RuntimeError("The openai package is required for DeepSeek. Run `pip install openai`.") from e

        client = OpenAI(
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
        )
        is_flash_model = "flash" in model.lower()
        extra_body: dict[str, Any] = {}
        if settings.deepseek_thinking_enabled and not is_flash_model:
            extra_body["thinking"] = {"type": "enabled"}

        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": False,
            "temperature": settings.temperature if temperature is None else temperature,
            "top_p": settings.top_p if top_p is None else top_p,
            "timeout": self.timeout,
        }
        if not is_flash_model:
            payload["reasoning_effort"] = settings.deepseek_reasoning_effort
        if extra_body:
            payload["extra_body"] = extra_body

        response = client.chat.completions.create(**payload)
        message = response.choices[0].message
        return (message.content or "").strip()

    def healthcheck(self) -> None:
        response = requests.get(f"{self.host}/api/tags", timeout=15)
        response.raise_for_status()
