"""Provider-agnostic LLM access.

Selection order when LLM_PROVIDER is unset: anthropic > openai > gemini >
groq > openrouter > azure > ollama. If no key/SDK is available, an offline
deterministic narrator is used so the full pipeline still runs.

The rest of the codebase sees `narrate()` (prose), `complete_json()` (structured
world-knowledge: real attractions, itinerary, dishes, hotels), and `has_llm`.
SDKs are imported lazily so you only need the one you actually use installed.
"""
from __future__ import annotations

import asyncio
import json
import re
from typing import Any, Optional

from app.config import settings
from app.logging_setup import get_logger

_log = get_logger("travel.llm")


def extract_json(text: str) -> Any:
    """Best-effort parse of a JSON object/array from an LLM reply."""
    if not text:
        raise ValueError("empty")
    t = text.strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z]*\n?", "", t)
        if t.endswith("```"):
            t = t[:-3]
        t = t.strip()
    # Slice to the outermost JSON bracket pair if there's surrounding prose.
    start = min((i for i in (t.find("{"), t.find("[")) if i != -1), default=-1)
    if start > 0:
        t = t[start:]
    end = max(t.rfind("}"), t.rfind("]"))
    if end != -1:
        t = t[: end + 1]
    return json.loads(t)

_DEFAULT_MODELS = {
    "anthropic": "claude-3-5-sonnet-latest",
    "openai": "gpt-4o-mini",
    "gemini": "gemini-1.5-flash",
    "groq": "llama-3.3-70b-versatile",
    "openrouter": "openai/gpt-4o-mini",
    "azure": "",  # uses deployment name
    "ollama": "llama3.1",
}


def select_provider() -> str:
    if settings.llm_provider:
        return settings.llm_provider
    if settings.anthropic_api_key:
        return "anthropic"
    if settings.openai_api_key:
        return "openai"
    if settings.gemini_api_key:
        return "gemini"
    if settings.groq_api_key:
        return "groq"
    if settings.openrouter_api_key:
        return "openrouter"
    if settings.azure_openai_api_key and settings.azure_openai_endpoint:
        return "azure"
    return "offline"  # ollama is opt-in via LLM_PROVIDER=ollama


class LLMClient:
    """Provider-agnostic LLM access with automatic fallback: if the selected
    provider's call fails, the next configured provider is tried, so content
    still generates as long as ANY key works. The provider that actually
    produced output is reported via `effective_provider`."""

    def __init__(self) -> None:
        self.provider = select_provider()      # display/default
        self.model = settings.llm_model or _DEFAULT_MODELS.get(self.provider, "")
        self.active_provider: Optional[str] = None
        self.last_error: str = ""

    def _candidates(self) -> list[str]:
        """Ordered providers to try: forced first, then any with a key."""
        avail = []
        if settings.anthropic_api_key:
            avail.append("anthropic")
        if settings.openai_api_key:
            avail.append("openai")
        if settings.gemini_api_key:
            avail.append("gemini")
        if settings.groq_api_key:
            avail.append("groq")
        if settings.openrouter_api_key:
            avail.append("openrouter")
        if settings.azure_openai_api_key and settings.azure_openai_endpoint:
            avail.append("azure")
        order: list[str] = []
        forced = settings.llm_provider
        if forced and forced != "offline":
            order.append(forced)            # honour the user's choice first
        for p in avail:
            if p not in order:
                order.append(p)             # then fall back to others with keys
        return order

    def _model_for(self, provider: str) -> str:
        # LLM_MODEL only applies to the explicitly-selected provider.
        if settings.llm_provider == provider and settings.llm_model:
            return settings.llm_model
        return _DEFAULT_MODELS.get(provider, "")

    @property
    def has_llm(self) -> bool:
        return bool(self._candidates())

    @property
    def effective_provider(self) -> str:
        return self.active_provider or (self._candidates()[0] if self._candidates() else "offline")

    async def complete_json(self, system: str, prompt: str, lang: str = "en") -> Any:
        """Ask the model for structured JSON (real-world content). Returns the
        parsed object, or None if there's no LLM or the reply isn't valid JSON."""
        if not self.has_llm:
            return None
        if lang and lang != "en":
            prompt += (f"\n\nWrite all human-readable text values in language code '{lang}'. "
                       f"Keep JSON keys and proper nouns (place/brand names) as-is.")
        try:
            raw = await self.complete(
                system + " Respond with ONLY valid minified JSON. No markdown, no commentary.",
                prompt,
            )
            return extract_json(raw)
        except Exception:
            return None

    async def narrate(self, role: str, context: dict, max_words: int = 70,
                      lang: str = "en") -> str:
        lang_clause = "" if (not lang or lang == "en") else f" Write in language code '{lang}'."
        prompt = (
            f"You are the {role} of a travel-planning system. Write {max_words} words "
            f"of concise, factual prose for the traveller based ONLY on this data.{lang_clause} "
            f"No markdown, no lists.\n\n{json.dumps(context, ensure_ascii=False)[:4000]}"
        )
        try:
            text = await self.complete("You write concise travel guidance.", prompt)
            return text.strip()
        except Exception:
            return _offline_narrate(role, context)

    async def complete(self, system: str, prompt: str) -> str:
        candidates = self._candidates()
        if not candidates:
            return _offline_narrate("assistant", {"prompt": prompt})
        errors = []
        for prov in candidates:
            fn = getattr(self, f"_call_{prov}", None)
            if fn is None:
                continue
            try:
                out = await fn(system, prompt)
                if out and out.strip():
                    if self.active_provider != prov:
                        _log.info("LLM: using %s (model=%s)", prov, self._model_for(prov))
                    self.active_provider = prov
                    return out
                errors.append(f"{prov}: empty response")
                _log.warning("LLM %s returned an empty response", prov)
            except Exception as exc:  # try the next configured provider
                msg = f"{type(exc).__name__}: {str(exc)[:160]}"
                errors.append(f"{prov}: {msg}")
                _log.warning("LLM %s FAILED -> %s", prov, msg)
        self.last_error = " | ".join(errors)
        _log.error("LLM: all providers failed -> %s", self.last_error)
        raise RuntimeError(self.last_error or "no provider available")

    # -- provider backends (lazy SDK imports) -------------------------------- #
    async def _call_anthropic(self, system: str, prompt: str) -> str:
        from anthropic import AsyncAnthropic

        client = AsyncAnthropic(api_key=settings.anthropic_api_key)
        resp = await client.messages.create(
            model=self._model_for("anthropic"), max_tokens=1500, system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")

    async def _call_openai_compatible(self, provider: str, base_url: Optional[str],
                                      api_key: str, system: str, prompt: str) -> str:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        resp = await client.chat.completions.create(
            model=self._model_for(provider), max_tokens=1500,
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": prompt}],
        )
        return resp.choices[0].message.content or ""

    async def _call_openai(self, system: str, prompt: str) -> str:
        return await self._call_openai_compatible("openai", None, settings.openai_api_key, system, prompt)

    async def _call_groq(self, system: str, prompt: str) -> str:
        return await self._call_openai_compatible(
            "groq", "https://api.groq.com/openai/v1", settings.groq_api_key, system, prompt)

    async def _call_openrouter(self, system: str, prompt: str) -> str:
        return await self._call_openai_compatible(
            "openrouter", "https://openrouter.ai/api/v1", settings.openrouter_api_key, system, prompt)

    async def _call_ollama(self, system: str, prompt: str) -> str:
        return await self._call_openai_compatible(
            "ollama", f"{settings.ollama_base_url}/v1", "ollama", system, prompt)

    async def _call_azure(self, system: str, prompt: str) -> str:
        from openai import AsyncAzureOpenAI

        client = AsyncAzureOpenAI(
            api_key=settings.azure_openai_api_key,
            azure_endpoint=settings.azure_openai_endpoint,
            api_version="2024-06-01",
        )
        resp = await client.chat.completions.create(
            model=settings.azure_openai_deployment, max_tokens=1500,
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": prompt}],
        )
        return resp.choices[0].message.content or ""

    async def _call_gemini(self, system: str, prompt: str) -> str:
        # Direct REST call. System folded into the user turn for compatibility.
        import httpx

        model = self._model_for("gemini") or "gemini-1.5-flash"
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        gen_cfg: dict = {"maxOutputTokens": 4096, "temperature": 0.4}
        if "2.5" in model or "3." in model:  # disable "thinking" so tokens go to the answer
            gen_cfg["thinkingConfig"] = {"thinkingBudget": 0}
        body = {
            "contents": [{"role": "user", "parts": [{"text": f"{system}\n\n{prompt}"}]}],
            "generationConfig": gen_cfg,
        }
        async with httpx.AsyncClient(timeout=settings.request_timeout_s * 2) as client:
            resp = await client.post(
                url, headers={"x-goog-api-key": settings.gemini_api_key}, json=body)
            if resp.status_code >= 400:
                # surface the API's own error message (helps diagnose key/model issues)
                raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:200]}")
            data = resp.json()
        cand = (data.get("candidates") or [{}])[0]
        parts = cand.get("content", {}).get("parts", [])
        return "".join(p.get("text", "") for p in parts)


def _offline_narrate(role: str, context: dict) -> str:
    """Deterministic templated prose so the pipeline runs without any keys."""
    keys = [k for k in context if k not in {"prompt"}]
    head = role.replace("_", " ").title()
    if not keys:
        return f"{head}: guidance generated from available data (offline mode)."
    return (f"{head}: prepared from {', '.join(keys[:5])}. "
            f"Connect an LLM provider for richer narration.")


_client: Optional[LLMClient] = None


def get_client() -> LLMClient:
    global _client
    if _client is None:
        _client = LLMClient()
    return _client
