import json

from gmsg import routes
from gmsg.utils import norm


def test_norm_strips_case_and_punctuation():
    assert norm(" Alex!! ") == "alex"
    assert norm("⚓️Team Chat⚓") == "team chat"


def test_route_set_resolve_and_remove(tmp_path, monkeypatch):
    routes_path = tmp_path / "routes.json"
    monkeypatch.setattr(routes, "ROUTES_PATH", routes_path)

    route_data = {"aliases": {"partner": "Alex"}}
    routes.save_routes(route_data)

    assert json.loads(routes_path.read_text())["aliases"]["partner"] == "Alex"
    assert routes.resolve_route("Partner") == "Alex"
    assert routes.resolve_route("unknown") == "unknown"


def test_load_routes_ignores_invalid_json(tmp_path, monkeypatch):
    routes_path = tmp_path / "routes.json"
    routes_path.write_text("not json")
    monkeypatch.setattr(routes, "ROUTES_PATH", routes_path)

    assert routes.load_routes() == {}
