"""Minimal Groq client (OpenAI-compatible REST API) using only the standard library.

If the configured model has been retired on Groq, the client picks a working chat model from the
account's model list, saves the choice to storage/settings.json and retries once.
"""
from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from typing import Iterator

from .config import STORAGE_DIR, settings


class LLMError(RuntimeError):
    pass


class ModelUnavailable(LLMError):
    pass


SETTINGS_FILE = STORAGE_DIR / "settings.json"

# Preferred chat models, best first. Matched as substrings so new versions still match.
PREFERRED = ["gpt-oss-120b", "llama-4-maverick", "kimi-k2", "qwen3", "llama-4-scout", "gpt-oss-20b",
             "llama-3.3-70b", "llama-3.1-8b", "gemma"]
NOT_CHAT = ("whisper", "tts", "guard", "playai", "orpheus", "distil", "embed", "prompt-guard", "safeguard",
            "compound", "allam")
THINK = re.compile(r"<think>.*?</think>", re.DOTALL)


def _load_saved_model() -> None:
    try:
        saved = json.loads(SETTINGS_FILE.read_text(encoding="utf-8")).get("groq_model")
        if saved:
            settings.groq_model = saved
    except (OSError, ValueError):
        pass


def save_model(model: str) -> None:
    settings.groq_model = model
    try:
        SETTINGS_FILE.write_text(json.dumps({"groq_model": model}), encoding="utf-8")
    except OSError:
        pass


_load_saved_model()


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
        text = str(body).lower()
        if e.code in (400, 404) and ("model" in text and ("not exist" in text or "decommission" in text
                                                            or "not found" in text or "no longer" in text
                                                            or "do not have access" in text)):
            raise ModelUnavailable(f"Groq API error {e.code}: {body}") from e
        raise LLMError(f"Groq API error {e.code}: {body}") from e
    except urllib.error.URLError as e:
        raise LLMError(f"Could not reach Groq: {e.reason}") from e


def list_models() -> list[str]:
    """Chat-capable models on this account."""
    with _request("/models", timeout=15) as resp:
        data = json.loads(resp.read())
    ids = [m["id"] for m in data.get("data", []) if m.get("active", True)]
    chat = [m for m in ids if not any(x in m.lower() for x in NOT_CHAT)]

    def rank(m: str) -> tuple[int, str]:
        low = m.lower()
        return (next((i for i, p in enumerate(PREFERRED) if p in low), len(PREFERRED)), m)

    return sorted(chat, key=rank)


def pick_working_model() -> str:
    models = list_models()
    if not models:
        raise LLMError("Your Groq account has no chat models available.")
    old = settings.groq_model
    choice = next((m for m in models if m != old), models[0])
    save_model(choice)
    return choice


def _payload(messages: list[dict], temperature: float, max_tokens: int, model: str | None, **extra) -> dict:
    model = model or settings.groq_model
    payload = {"model": model, "messages": messages, "temperature": temperature,
               "max_tokens": max(max_tokens, 256), **extra}
    low = model.lower()
    if "gpt-oss" in low:
        payload["reasoning_effort"] = "low"        # keep reasoning short so the answer gets the tokens
    elif "qwen3" in low or "deepseek" in low:
        payload["reasoning_format"] = "hidden"     # hide <think> blocks
    return payload


def chat(messages: list[dict], temperature: float = 0.2, max_tokens: int = 1200,
         json_mode: bool = False, model: str | None = None, _retry: bool = True) -> str:
    extra = {"response_format": {"type": "json_object"}} if json_mode else {}
    try:
        with _request("/chat/completions", _payload(messages, temperature, max_tokens, model, **extra),
                      timeout=90) as resp:
            data = json.loads(resp.read())
    except ModelUnavailable:
        if not _retry or model:
            raise
        pick_working_model()
        return chat(messages, temperature, max_tokens, json_mode, None, _retry=False)
    content = data["choices"][0]["message"].get("content") or ""
    return THINK.sub("", content).strip()


def stream_chat(messages: list[dict], temperature: float = 0.2, max_tokens: int = 1400,
                model: str | None = None, _retry: bool = True) -> Iterator[str]:
    payload = _payload(messages, temperature, max_tokens, model, stream=True)
    try:
        resp = _request("/chat/completions", payload, stream=True, timeout=90)
    except ModelUnavailable:
        if not _retry or model:
            raise
        pick_working_model()
        yield from stream_chat(messages, temperature, max_tokens, None, _retry=False)
        return
    in_think = False
    with resp:
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
            if not delta:
                continue
            # Drop any <think>...</think> text a reasoning model streams.
            if "<think>" in delta:
                in_think = True
                delta = delta.split("<think>", 1)[0]
            if in_think and "</think>" in delta:
                in_think = False
                delta = delta.split("</think>", 1)[1]
            elif in_think:
                continue
            if delta:
                yield delta


def ping() -> dict:
    if not available():
        return {"ok": False, "configured": False, "message": "GROQ_API_KEY is not set (offline mode)."}
    t0 = time.perf_counter()
    before = settings.groq_model
    try:
        chat([{"role": "user", "content": "Reply with the single word: ok"}], max_tokens=64)
        out = {"ok": True, "configured": True, "model": settings.groq_model,
               "latency_ms": round((time.perf_counter() - t0) * 1000)}
        if settings.groq_model != before:
            out["switched_from"] = before
        return out
    except LLMError as e:
        return {"ok": False, "configured": True, "model": settings.groq_model, "message": str(e)}
