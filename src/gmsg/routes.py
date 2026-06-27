"""Local route alias storage."""
from __future__ import annotations

import json

from .config import ROUTES_PATH
from .utils import norm

def load_routes() -> dict:
    try:
        if ROUTES_PATH.exists():
            data = json.loads(ROUTES_PATH.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}
    return {}


def save_routes(routes: dict) -> None:
    ROUTES_PATH.parent.mkdir(parents=True, exist_ok=True)
    ROUTES_PATH.write_text(json.dumps(routes, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def resolve_route(recipient: str) -> str:
    routes = load_routes()
    aliases = routes.get("aliases", {}) if isinstance(routes.get("aliases", {}), dict) else {}
    key = norm(recipient)
    for alias, target in aliases.items():
        if norm(alias) == key and isinstance(target, str) and target.strip():
            return target.strip()
    return recipient


def route_main(args) -> int:
    routes = load_routes()
    aliases = routes.get("aliases") if isinstance(routes.get("aliases"), dict) else {}
    routes["aliases"] = aliases
    action = getattr(args, "route_action", "list")
    if action == "list":
        items = [{"alias": k, "target": v} for k, v in sorted(aliases.items(), key=lambda kv: kv[0].lower())]
        if args.json:
            print(json.dumps({"ok": True, "routes_path": str(ROUTES_PATH), "aliases": items}, ensure_ascii=False))
        else:
            for item in items:
                print(f"{item['alias']} -> {item['target']}")
        return 0
    if action == "resolve":
        target = resolve_route(args.alias)
        data = {"ok": True, "alias": args.alias, "target": target, "matched": target != args.alias}
        if args.json:
            print(json.dumps(data, ensure_ascii=False))
        else:
            print(target)
        return 0
    if action == "set":
        aliases[args.alias] = args.target
        save_routes(routes)
        data = {"ok": True, "alias": args.alias, "target": args.target, "routes_path": str(ROUTES_PATH)}
        print(json.dumps(data, ensure_ascii=False) if args.json else f"{args.alias} -> {args.target}")
        return 0
    if action == "remove":
        existed = args.alias in aliases
        aliases.pop(args.alias, None)
        save_routes(routes)
        data = {"ok": True, "alias": args.alias, "removed": existed, "routes_path": str(ROUTES_PATH)}
        print(json.dumps(data, ensure_ascii=False) if args.json else ("removed" if existed else "not found"))
        return 0
    return 2
