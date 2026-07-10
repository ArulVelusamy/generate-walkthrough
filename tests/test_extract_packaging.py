import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_plugin_version_bumped():
    data = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text())
    assert data["version"] == "1.2.0"


def test_skill_md_present_and_shaped():
    text = (ROOT / "skills" / "extract-api-spec" / "SKILL.md").read_text()
    assert text.startswith("---")                     # YAML frontmatter
    assert "name: extract-api-spec" in text
    assert "serialize.py" in text
    for out in ["openapi.json", "postman_collection.json", "aws-calls.md"]:
        assert out in text


def test_changelog_has_120_release():
    text = (ROOT / "CHANGELOG.md").read_text()
    assert "## [1.2.0]" in text
    assert "extract-api-spec" in text
