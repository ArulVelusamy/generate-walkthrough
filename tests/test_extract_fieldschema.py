import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "extract-api-spec"))

from fieldschema import render_field


def r(field):
    hoisted = {}
    return render_field(field, hoisted), hoisted


def test_primitive_with_format():
    out, _ = r({"name": "created", "type": "string", "format": "date-time"})
    assert out == {"type": "string", "format": "date-time"}


def test_integer():
    out, _ = r({"name": "n", "type": "integer"})
    assert out == {"type": "integer"}


def test_enum_infers_string_type():
    out, _ = r({"name": "status", "type": "enum", "enum": ["DRAFT", "PUBLISHED"]})
    assert out == {"type": "string", "enum": ["DRAFT", "PUBLISHED"]}


def test_array_of_objects():
    out, _ = r({"name": "items", "type": "array",
                "items": {"name": "item", "type": "object",
                          "properties": [{"name": "id", "type": "integer", "required": True}]}})
    assert out == {"type": "array", "items": {"type": "object", "properties": {"id": {"type": "integer"}}, "required": ["id"]}}


def test_object_required_derived_from_children():
    out, _ = r({"name": "root", "type": "object", "properties": [
        {"name": "title", "type": "string", "required": True},
        {"name": "body", "type": "string", "required": False},
    ]})
    assert out["type"] == "object"
    assert out["properties"] == {"title": {"type": "string"}, "body": {"type": "string"}}
    assert out["required"] == ["title"]  # only required children, sorted


def test_object_with_no_required_omits_required_key():
    out, _ = r({"name": "root", "type": "object", "properties": [{"name": "x", "type": "string"}]})
    assert "required" not in out


def test_nullable_and_readonly():
    out, _ = r({"name": "id", "type": "integer", "nullable": True, "readOnly": True})
    assert out == {"type": "integer", "nullable": True, "readOnly": True}


def test_additional_properties_bool():
    out, _ = r({"name": "meta", "type": "object", "additionalProperties": True})
    assert out == {"type": "object", "additionalProperties": True}


def test_unknown_type_is_empty_schema_no_bare_nullable():
    # no type, nullable set -> must NOT emit bare nullable on {} (invalid 3.0.3)
    out, _ = r({"name": "x", "nullable": True})
    assert out == {}


def test_oneof_hoists_branches_and_sets_discriminator():
    out, hoisted = r({"name": "payload", "type": "object", "discriminator": "kind", "oneOf": [
        {"name": "A", "type": "object", "properties": [{"name": "kind", "type": "string", "required": True}]},
        {"name": "B", "type": "object", "properties": [{"name": "kind", "type": "string", "required": True}]},
    ]})
    assert out["oneOf"] == [{"$ref": "#/components/schemas/A"}, {"$ref": "#/components/schemas/B"}]
    assert out["discriminator"] == {"propertyName": "kind"}
    assert set(hoisted.keys()) == {"A", "B"}
    assert hoisted["A"]["type"] == "object"
