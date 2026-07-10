import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "extract-api-spec"))

from auth import render_scheme, render_endpoint_security


def test_apikey_cookie():
    obj, gap = render_scheme({"scheme_name": "session", "kind": "apiKey", "in": "cookie", "name": "session"})
    assert obj == {"type": "apiKey", "in": "cookie", "name": "session"}
    assert gap is None


def test_apikey_header():
    obj, gap = render_scheme({"scheme_name": "apikey", "kind": "apiKey", "in": "header", "name": "x-api-key"})
    assert obj == {"type": "apiKey", "in": "header", "name": "x-api-key"}
    assert gap is None


def test_apikey_gap_preserved():
    obj, gap = render_scheme({"scheme_name": "session", "kind": "apiKey", "in": "cookie",
                              "name": "session", "gap": "cookie name assumed"})
    assert obj["type"] == "apiKey"
    assert gap == "cookie name assumed"   # disclosed gap flows to x-coverage-gaps


def test_http_bearer_jwt():
    obj, gap = render_scheme({"scheme_name": "cognito", "kind": "http", "scheme": "bearer", "bearerFormat": "JWT"})
    assert obj == {"type": "http", "scheme": "bearer", "bearerFormat": "JWT"}


def test_oauth2_scheme_shape():
    obj, gap = render_scheme({"scheme_name": "cognito", "kind": "oauth2", "scopes": ["posts.write"]})
    assert obj["type"] == "oauth2"
    assert obj["flows"]["clientCredentials"]["tokenUrl"]   # 3.0.3 requires a flow with a URL
    assert gap and "not recoverable" in gap                # placeholder URL is a documented gap


def test_custom_sigv4_is_gap_not_none():
    obj, gap = render_scheme({"scheme_name": "sigv4", "kind": "custom", "gap": "IAM SigV4 — not expressible in OpenAPI"})
    assert obj is None
    assert "SigV4" in gap


def test_endpoint_security_empty_auth_invents_nothing():
    schemes, gaps = {}, []
    assert render_endpoint_security([], schemes, gaps) == []
    assert schemes == {}
    assert gaps == []


def test_endpoint_security_collects_scheme_and_scopes():
    schemes, gaps = {}, []
    sec = render_endpoint_security(
        [{"scheme_name": "cognito", "kind": "oauth2", "scopes": ["posts.write"]}], schemes, gaps)
    assert sec == [{"cognito": ["posts.write"]}]
    assert "cognito" in schemes and schemes["cognito"]["type"] == "oauth2"


def test_endpoint_security_custom_adds_gap_no_requirement():
    schemes, gaps = {}, []
    sec = render_endpoint_security(
        [{"scheme_name": "sigv4", "kind": "custom", "gap": "IAM SigV4 — not expressible in OpenAPI"}], schemes, gaps)
    assert sec == []          # no invented requirement
    assert schemes == {}
    assert any("SigV4" in g for g in gaps)
