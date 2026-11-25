"""The .env loader (Windows editor quirks) and the Groq client's retired-model fallback."""
import io
import json

import pytest

from backend import config, llm


@pytest.mark.parametrize("raw", [
    b"\xef\xbb\xbfGROQ_TEST_KEY=gsk_abc\r\n",            # UTF-8 with BOM (Notepad)
    "GROQ_TEST_KEY=gsk_abc\r\n".encode("utf-16"),        # UTF-16 (PowerShell echo >)
    b'GROQ_TEST_KEY = "gsk_abc"\n',                      # spaces and quotes
    b"export GROQ_TEST_KEY=gsk_abc  # comment\n",
])
def test_dotenv_formats(tmp_path, monkeypatch, raw):
    monkeypatch.delenv("GROQ_TEST_KEY", raising=False)
    f = tmp_path / ".env"
    f.write_bytes(raw)
    config._load_dotenv(f)
    import os
    assert os.environ["GROQ_TEST_KEY"] == "gsk_abc"


def test_empty_windows_variable_does_not_block_env_file(tmp_path, monkeypatch):
    monkeypatch.setenv("GROQ_TEST_KEY", "")
    f = tmp_path / ".env"
    f.write_text("GROQ_TEST_KEY=gsk_abc\n")
    config._load_dotenv(f)
    import os
    assert os.environ["GROQ_TEST_KEY"] == "gsk_abc"


def test_tests_run_offline():
    assert config.OFFLINE and not llm.available()


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_retired_model_switches_to_working_one(monkeypatch):
    calls = []

    def fake_request(path, payload=None, stream=False, timeout=60, retries=1):
        if path == "/models":
            return FakeResponse(json.dumps({"data": [{"id": m} for m in
                                ["allam-2-7b", "whisper-large-v3", "llama-3.1-8b-instant", "openai/gpt-oss-120b"]]}).encode())
        calls.append(payload["model"])
        if payload["model"] == "llama-3.3-70b-versatile":
            raise llm.ModelUnavailable("model does not exist")
        assert payload.get("reasoning_effort") == "low"
        return FakeResponse(json.dumps({"choices": [{"message": {"content": "<think>x</think>ok"}}]}).encode())

    monkeypatch.setattr(llm, "_request", fake_request)
    monkeypatch.setattr(llm, "save_model", lambda m: setattr(config.settings, "groq_model", m))
    monkeypatch.setattr(config.settings, "groq_model", "llama-3.3-70b-versatile")
    assert llm.chat([{"role": "user", "content": "hi"}]) == "ok"
    assert calls == ["llama-3.3-70b-versatile", "openai/gpt-oss-120b"]
    assert config.settings.groq_model == "openai/gpt-oss-120b"


def test_model_list_hides_non_chat_models(monkeypatch):
    monkeypatch.setattr(llm, "_request", lambda *a, **k: FakeResponse(json.dumps({"data": [
        {"id": m} for m in ["allam-2-7b", "whisper-large-v3", "meta-llama/llama-guard-4-12b", "openai/gpt-oss-20b",
                            "openai/gpt-oss-120b"]]}).encode()))
    assert llm.list_models() == ["openai/gpt-oss-120b", "openai/gpt-oss-20b"]
