"""Render sidecar AuthScheme entries into OpenAPI securitySchemes + security. Stdlib only."""


def render_scheme(auth):
    """Return (openapi_security_scheme | None, gap | None) for one AuthScheme."""
    kind = auth.get("kind")
    if kind == "apiKey":
        obj = {"type": "apiKey", "in": auth["in"], "name": auth.get("name", "")}
        return obj, auth.get("gap")     # preserve any disclosed gap (e.g. assumed cookie name)
    if kind == "http":
        obj = {"type": "http", "scheme": auth.get("scheme", "bearer")}
        if auth.get("bearerFormat"):
            obj["bearerFormat"] = auth["bearerFormat"]
        return obj, auth.get("gap")
    if kind == "oauth2":
        # 3.0.3 requires a flows object with a URL; the URL is not recoverable from source,
        # so a REPLACE_ME placeholder is used and recorded as a gap. Scopes survive on the
        # per-operation security requirement.
        obj = {"type": "oauth2", "flows": {"clientCredentials": {
            "tokenUrl": "https://REPLACE_ME/oauth2/token", "scopes": {}}}}
        return obj, "oauth2 token URL for scheme not recoverable from source — placeholder used"
    if kind == "openIdConnect":
        obj = {"type": "openIdConnect",
               "openIdConnectUrl": "https://REPLACE_ME/.well-known/openid-configuration"}
        return obj, "openIdConnect URL not recoverable from source — placeholder used"
    if kind == "mutualTLS":
        # mutualTLS is an OpenAPI 3.1 scheme type; not expressible in 3.0.3 -> gap.
        return None, "mutualTLS security is not expressible in OpenAPI 3.0.3"
    if kind == "none":
        return None, None
    # custom / SigV4 / anything unmappable -> documented gap, never a scheme
    return None, auth.get("gap") or "auth kind '%s' not expressible in OpenAPI" % kind


def render_endpoint_security(auth_list, schemes, gaps):
    """Return the operation `security` list; register schemes; append gaps for unmappable auth."""
    security = []
    for auth in auth_list:
        obj, gap = render_scheme(auth)
        if gap:                        # record gap even when the scheme DOES map (e.g. oauth2 placeholder URL)
            gaps.append(gap)
        if obj is None:
            continue
        name = auth["scheme_name"]
        schemes[name] = obj
        security.append({name: list(auth.get("scopes") or [])})
    return security
