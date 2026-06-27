"""Playwright/CDP backend."""
from __future__ import annotations

import json
import re
import subprocess
import sys
import time as _time
import urllib.request

from ..config import (
    AUTH_MODE,
    AUTH_STATE,
    AUTOMATION_USER_DATA_DIR,
    CDP_PORT,
    MESSAGES_URL,
    PROFILE_DIRECTORY,
    REAL_CHROME_USER_DATA_DIR,
)
from ..utils import norm

try:
    from playwright.sync_api import TimeoutError as PWTimeout
    from playwright.sync_api import sync_playwright
except Exception:  # pragma: no cover - exercised in environments without Playwright
    sync_playwright = None
    PWTimeout = TimeoutError

def get_page(headless: bool = True):
    if sync_playwright is None:
        raise RuntimeError("Playwright is required for browser automation. Install with `pip install gmsg[playwright]`.")
    """Launch browser and return a page on the Messages URL with persisted auth.

    Use a persistent Chrome profile instead of Playwright storage_state. Google
    Messages auth relies on more than cookies/localStorage, and storage_state can
    report a misleading paired-looking URL after auth expires. A persistent
    profile gives us QR-pairing and Google sign-in durability.
    """
    p = sync_playwright().start()
    AUTH_STATE.parent.mkdir(parents=True, exist_ok=True)
    if AUTH_MODE == "cdp":
        return get_cdp_page(p)

    AUTOMATION_USER_DATA_DIR.mkdir(parents=True, exist_ok=True)

    chrome_args = ["--no-sandbox", "--disable-dev-shm-usage"]
    if PROFILE_DIRECTORY:
        chrome_args.append(f"--profile-directory={PROFILE_DIRECTORY}")

    context = p.chromium.launch_persistent_context(
        str(AUTOMATION_USER_DATA_DIR),
        headless=headless,
        channel="chrome",
        viewport={"width": 1280, "height": 800},
        args=chrome_args,
    )
    page = context.pages[0] if context.pages else context.new_page()
    page.goto(MESSAGES_URL, wait_until="domcontentloaded", timeout=30000)

    return p, None, context, page


def cdp_available() -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{CDP_PORT}/json/version", timeout=1) as r:
            return r.status == 200
    except Exception:
        return False


def open_real_chrome_profile() -> None:
    args = [
        "open", "-na", "Google Chrome", "--args",
        f"--remote-debugging-port={CDP_PORT}",
        f"--profile-directory={PROFILE_DIRECTORY}",
        MESSAGES_URL,
    ]
    subprocess.run(args, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def get_cdp_page(p):
    if not cdp_available():
        open_real_chrome_profile()
        deadline = _time.time() + 20
        while _time.time() < deadline and not cdp_available():
            _time.sleep(0.5)
    if not cdp_available():
        raise RuntimeError(
            f"Chrome CDP port {CDP_PORT} is not available. Quit Chrome and run again, "
            "or launch Chrome with --remote-debugging-port first."
        )
    browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{CDP_PORT}")
    context = browser.contexts[0] if browser.contexts else browser.new_context(viewport={"width": 1280, "height": 800})
    page = None
    for candidate in context.pages:
        if "messages.google.com" in candidate.url:
            page = candidate
            break
    if page is None:
        page = context.new_page()
    page.goto(MESSAGES_URL, wait_until="domcontentloaded", timeout=30000)
    return p, browser, context, page


def save_auth(context) -> None:
    # Keep legacy storage_state as a diagnostic/export artifact, but the durable
    # auth source is PROFILE_DIR.
    try:
        context.storage_state(path=str(AUTH_STATE))
    except Exception:
        pass


def close_browser(p, browser, context) -> None:
    try:
        if AUTH_MODE != "cdp":
            context.close()
    finally:
        if browser is not None and AUTH_MODE != "cdp":
            browser.close()
        p.stop()


def status_data(page) -> dict:
    try:
        url = page.url
        has_conversations = False
        try:
            has_conversations = page.locator("a[role='option']").count() > 0
        except Exception:
            has_conversations = False
        on_welcome = "/welcome" in url or "Welcome to Google Messages" in (page.locator("body").inner_text(timeout=2000) or "")
        paired = ("/conversations" in url) and not on_welcome and has_conversations
        return {
            "ok": True,
            "paired": paired,
            "detail": "Google Messages automation is ready." if paired else "Not paired or Google session expired. Run 'gmsg pair'.",
            "url": url,
            "title": page.title(),
            "auth_mode": AUTH_MODE,
            "user_data_dir": str(AUTOMATION_USER_DATA_DIR if AUTH_MODE != "cdp" else REAL_CHROME_USER_DATA_DIR),
            "profile_directory": PROFILE_DIRECTORY,
            "cdp_port": CDP_PORT if AUTH_MODE == "cdp" else None,
            "conversation_count": page.locator("a[role='option']").count() if not on_welcome else 0,
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def _wait_for_convs(page, timeout=25000):
    try:
        page.wait_for_selector("a[role='option']", timeout=timeout)
    except PWTimeout:
        return False
    page.wait_for_timeout(1000)
    return True


def _find_chat(page, recipient: str):
    """Find a conversation by name, click it, return True if found."""
    if not _wait_for_convs(page):
        return False

    target = norm(recipient)
    links = page.locator("a[role='option']")
    count = links.count()
    for i in range(count):
        link = links.nth(i)
        text = norm(link.inner_text())
        if target in text or text in target:
            link.click()
            return True
    return False


def list_chats(page, limit: int) -> list[dict]:
    if not _wait_for_convs(page):
        return []

    raw = page.evaluate(f"""
        JSON.stringify(Array.from(document.querySelectorAll("a[role='option']"))
          .filter(el => {{ const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; }})
          .slice(0, {limit})
          .map((el, i) => ({{
            index: String(i + 1),
            title: (el.innerText || '').trim().split('\\n')[0] || '',
            preview: (el.innerText || '').trim().split('\\n').slice(1).join(' '),
            url: el.href || ''
          }})))
    """)
    return json.loads(raw)


def get_history(page, recipient: str, limit: int = 20) -> dict:
    """Fetch recent messages from a conversation."""
    if not _find_chat(page, recipient):
        return {"ok": False, "error": f"Conversation not found: {recipient}"}

    page.wait_for_timeout(2000)

    raw = page.evaluate(f"""
        JSON.stringify(Array.from(document.querySelectorAll("mws-text-message-part, mws-image-message-part, mws-reply-message-part"))
          .filter(el => {{ const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; }})
          .slice(-{limit})
          .map(el => ({{
            text: (el.innerText || '').trim(),
            aria: (el.getAttribute('aria-label') || '').trim(),
            tag: el.tagName,
          }})))
    """)
    items = json.loads(raw)
    messages = []
    for item in items:
        aria = item.get("aria", "")
        text = item.get("text", "")
        direction = "received" if "said:" in aria and "You said:" not in aria and "You sent:" not in aria else "sent"
        # Extract message text from aria or innerText
        body = text
        if "said:" in aria:
            body = re.sub(r"^.*?said:\s*", "", aria).split(".")[0]
            body = re.sub(r"\. Received on.*$|\. Sent on.*$|\. Read\..*$|\. Pending.*$", "", body)
        if "You said:" in aria or "You sent:" in aria:
            body = re.sub(r"^.*?said:\s*|^.*?sent:\s*", "", aria).split(".")[0]
            body = re.sub(r"\. Sent on.*$|\. Read\..*$|\. Delivered.*$", "", body)
        timestamp = ""
        ts_match = re.search(r"(?:Sent|Received|Read|Delivered)\s+on\s+(.*?)(?:\.|$)", aria)
        if ts_match:
            timestamp = ts_match.group(1).strip()
        messages.append({
            "direction": direction,
            "body": body,
            "timestamp": timestamp,
            "raw_aria": aria[:120],
        })

    return {"ok": True, "messages": messages, "count": len(messages)}


def send_message(page, recipient: str, message: str, draft: bool = False) -> dict:
    """Click recipient conversation, compose message, optionally send."""
    if not _find_chat(page, recipient):
        return {"ok": False, "error": f"Conversation not found: {recipient}"}

    page.wait_for_timeout(2500)

    try:
        msg_box = page.wait_for_selector("textarea, [contenteditable='true']", timeout=10000)
    except PWTimeout:
        return {"ok": False, "error": "Message field not found"}

    msg_box.focus()
    msg_box.fill(message)
    page.wait_for_timeout(1500)

    if not draft:
        # Send via Enter key — more reliable than button selector
        page.keyboard.press("Enter")
        page.wait_for_timeout(2000)

        # Verify: check if our message appears in the conversation
        last_sent = page.evaluate("""() => {
            const items = document.querySelectorAll('[role="row"] mws-conversation-message-item');
            for (let i = items.length - 1; i >= 0; i--) {
                const aria = items[i].getAttribute('aria-label') || '';
                if (aria.includes('You said:')) {
                    const sent = items[i].querySelector('[data-test-id="message-text"], mws-text-message-part');
                    return sent ? sent.innerText.trim() : '';
                }
            }
            return '';
        }""")
        if last_sent:
            return {"ok": True, "sent": True, "detail": "Message sent.", "preview": last_sent[:80]}

        # Fallback: try the send button
        try:
            send_btn = page.locator('button[aria-label*="Send"], mw-message-send-button button').first
            send_btn.click(timeout=3000)
            page.wait_for_timeout(1500)
            return {"ok": True, "sent": True, "detail": "Message sent (via button)."}
        except PWTimeout:
            return {"ok": True, "sent": False, "detail": "Composed but send button not found"}

    return {"ok": True, "sent": False, "detail": "Message drafted."}


def cmd_status(page, args) -> int:
    data = status_data(page)
    if args.json:
        print(json.dumps(data, ensure_ascii=False))
    elif data.get("paired"):
        print("Google Messages automation is ready.")
    else:
        print("Not paired:", data.get("detail", "unknown"))
    return 0 if data.get("ok") else 1


def cmd_chats(page, args) -> int:
    chats = list_chats(page, args.limit)
    if args.json:
        print(json.dumps({"ok": True, "chats": chats}, ensure_ascii=False))
    else:
        for c in chats:
            preview = c.get("preview", "")
            if len(preview) > 120:
                preview = preview[:117] + "..."
            extra = f" — {preview}" if preview else ""
            print(f"{c['index']}. {c['title']}{extra}")
    return 0


def cmd_history(page, args) -> int:
    result = get_history(page, args.to, limit=args.limit)
    if args.json:
        print(json.dumps(result, ensure_ascii=False))
    elif result.get("ok"):
        print(f"Conversation: {args.to}\n")
        for msg in reversed(result.get("messages", [])):
            prefix = "→" if msg["direction"] == "received" else "←"
            ts = f" ({msg['timestamp']})" if msg["timestamp"] else ""
            body = msg["body"][:200]
            print(f"  {prefix} {body}{ts}")
    else:
        print(f"gmsg: {result.get('error', 'unknown error')}", file=sys.stderr)
        return 1
    return 0


def cmd_send(page, args) -> int:
    result = send_message(page, args.to, args.text, draft=args.draft)
    if result.get("ok"):
        verb = "prepared" if args.draft else "sent"
        preview = result.get("preview", "")
        if preview:
            print(f"Message {verb}: {preview}")
        else:
            print(f"Message {verb} via headless.")
        if args.json:
            print(json.dumps(result, ensure_ascii=False))
    else:
        print(f"gmsg: {result.get('error', 'unknown error')}", file=sys.stderr)
        return 1
    return 0
