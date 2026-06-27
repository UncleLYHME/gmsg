# AGENTS.md

## Goal

Make `gmsg` a clean, reusable, open-source CLI for Google Messages for Web without leaking local automation assumptions, private contacts, credentials, or machine-specific paths.

## Standards

- Keep the public CLI boring and predictable.
- Never hardcode personal names, phone numbers, emails, local usernames, Tailnet hosts, tokens, or private paths.
- Default to safe behavior in docs and examples. Use `--draft` in tests and onboarding examples where possible.
- Do not add live-send tests. Unit tests must not open browsers, send messages, or require a paired account.
- Treat Google Messages DOM selectors as unstable. Keep selector changes small and documented.
- Keep browser automation imports optional so `gmsg --help` and unit tests work without Playwright installed.
- Keep backend-specific browser automation in `src/gmsg/backends/`; `cli.py` should stay thin and only parse/dispatch.

## Verification before commit

Run:

```bash
python -m compileall src tests
pytest
python -m gmsg --help
```

If browser behavior changes, test manually with:

```bash
gmsg status --json
gmsg chats --limit 5 --json
gmsg send --to "<safe test chat>" --text "draft test" --draft --json
```

Do not run a live send unless the maintainer explicitly asks.

## Release checklist

- README examples are generic.
- No personal names, contacts, paths, tokens, hosts, or screenshots are committed.
- `pytest` passes without browser credentials.
- `gmsg --help` works in a fresh virtualenv.
- Known limitations are documented instead of hidden.
