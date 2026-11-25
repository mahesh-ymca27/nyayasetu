"""HTTP API: auth, law endpoints, documents, assistant (offline), and that users cannot see each other's data."""
import json

from conftest import SAMPLES


def test_health(client):
    r = client.get("/api/health").json()
    assert r["status"] == "ok" and r["sections"] == 2354 and r["llm_configured"] is False


def test_auth_required(client):
    assert client.get("/api/stats/overview").status_code == 401
    assert client.get("/api/stats/overview", headers={"Authorization": "Bearer junk"}).status_code == 401


def test_login_and_register_errors(client):
    assert client.post("/api/auth/login", json={"email": "demo@nyayasetu.in", "password": "wrong"}).status_code == 401
    dup = client.post("/api/auth/register", json={"name": "X Y", "email": "demo@nyayasetu.in", "password": "secret12"})
    assert dup.status_code == 409
    short = client.post("/api/auth/register", json={"name": "X Y", "email": "a@b.co", "password": "123"})
    assert short.status_code == 400


def test_dashboard_overview(client, auth):
    r = client.get("/api/stats/overview", headers=auth).json()
    c = r["corpus"]
    assert c["sections"] == 2354 and c["mappings"] == 1059 and c["classified_offences"] == 466
    assert len(c["bns_chapters"]) == 20


def test_convert_endpoints(client, auth):
    r = client.get("/api/convert", params={"act": "IPC", "number": "420"}, headers=auth).json()
    assert r["results"][0]["id"] == "BNS-318"
    assert r["results"][0]["classification"][0]["provision"] == "318(4)"
    assert client.get("/api/convert", params={"act": "IPC", "number": "9999"}, headers=auth).status_code == 404
    t = client.post("/api/convert/text", json={"text": "u/s 302 IPC"}, headers=auth).json()
    assert "BNS 103" in t["converted_text"]


def test_law_browsing(client, auth):
    assert client.get("/api/sections/BNS-103", headers=auth).json()["heading"] == "Punishment for murder"
    assert client.get("/api/sections/BNS-9999", headers=auth).status_code == 404
    assert len(client.get("/api/acts/BNS/chapters", headers=auth).json()) == 20
    assert client.get("/api/mappings", params={"act": "BNSS", "q": "bail"}, headers=auth).json()["total"] > 0
    for path in ("/api/graph/overview", "/api/graph/section/BNS-318"):
        assert client.get(path, headers=auth).json()["nodes"]


def test_search_and_evaluation(client, auth):
    r = client.get("/api/search", params={"q": "dowry death", "k": 3}, headers=auth).json()
    assert "BNS-80" in [x["id"] for x in r["results"]]
    assert client.get("/api/search", params={"q": "x", "method": "bad"}, headers=auth).status_code == 400
    assert client.get("/api/evaluation", headers=auth).json()["questions"] == 42


def test_ask_streams_offline_answer_with_verified_citations(client, auth):
    r = client.post("/api/ask", json={"question": "IPC 420 ka naya section kya hai"}, headers=auth)
    events = [json.loads(line[5:]) for line in r.text.splitlines() if line.startswith("data:")]
    assert events[0]["type"] == "sources" and events[0]["sources"][0]["id"] == "BNS-318"
    done = events[-1]
    assert done["type"] == "done" and done["mode"] == "offline"
    assert done["verification"]["total"] > 0 and done["verification"]["score"] == 1.0
    assert client.post("/api/ask", json={"question": "  "}, headers=auth).status_code == 400


def test_document_lifecycle(client, auth, new_user):
    pdf = (SAMPLES / "test_fir_5page.pdf").read_bytes()
    up = client.post("/api/documents", files={"file": ("fir.pdf", pdf, "application/pdf")}, headers=auth)
    assert up.status_code == 200
    doc_id = up.json()["id"]
    assert len(up.json()["analysis"]["references"]) == 24

    assert client.get(f"/api/documents/{doc_id}", headers=auth).status_code == 200
    assert client.get(f"/api/documents/{doc_id}", headers=new_user).status_code == 404  # other users cannot see it
    assert client.delete(f"/api/documents/{doc_id}", headers=new_user).status_code == 404

    s = client.post(f"/api/documents/{doc_id}/summary", headers=auth).json()
    assert s["mode"] == "offline" and s["summary"]
    a = client.post(f"/api/documents/{doc_id}/ask", json={"question": "How much money was transferred?"}, headers=auth)
    assert a.json()["passages"]
    for fmt, marker in (("txt", "===== Page 1 ====="), ("md", "# NyayaSetu analysis"), ("json", '"analysis"')):
        r = client.get(f"/api/documents/{doc_id}/export", params={"format": fmt}, headers=auth)
        assert r.status_code == 200 and marker in r.text

    assert client.delete(f"/api/documents/{doc_id}", headers=auth).json() == {"deleted": True}
    assert client.get(f"/api/documents/{doc_id}", headers=auth).status_code == 404


def test_upload_validation(client, auth):
    def up(name, data, ctype="application/octet-stream"):
        return client.post("/api/documents", files={"file": (name, data, ctype)}, headers=auth).status_code

    assert up("empty.txt", b"") == 400
    assert up("x.docx", b"PK\x03\x04junk") == 415
    assert up("bad.pdf", b"%PDF-1.4 garbage") == 422
    assert up("notice.txt", (SAMPLES / "test_fir_5page.txt").read_bytes(), "text/plain") == 200


def test_frontend_is_served(client):
    assert "NyayaSetu" in client.get("/").text
    assert client.get("/js/app.js").status_code == 200
    assert client.get("/samples/sample_fir.pdf").status_code == 200
