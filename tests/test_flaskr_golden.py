from pathlib import Path
from test_schema import load, make_validator

GOLDEN = Path(__file__).resolve().parent / "fixtures" / "valid" / "flaskr.model.json"


def _endpoints():
    return { (e["method"], e["path"]): e for e in load(GOLDEN)["endpoints"] }


def test_golden_validates_against_schema():
    errors = list(make_validator().iter_errors(load(GOLDEN)))
    assert errors == [], [e.message for e in errors]


def test_full_route_set_including_twins_and_smoke():
    keys = set(_endpoints().keys())
    expected = {
        ("GET", "/"),
        ("GET", "/auth/register"), ("POST", "/auth/register"),
        ("GET", "/auth/login"), ("POST", "/auth/login"),
        ("POST", "/auth/logout"),
        ("GET", "/create"), ("POST", "/create"),
        ("GET", "/{id}/update"), ("POST", "/{id}/update"),
        ("POST", "/{id}/delete"),
        ("GET", "/hello"),
    }
    assert expected <= keys, f"missing: {expected - keys}"


def test_hello_is_non_journey():
    assert _endpoints()[("GET", "/hello")]["in_journey"] is False


def test_create_post_is_form_encoded():
    assert _endpoints()[("POST", "/create")]["request"]["media_type"] == "application/x-www-form-urlencoded"


def test_create_post_success_is_302_with_location_and_no_401():
    statuses = { r["status"] for r in _endpoints()[("POST", "/create")]["responses"] }
    assert 302 in statuses
    assert 401 not in statuses  # auth gate redirects; never a synthesized 401
    redirect = next(r for r in _endpoints()[("POST", "/create")]["responses"] if r["status"] == 302)
    assert any(h["name"].lower() == "location" for h in redirect.get("headers", []))


def test_update_uses_integer_path_param():
    params = _endpoints()[("POST", "/{id}/update")]["request"]["path_params"]
    assert any(p["name"] == "id" and p["type"] == "integer" for p in params)


def test_delete_models_403_and_404_only_where_get_post_guards():
    statuses = { r["status"] for r in _endpoints()[("POST", "/{id}/delete")]["responses"] }
    assert {403, 404} <= statuses
