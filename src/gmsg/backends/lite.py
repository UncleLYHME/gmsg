"""macOS Google Messages Lite accessibility backend."""
from __future__ import annotations

import json
import re
import subprocess
import sys
import time as _time
from pathlib import Path

from ..config import LITE_APP_NAME, LITE_PROCESS_NAME
from ..routes import resolve_route
from ..utils import norm

def lite_osascript(script: str, timeout: int = 30) -> str:
    return subprocess.check_output(["osascript"], input=script, text=True, timeout=timeout).strip()


def lite_running() -> bool:
    try:
        out = lite_osascript(f'tell application "System Events" to exists process "{LITE_PROCESS_NAME}"', timeout=5)
        return out.lower() == "true"
    except Exception:
        return False


def open_lite_messages() -> None:
    subprocess.run(["open", "-a", LITE_APP_NAME], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def lite_window_count() -> int:
    try:
        out = lite_osascript(
            f'tell application "System Events" to tell process "{LITE_PROCESS_NAME}" to count windows',
            timeout=5,
        )
        return int(out or "0")
    except Exception:
        return 0


def reopen_lite_window() -> None:
    script = f'''
tell application "{LITE_APP_NAME}" to activate
delay 0.2
tell application "System Events"
  keystroke "n" using {{command down, shift down}}
end tell
'''
    try:
        lite_osascript(script, timeout=10)
    except Exception:
        open_lite_messages()


def ensure_lite_messages() -> None:
    if not lite_running():
        open_lite_messages()
    deadline = _time.time() + 20
    reopened = False
    while _time.time() < deadline:
        if lite_running():
            if lite_window_count() == 0 and not reopened:
                reopen_lite_window()
                reopened = True
            try:
                data = lite_status_data(open_if_needed=False)
                if data.get("ok"):
                    return
            except Exception:
                pass
        _time.sleep(0.5)
    raise RuntimeError("Google Messages Lite did not become available")


def lite_collect() -> str:
    script = f'''
on collect(e)
  set out to ""
  tell application "System Events"
    try
      set r to role of e as text
    on error
      set r to "?"
    end try
    try
      set n to name of e as text
    on error
      set n to ""
    end try
    try
      set d to description of e as text
    on error
      set d to ""
    end try
    try
      set v to value of e as text
    on error
      set v to ""
    end try
    if n is "missing value" then set n to ""
    if v is "missing value" then set v to ""
    set out to out & r & " | n=" & n & " | d=" & d & " | v=" & v & linefeed
    try
      repeat with child in UI elements of e
        set out to out & my collect(child)
      end repeat
    end try
  end tell
  return out
end collect

tell application "System Events"
  tell process "{LITE_PROCESS_NAME}"
    return my collect(window 1)
  end tell
end tell
'''
    return lite_osascript(script, timeout=60)


def lite_current_conversation(raw: str | None = None) -> str:
    raw = raw if raw is not None else lite_collect()
    for line in raw.splitlines():
        m = re.search(r"AXTextArea \| n=Type an (?:RCS|SMS) message to (.*?) \|", line)
        if m:
            return m.group(1).strip()
    for line in raw.splitlines():
        if line.startswith("AXHeading | n="):
            name = line.split(" | n=", 1)[1].split(" |", 1)[0].strip()
            if name and name not in {"Google Messages", "Conversations list", "New conversation", "Top contacts"} and not re.search(r"\d|AM|PM|Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday", name):
                return name
    return ""


def lite_recover_window() -> None:
    """Recover the Lite wrapper when Pake/WebView is running but the UI is blank.

    The cron failure mode is usually a live process with either no window or a
    window that has not loaded Google Messages' conversation/composer tree yet.
    Reopen the wrapper window, activate it, and refresh the WebView before the
    send path gives up.
    """
    if not lite_running():
        open_lite_messages()
        _time.sleep(1)
    if lite_running() and lite_window_count() == 0:
        reopen_lite_window()
        _time.sleep(1)
    script = f'''
tell application "{LITE_APP_NAME}" to activate
delay 0.2
tell application "System Events"
  tell process "{LITE_PROCESS_NAME}"
    if (count windows) is 0 then
      keystroke "n" using {{command down, shift down}}
      delay 0.5
    end if
    try
      keystroke "r" using {{command down}}
    end try
  end tell
end tell
'''
    try:
        lite_osascript(script, timeout=10)
    except Exception:
        open_lite_messages()


def lite_status_data(open_if_needed: bool = True) -> dict:
    if open_if_needed:
        if not lite_running():
            open_lite_messages()
            _time.sleep(1)
        if lite_running() and lite_window_count() == 0:
            reopen_lite_window()
            _time.sleep(1)
    if not lite_running():
        return {"ok": False, "paired": False, "detail": "Google Messages Lite is not running.", "auth_mode": "lite"}
    if lite_window_count() == 0:
        return {"ok": False, "paired": False, "detail": "Google Messages Lite is running with no open window.", "auth_mode": "lite"}
    raw = lite_collect()
    current = lite_current_conversation(raw)
    has_web = "Google Messages" in raw
    has_conversation_list = "Conversations list" in raw or "Conversations. Use the" in raw
    has_start_chat = "Start chat" in raw
    has_composer = "AXTextArea | n=Type an " in raw
    paired = has_web and (has_composer or has_conversation_list or has_start_chat)
    return {
        "ok": True,
        "paired": paired,
        "detail": "Google Messages Lite automation is ready." if paired else "Google Messages Lite is open, but no paired conversation/composer was found.",
        "auth_mode": "lite",
        "app": LITE_APP_NAME,
        "process": LITE_PROCESS_NAME,
        "title": "Google Messages for web: Conversations" if has_web else "",
        "conversation": current,
        "conversation_count": 1 if current else (1 if has_conversation_list else 0),
    }


def lite_require_paired() -> dict:
    status = lite_status_data()
    if status.get("paired"):
        return status
    lite_recover_window()
    deadline = _time.time() + 25
    while _time.time() < deadline:
        status = lite_status_data(open_if_needed=False)
        if status.get("paired"):
            return status
        _time.sleep(1)
    raise RuntimeError(status.get("detail") or "Google Messages Lite is not ready")


def lite_list_chats(limit: int) -> list[dict]:
    status = lite_require_paired()
    current = status.get("conversation") or ""
    return [{"index": "1", "title": current, "preview": "currently open in Google Messages Lite", "url": ""}] if current else []


def lite_parse_history(raw: str, limit: int = 20) -> list[dict]:
    messages = []
    for line in raw.splitlines():
        if not line.startswith("AXGroup | n="):
            continue
        aria = line.split(" | n=", 1)[1].split(" | d=", 1)[0].strip()
        if not aria or not (" said:" in aria or aria.startswith("You said:") or aria.startswith("You sent:")):
            continue
        direction = "received" if " said:" in aria and not aria.startswith("You said:") and not aria.startswith("You sent:") else "sent"
        body = aria
        if " said:" in aria:
            body = re.sub(r"^.*?said:\s*", "", body)
        elif " sent:" in aria:
            body = re.sub(r"^.*?sent:\s*", "", body)
        body = re.sub(r"\. Received on.*$|\. Sent on.*$|\. Read\..*$|\. Delivered\..*$|\. Pending.*$", "", body).strip()
        ts_match = re.search(r"(?:Sent|Received|Read|Delivered)\s+on\s+(.*?)(?:\.|$)", aria)
        messages.append({"direction": direction, "body": body, "timestamp": ts_match.group(1).strip() if ts_match else "", "raw_aria": aria[:160]})
    return messages[-int(limit):]


def lite_current_matches(recipient: str, current: str) -> bool:
    target = norm(recipient)
    here = norm(current)
    return bool(here and target and (here == target or here in target or target in here))


def lite_search_and_open(recipient: str) -> dict:
    target = resolve_route(recipient)
    query_path = Path("/tmp/gmsg-lite-query.txt")
    query_path.write_text(target, encoding="utf-8")
    script = f'''
on pressStart(e)
  tell application "System Events"
    try
      if role of e is "AXLink" and name of e is "Start chat" then
        perform action "AXPress" of e
        return true
      end if
    end try
    try
      repeat with child in UI elements of e
        if my pressStart(child) then return true
      end repeat
    end try
  end tell
  return false
end pressStart

on findTextField(e)
  tell application "System Events"
    try
      if role of e is "AXTextField" then return e
    end try
    try
      repeat with child in UI elements of e
        set found to my findTextField(child)
        if found is not missing value then return found
      end repeat
    end try
  end tell
  return missing value
end findTextField

on pressBest(e, wanted)
  tell application "System Events"
    try
      set r to role of e as text
      set n to name of e as text
      if n is "missing value" then set n to ""
      if n contains wanted and (r is "AXHeading" or r is "AXCheckBox" or r is "AXGroup") then
        try
          perform action "AXPress" of e
        on error
          click e
        end try
        return r & "|" & n
      end if
    end try
    try
      repeat with child in UI elements of e
        set hit to my pressBest(child, wanted)
        if hit is not "" then return hit
      end repeat
    end try
  end tell
  return ""
end pressBest

set wanted to read POSIX file "{query_path}"
tell application "{LITE_APP_NAME}" to activate
delay 0.2
tell application "System Events"
  tell process "{LITE_PROCESS_NAME}"
    my pressStart(window 1)
    delay 0.5
    set tf to my findTextField(window 1)
    if tf is missing value then error "Search field not found"
    set value of tf to wanted
    delay 1.0
    set hit to my pressBest(window 1, wanted)
    if hit is "" then error "Conversation not found in Lite search: " & wanted
    return hit
  end tell
end tell
'''
    hit = lite_osascript(script, timeout=35)
    deadline = _time.time() + 10
    while _time.time() < deadline:
        raw = lite_collect()
        current = lite_current_conversation(raw)
        if lite_current_matches(target, current):
            return {"ok": True, "title": current, "resolved": target, "selected": hit, "alreadyOpen": False}
        _time.sleep(0.5)
    current = lite_current_conversation()
    if current:
        return {"ok": True, "title": current, "resolved": target, "selected": hit, "alreadyOpen": False, "warning": "Selected search result but exact title did not match route"}
    return {"ok": False, "error": f"Selected {target}, but no conversation opened"}


def lite_click_current_chat_or_error(recipient: str) -> dict:
    status = lite_require_paired()
    target = resolve_route(recipient)
    current = status.get("conversation") or ""
    if lite_current_matches(target, current):
        return {"ok": True, "title": current, "resolved": target, "alreadyOpen": True}
    return lite_search_and_open(target)


def lite_history(recipient: str, limit: int = 20) -> dict:
    clicked = lite_click_current_chat_or_error(recipient)
    if not clicked.get("ok"):
        return clicked
    raw = lite_collect()
    messages = lite_parse_history(raw, limit=limit)
    return {"ok": True, "conversation": clicked.get("title"), "messages": messages, "count": len(messages)}


def lite_set_textarea(message: str) -> str:
    msg_path = Path("/tmp/gmsg-lite-message.txt")
    msg_path.write_text(message, encoding="utf-8")
    msg_source = 'set msg to ""' if message == "" else f'set msg to read POSIX file "{msg_path}" as «class utf8»'
    script = f'''
on findTextArea(e)
  tell application "System Events"
    try
      if role of e is "AXTextArea" then return e
    end try
    try
      repeat with child in UI elements of e
        set found to my findTextArea(child)
        if found is not missing value then return found
      end repeat
    end try
  end tell
  return missing value
end findTextArea

{msg_source}
tell application "{LITE_APP_NAME}" to activate
delay 0.2
tell application "System Events"
  tell process "{LITE_PROCESS_NAME}"
    set ta to my findTextArea(window 1)
    if ta is missing value then error "Message field not found"
    set value of ta to msg
    return (value of ta as text)
  end tell
end tell
'''
    return lite_osascript(script, timeout=20)


def lite_press_send() -> str:
    script = f'''
on findTextArea(e)
  tell application "System Events"
    try
      if role of e is "AXTextArea" then return e
    end try
    try
      repeat with child in UI elements of e
        set found to my findTextArea(child)
        if found is not missing value then return found
      end repeat
    end try
  end tell
  return missing value
end findTextArea

tell application "{LITE_APP_NAME}" to activate
delay 0.2
tell application "System Events"
  tell process "{LITE_PROCESS_NAME}"
    set ta to my findTextArea(window 1)
    if ta is missing value then error "Message field not found"
    set focused of ta to true
    delay 0.1
    key code 36 using {{command down}}
    return "sent-keyed"
  end tell
end tell
'''
    return lite_osascript(script, timeout=20)


def lite_send(recipient: str, message: str, draft: bool = False) -> dict:
    clicked = lite_click_current_chat_or_error(recipient)
    if not clicked.get("ok"):
        return clicked
    drafted_value = lite_set_textarea(message)
    if draft:
        return {"ok": True, "sent": False, "detail": "Message drafted in Google Messages Lite.", "conversation": clicked.get("title"), "preview": message[:80], "drafted": drafted_value[:80]}
    lite_press_send()
    wanted = re.sub(r"\s+", " ", message.strip())
    deadline = _time.time() + 20
    while _time.time() < deadline:
        hist = lite_history(recipient, limit=12)
        if hist.get("ok"):
            for msg in reversed(hist.get("messages", [])):
                if msg.get("direction") != "sent":
                    continue
                body = re.sub(r"\s+", " ", (msg.get("body") or "").strip())
                if body == wanted or wanted in body or body in wanted:
                    return {"ok": True, "sent": True, "detail": "Message sent via Google Messages Lite.", "conversation": clicked.get("title"), "preview": message[:80]}
        _time.sleep(1)
    return {"ok": False, "sent": False, "error": "Message was composed/sent-clicked but not verified in Lite history", "conversation": clicked.get("title")}


def lite_main(args) -> int:
    try:
        if args.command == "pair":
            open_lite_messages()
            print("Google Messages Lite opened. Pair/sign in there, then rerun `gmsg status`.")
            return 0
        if args.command == "status":
            data = lite_status_data()
            if args.json:
                print(json.dumps(data, ensure_ascii=False))
            elif data.get("paired"):
                print("Google Messages Lite automation is ready.")
            else:
                print(data.get("detail", "Not ready."))
            return 0 if data.get("ok") else 1
        if args.command == "chats":
            chats = lite_list_chats(args.limit)
            if args.json:
                print(json.dumps({"ok": True, "chats": chats, "auth_mode": "lite", "limited": True}, ensure_ascii=False))
            else:
                for c in chats:
                    extra = f" — {c.get('preview', '')}" if c.get("preview") else ""
                    print(f"{c['index']}. {c['title']}{extra}")
            return 0
        if args.command == "history":
            result = lite_history(args.to, args.limit)
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
            result = lite_send(args.to, args.text, draft=args.draft)
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
