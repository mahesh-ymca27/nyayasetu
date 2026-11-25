"""Minimal Groq client (OpenAI-compatible REST API) using only the standard library."""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Iterator

from .config import settings


class LLMError(RuntimeError):
    pass


def available() -> bool:
    return bool(settings.groq_api_key)


def _request(path: str, payload: dict | None = None, stream: bool = False, timeout: int = 60):
    url = settings.groq_base_url.rstrip("/") + path
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        method="POST" if data else "GET",
        headers={
            "Authorization": f"Bearer {settings.groq_api_key}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream" if stream else "application/json",
            "User-Agent": "NyayaSetu/1.0",
        },
    )
    try:
        return urllib.request.urlopen(req, timeout=timeout)
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="ignore")[:400]
        try:
            body = json.loads(body).get("error", {}).get("message", body)
        except (ValueError, AttributeError):
            pass
        raise LLMError(f"Groq API error {e.code}: {body}") from e
    except urllib.error.URLError as e:
        raise LLMError(f"Could not reach Groq: {e.reason}") from e


def list_models() -> list[str]:
    with _request("/models", timeout=15) as resp:
        data = json.loads(resp.read())
    return sorted(m["id"] for m in data.get("data", []))


def chat(messages: list[dict], temperature: float = 0.2, max_tokens: int = 1200,
         json_mode: bool = False, model: str | None = None) -> str:
    payload = {"model": model or settings.groq_model, "messages": messages,
               "temperature": temperature, "max_tokens": max_tokens}
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    with _request("/chat/completions", payload, timeout=90) as resp:
        data = json.loads(resp.read())
    return data["choices"][0]["message"]["content"]


def stream_chat(messages: list[dict], temperature: float = 0.2, max_tokens: int = 1400,
                model: str | None = None) -> Iterator[str]:
    payload = {"model": model or settings.groq_model, "messages": messages,
               "temperature": temperature, "max_tokens": max_tokens, "stream": True}
    with _request("/chat/completions", payload, stream=True, timeout=90) as resp:
        for raw in resp:
            line = raw.decode("utf-8", errors="ignore").strip()
            if not line.startswith("data:"):
                continue
            chunk = line[5:].strip()
            if chunk == "[DONE]":
                break
            try:
                delta = json.loads(chunk)["choices"][0].get("delta", {}).get("content")
            except (ValueError, KeyError, IndexError):
                continue
            if delta:
                yield delta


def ping() -> dict:
    if not available():
        return {"ok": False, "configured": False, "message": "GROQ_API_KEY is not set (offline mode)."}
    t0 = time.perf_counter()
    try:
        chat([{"role": "user", "content": "Reply with the single word: ok"}], max_tokens=5)
        return {"ok": True, "configured": True, "model": settings.groq_model,
                "latency_ms": round((time.perf_counter() - t0) * 1000)}
    except LLMError as e:
        return {"ok": False, "configured": True, "model": settings.groq_model, "message": str(e)}
