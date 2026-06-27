"""Google Chrome AppleScript backend."""
from __future__ import annotations

import base64
import json
import re
import subprocess
import sys
import time as _time

from ..config import MESSAGES_URL, PROFILE_DIRECTORY
from ..utils import js_string

def run_osascript(script: str, timeout: int = 30) -> str:
    return subprocess.check_output(["osascript", "-e", script], text=True, timeout=timeout).strip()


def chrome_running() -> bool:
    try:
        out = run_osascript('application "Google Chrome" is running', timeout=5)
        return out.lower() == "true"
    except Exception:
        return False


def open_chrome_messages() -> None:
    subprocess.run(["open", "-a", "Google Chrome", MESSAGES_URL], check=False)


def chrome_js(js: str, timeout: int = 30) -> str:
    encoded = base64.b64encode(js.encode("utf-8")).decode("ascii")
    safe_js = (
        "(() => {"
        f"const b = atob('{encoded}');"
        "const bytes = Uint8Array.from(b, c => c.charCodeAt(0));"
        "return eval(new TextDecoder('utf-8').decode(bytes));"
        "})()"
    )
    script = 'tell application "Google Chrome" to tell active tab of front window to execute javascript ' + json.dumps(safe_js)
    return run_osascript(script, timeout=timeout)


def ensure_chrome_messages() -> None:
    if not chrome_running():
        open_chrome_messages()
    else:
        try:
            has_window = run_osascript('tell application "Google Chrome" to count windows', timeout=5)
            if int(has_window or "0") == 0:
                open_chrome_messages()
            else:
                url = run_osascript('tell application "Google Chrome" to get URL of active tab of front window', timeout=5)
                if "messages.google.com" not in url:
                    open_chrome_messages()
        except Exception:
            open_chrome_messages()

    deadline = _time.time() + 30
    last = ""
    while _time.time() < deadline:
        try:
            last = chrome_js("location.href + '\\n' + document.title", timeout=5)
            if "messages.google.com" in last:
                return
        except Exception as exc:
            last = str(exc)
        _time.sleep(0.5)
    raise RuntimeError(f"Chrome did not open Google Messages: {last}")


def chrome_status_data() -> dict:
    ensure_chrome_messages()
    raw = chrome_js("""JSON.stringify({
      url: location.href,
      title: document.title,
      body: document.body.innerText.slice(0, 500),
      conversation_count: document.querySelectorAll('a[role="option"]').length,
      account: (document.querySelector('a[aria-label^="Google Account"]') || {}).getAttribute?.('aria-label') || ''
    })""", timeout=10)
    data = json.loads(raw)
    on_welcome = "/welcome" in data.get("url", "") or "Welcome to Google Messages" in data.get("body", "")
    paired = data.get("conversation_count", 0) > 0 and not on_welcome
    return {
        "ok": True,
        "paired": paired,
        "detail": "Google Messages automation is ready." if paired else "Chrome opened, but Google Messages is not signed in or paired.",
        "url": data.get("url", ""),
        "title": data.get("title", ""),
        "auth_mode": "chrome",
        "profile_directory": PROFILE_DIRECTORY,
        "conversation_count": data.get("conversation_count", 0),
        "account": data.get("account", ""),
    }


def chrome_require_paired() -> dict:
    status = chrome_status_data()
    if not status.get("paired"):
        raise RuntimeError(status.get("detail") or "Google Messages is not ready")
    return status


def chrome_list_chats(limit: int) -> list[dict]:
    chrome_require_paired()
    raw = chrome_js(f"""JSON.stringify(Array.from(document.querySelectorAll('a[role="option"]'))
      .filter(el => {{ const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; }})
      .slice(0, {int(limit)})
      .map((el, i) => {{
        const parts = (el.innerText || '').trim().split('\\n');
        return {{index: String(i + 1), title: parts[0] || '', preview: parts.slice(1).join(' '), url: el.href || ''}};
      }}))""", timeout=10)
    return json.loads(raw)


def chrome_click_chat(recipient: str) -> dict:
    chrome_require_paired()
    js = rf"""(() => {{
      const norm = s => (s || '').toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim();
      const target = norm({js_string(recipient)});
      const currentBox = document.querySelector('textarea[aria-label^="Type an RCS message to"]');
      const currentLabel = currentBox ? currentBox.getAttribute('aria-label') || '' : '';
      const currentTitle = currentLabel.replace(/^Type an RCS message to\s*/, '').trim();
      if (currentTitle && target && (norm(currentTitle) === target || norm(currentTitle).includes(target) || target.includes(norm(currentTitle)))) {{
        return JSON.stringify({{ok:true, title:currentTitle, alreadyOpen:true}});
      }}
      const links = Array.from(document.querySelectorAll('a[role="option"]'));
      let exact = null, fuzzy = null;
      for (const link of links) {{
        const title = (link.innerText || '').trim().split('\\n')[0] || '';
        const n = norm(title);
        if (title === {js_string(recipient)} || n === target) {{ exact = link; break; }}
        if (!fuzzy && target && (n.includes(target) || target.includes(n))) fuzzy = link;
      }}
      const found = exact || fuzzy;
      if (!found) return JSON.stringify({{ok:false, error:'Conversation not found: {recipient}', seen:links.slice(0,20).map(a=>(a.innerText||'').trim().split('\\n')[0])}});
      const title = (found.innerText || '').trim().split('\\n')[0] || '';
      found.click();
      return JSON.stringify({{ok:true, title, alreadyOpen:false}});
    }})()"""
    result = json.loads(chrome_js(js, timeout=10))
    if not result.get("ok") or result.get("alreadyOpen"):
        return result

    expected = result.get("title", recipient)
    deadline = _time.time() + 5
    while _time.time() < deadline:
        ready_raw = chrome_js(f"""(() => {{
          const norm = s => (s || '').toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim();
          const box = document.querySelector('textarea[aria-label^="Type an RCS message to"]');
          const label = box ? box.getAttribute('aria-label') || '' : '';
          const wanted = norm({js_string(expected)});
          return JSON.stringify({{ready: !!box && (!wanted || norm(label).includes(wanted) || wanted.includes(norm(label.replace(/^Type an RCS message to\\s*/, '')))), label}});
        }})()""", timeout=5)
        ready = json.loads(ready_raw)
        if ready.get("ready"):
            return result
        _time.sleep(0.2)
    return result


def chrome_history(recipient: str, limit: int = 20) -> dict:
    clicked = chrome_click_chat(recipient)
    if not clicked.get("ok"):
        return clicked
    items = []
    for _ in range(25):
        raw = chrome_js(f"""JSON.stringify(Array.from(document.querySelectorAll('mws-text-message-part, mws-image-message-part'))
          .filter(el => {{ const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; }})
          .slice(-{int(limit)})
          .map(el => ({{text:(el.innerText || '').trim(), aria:(el.getAttribute('aria-label') || '').trim(), tag:el.tagName}})))""", timeout=10)
        items = json.loads(raw)
        if items:
            break
        _time.sleep(0.2)
    messages = []
    for item in items:
        aria = item.get("aria", "")
        text = item.get("text", "")
        direction = "received" if "said:" in aria and "You said:" not in aria and "You sent:" not in aria else "sent"
        body = text
        if "said:" in aria:
            body = re.sub(r"^.*?said:\s*", "", aria)
            body = re.sub(r"\. Received on.*$|\. Sent on.*$|\. Read\..*$|\. Delivered\..*$|\. Pending.*$", "", body)
        if "You said:" in aria or "You sent:" in aria:
            body = re.sub(r"^.*?said:\s*|^.*?sent:\s*", "", aria)
            body = re.sub(r"\. Sent on.*$|\. Read\..*$|\. Delivered\..*$|\. Pending.*$", "", body)
        ts_match = re.search(r"(?:Sent|Received|Read|Delivered)\s+on\s+(.*?)(?:\.|$)", aria)
        messages.append({"direction": direction, "body": body, "timestamp": ts_match.group(1).strip() if ts_match else "", "raw_aria": aria[:160]})
    return {"ok": True, "conversation": clicked.get("title"), "messages": messages, "count": len(messages)}


def chrome_send(recipient: str, message: str, draft: bool = False) -> dict:
    clicked = chrome_click_chat(recipient)
    if not clicked.get("ok"):
        return clicked
    js = f"""(() => {{
      const box = document.querySelector('textarea');
      if (!box) return JSON.stringify({{ok:false,error:'Message field not found'}});
      box.focus();
      const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set;
      setter.call(box, {js_string(message)});
      box.dispatchEvent(new InputEvent('input', {{bubbles:true, inputType:'insertText', data:{js_string(message)}}}));
      box.dispatchEvent(new Event('change', {{bubbles:true}}));
      return JSON.stringify({{ok:true, drafted:box.value}});
    }})()"""
    drafted = json.loads(chrome_js(js, timeout=10))
    if not drafted.get("ok"):
        return drafted
    if draft:
        return {"ok": True, "sent": False, "detail": "Message drafted.", "conversation": clicked.get("title"), "preview": message[:80]}

    def normalize_message_text(value: str) -> str:
        # Google Messages aria text can normalize NBSPs, narrow spaces, and emoji
        # variation selectors differently than the textarea value. Compare the
        # human-visible text, not byte-for-byte DOM trivia.
        return re.sub(r"\s+", " ", (value or "").replace("\u200b", "").replace("\ufe0f", "").strip())

    wanted = normalize_message_text(message)

    def verify_sent() -> bool:
        deadline = _time.time() + 20
        while _time.time() < deadline:
            verify = chrome_history(recipient, limit=12)
            if verify.get("ok"):
                for msg in reversed(verify.get("messages", [])):
                    if msg.get("direction") != "sent":
                        continue
                    body = normalize_message_text(msg.get("body", ""))
                    if body == wanted or wanted in body or body in wanted:
                        return True
            _time.sleep(1)
        return False

    # Google Messages sends the current draft with Cmd+Return. Plain Return now
    # inserts/does nothing in some composer states, which caused false failures.
    run_osascript('tell application "Google Chrome" to set visible of front window to true\ntell application "Google Chrome" to activate\ndelay 0.2\ntell application "System Events" to key code 36 using command down', timeout=10)
    if verify_sent():
        return {"ok": True, "sent": True, "detail": "Message sent.", "conversation": clicked.get("title"), "preview": message[:80]}

    # Google Messages sometimes ignores the Return key even after the textarea is focused.
    # Clicking the explicit send button used to be a false positive, so keep it as a
    # verified fallback only: click, then require the exact message to appear in history.
    click_raw = chrome_js("""(() => {
      const buttons = Array.from(document.querySelectorAll('button[data-e2e-send-text-button], button[aria-label="Send RCS message"], button[aria-label="Send SMS"]'));
      const button = buttons.find(b => {
        const r = b.getBoundingClientRect();
        return r.width > 0 && r.height > 0 && !b.disabled && b.getAttribute('aria-disabled') !== 'true';
      });
      if (!button) return JSON.stringify({ok:false,error:'Send button not found or disabled'});
      button.click();
      return JSON.stringify({ok:true, aria:button.getAttribute('aria-label') || ''});
    })()""", timeout=10)
    clicked_button = json.loads(click_raw)
    if clicked_button.get("ok") and verify_sent():
        return {"ok": True, "sent": True, "detail": "Message sent.", "conversation": clicked.get("title"), "preview": message[:80], "fallback": "send-button"}

    return {"ok": False, "sent": False, "error": clicked_button.get("error") or "Message was composed but not verified as sent", "conversation": clicked.get("title")}


def chrome_main(args) -> int:
    try:
        if args.command == "pair":
            open_chrome_messages()
            print("Chrome opened to Google Messages. Sign in or pair there, then rerun `gmsg status`.")
            return 0
        if args.command == "status":
            data = chrome_status_data()
            if args.json:
                print(json.dumps(data, ensure_ascii=False))
            elif data.get("paired"):
                print("Google Messages automation is ready.")
            else:
                print(data.get("detail", "Not ready."))
            return 0 if data.get("ok") else 1
        if args.command == "chats":
            chats = chrome_list_chats(args.limit)
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
        if args.command == "history":
            result = chrome_history(args.to, args.limit)
            if args.json:
                print(json.dumps(result, ensure_ascii=False))
            elif result.get("ok"):
                print(f"Conversation: {result.get('conversation') or args.to}\n")
                for msg in reversed(result.get("messages", [])):
                    prefix = "→" if msg["direction"] == "received" else "←"
                    ts = f" ({msg['timestamp']})" if msg["timestamp"] else ""
                    print(f"  {prefix} {msg['body'][:200]}{ts}")
            else:
                print(f"gmsg: {result.get('error', 'unknown error')}", file=sys.stderr)
                return 1
            return 0
        if args.command == "send":
            result = chrome_send(args.to, args.text, draft=args.draft)
            if args.json:
                print(json.dumps(result, ensure_ascii=False))
            elif result.get("ok"):
                verb = "prepared" if args.draft else "sent"
                print(f"Message {verb}: {result.get('preview', '')}".rstrip())
            else:
                print(f"gmsg: {result.get('error', 'unknown error')}", file=sys.stderr)
                return 1
            return 0 if result.get("ok") else 1
        return 2
    except Exception as exc:
        if getattr(args, "json", False):
            print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        else:
            print(f"gmsg: {exc}", file=sys.stderr)
        return 1
