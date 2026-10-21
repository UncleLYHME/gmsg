# Restore: gmsg

- What: Python CLI for Google Messages for Web (status, chats, history, send, route aliases). Public repo `UncleLYHME/gmsg`. Used by the Mini's family/dinner/goodnight pipeline scripts (homelab `services/ollie/scripts/pipeline/*.sh`, `tools/lib/automation-delivery.sh`).
- Where it runs: the Mini only (Mac-bound: Chrome, Accessibility/AppleScript, the paired phone session). Installed command: `~/.local/bin/gmsg`. Not a service; no URL.
- Depends on: Python 3.10+, Google Chrome, a phone paired at https://messages.google.com/web; Playwright for the `automation`/`cdp` backends.
- Backups:
  - Code: GitHub only (`UncleLYHME/gmsg`). Nightly git mirror on BufferDaddy (`/volume1/backups/git-mirrors/gmsg.git`, 2:30 AM, verified present) and the Harbor checkout in Harbor's nightly `/volume1/backups/<date>/harbor/projects.tar.gz`. The Mini keeps no copy of the repo.
  - Config/env: none in git. Env names: `GMSG_AUTH_MODE` (the pipelines use `chrome`), `GMSG_ROUTES_PATH`, `GMSG_USER_DATA_DIR`, `GMSG_CDP_PORT`, `GMSG_LITE_APP_NAME`, `GMSG_LITE_PROCESS_NAME`, `GMSG_SEND_TIMEOUT_SECONDS`, `GMSG_SEND_RETRIES`.
  - **Not backed up anywhere:** `~/.config/gmsg/` (`routes.json` aliases, `playwright-auth.json`, `chrome-profile/`) and the live `~/.local/bin/gmsg` plus `~/.local/share/gmsg-pw/.venv`. The installed `~/.local/bin/gmsg` is a 56 KB standalone headless-Playwright script dated Jul 5, 2026 that is not the repo's `src/gmsg` package and is not in any repo. Auth is re-pairable; the aliases and that script are not recoverable from git.

## Restore steps

```sh
gh repo clone UncleLYHME/gmsg ~/Projects/gmsg
cd ~/Projects/gmsg
python3 -m venv .venv && . .venv/bin/activate
pip install -e '.[dev,playwright]' && playwright install chromium   # playwright only for automation/cdp modes
export GMSG_AUTH_MODE=chrome
gmsg --help
```

Then: open Chrome, go to https://messages.google.com/web, re-pair the phone, allow macOS Automation prompts (Terminal/shell controlling Chrome and System Events). Recreate aliases with `gmsg route set <alias> "<chat name>"`. The pipelines expect `gmsg` on `PATH` (`~/.local/bin`): `ln -s ~/Projects/gmsg/.venv/bin/gmsg ~/.local/bin/gmsg`, or re-create the old standalone script if it is still needed.

## Verify

```sh
python -m compileall src tests && pytest && python -m gmsg --help
GMSG_AUTH_MODE=chrome gmsg status --json
GMSG_AUTH_MODE=chrome gmsg send --to "<chat>" --text test --draft     # draft only, never a live send for a test
```

## Gotchas

- Never add live-send tests; use `--draft`.
- The first call on a cold-start Chrome often fails; the pipelines run `gmsg status --json` first and retry.
- Google Messages DOM selectors are unstable; fix selectors in `src/gmsg/backends/`.
