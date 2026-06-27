"""Command line access to Google Messages for Web."""
from __future__ import annotations

import argparse
import sys
import textwrap
import time as _time

from .backends.chrome import chrome_main
from .backends.lite import lite_main
from .backends.playwright import (
    AUTH_STATE,
    close_browser,
    cmd_chats,
    cmd_history,
    cmd_send,
    cmd_status,
    get_page,
    save_auth,
    status_data,
)
from .config import AUTH_MODE
from .routes import route_main
from .utils import norm


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gmsg",
        description="Google Messages CLI for Messages for Web.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            Examples:
              gmsg status
              gmsg chats --limit 10 --json
              gmsg history --to "Alex" --limit 10
              gmsg send --to "Alex" --text "On my way"
              gmsg send --to "Alex" --text "Draft test" --draft
              gmsg route list
              gmsg route set partner "Alex"
              gmsg route resolve family
              gmsg pair  (opens browser for QR scan)
        """),
    )
    sub = parser.add_subparsers(dest="command")

    status_p = sub.add_parser("status", help="Check pairing / readiness")
    status_p.add_argument("--json", "-j", action="store_true")
    sub.add_parser("pair", help="Open visible browser for QR pairing")

    chats_p = sub.add_parser("chats", help="List conversations")
    chats_p.add_argument("--limit", type=int, default=20)
    chats_p.add_argument("--json", "-j", action="store_true")

    hist_p = sub.add_parser("history", help="Show recent messages in a conversation")
    hist_p.add_argument("--to", required=True, help="Contact name")
    hist_p.add_argument("--limit", type=int, default=20)
    hist_p.add_argument("--json", "-j", action="store_true")

    send_p = sub.add_parser("send", help="Send or draft a message")
    send_p.add_argument("--to", required=True, help="Contact name or phone number")
    text_grp = send_p.add_mutually_exclusive_group(required=True)
    text_grp.add_argument("--text", help="Message body")
    text_grp.add_argument("--message", "-m", dest="text", help="Message body (alias)")
    send_p.add_argument("--draft", action="store_true", help="Compose without sending")
    send_p.add_argument("--json", "-j", action="store_true", help="JSON output")

    route_p = sub.add_parser("route", help="Manage gmsg route aliases")
    route_sub = route_p.add_subparsers(dest="route_action")
    route_list = route_sub.add_parser("list", help="List route aliases")
    route_list.add_argument("--json", "-j", action="store_true")
    route_resolve = route_sub.add_parser("resolve", help="Resolve an alias to a target chat/contact")
    route_resolve.add_argument("alias")
    route_resolve.add_argument("--json", "-j", action="store_true")
    route_set = route_sub.add_parser("set", help="Set an alias, e.g. gmsg route set partner 'Alex'")
    route_set.add_argument("alias")
    route_set.add_argument("target")
    route_set.add_argument("--json", "-j", action="store_true")
    route_remove = route_sub.add_parser("remove", help="Remove an alias")
    route_remove.add_argument("alias")
    route_remove.add_argument("--json", "-j", action="store_true")
    return parser


def playwright_main(args, parser: argparse.ArgumentParser) -> int:
    if args.command == "pair":
        p, browser, context, page = get_page(headless=False)
        print("Browser opened. Sign in with Google or scan the QR code to pair.")
        print("Waiting for conversations to load...")

        paired = False
        for _ in range(120):
            try:
                has_convs = page.evaluate("document.querySelectorAll('a[role=option]').length > 0")
                if has_convs:
                    paired = True
                    break
            except Exception:
                pass
            _time.sleep(1)

        print("Paired! Saving auth..." if paired else "Timed out. Saving whatever state we have...")
        save_auth(context)
        print(f"Auth saved to {AUTH_STATE}")
        close_browser(p, browser, context)
        return 0 if paired else 1

    p, browser, context, page = get_page(headless=True)
    status = status_data(page)
    if not status.get("paired") and args.command != "status":
        print("Not paired or Google session expired. Run 'gmsg pair' first.", file=sys.stderr)
        close_browser(p, browser, context)
        return 1

    try:
        if args.command == "status":
            return cmd_status(page, args)
        if args.command == "chats":
            return cmd_chats(page, args)
        if args.command == "history":
            return cmd_history(page, args)
        if args.command == "send":
            return cmd_send(page, args)
        parser.print_help()
        return 2
    finally:
        save_auth(context)
        close_browser(p, browser, context)


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "route":
        if getattr(args, "route_action", None) is None:
            args.route_action = "list"
            args.json = False
        return route_main(args)

    if AUTH_MODE == "chrome":
        return chrome_main(args)
    if AUTH_MODE == "lite":
        return lite_main(args)
    return playwright_main(args, parser)


if __name__ == "__main__":
    raise SystemExit(main())
