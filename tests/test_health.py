"""Tests for shared.health -- health check endpoints."""

from __future__ import annotations

from unittest.mock import patch


class TestHealthz:
    def test_returns_ok(self, health_test_client):
        resp = health_test_client.get("/healthz")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}


class TestReadyz:
    @patch("shared.health._neo4j_http_query")
    def test_ready_when_neo4j_ok(self, mock_query, health_test_client):
        mock_query.return_value = [{"ping": 1}]
        resp = health_test_client.get("/readyz")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ready"
        assert data["checks"]["neo4j"] == "ok"

    @patch("shared.health._neo4j_http_query")
    def test_not_ready_when_neo4j_down(self, mock_query, health_test_client):
        mock_query.side_effect = RuntimeError("connection refused")
        resp = health_test_client.get("/readyz")
        assert resp.status_code == 503
        data = resp.json()
        assert data["status"] == "not_ready"
        assert "error" in data["checks"]["neo4j"]
