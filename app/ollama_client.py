from __future__ import annotations

from typing import Any

import requests

from app.config import settings


class OllamaClient:
    def __init__(self, host: str | None = None, timeout: int = 120) -> None:
        self.host = (host or settings.ollama_host).rstrip("/")
        self.timeout = timeout
        self._session = requests.Session()
        self._session.trust_env = False  # 不走系统代理，Ollama 始终是本地服务

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.host}{path}"
        try:
            response = self._session.post(url, json=payload, timeout=self.timeout)
            response.raise_for_status()
        except requests.exceptions.HTTPError as e:
            raise RuntimeError(f"Ollama API Error: {response.status_code} - {response.text}") from e
        return response.json()

    def embed(self, texts: list[str], model: str | None = None) -> list[list[float]]:
        model_name = model or settings.embed_model
        data = self._post(
            "/api/embed",
            {
                "model": model_name,
                "input": texts,
                "truncate": True,
                "options": {"num_ctx": settings.num_ctx}
            },
        )
        embeddings = data.get("embeddings") or []
        if len(embeddings) != len(texts):
            raise RuntimeError(f"Ollama /api/embed returned {len(embeddings)} embeddings, expected {len(texts)}.")
        return embeddings

    def chat(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float | None = None,
        top_p: float | None = None,
        num_ctx: int | None = None,
        deepseek_thinking_enabled: bool | None = None,
        custom_openai: dict[str, Any] | None = None,
    ) -> str:
        model_name = model or settings.chat_model
        if model_name.startswith("custom-openai:"):
            if not custom_openai:
                raise RuntimeError("Custom OpenAI model is not configured.")
            return self._openai_compatible_chat(
                messages=messages,
                model=model_name.removeprefix("custom-openai:") or custom_openai.get("model_name", ""),
                config=custom_openai,
                temperature=temperature,
                top_p=top_p,
            )
        if model_name.startswith("deepseek-"):
            return self._deepseek_chat(
                messages=messages,
                model=model_name,
                temperature=temperature,
                top_p=top_p,
                thinking_enabled=deepseek_thinking_enabled,
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
        thinking_enabled: bool | None = None,
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
        extra_body: dict[str, Any] = {}
        use_thinking = settings.deepseek_thinking_enabled if thinking_enabled is None else thinking_enabled
        if use_thinking:
            extra_body["thinking"] = {"type": "enabled"}

        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": False,
            "temperature": settings.temperature if temperature is None else temperature,
            "top_p": settings.top_p if top_p is None else top_p,
            "timeout": self.timeout,
            "reasoning_effort": settings.deepseek_reasoning_effort,
        }
        if extra_body:
            payload["extra_body"] = extra_body

        response = client.chat.completions.create(**payload)
        message = response.choices[0].message
        return (message.content or "").strip()

    def _openai_compatible_chat(
        self,
        messages: list[dict[str, str]],
        model: str,
        config: dict[str, Any],
        temperature: float | None = None,
        top_p: float | None = None,
    ) -> str:
        api_key = str(config.get("api_key") or "").strip()
        base_url = str(config.get("base_url") or "").strip().rstrip("/")
        model_name = str(model or config.get("model_name") or "").strip()
        if not api_key or not base_url or not model_name:
            raise RuntimeError("自定义 OpenAI API 配置缺少 api_key、base_url 或 model_name。")

        try:
            from openai import OpenAI
        except ImportError as e:
            raise RuntimeError("The openai package is required for OpenAI-compatible models. Run `pip install openai`.") from e

        timeout = config.get("timeout") or self.timeout
        client = OpenAI(api_key=api_key, base_url=base_url, timeout=timeout)
        payload: dict[str, Any] = {
            "model": model_name,
            "messages": messages,
            "stream": False,
        }
        payload["temperature"] = settings.temperature if temperature is None else temperature
        if config.get("temperature") is not None and temperature is None:
            payload["temperature"] = config["temperature"]
        payload["top_p"] = settings.top_p if top_p is None else top_p
        if config.get("top_p") is not None and top_p is None:
            payload["top_p"] = config["top_p"]
        if config.get("max_tokens") is not None:
            payload["max_tokens"] = config["max_tokens"]

        response = client.chat.completions.create(**payload)
        message = response.choices[0].message
        return (message.content or "").strip()

    def healthcheck(self) -> None:
        response = self._session.get(f"{self.host}/api/tags", timeout=15)
        response.raise_for_status()
