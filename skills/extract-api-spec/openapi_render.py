"""Assemble an OpenAPI 3.0.3 document from a walkthrough sidecar. Stdlib only."""

from fieldschema import render_field
from auth import render_endpoint_security

_METHODS = ("get", "post", "put", "patch", "delete", "head", "options")


def _param(field, location):
    p = {"name": field["name"], "in": location,
         "required": bool(field.get("required")) or location == "path",
         "schema": render_field(field, {})}
    return p


def _body_schema(body, comp_name, components, gaps):
    """Return an OpenAPI schema object for a request/response body, registering a named component when grounded."""
    if body.get("grounded") and body.get("schema"):
        hoisted = {}
        rendered = render_field(body["schema"], hoisted)
        components.update(hoisted)
        components[comp_name] = rendered
        return {"$ref": "#/components/schemas/%s" % comp_name}
    gap = body.get("gap") or "not recoverable from source"
    gaps.append(gap)
    return {"description": gap}   # {} (any) + gap marker; nothing invented


def render_openapi(sidecar):
    project = sidecar["project"]
    components_schemas = {}
    security_schemes = {}
    gaps = []
    paths = {}

    for ep in sidecar["endpoints"]:
        op = {"operationId": ep["operationId"], "tags": [ep["group"]], "summary": ep.get("summary", "")}

        params = [_param(f, "path") for f in ep["request"].get("path_params", [])]
        params += [_param(f, "query") for f in ep["request"].get("query_params", [])]
        params += [_param(f, "header") for f in ep["request"].get("headers", [])]
        if params:
            op["parameters"] = params

        body = ep["request"].get("body") or {}
        grounded_body = body.get("grounded") and body.get("schema")
        gap_body = (not body.get("grounded")) and body.get("gap")   # ungrounded body still surfaces its gap
        if grounded_body or gap_body:
            mt = ep["request"].get("media_type") or "application/json"
            schema = _body_schema(body, ep["operationId"] + "Request", components_schemas, gaps)
            op["requestBody"] = {"content": {mt: {"schema": schema}}}

        responses = {}
        for resp in ep["responses"]:
            status = str(resp["status"])
            entry = {"description": resp["description"]}
            headers = {h["name"]: {"schema": render_field(h, {})} for h in resp.get("headers", [])}
            if headers:
                entry["headers"] = headers
            content = {}
            for c in resp.get("content", []):
                schema = _body_schema(c["body"], ep["operationId"] + "Response" + status, components_schemas, gaps)
                content[c["media_type"]] = {"schema": schema}
            if content:
                entry["content"] = content
            responses[status] = entry
        op["responses"] = responses

        security = render_endpoint_security(ep.get("auth", []), security_schemes, gaps)
        if security:
            op["security"] = security

        paths.setdefault(ep["path"], {})[ep["method"].lower()] = op

    doc = {
        "openapi": "3.0.3",
        "info": {"title": project["name"], "version": project["version"]},
        "servers": [{"url": "{baseUrl}", "variables": {"baseUrl": {
            "default": "https://REPLACE_ME",
            "description": "not recoverable from source — set before use"}}}],
        "paths": paths,
    }
    components = {}
    if components_schemas:
        components["schemas"] = components_schemas
    if security_schemes:
        components["securitySchemes"] = security_schemes
    if components:
        doc["components"] = components
    if gaps:
        doc["x-coverage-gaps"] = gaps
    return doc
