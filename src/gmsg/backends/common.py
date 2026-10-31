"""Helpers shared by the backends: aria-label parsing, send checks, CLI output."""
from __future__ import annotations

import json
import re
import sys
from collections.abc import Callable

# Status text Google Messages appends to a message's aria-label.
MESSAGE_SUFFIX_RE = r"\. Received on.*$|\. Sent on.*$|\. Read\..*$|\. Delivered\..*$|\. Pending.*$"
_TIMESTAMP_RE = re.compile(r"(?:Sent|Received|Read|Delivered)\s+on\s+(.*?)(?:\.|$)")


def aria_direction(aria: str) -> str:
    """Return "received" for another person's message aria-label, else "sent"."""
    if "said:" in aria and "You said:" not in aria and "You sent:" not in aria:
        return "received"
    return "sent"


def aria_timestamp(aria: str) -> str:
    match = _TIMESTAMP_RE.search(aria)
    return match.group(1).strip() if match else ""


def sent_message_seen(messages: list[dict], wanted: str, normalize: Callable[[str], str]) -> bool:
    """True if a sent message in ``messages`` matches the normalized ``wanted`` text."""
    for msg in reversed(messages):
        if msg.get("direction") != "sent":
            continue
        body = normalize(msg.get("body") or "")
        if body == wanted or wanted in body or body in wanted:
            return True
    return False


def print_json(data) -> None:
    print(json.dumps(data, ensure_ascii=False))


def print_error(message: str) -> None:
    print(f"gmsg: {message}", file=sys.stderr)


def print_chats(chats: list[dict]) -> None:
    for c in chats:
        preview = c.get("preview", "")
        if len(preview) > 120:
            preview = preview[:117] + "..."
        extra = f" — {preview}" if preview else ""
        print(f"{c['index']}. {c['title']}{extra}")


def print_history(result: dict, args) -> int:
    if args.json:
        print_json(result)
        return 0
    if not result.get("ok"):
        print_error(result.get("error", "unknown error"))
        return 1
    print(f"Conversation: {result.get('conversation') or args.to}\n")
    for msg in reversed(result.get("messages", [])):
        prefix = "→" if msg["direction"] == "received" else "←"
        ts = f" ({msg['timestamp']})" if msg["timestamp"] else ""
        print(f"  {prefix} {msg['body'][:200]}{ts}")
    return 0


def run_app_backend(
    args,
    *,
    open_app: Callable[[], None],
    pair_text: str,
    status: Callable[[], dict],
    ready_text: str,
    list_chats: Callable[[int], list[dict]],
    history: Callable[[str, int], dict],
    send: Callable[..., dict],
    chats_extra: dict | None = None,
) -> int:
    """Run one CLI command for an app-driving backend (chrome, lite).

    Each backend supplies its own callables; output format and exit codes are
    shared so both backends behave the same at the CLI.
    """
    try:
        if args.command == "pair":
            open_app()
            print(pair_text)
            return 0
        if args.command == "status":
            data = status()
            if args.json:
                print_json(data)
            elif data.get("paired"):
                print(ready_text)
            else:
                print(data.get("detail", "Not ready."))
            return 0 if data.get("ok") else 1
        if args.command == "chats":
            chats = list_chats(args.limit)
            if args.json:
                print_json({"ok": True, "chats": chats, **(chats_extra or {})})
            else:
                print_chats(chats)
            return 0
        if args.command == "history":
            return print_history(history(args.to, args.limit), args)
        if args.command == "send":
            result = send(args.to, args.text, draft=args.draft)
            if args.json:
                print_json(result)
            elif result.get("ok"):
                verb = "prepared" if args.draft else "sent"
                print(f"Message {verb}: {result.get('preview', '')}".rstrip())
            else:
                print_error(result.get("error", "unknown error"))
                return 1
            return 0 if result.get("ok") else 1
        return 2
    except Exception as exc:
        if getattr(args, "json", False):
            print_json({"ok": False, "error": str(exc)})
        else:
            print_error(str(exc))
        return 1
