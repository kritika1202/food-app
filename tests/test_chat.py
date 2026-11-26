from datetime import datetime, timedelta
import json
from types import SimpleNamespace
from fastapi.testclient import TestClient
from app import chat
from app.database import SessionLocal
from app.main import app
from app.models import PendingAction

def test_chat_ownership_and_failure_is_persisted(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with TestClient(app) as client:
        session_id = client.post("/api/chat/sessions", auth=("maya", "demo1234")).json()["id"]
        response = client.post(f"/api/chat/sessions/{session_id}/messages", auth=("maya", "demo1234"), json={"message": "Hello"})
        assert response.json()["mode"] == "ERROR"
        history = client.get(f"/api/chat/sessions/{session_id}/messages", auth=("maya", "demo1234")).json()
        assert [row["role"] for row in history] == ["user", "assistant"]
        assert client.get(f"/api/chat/sessions/{session_id}/messages", auth=("arjun", "demo1234")).status_code == 404

def test_confirmation_is_required_and_replay_is_idempotent(monkeypatch):
    calls = []
    def fake_api(method, path, auth, **kwargs):
        calls.append((method, path))
        return {"id": 71, "status": "CONFIRMED", "total": "90.00", "lines": []}
    monkeypatch.setattr(chat, "api", fake_api)
    with TestClient(app) as client:
        session_id = client.post("/api/chat/sessions", auth=("maya", "demo1234")).json()["id"]
        with SessionLocal() as db:
            from app.models import ChatSession
            session = db.get(ChatSession, session_id)
            action = PendingAction(session_id=session_id, user_id=session.user_id, action="prepare_order", payload={"lines": [{"item_id": 1, "quantity": 1, "expected_unit_price": "90.00"}]}, expires_at=datetime.utcnow() + timedelta(minutes=5), idempotency_key=f"test-action-{session_id}")
            db.add(action)
            db.commit()
            action_id = action.id
        assert calls == []
        assert client.post(f"/api/chat/actions/{action_id}/confirm", auth=("arjun", "demo1234"), json={"confirm": True}).status_code == 404
        assert client.post(f"/api/chat/actions/{action_id}/confirm", auth=("maya", "demo1234"), json={"confirm": True}).status_code == 200
        assert client.post(f"/api/chat/actions/{action_id}/confirm", auth=("maya", "demo1234"), json={"confirm": True}).status_code == 200
        assert len(calls) == 1

def test_agent_creates_pending_action_without_ordering(monkeypatch):
    calls = []
    def fake_api(method, path, auth, **kwargs):
        calls.append((method, path))
        return {"id": 1, "title": "Masala Dosa", "price": "90.00", "capacity": 10}
    class ToolReply:
        tool_calls = [SimpleNamespace(id="call-1", function=SimpleNamespace(name="prepare_order", arguments=json.dumps({"lines": [{"item_id": 1, "quantity": 1}]})))]
        def model_dump(self, **kwargs):
            return {"role": "assistant", "tool_calls": [{"id": "call-1", "type": "function", "function": {"name": "prepare_order", "arguments": json.dumps({"lines": [{"item_id": 1, "quantity": 1}]})}}]}
    class Completions:
        count = 0
        def create(self, **kwargs):
            self.count += 1
            message = ToolReply() if self.count == 1 else SimpleNamespace(tool_calls=None, content="Please confirm your order.")
            return SimpleNamespace(choices=[SimpleNamespace(message=message)])
    monkeypatch.setattr(chat, "api", fake_api)
    monkeypatch.setattr(chat, "openai_client", lambda: SimpleNamespace(chat=SimpleNamespace(completions=Completions())))
    with TestClient(app) as client:
        session_id = client.post("/api/chat/sessions", auth=("maya", "demo1234")).json()["id"]
        response = client.post(f"/api/chat/sessions/{session_id}/messages", auth=("maya", "demo1234"), json={"message": "Order a dosa"})
        assert response.status_code == 200
        assert response.json()["mode"] == "AGENT"
        assert len(response.json()["pending_actions"]) == 1
        assert calls == [("GET", "/api/menu_items/1")]
        action_id = response.json()["pending_actions"][0]["pending_action_id"]
        history = client.get(f"/api/chat/sessions/{session_id}/messages", auth=("maya", "demo1234")).json()
        assert history[-1]["pending_actions"][0]["status"] == "PENDING"
        assert client.post(f"/api/chat/actions/{action_id}/confirm", auth=("maya", "demo1234"), json={"confirm": False}).json()["status"] == "REJECTED"
        assert calls == [("GET", "/api/menu_items/1")]