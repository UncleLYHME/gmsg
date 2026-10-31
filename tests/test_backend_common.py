import types

from gmsg.backends import common


def args(**kw):
    base = {"json": False, "to": "Alex", "limit": 5, "draft": True, "text": "hi"}
    base.update(kw)
    return types.SimpleNamespace(**base)


def test_aria_direction_and_timestamp():
    assert common.aria_direction("Alex said: hi. Received on Monday 9:00 AM.") == "received"
    assert common.aria_direction("You said: hi. Sent on Monday.") == "sent"
    assert common.aria_direction("") == "sent"
    assert common.aria_timestamp("You said: hi. Sent on Monday 9:05 AM. Delivered.") == "Monday 9:05 AM"
    assert common.aria_timestamp("no stamp") == ""


def test_sent_message_seen_ignores_received():
    msgs = [{"direction": "received", "body": "On my way"}, {"direction": "sent", "body": "other"}]
    assert not common.sent_message_seen(msgs, "on my way", str.lower)
    msgs.append({"direction": "sent", "body": "On my way now"})
    assert common.sent_message_seen(msgs, "on my way", str.lower)


def backend(**overrides):
    calls = {"open": 0, "send": []}
    def open_app():
        calls["open"] += 1
    def send(to, text, draft=False):
        calls["send"].append((to, text, draft))
        return {"ok": True, "sent": not draft, "preview": text}
    kw = dict(
        open_app=open_app,
        pair_text="paired?",
        status=lambda: {"ok": True, "paired": True},
        ready_text="ready",
        list_chats=lambda limit: [{"index": "1", "title": "Alex", "preview": "x" * 130}],
        history=lambda to, limit: {"ok": False, "error": "Conversation not found"},
        send=send,
    )
    kw.update(overrides)
    return kw, calls


def test_run_app_backend_dispatch(capsys):
    kw, calls = backend()
    assert common.run_app_backend(args(command="pair"), **kw) == 0
    assert calls["open"] == 1
    assert common.run_app_backend(args(command="status"), **kw) == 0
    assert common.run_app_backend(args(command="chats"), **kw) == 0
    assert common.run_app_backend(args(command="send"), **kw) == 0
    assert calls["send"] == [("Alex", "hi", True)]
    assert common.run_app_backend(args(command="history"), **kw) == 1
    assert common.run_app_backend(args(command="nope"), **kw) == 2
    out, err = capsys.readouterr()
    assert out.splitlines() == ["paired?", "ready", "1. Alex — " + "x" * 117 + "...", "Message prepared: hi"]
    assert err == "gmsg: Conversation not found\n"


def test_run_app_backend_json_error(capsys):
    def boom():
        raise RuntimeError("not ready")
    kw, _ = backend(status=boom)
    assert common.run_app_backend(args(command="status", json=True), **kw) == 1
    assert capsys.readouterr().out == '{"ok": false, "error": "not ready"}\n'
