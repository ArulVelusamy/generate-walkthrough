from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "skills" / "generate-walkthrough" / "walkthrough-spec.md"
SKILL = ROOT / "skills" / "generate-walkthrough" / "SKILL.md"


def test_spec_has_sidecar_section():
    text = SPEC.read_text()
    assert "## Sidecar knowledge model" in text
    assert "schema/walkthrough-model.schema.json" in text
    # every top-level sidecar key is documented
    for key in ["endpoints", "aws_calls", "data_model", "parameters", "boundaries", "architecture", "sequence", "state"]:
        assert key in text, f"{key} not documented in walkthrough-spec.md"


def test_spec_has_field_to_html_region_mapping():
    text = SPEC.read_text()
    assert "HTML region" in text  # the mapping table header
    for region in ["Foundations", "Primary journey", "Boundaries", "Parameter glossary"]:
        assert region in text


def test_skill_phase2_is_sidecar_first():
    text = SKILL.read_text()
    assert "walkthrough-model.schema.json" in text
    assert "sidecar" in text.lower()
    # phase 2 builds the sidecar before rendering HTML
    assert "before" in text.lower() and "render" in text.lower()


def test_skill_phase3_has_three_way_verification():
    text = SKILL.read_text().lower()
    assert "sidecar vs source" in text
    assert "html vs sidecar" in text
    assert "narrative" in text and "source" in text
