"""Render a sidecar FieldSchema into an OpenAPI 3.0.3 Schema Object. Stdlib only."""

_PRIMITIVES = {"string", "number", "integer", "boolean", "object", "array"}


def _infer_enum_type(values):
    if values and all(isinstance(v, bool) for v in values):
        return "boolean"
    if values and all(isinstance(v, int) and not isinstance(v, bool) for v in values):
        return "integer"
    if values and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in values):
        return "number"
    if values and all(isinstance(v, str) for v in values):
        return "string"
    return None


def render_field(field, hoisted):
    t = field.get("type")
    out = {}

    if field.get("oneOf"):
        refs = []
        for branch in field["oneOf"]:
            name = branch.get("name") or "OneOf%d" % (len(hoisted) + 1)
            hoisted[name] = render_field(branch, hoisted)
            refs.append({"$ref": "#/components/schemas/%s" % name})
        out["oneOf"] = refs
        if field.get("discriminator"):
            out["discriminator"] = {"propertyName": field["discriminator"]}
        return out

    if t == "enum":
        inferred = _infer_enum_type(field.get("enum") or [])
        if inferred:
            out["type"] = inferred
        out["enum"] = list(field.get("enum") or [])
    elif t == "array":
        out["type"] = "array"
        items = field.get("items")
        out["items"] = render_field(items, hoisted) if items else {}
    elif t == "object":
        out["type"] = "object"
        props = field.get("properties") or []
        if props:                       # omit an empty properties map (keeps output minimal/valid)
            out["properties"] = {p["name"]: render_field(p, hoisted) for p in props}
        required = sorted(p["name"] for p in props if p.get("required"))
        if required:
            out["required"] = required
        ap = field.get("additionalProperties")
        if isinstance(ap, bool):
            out["additionalProperties"] = ap
        elif isinstance(ap, dict):
            out["additionalProperties"] = render_field(ap, hoisted)
    elif t in _PRIMITIVES:
        out["type"] = t
    # else: unknown type -> {} (any); do NOT add a bare nullable

    if "format" in field and t not in (None, "object", "array", "enum"):
        out["format"] = field["format"]
    # nullable only when a concrete type is present (never bare nullable on {})
    if field.get("nullable") and "type" in out:
        out["nullable"] = True
    if field.get("readOnly"):
        out["readOnly"] = True
    if field.get("writeOnly"):
        out["writeOnly"] = True
    return out
