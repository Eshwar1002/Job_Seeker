"""Hybrid LLM router: local Ollama SLM -> HuggingFace / Groq cloud -> None (heuristic fallback)."""
import json
import logging
import re
import time

import httpx

from .config import settings

logger = logging.getLogger(__name__)

_ollama_ok: bool | None = None
_ollama_checked_at: float = 0.0


def _ollama_available() -> bool:
    global _ollama_ok, _ollama_checked_at
    if _ollama_ok is not None and time.time() - _ollama_checked_at < 60:
        return _ollama_ok
    try:
        r = httpx.get(f"{settings.ollama_base_url}/api/tags", timeout=2.0)
        _ollama_ok = r.status_code == 200
    except Exception:
        _ollama_ok = False
    _ollama_checked_at = time.time()
    return _ollama_ok


def provider_status() -> dict:
    return {
        "ollama": {"available": _ollama_available(), "model": settings.ollama_model, "kind": "local_slm"},
        "huggingface": {"available": bool(settings.hf_token), "model": settings.hf_model, "kind": "cloud"},
        "groq": {"available": bool(settings.groq_api_key), "model": settings.groq_model, "kind": "cloud_slm"},
    }


def _chat_ollama(messages: list[dict], json_mode: bool) -> str | None:
    try:
        payload = {"model": settings.ollama_model, "messages": messages, "stream": False,
                   "options": {"temperature": 0.1, "num_predict": 2048}}
        if json_mode:
            payload["format"] = "json"
        r = httpx.post(f"{settings.ollama_base_url}/api/chat", json=payload, timeout=120.0)
        r.raise_for_status()
        return r.json()["message"]["content"]
    except Exception as e:
        logger.warning("Ollama chat failed: %s", e)
        return None


def _chat_hf(messages: list[dict], json_mode: bool) -> str | None:
    if not settings.hf_token:
        return None
    try:
        payload = {"model": settings.hf_model, "messages": messages, "max_tokens": 2048, "temperature": 0.1}
        r = httpx.post(
            "https://router.huggingface.co/v1/chat/completions",
            headers={"Authorization": f"Bearer {settings.hf_token}"},
            json=payload, timeout=90.0,
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]
    except Exception as e:
        logger.warning("HuggingFace chat failed: %s", e)
        return None


def _chat_groq(messages: list[dict], json_mode: bool) -> str | None:
    if not settings.groq_api_key:
        return None
    try:
        payload = {"model": settings.groq_model, "messages": messages, "max_tokens": 2048, "temperature": 0.1}
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        r = httpx.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {settings.groq_api_key}"},
            json=payload, timeout=60.0,
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]
    except Exception as e:
        logger.warning("Groq chat failed: %s", e)
        return None


def chat(messages: list[dict], json_mode: bool = False, prefer: str = "local") -> str | None:
    """Route to the best available provider. prefer='local' tries Ollama first, 'cloud' tries Groq/HF first."""
    local = [_chat_ollama] if _ollama_available() else []
    cloud = [_chat_groq, _chat_hf]
    order = local + cloud if prefer == "local" else cloud + local
    for fn in order:
        out = fn(messages, json_mode)
        if out:
            return out
    return None


def _extract_json(text: str) -> dict | None:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except Exception:
        pass
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start:i + 1])
                except Exception:
                    return None
    return None


def chat_json(system: str, user: str, prefer: str = "local") -> dict | None:
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    out = chat(messages, json_mode=True, prefer=prefer)
    if not out:
        return None
    parsed = _extract_json(out)
    if parsed is None:
        logger.warning("LLM returned non-JSON output: %.200s", out)
    return parsed