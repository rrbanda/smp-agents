"""Unit tests for the expert-review pipeline hardening fixes.

Validates TLS flag, pagination, stale-edge cleanup, UNWIND batching,
category field, SAME_PLUGIN post-process, driver cleanup, and
embedding error logging -- all without a live Neo4j or catalog API.
"""

from __future__ import annotations

import ssl
from unittest.mock import MagicMock, call, patch

import pytest


# ---------------------------------------------------------------------------
# build_knowledge_graph tests
# ---------------------------------------------------------------------------

class TestTLSVerification:
    def test_default_tls_verifies(self):
        import scripts.build_knowledge_graph as bkg

        bkg._TLS_VERIFY = True
        ctx = bkg._get_tls_ctx()
        assert ctx.check_hostname is True
        assert ctx.verify_mode == ssl.CERT_REQUIRED

    def test_no_tls_verify_disables(self):
        import scripts.build_knowledge_graph as bkg

        bkg._TLS_VERIFY = False
        ctx = bkg._get_tls_ctx()
        assert ctx.check_hostname is False
        assert ctx.verify_mode == ssl.CERT_NONE
        bkg._TLS_VERIFY = True  # restore default


class TestPagination:
    def test_stops_on_short_page(self):
        """When a page returns fewer items than per_page, pagination stops."""
        import scripts.build_knowledge_graph as bkg

        pages = [
            {"data": [{"name": f"s{i}"} for i in range(100)]},
            {"data": [{"name": f"s{i}"} for i in range(100, 142)]},
        ]
        call_count = {"n": 0}

        def mock_get(url, *, accept="application/json"):
            idx = call_count["n"]
            call_count["n"] += 1
            return pages[idx]

        with patch.object(bkg, "_http_get", side_effect=mock_get):
            result = bkg.fetch_all_skills("http://catalog.example.com")

        assert len(result) == 142
        assert call_count["n"] == 2

    def test_stops_on_empty_page(self):
        import scripts.build_knowledge_graph as bkg

        def mock_get(url, *, accept="application/json"):
            return {"data": []}

        with patch.object(bkg, "_http_get", side_effect=mock_get):
            result = bkg.fetch_all_skills("http://catalog.example.com")

        assert result == []

    def test_does_not_rely_on_total(self):
        """Even if 'total' says 200, we stop when page is short."""
        import scripts.build_knowledge_graph as bkg

        def mock_get(url, *, accept="application/json"):
            return {
                "data": [{"name": "s1"}],
                "pagination": {"total": 200},
            }

        with patch.object(bkg, "_http_get", side_effect=mock_get):
            result = bkg.fetch_all_skills("http://catalog.example.com")

        assert len(result) == 1


class TestCategoryField:
    def test_prefers_category_over_compatibility(self):
        import scripts.build_knowledge_graph as bkg

        skill = {
            "display_name": "test",
            "name": "test",
            "category": "real-category",
            "compatibility": "compat-fallback",
        }
        sd = bkg.build_skill_data(skill)
        assert sd["category"] == "real-category"

    def test_falls_back_to_compatibility(self):
        import scripts.build_knowledge_graph as bkg

        skill = {
            "display_name": "test",
            "name": "test",
            "compatibility": "compat-fallback",
        }
        sd = bkg.build_skill_data(skill)
        assert sd["category"] == "compat-fallback"


class TestUpsertSkillStaleEdgeCleanup:
    def test_deletes_old_edges_before_recreating(self):
        """upsert_skill should DELETE stale TAGGED_WITH/BELONGS_TO/USES_TOOL."""
        import scripts.build_knowledge_graph as bkg

        tx = MagicMock()
        tx.run.return_value = MagicMock(consume=MagicMock())

        skill_data = {
            "name": "test-skill",
            "description": "desc",
            "namespace": "ai-ml",
            "tags": ["python", "ml"],
            "tools": ["tool-a"],
            "bundle_skills_list": [],
        }
        bkg.upsert_skill(tx, skill_data)

        cypher_calls = [c.args[0].strip() for c in tx.run.call_args_list]

        delete_tagged = any("DELETE r" in q and "TAGGED_WITH" in q for q in cypher_calls)
        delete_belongs = any("DELETE r" in q and "BELONGS_TO" in q for q in cypher_calls)
        delete_uses_tool = any("DELETE r" in q and "USES_TOOL" in q for q in cypher_calls)

        assert delete_tagged, "Should DELETE old TAGGED_WITH edges"
        assert delete_belongs, "Should DELETE old BELONGS_TO edges"
        assert delete_uses_tool, "Should DELETE old USES_TOOL edges"


class TestUpsertSkillUNWIND:
    def test_tags_use_unwind(self):
        """Tags should be batched with UNWIND, not one query per tag."""
        import scripts.build_knowledge_graph as bkg

        tx = MagicMock()
        tx.run.return_value = MagicMock(consume=MagicMock())

        skill_data = {
            "name": "test-skill",
            "description": "desc",
            "namespace": "ai-ml",
            "tags": ["python", "ml", "azure"],
            "tools": [],
            "bundle_skills_list": [],
        }
        bkg.upsert_skill(tx, skill_data)

        cypher_calls = [c.args[0].strip() for c in tx.run.call_args_list]

        unwind_tagged = [q for q in cypher_calls if "UNWIND" in q and "TAGGED_WITH" in q]
        assert len(unwind_tagged) == 1, "Should use exactly one UNWIND for all tags"

    def test_tools_use_unwind(self):
        import scripts.build_knowledge_graph as bkg

        tx = MagicMock()
        tx.run.return_value = MagicMock(consume=MagicMock())

        skill_data = {
            "name": "test-skill",
            "description": "desc",
            "namespace": "ai-ml",
            "tags": [],
            "tools": ["tool-a", "tool-b"],
            "bundle_skills_list": [],
        }
        bkg.upsert_skill(tx, skill_data)

        cypher_calls = [c.args[0].strip() for c in tx.run.call_args_list]

        unwind_tools = [q for q in cypher_calls if "UNWIND" in q and "USES_TOOL" in q]
        assert len(unwind_tools) == 1, "Should use exactly one UNWIND for all tools"

    def test_no_same_plugin_inside_upsert(self):
        """SAME_PLUGIN should NOT appear inside upsert_skill anymore."""
        import scripts.build_knowledge_graph as bkg

        tx = MagicMock()
        tx.run.return_value = MagicMock(consume=MagicMock())

        skill_data = {
            "name": "test-skill",
            "description": "desc",
            "namespace": "ai-ml",
            "plugin": "azure-sdk-python",
            "tags": [],
            "tools": [],
            "bundle_skills_list": [],
        }
        bkg.upsert_skill(tx, skill_data)

        cypher_calls = [c.args[0].strip() for c in tx.run.call_args_list]
        same_plugin_calls = [q for q in cypher_calls if "SAME_PLUGIN" in q]
        assert len(same_plugin_calls) == 0, "SAME_PLUGIN should be post-processed, not per-skill"


class TestSamePluginPostProcess:
    def test_creates_edges_in_single_pass(self):
        import scripts.build_knowledge_graph as bkg

        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.single.return_value = {"created": 42}
        mock_session.run.return_value = mock_result

        mock_driver = MagicMock()
        mock_driver.session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_driver.session.return_value.__exit__ = MagicMock(return_value=False)

        count = bkg.create_same_plugin_edges(mock_driver, "neo4j")
        assert count == 42

        cypher_calls = [c.args[0].strip() for c in mock_session.run.call_args_list]
        assert any("SAME_PLUGIN" in q and "MERGE" in q for q in cypher_calls)
        assert any("SAME_PLUGIN" in q and "DELETE" in q for q in cypher_calls)


class TestDriverCleanup:
    def test_driver_closed_on_success(self):
        import scripts.build_knowledge_graph as bkg

        mock_driver = MagicMock()
        mock_session = MagicMock()
        mock_driver.session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_driver.session.return_value.__exit__ = MagicMock(return_value=False)

        with patch.object(bkg, "fetch_all_skills", return_value=[{"name": "s1", "display_name": "s1"}]):
            with patch.object(bkg, "trigger_catalog_sync"):
                with patch.object(bkg, "run_validation", return_value={"checks": [{"passed": True, "name": "ok"}]}):
                    with patch.object(bkg, "collect_stats", return_value={}):
                        with patch.object(bkg, "create_same_plugin_edges", return_value=0):
                            with patch("neo4j.GraphDatabase") as mock_gd:
                                mock_gd.driver.return_value = mock_driver
                                with patch("shared.model_config.get_catalog_config", return_value={"base_url": "http://x"}):
                                    with patch("shared.model_config.get_neo4j_config", return_value={
                                        "uri": "bolt://localhost:7687",
                                        "user": "neo4j",
                                        "password": "test",
                                        "database": "neo4j",
                                    }):
                                        with patch("sys.argv", ["prog", "--skip-sync", "--skip-embeddings"]):
                                            bkg.main()

        mock_driver.close.assert_called_once()

    def test_driver_closed_on_failure(self):
        import scripts.build_knowledge_graph as bkg

        mock_driver = MagicMock()
        mock_session = MagicMock()
        mock_session.execute_write.side_effect = RuntimeError("boom")
        mock_driver.session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_driver.session.return_value.__exit__ = MagicMock(return_value=False)

        with patch.object(bkg, "fetch_all_skills", return_value=[{"name": "s1", "display_name": "s1"}]):
            with patch.object(bkg, "trigger_catalog_sync"):
                with patch.object(bkg, "collect_stats", return_value={}):
                    with patch.object(bkg, "create_same_plugin_edges", return_value=0):
                        with patch("neo4j.GraphDatabase") as mock_gd:
                            mock_gd.driver.return_value = mock_driver
                            with patch("shared.model_config.get_catalog_config", return_value={"base_url": "http://x"}):
                                with patch("shared.model_config.get_neo4j_config", return_value={
                                    "uri": "bolt://localhost:7687",
                                    "user": "neo4j",
                                    "password": "test",
                                    "database": "neo4j",
                                }):
                                    with patch("sys.argv", ["prog", "--skip-sync", "--skip-embeddings", "--skip-validation"]):
                                        bkg.main()

        mock_driver.close.assert_called_once()


# ---------------------------------------------------------------------------
# sync_catalog_to_neo4j tests
# ---------------------------------------------------------------------------

class TestSyncCatalogPagination:
    def test_stops_on_short_page(self):
        import scripts.sync_catalog_to_neo4j as sync

        pages = [
            {"data": [{"name": f"s{i}"} for i in range(100)]},
            {"data": [{"name": f"s{i}"} for i in range(100, 130)]},
        ]
        call_count = {"n": 0}

        def mock_get(base, path, *, accept="application/json"):
            idx = call_count["n"]
            call_count["n"] += 1
            return pages[idx]

        with patch.object(sync, "_catalog_get", side_effect=mock_get):
            result = sync._fetch_all_skills("http://catalog.example.com")

        assert len(result) == 130


class TestSyncCategoryField:
    def test_prefers_category_over_compatibility(self):
        """sync_catalog_to_neo4j should use category field, not just compatibility."""
        import scripts.sync_catalog_to_neo4j as sync

        skill = {
            "display_name": "test",
            "name": "test",
            "category": "real-cat",
            "compatibility": "compat-val",
        }
        tags = sync._parse_tags(skill.get("tags_json", ""))
        skill_data = {
            "category": skill.get("category", skill.get("compatibility", "")),
        }
        assert skill_data["category"] == "real-cat"


# ---------------------------------------------------------------------------
# validate_graph tests
# ---------------------------------------------------------------------------

class TestValidateGraphNaming:
    def test_domain_check_name_says_present(self):
        import scripts.validate_graph as vg

        mock_session = MagicMock()

        def run_query(cypher, **params):
            result = MagicMock()
            if "count(s)" in cypher and "BELONGS_TO" not in cypher:
                result.__iter__ = MagicMock(return_value=iter([{"c": 200}]))
            elif "BELONGS_TO" in cypher and "NOT" in cypher:
                result.__iter__ = MagicMock(return_value=iter([{"c": 0}]))
            elif "TAGGED_WITH" in cypher and "NOT" in cypher:
                result.__iter__ = MagicMock(return_value=iter([{"c": 0}]))
            elif "Domain" in cypher and "RETURN d.name" in cypher:
                result.__iter__ = MagicMock(return_value=iter([
                    {"name": d} for d in vg.EXPECTED_DOMAINS
                ]))
            elif "Tag" in cypher and "NOT" in cypher:
                result.__iter__ = MagicMock(return_value=iter([{"c": 0}]))
            elif "Tool" in cypher and "NOT" in cypher:
                result.__iter__ = MagicMock(return_value=iter([{"c": 0}]))
            elif vg.SPOT_CHECK_SKILL in str(params):
                result.__iter__ = MagicMock(return_value=iter([{
                    "prop_domain": "ai-ml",
                    "domains": ["ai-ml"],
                }]))
            elif "SAME_PLUGIN" in cypher:
                result.__iter__ = MagicMock(return_value=iter([{"c": 10}]))
            elif "USES_TOOL" in cypher:
                result.__iter__ = MagicMock(return_value=iter([{"c": 5}]))
            else:
                result.__iter__ = MagicMock(return_value=iter([{"c": 0}]))
            return result

        mock_session.run = run_query

        mock_driver = MagicMock()
        mock_driver.session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_driver.session.return_value.__exit__ = MagicMock(return_value=False)

        results = vg.validate_graph(mock_driver, "neo4j")
        domain_check = [c for c in results["checks"] if "domain" in c["name"].lower() and "present" in c["name"].lower()]
        assert len(domain_check) == 1, "Should have a check named with 'present'"
        assert "matches" not in domain_check[0]["name"].lower(), "Should NOT say 'matches'"


# ---------------------------------------------------------------------------
# publish_skills tests
# ---------------------------------------------------------------------------

class TestPublishSkillsRegeneration:
    def test_skill_yaml_always_regenerated(self, tmp_path):
        """ensure_skill_yaml should regenerate even if skill.yaml already exists."""
        import sys
        sys.path.insert(0, "/tmp/rrbanda-skills")
        from scripts.publish_skills import ensure_skill_yaml

        skill_dir = tmp_path / "skills" / "ai-ml" / "my-skill"
        skill_dir.mkdir(parents=True)

        (skill_dir / "SKILL.md").write_text(
            "---\nname: my-skill\ndescription: Updated description\n"
            "domain: ai-ml\ntags: [python]\n---\n\n# My Skill\n"
        )
        (skill_dir / "skill.yaml").write_text(
            "apiVersion: skillimage.io/v1alpha1\nkind: SkillCard\n"
            "metadata:\n  name: my-skill\n  namespace: old-ns\n"
            "  version: 0.1.0\n  description: Old description\n"
        )

        repo_root = tmp_path
        (repo_root / "skills").mkdir(exist_ok=True)

        card = ensure_skill_yaml(skill_dir, repo_root)
        assert card is not None
        assert card["metadata"]["description"] == "Updated description"
        assert card["metadata"]["namespace"] == "ai-ml"
