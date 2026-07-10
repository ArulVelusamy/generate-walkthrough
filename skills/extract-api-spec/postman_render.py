"""Render a Postman Collection v2.1 + environment from a walkthrough sidecar. Stdlib only."""

_SCHEMA = "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"


def _url(path):
    segments = [s for s in path.split("/") if s != ""]
    postman_segments = []
    variables = []
    for s in segments:
        if s.startswith("{") and s.endswith("}"):
            key = s[1:-1]
            postman_segments.append(":" + key)
            variables.append({"key": key})
        else:
            postman_segments.append(s)
    url = {"raw": "{{baseUrl}}/" + "/".join(postman_segments), "host": ["{{baseUrl}}"], "path": postman_segments}
    if variables:
        url["variable"] = variables
    return url


def _body(request):
    body = request.get("body") or {}
    if not (body.get("grounded") and body.get("schema")):
        return None
    fields = body["schema"].get("properties") or []
    mt = request.get("media_type") or "application/json"
    if mt == "application/x-www-form-urlencoded":
        return {"mode": "urlencoded", "urlencoded": [{"key": f["name"], "value": "", "type": "text"} for f in fields]}
    if mt.startswith("multipart/"):
        return {"mode": "formdata", "formdata": [{"key": f["name"], "value": "", "type": "text"} for f in fields]}
    # default JSON
    example = {f["name"]: "" for f in fields}
    import json
    return {"mode": "raw", "raw": json.dumps(example, indent=2),
            "options": {"raw": {"language": "json"}}}


def _auth(auth_list, env_keys):
    for a in auth_list:
        if a.get("kind") == "http" and a.get("scheme") == "bearer":
            env_keys.add("token")
            return {"type": "bearer", "bearer": [{"key": "token", "value": "{{token}}", "type": "string"}]}
        if a.get("kind") in ("oauth2", "openIdConnect"):
            # Postman's native oauth2 config isn't recoverable from source; ship a bearer hint
            # so the request carries the access token rather than shipping with no auth.
            env_keys.add("accessToken")
            return {"type": "bearer", "bearer": [{"key": "token", "value": "{{accessToken}}", "type": "string"}]}
        if a.get("kind") == "apiKey" and a.get("in") == "header":
            env_keys.add("apiKey")
            return {"type": "apikey", "apikey": [
                {"key": "key", "value": a.get("name", "x-api-key"), "type": "string"},
                {"key": "value", "value": "{{apiKey}}", "type": "string"},
                {"key": "in", "value": "header", "type": "string"}]}
        # session/cookie auth lives in the cookie jar, not the request auth object; skip
    return None


def render_postman(sidecar):
    env_keys = {"baseUrl"}
    folders = {}
    for ep in sidecar["endpoints"]:
        request = {"method": ep["method"], "header": [], "url": _url(ep["path"])}
        body = _body(ep["request"])
        if body:
            request["body"] = body
        auth = _auth(ep.get("auth", []), env_keys)
        if auth:
            request["auth"] = auth
        item = {"name": ep["operationId"], "request": request}
        folders.setdefault(ep["group"], []).append(item)

    collection = {
        "info": {"name": sidecar["project"]["name"], "schema": _SCHEMA},
        "item": [{"name": group, "item": items} for group, items in sorted(folders.items())],
    }
    environment = {
        "name": sidecar["project"]["name"] + " environment",
        "values": [{"key": k, "value": "", "enabled": True} for k in sorted(env_keys)],
    }
    return collection, environment
