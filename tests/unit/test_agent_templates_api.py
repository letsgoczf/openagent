from __future__ import annotations

from fastapi.testclient import TestClient

from backend.api.app import app


def test_agent_templates_lists_alignment() -> None:
    client = TestClient(app)
    r = client.get("/v1/agent-templates")
    assert r.status_code == 200
    data = r.json()
    assert "agents" in data
    ids = {a["id"] for a in data["agents"]}
    assert "alignment" in ids
    for a in data["agents"]:
        assert "blurb" in a
        assert isinstance(a["blurb"], str)
