"""
LLM Factory.
Supports LM Studio (OpenAI-compatible API) and Ollama.
"""

from __future__ import annotations

from typing import AsyncIterator, List
from threading import Lock

import httpx
from langchain_core.messages import BaseMessage, SystemMessage

try:
    from langchain_openai import ChatOpenAI
except Exception:
    ChatOpenAI = None

# Try importing standard langchain_ollama, fall back if needed
try:
    from langchain_ollama import ChatOllama
except Exception:
    from langchain_community.chat_models import ChatOllama

from server.config import settings


INTERVIEWER_SYSTEM_PROMPT = """You are an expert professional interviewer.
Current interview phase: {phase}

Your role:
- Adopt the persona appropriate for the candidate's target role (e.g. Clinical for Nursing, Strategic for Business).
- Ask clear, focused questions one at a time.
- Listen carefully to responses.
- Be encouraging but maintain professional standards.
- Be concise (2-3 sentences max).
"""

_MODEL_LOCK = Lock()
_MAIN_MODEL: "ChatWrapper | None" = None
_FAST_MODEL: "ChatWrapper | None" = None
_MAIN_SIG: tuple | None = None
_FAST_SIG: tuple | None = None
_REQUEST_SEMAPHORE: "asyncio.Semaphore | None" = None
_SEMAPHORE_SIZE: int = 0


def _extract_chunk_text(chunk) -> str:
    """Normalize chunk content across providers to plain text."""
    content = getattr(chunk, "content", None)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
                continue
            if isinstance(item, dict):
                text = item.get("text") or item.get("content") or item.get("value") or ""
                if isinstance(text, str):
                    parts.append(text)
                continue
            text = getattr(item, "text", None) or getattr(item, "content", None)
            if isinstance(text, str):
                parts.append(text)
        return "".join(parts)
    return ""


class ChatWrapper:
    """Provider-agnostic wrapper exposing ainvoke/astream/generate_response_stream."""

    def __init__(
        self,
        *,
        model: str,
        temperature: float,
        provider: str,
        base_url: str,
        api_key: str,
    ):
        self.model = model
        self.temperature = temperature
        self.provider = str(provider or "lmstudio").strip().lower()
        self.base_url = self._normalize_base_url(str(base_url or "").strip(), self.provider)
        self.api_key = str(api_key or "lm-studio").strip() or "lm-studio"
        self._client = self._build_client(self.model)

    @staticmethod
    def _normalize_base_url(base_url: str, provider: str) -> str:
        url = (base_url or "").strip().rstrip("/")
        if provider == "lmstudio":
            return f"{url}/v1" if url and not url.endswith("/v1") else url
        if provider == "ollama":
            return url[:-3] if url.endswith("/v1") else url
        return url

    def _build_client(self, model_name: str):
        if self.provider == "ollama":
            return ChatOllama(
                model=model_name,
                temperature=self.temperature,
                base_url=self.base_url,
                reasoning=False,
                num_ctx=8192,
            )
        if ChatOpenAI is None:
            raise RuntimeError(
                "LM Studio provider requires langchain_openai. Install with: pip install langchain-openai"
            )
        extra_body = None
        top_p = None
        presence_penalty = None
        # LM Studio and other OpenAI-compatible providers can accept
        # chat_template_kwargs to disable Qwen-style thinking.
        if bool(getattr(settings, "LLM_DISABLE_THINKING", True)):
            extra_body = {
                "chat_template_kwargs": {"enable_thinking": False},
            }
            # Qwen-recommended Instruct (non-thinking) mode params
            self.temperature = 0.7
            top_p = 0.8
            presence_penalty = 1.5

        kwargs = dict(
            model=model_name,
            temperature=self.temperature,
            base_url=self.base_url,
            api_key=self.api_key,
            max_retries=1,
            max_tokens=int(getattr(settings, "LLM_MAX_TOKENS", 1200)),
        )
        if extra_body is not None:
            kwargs["extra_body"] = extra_body
        if top_p is not None:
            kwargs["top_p"] = top_p
        if presence_penalty is not None:
            kwargs["presence_penalty"] = presence_penalty
        return ChatOpenAI(**kwargs)

    async def _discover_lmstudio_model(self) -> str | None:
        """Query LM Studio /models and return first available model id."""
        if self.provider != "lmstudio":
            return None
        try:
            async with httpx.AsyncClient(timeout=4.0) as client:
                response = await client.get(f"{self.base_url.rstrip('/')}/models")
                response.raise_for_status()
                payload = response.json() if response.content else {}
            data = payload.get("data") or []
            if not data:
                return None
            first = data[0]
            model_id = str(first.get("id") or "").strip()
            return model_id or None
        except Exception:
            return None

    async def _invoke_with_fallback(self, messages: List[BaseMessage], kwargs: dict | None = None):
        kwargs = kwargs or {}
        try:
            return await self._client.ainvoke(messages, **kwargs)
        except Exception as exc:
            if self.provider != "lmstudio":
                raise
            fallback_model = await self._discover_lmstudio_model()
            if not fallback_model or fallback_model == self.model:
                raise
            print(
                f"⚠️ LM Studio model '{self.model}' unavailable; auto-falling back to '{fallback_model}'. "
                f"Original error: {exc}"
            )
            self.model = fallback_model
            self._client = self._build_client(fallback_model)
            return await self._client.ainvoke(messages, **kwargs)

    async def ainvoke(
        self,
        messages: List[BaseMessage],
        *,
        json_mode: bool = False,
        json_schema: dict | None = None,
        max_tokens: int | None = None
    ):
        """Invoke the model with optional JSON enforcement.

        Args:
            json_mode: For non-LM Studio providers, sends ``response_format: json_object``.
                       For LM Studio, this is a no-op (use ``json_schema`` instead).
            json_schema: A hand-crafted JSON Schema dict.  When provided, sends
                         ``response_format: { type: json_schema, ... }`` which
                         LM Studio enforces via constrained decoding — much more
                         reliable than prompt-only JSON enforcement.
            max_tokens: Override the default max_tokens for this call.
        """
        kwargs = {}
        if max_tokens is not None:
            kwargs["max_tokens"] = int(max_tokens)

        if json_schema is not None:
            # LM Studio constrained decoding — guarantees valid JSON matching schema
            schema_name = json_schema.get("name", "response")
            # Build a clean schema dict without the 'name' key (it goes one level up)
            schema_body = {k: v for k, v in json_schema.items() if k != "name"}
            kwargs["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": schema_name,
                    "strict": True,
                    "schema": schema_body,
                },
            }
        elif json_mode and self.provider != "lmstudio":
            kwargs["response_format"] = {"type": "json_object"}
        # For LM Studio + json_mode without schema: rely on prompt instructions

        semaphore = self._get_semaphore()
        async with semaphore:
            return await self._invoke_with_fallback(messages, kwargs=kwargs)

    async def astream(self, messages: List[BaseMessage]):
        semaphore = self._get_semaphore()
        async with semaphore:
            try:
                async for chunk in self._client.astream(messages):
                    yield chunk
                return
            except Exception as exc:
                if self.provider != "lmstudio":
                    raise
                fallback_model = await self._discover_lmstudio_model()
                if not fallback_model or fallback_model == self.model:
                    raise
                print(
                    f"⚠️ LM Studio model '{self.model}' unavailable for stream; "
                    f"auto-falling back to '{fallback_model}'. Original error: {exc}"
                )
                self.model = fallback_model
                self._client = self._build_client(fallback_model)
                async for chunk in self._client.astream(messages):
                    yield chunk

    @staticmethod
    def _get_semaphore():
        import asyncio
        global _REQUEST_SEMAPHORE, _SEMAPHORE_SIZE
        max_concurrency = int(getattr(settings, "LLM_MAX_CONCURRENCY", 1) or 1)
        max_concurrency = max(1, max_concurrency)
        if _REQUEST_SEMAPHORE is None or _SEMAPHORE_SIZE != max_concurrency:
            _REQUEST_SEMAPHORE = asyncio.Semaphore(max_concurrency)
            _SEMAPHORE_SIZE = max_concurrency
        return _REQUEST_SEMAPHORE

    def with_structured_output(self, schema_model: type):
        """Delegate structured output when provider client supports it.

        NOTE: LM Studio's MLX models return empty content (0 tokens) when
        ``response_format: json_schema`` with ``strict: true`` is used.
        We intentionally skip structured output for LM Studio and fall back
        to the parser path which uses prompt-based JSON enforcement.
        """
        if self.provider == "lmstudio":
            raise AttributeError(
                "LM Studio MLX models do not support strict json_schema; "
                "falling back to parser path."
            )
        if hasattr(self._client, "with_structured_output"):
            return self._client.with_structured_output(schema_model)
        raise AttributeError("Underlying model does not support structured output.")

    async def generate_response_stream(
        self,
        messages: List[BaseMessage],
        phase: str = "general"
    ) -> AsyncIterator[str]:
        """Custom streaming wrapper for main.py compatibility."""
        system_content = INTERVIEWER_SYSTEM_PROMPT.format(phase=phase)
        normalized = list(messages) if messages else []
        if not normalized or not isinstance(normalized[0], SystemMessage):
            normalized.insert(0, SystemMessage(content=system_content))
        else:
            normalized[0] = SystemMessage(content=system_content)

        try:
            async for chunk in self.astream(normalized):
                token = _extract_chunk_text(chunk)
                if token:
                    yield token
        except Exception as e:
            provider = "LM Studio" if self.provider == "lmstudio" else "Ollama"
            yield (
                f"\n\n[System Error: Could not connect to {provider} at {self.base_url}. "
                f"Check that the server is running and model is loaded.]"
            )
            print(f"❌ {provider} Error: {e}")


def get_chat_model() -> ChatWrapper:
    """Factory function for the main chat model (singleton by config signature)."""
    global _MAIN_MODEL, _MAIN_SIG
    provider = getattr(settings, "LLM_PROVIDER", "lmstudio")
    base_url = settings.LLM_BASE_URL
    api_key = getattr(settings, "LLM_API_KEY", "lm-studio")
    sig = (provider, base_url, api_key, settings.LLM_MODEL_ID, 0.7)
    with _MODEL_LOCK:
        if _MAIN_MODEL is None or _MAIN_SIG != sig:
            _MAIN_MODEL = ChatWrapper(
                model=settings.LLM_MODEL_ID,
                temperature=0.7,
                provider=provider,
                base_url=base_url,
                api_key=api_key,
            )
            _MAIN_SIG = sig
    return _MAIN_MODEL


def preload_model():
    """Eagerly build the singleton and validate the configured model against the provider."""
    import asyncio

    provider = str(getattr(settings, "LLM_PROVIDER", "lmstudio")).strip().lower()
    provider_name = "LM Studio" if provider == "lmstudio" else "Ollama"
    shared = bool(getattr(settings, "LLM_SINGLE_INSTANCE", True))
    print(f"🔄 Using {provider_name} model: {settings.LLM_MODEL_ID}")
    print(f"🌐 {provider_name} base URL: {settings.LLM_BASE_URL}")
    print(f"🧠 Disable thinking: {bool(getattr(settings, 'LLM_DISABLE_THINKING', True))}")
    print(f"✂️ Max tokens: {int(getattr(settings, 'LLM_MAX_TOKENS', 1200))}")
    print(f"🧩 Single LLM instance: {shared}")
    # Build singleton eagerly so first request doesn't create a second transient client.
    wrapper = get_chat_model()
    # Proactively validate model ID for LM Studio. If the configured model is not
    # loaded, auto-correct to the first available model so first request doesn't crash.
    if provider == "lmstudio":
        try:
            discovered = asyncio.get_event_loop().run_until_complete(
                wrapper._discover_lmstudio_model()
            )
        except RuntimeError:
            # No running event loop — create a temporary one.
            discovered = asyncio.run(wrapper._discover_lmstudio_model())
        if discovered and discovered != wrapper.model:
            print(
                f"⚠️ Configured model '{wrapper.model}' not found in {provider_name}; "
                f"auto-correcting to '{discovered}'"
            )
            wrapper.model = discovered
            wrapper._client = wrapper._build_client(discovered)
    print(f"✅ {provider_name} backend wrapper ready")


def get_fast_chat_model() -> ChatWrapper:
    """Factory function for fast coaching/tips model."""
    global _FAST_MODEL, _FAST_SIG
    if bool(getattr(settings, "LLM_SINGLE_INSTANCE", True)):
        return get_chat_model()

    fast_model = getattr(settings, "FAST_LLM_MODEL_ID", None) or settings.LLM_MODEL_ID
    provider = getattr(settings, "LLM_PROVIDER", "lmstudio")
    base_url = settings.LLM_BASE_URL
    api_key = getattr(settings, "LLM_API_KEY", "lm-studio")
    sig = (provider, base_url, api_key, fast_model, 0.5)
    with _MODEL_LOCK:
        if _FAST_MODEL is None or _FAST_SIG != sig:
            _FAST_MODEL = ChatWrapper(
                model=fast_model,
                temperature=0.5,
                provider=provider,
                base_url=base_url,
                api_key=api_key,
            )
            _FAST_SIG = sig
    return _FAST_MODEL
