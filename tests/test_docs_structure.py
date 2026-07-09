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
