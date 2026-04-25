"""Unit tests for shared/catalog_tools.py (all HTTP mocked)."""

from __future__ import annotations

import json
from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest

from shared.catalog_tools import (
    get_skill_content,
    get_skill_detail,
    get_skill_versions,
    search_skill_catalog,
    trigger_catalog_sync,
)

_BASE = "https://catalog.example.com"


def _mock_config():
    return {"base_url": _BASE}


def _make_response(body: str | bytes, content_type: str = "application/json"):
    if isinstance(body, str):
        body = body.encode()
    resp = MagicMock()
    resp.read.return_value = body
    resp.headers = {"Content-Type": content_type}
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    return resp


@pytest.mark.unit
class TestSearchSkillCatalog:
    @patch("shared.catalog_tools.get_catalog_config", return_value=_mock_config())
    @patch("shared.catalog_tools.urllib.request.urlopen")
    def test_basic_search(self, mock_urlopen, _mock_cfg):
        payload = {"data": [{"name": "k8s-deploy"}], "pagination": {"total": 1}}
        mock_urlopen.return_value = _make_response(json.dumps(payload))

        result = json.loads(search_skill_catalog(query="kubernetes"))
        assert result["data"][0]["name"] == "k8s-deploy"
        assert result["pagination"]["total"] == 1

        call_url = mock_urlopen.call_args[0][0].full_url
        assert "q=kubernetes" in call_url
        assert "page=1" in call_url

    @patch("shared.catalog_tools.get_catalog_config", return_value=_mock_config())
    @patch("shared.catalog_tools.urllib.request.urlopen")
    def test_filters(self, mock_urlopen, _mock_cfg):
        mock_urlopen.return_value = _make_response('{"data":[],"pagination":{"total":0}}')

        search_skill_catalog(status="published", namespace="devops", tags="ci,cd")
        call_url = mock_urlopen.call_args[0][0].full_url
        assert "status=published" in call_url
        assert "namespace=devops" in call_url
        assert "tags=ci%2Ccd" in call_url

    @patch("shared.catalog_tools.get_catalog_config", return_value=_mock_config())
    @patch("shared.catalog_tools.urllib.request.urlopen")
    def test_per_page_capped(self, mock_urlopen, _mock_cfg):
        mock_urlopen.return_value = _make_response('{"data":[],"pagination":{"total":0}}')

        search_skill_catalog(per_page=200)
        call_url = mock_urlopen.call_args[0][0].full_url
        assert "per_page=100" in call_url


@pytest.mark.unit
class TestGetSkillDetail:
    @patch("shared.catalog_tools.get_catalog_config", return_value=_mock_config())
    @patch("shared.catalog_tools.urllib.request.urlopen")
    def test_returns_detail(self, mock_urlopen, _mock_cfg):
        payload = {"data": {"name": "doc-reviewer", "namespace": "business", "version": "1.0.0"}}
        mock_urlopen.return_value = _make_response(json.dumps(payload))

        result = json.loads(get_skill_detail("business", "doc-reviewer"))
        assert result["data"]["name"] == "doc-reviewer"

        call_url = mock_urlopen.call_args[0][0].full_url
        assert "/api/v1/skills/business/doc-reviewer" in call_url


@pytest.mark.unit
class TestGetSkillVersions:
    @patch("shared.catalog_tools.get_catalog_config", return_value=_mock_config())
    @patch("shared.catalog_tools.urllib.request.urlopen")
    def test_returns_versions(self, mock_urlopen, _mock_cfg):
        payload = {"data": [{"version": "1.0.0", "status": "draft"}, {"version": "1.0.0", "status": "testing"}]}
        mock_urlopen.return_value = _make_response(json.dumps(payload))

        result = json.loads(get_skill_versions("business", "doc-summarizer"))
        assert len(result["data"]) == 2

        call_url = mock_urlopen.call_args[0][0].full_url
        assert "/api/v1/skills/business/doc-summarizer/versions" in call_url


@pytest.mark.unit
class TestGetSkillContent:
    @patch("shared.catalog_tools.get_catalog_config", return_value=_mock_config())
    @patch("shared.catalog_tools.urllib.request.urlopen")
    def test_returns_markdown(self, mock_urlopen, _mock_cfg):
        md = "---\nname: doc-reviewer\n---\n\nYou are a reviewer."
        mock_urlopen.return_value = _make_response(md, "text/markdown")

        result = get_skill_content("business", "doc-reviewer", "1.0.0")
        assert "You are a reviewer" in result

        call_url = mock_urlopen.call_args[0][0].full_url
        assert "/versions/1.0.0/content" in call_url


@pytest.mark.unit
class TestTriggerCatalogSync:
    @patch("shared.catalog_tools.get_catalog_config", return_value=_mock_config())
    @patch("shared.catalog_tools.urllib.request.urlopen")
    def test_triggers_sync(self, mock_urlopen, _mock_cfg):
        mock_urlopen.return_value = _make_response('{"status":"syncing","skills_found":10}')

        result = json.loads(trigger_catalog_sync())
        assert result["status"] == "syncing"

        req = mock_urlopen.call_args[0][0]
        assert req.method == "POST"
        assert "/api/v1/sync" in req.full_url


@pytest.mark.unit
class TestCatalogErrors:
    @patch("shared.catalog_tools.get_catalog_config", return_value=_mock_config())
    @patch("shared.catalog_tools.urllib.request.urlopen")
    def test_http_error(self, mock_urlopen, _mock_cfg):
        import urllib.error

        error_resp = BytesIO(b'{"title":"not found","status":404}')
        mock_urlopen.side_effect = urllib.error.HTTPError(
            url="http://x", code=404, msg="Not Found", hdrs={}, fp=error_resp
        )

        with pytest.raises(RuntimeError, match="Catalog API error 404"):
            get_skill_detail("bad", "nonexistent")

    @patch("shared.catalog_tools.get_catalog_config", return_value=_mock_config())
    @patch("shared.catalog_tools.urllib.request.urlopen")
    def test_url_error(self, mock_urlopen, _mock_cfg):
        import urllib.error

        mock_urlopen.side_effect = urllib.error.URLError("Connection refused")

        with pytest.raises(RuntimeError, match="Catalog API unreachable"):
            search_skill_catalog(query="test")
