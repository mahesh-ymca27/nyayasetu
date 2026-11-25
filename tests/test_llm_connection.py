"""Groq connection problems: dropped connections are retried once, then reported as LLMError, so the
assistant shows the offline answer instead of crashing with 'network error'."""
import http.client
import io
import json

import pytest

from backend import case_analyzer, config, llm, rag


class Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def reply(text="ok"):
    return Resp(json.dumps({"choices": [{"message": {"content": text}}]}).encode())


@pytest.fixture
def online(monkeypatch):
    monkeypatch.setattr(config.settings, "groq_api_key", "gsk_test")
    monkeypatch.setattr(config.settings, "groq_model", "openai/gpt-oss-120b")
    monkeypatch.setattr(llm.time, "sleep", lambda s: None)


def test_dropped_connection_is_retried_once(online, monkeypatch):
    calls = []

    def urlopen(req, timeout):
        calls.append(timeout)
        if len(calls) == 1:
            raise http.client.RemoteDisconnected("Remote end closed connection without response")
        return reply("hello")

    monkeypatch.setattr(llm.urllib.request, "urlopen", urlopen)
    assert llm.chat([{"role": "user", "content": "hi"}]) == "hello"
    assert len(calls) == 2


def test_connection_that_keeps_failing_becomes_llm_error(online, monkeypatch):
    def urlopen(req, timeout):
        raise ConnectionResetError("reset")

    monkeypatch.setattr(llm.urllib.request, "urlopen", urlopen)
    with pytest.raises(llm.LLMError):
        llm.chat([{"role": "user", "content": "hi"}])
    with pytest.raises(llm.LLMError):
        list(llm.stream_chat([{"role": "user", "content": "hi"}]))


def test_error_replies_are_not_retried(online, monkeypatch):
    calls = []

    def urlopen(req, timeout):
        calls.append(1)
        raise llm.urllib.error.HTTPError(req.full_url, 401, "Unauthorized", {}, io.BytesIO(b'{"error":{"message":"bad key"}}'))

    monkeypatch.setattr(llm.urllib.request, "urlopen", urlopen)
    with pytest.raises(llm.LLMError, match="401"):
        llm.chat([{"role": "user", "content": "hi"}])
    assert len(calls) == 1


def test_connection_dropped_in_the_middle_of_a_streamed_answer(online, monkeypatch):
    class Broken(Resp):
        def __iter__(self):
            yield b'data: {"choices":[{"delta":{"content":"Partial "}}]}\n'
            raise http.client.IncompleteRead(b"")

    monkeypatch.setattr(llm.urllib.request, "urlopen", lambda req, timeout: Broken(b""))
    out = []
    with pytest.raises(llm.LLMError):
        for tok in llm.stream_chat([{"role": "user", "content": "hi"}]):
            out.append(tok)
    assert out == ["Partial "]


def test_assistant_falls_back_to_offline_answer(online, monkeypatch):
    def urlopen(req, timeout):
        raise http.client.RemoteDisconnected("closed")

    monkeypatch.setattr(llm.urllib.request, "urlopen", urlopen)
    events = list(rag.answer_stream("IPC 420 ka naya section kya hai"))
    types = [e["type"] for e in events]
    assert types[0] == "sources" and "error" in types and types[-1] == "done"
    text = "".join(e.get("text", "") for e in events if e["type"] == "token")
    assert "[BNS 318]" in text  # offline answer with the right section


def test_query_rewrite_waits_at_most_four_seconds(online, monkeypatch):
    seen = {}

    def fake_chat(messages, **kw):
        seen.update(kw)
        return "cheating dishonestly"

    monkeypatch.setattr(llm, "chat", fake_chat)
    assert rag.rewrite_query("IPC 420") == "cheating dishonestly"
    assert seen["timeout"] == 4 and seen["retries"] == 0


def test_severity_counts_only_charges_against_the_user(monkeypatch):
    monkeypatch.setattr(llm, "available", lambda: True)
    monkeypatch.setattr(llm, "chat", lambda *a, **k: "Explanation. This is legal information, not legal advice.")

    def fake_chat_json(messages, **kw):
        if messages[0]["content"].startswith("You analyse incidents"):
            return {"summary": "Drunk riding, parked car hit.", "user_role": "accused",
                    "flags": {"vehicle": True, "intoxication": True, "property_damage": True, "false_accusation": True}}
        return {"assessments": [
            {"id": "BNS-281", "verdict": "applies", "against": "user", "reason": "rash riding"},
            {"id": "BNS-324", "verdict": "applies", "against": "user", "reason": "damage"},
            {"id": "BNS-227", "verdict": "applies", "against": "other_party", "reason": "false claim"}]}

    monkeypatch.setattr(llm, "chat_json", fake_chat_json)
    r = case_analyzer.analyze("Two friends and I were riding a scooty. I was drunk and hit a parked car; "
                              "the owner falsely claims we hit her.")
    assert r["severity"]["charges"] == 2
