"""Tests for shared.oci_tools."""

from __future__ import annotations

import json

from shared.oci_tools import validate_skill_yaml
from tests.conftest import (
    INVALID_SKILL_MD_BAD_NAME,
    INVALID_SKILL_MD_NO_FRONTMATTER,
    LONG_DESC_SKILL_MD,
    VALID_SKILL_MD,
)


class TestValidateSkillYaml:
    def test_valid_skill(self):
        result = json.loads(validate_skill_yaml(VALID_SKILL_MD))
        assert result["valid"] is True
        assert result["errors"] == []

    def test_missing_frontmatter(self):
        result = json.loads(validate_skill_yaml(INVALID_SKILL_MD_NO_FRONTMATTER))
        assert result["valid"] is False
        assert any("frontmatter" in e.lower() for e in result["errors"])

    def test_bad_name(self):
        result = json.loads(validate_skill_yaml(INVALID_SKILL_MD_BAD_NAME))
        assert result["valid"] is False
        assert any("kebab-case" in e for e in result["errors"])

    def test_long_description(self):
        result = json.loads(validate_skill_yaml(LONG_DESC_SKILL_MD))
        assert result["valid"] is False
        assert any("1024" in e for e in result["errors"])

    def test_empty_body_warning(self):
        skill_md = "---\nname: test\ndescription: ok\n---\n"
        result = json.loads(validate_skill_yaml(skill_md))
        assert result["valid"] is True
        assert any("empty" in w.lower() for w in result["warnings"])

    def test_missing_name(self):
        skill_md = "---\ndescription: has no name\n---\n\n# Content"
        result = json.loads(validate_skill_yaml(skill_md))
        assert result["valid"] is False
        assert any("name" in e.lower() for e in result["errors"])

    def test_missing_description(self):
        skill_md = "---\nname: my-skill\n---\n\n# Content"
        result = json.loads(validate_skill_yaml(skill_md))
        assert result["valid"] is False
        assert any("description" in e.lower() for e in result["errors"])

    def test_invalid_yaml(self):
        skill_md = "---\n: invalid: yaml: [broken\n---\n\n# Content"
        result = json.loads(validate_skill_yaml(skill_md))
        assert result["valid"] is False
        assert any("yaml" in e.lower() for e in result["errors"])
