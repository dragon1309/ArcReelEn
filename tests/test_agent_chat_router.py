"""Tests for the synchronous agent-chat endpoint."""

from unittest.mock import AsyncMock, MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.auth import CurrentUserInfo, get_current_user
from server.routers import agent_chat


def _make_client() -> TestClient:
    app = FastAPI()
    app.dependency_overrides[get_current_user] = lambda: CurrentUserInfo(id="default", sub="testuser", role="admin")
    app.include_router(agent_chat.router, prefix="/api/v1")
    return TestClient(app)


def _fake_session(session_id: str = "sess-1", project_name: str = "demo"):
    meta = MagicMock()
    meta.id = session_id
    meta.project_name = project_name
    return meta


class TestAgentChatEndpoint:
    def _patch_service(
        self, monkeypatch, *, project_exists=True, reply_text="Hello", status="completed", session_id="sess-1"
    ):
        """Build and inject a mocked AssistantService."""
        mock_service = AsyncMock()

        # Project existence check.
        pm = MagicMock()
        if project_exists:
            pm.get_project_path = MagicMock(return_value="/fake/path")
        else:
            pm.get_project_path = MagicMock(side_effect=FileNotFoundError("not found"))
        mock_service.pm = pm

        # Session lookup used for ownership validation.
        mock_service.get_session = AsyncMock(return_value=_fake_session(session_id=session_id))

        # Unified send endpoint.
        mock_service.send_or_create = AsyncMock(return_value={"status": "accepted", "session_id": session_id})

        monkeypatch.setattr(agent_chat, "get_assistant_service", lambda: mock_service)
        monkeypatch.setattr(
            agent_chat,
            "_collect_reply",
            AsyncMock(return_value=(reply_text, status)),
        )
        return mock_service

    def test_new_session_returns_reply(self, monkeypatch):
        self._patch_service(monkeypatch, reply_text="I generated a script for you")
        with _make_client() as client:
            resp = client.post(
                "/api/v1/agent/chat",
                json={
                    "project_name": "demo",
                    "message": "Write a script for me",
                },
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["reply"] == "I generated a script for you"
        assert body["status"] == "completed"
        assert "session_id" in body

    def test_reuse_existing_session(self, monkeypatch):
        self._patch_service(monkeypatch, reply_text="Continuing the conversation")
        with _make_client() as client:
            resp = client.post(
                "/api/v1/agent/chat",
                json={
                    "project_name": "demo",
                    "message": "Continue",
                    "session_id": "sess-1",
                },
            )
        assert resp.status_code == 200
        assert resp.json()["session_id"] == "sess-1"

    def test_project_not_found_returns_404(self, monkeypatch):
        self._patch_service(monkeypatch, project_exists=False)
        with _make_client() as client:
            resp = client.post(
                "/api/v1/agent/chat",
                json={
                    "project_name": "nonexistent",
                    "message": "test",
                },
            )
        assert resp.status_code == 404

    def test_timeout_status_propagated(self, monkeypatch):
        self._patch_service(monkeypatch, reply_text="Partial response", status="timeout")
        with _make_client() as client:
            resp = client.post(
                "/api/v1/agent/chat",
                json={
                    "project_name": "demo",
                    "message": "Long-running task",
                },
            )
        assert resp.status_code == 200
        assert resp.json()["status"] == "timeout"
        assert resp.json()["reply"] == "Partial response"


class TestExtractTextFromAssistantMessage:
    def test_list_content(self):
        msg = {"type": "assistant", "content": [{"type": "text", "text": "Hello"}]}
        assert agent_chat._extract_text_from_assistant_message(msg) == "Hello"

    def test_string_content(self):
        msg = {"type": "assistant", "content": "Plain text"}
        assert agent_chat._extract_text_from_assistant_message(msg) == "Plain text"

    def test_multiple_text_blocks(self):
        msg = {
            "type": "assistant",
            "content": [
                {"type": "text", "text": "第一段"},
                {"type": "tool_use", "name": "Read"},
                {"type": "text", "text": "First part"},
                {"type": "tool_use", "name": "Read"},
                {"type": "text", "text": "Second part"},
            ],
        }
        assert agent_chat._extract_text_from_assistant_message(msg) == "First partSecond part"

    def test_no_text_blocks(self):
        msg = {"type": "assistant", "content": [{"type": "tool_use", "name": "Read"}]}
        assert agent_chat._extract_text_from_assistant_message(msg) == ""
