# gmsg

`gmsg` is a small command line tool for Google Messages for Web. It can check readiness, list chats, read recent conversation history, compose drafts, send messages, and manage local route aliases.

This project is early and sharp-edged. It automates a browser session, so treat live sends with the same care you would treat any messaging automation.

## What works today

- `gmsg status` checks whether Messages for Web looks usable.
- `gmsg chats --limit 20` lists visible conversations.
- `gmsg history --to "Alex" --limit 10` reads recent messages from a conversation.
- `gmsg send --to "Alex" --text "On my way"` sends a message.
- `gmsg send --to "Alex" --text "Draft only" --draft` composes without sending.
- `gmsg route set partner "Alex"` stores local aliases in `~/.config/gmsg/routes.json`.

## Requirements

- Python 3.14.7
- Google Chrome, if using the `chrome`, `automation`, or `cdp` backends
- macOS, for the default `lite` backend and the `chrome` AppleScript backend
- A phone paired with Google Messages for Web: <https://messages.google.com/web>

Backend support:

| Backend | Platform | Install extras | Notes |
|---|---|---|---|
| `lite` | macOS | none | Default. Drives a lightweight Google Messages app wrapper via Accessibility. |
| `chrome` | macOS | none | Drives normal Google Chrome via AppleScript. |
| `automation` | macOS/Linux/Windows-ish | `.[playwright]` | Uses Playwright with an isolated browser profile. |
| `cdp` | macOS/Linux/Windows-ish | `.[playwright]` | Attaches to Chrome through a remote debugging port. |

The default is `GMSG_AUTH_MODE=lite`. If you do not have a Google Messages Lite wrapper app, use `chrome` first.

## Install from source

Clone the repo, create a virtual environment, and install the CLI:

```bash
git clone https://github.com/<owner>/gmsg.git
cd gmsg
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
gmsg --help
```

For Playwright-backed modes:

```bash
pip install -e '.[playwright]'
playwright install chromium
```

For development tools:

```bash
pip install -e '.[dev,playwright]'
```

## First-time setup

### Option A: normal Chrome on macOS

This is the easiest setup if you already use Google Messages in Chrome.

1. Open Chrome and go to <https://messages.google.com/web>.
2. Pair your phone if Google asks.
3. Allow macOS Automation permissions if prompted.
4. Run:

```bash
export GMSG_AUTH_MODE=chrome
gmsg status
gmsg chats --limit 5
```

If macOS asks for permissions, allow Terminal or your shell app to control Google Chrome and System Events.

### Option B: Playwright isolated browser profile

This keeps a separate browser profile under `~/.config/gmsg/chrome-profile`.

```bash
pip install -e '.[playwright]'
playwright install chromium
export GMSG_AUTH_MODE=automation
gmsg pair
```

A browser opens. Pair Google Messages there, then verify:

```bash
gmsg status --json
gmsg chats --limit 5
```

### Option C: Chrome DevTools Protocol

Use this if you want `gmsg` to attach to a Chrome instance with remote debugging enabled.

```bash
export GMSG_AUTH_MODE=cdp
export GMSG_CDP_PORT=9222
gmsg status
```

If Chrome is not already listening on that port, `gmsg` tries to launch it with `--remote-debugging-port`.

### Option D: Google Messages Lite wrapper

The default `lite` backend expects a macOS app named `Google Messages Lite` with process name `pake-googlemessageslite`.

Override those if your wrapper differs:

```bash
export GMSG_AUTH_MODE=lite
export GMSG_LITE_APP_NAME="Google Messages Lite"
export GMSG_LITE_PROCESS_NAME="pake-googlemessageslite"
gmsg status
```

## Usage

```bash
gmsg status
gmsg chats --limit 10 --json
gmsg history --to "Alex" --limit 10
gmsg send --to "Alex" --text "On my way"
gmsg send --to "Alex" --text "Draft test" --draft
gmsg route set partner "Alex"
gmsg route resolve partner
```

## Safer test flow

Before sending anything live, use drafts:

```bash
gmsg chats --limit 10
gmsg history --to "Alex" --limit 5
gmsg send --to "Alex" --text "draft route test" --draft --json
```

Only send live after the draft lands in the correct conversation:

```bash
gmsg send --to "Alex" --text "Hello from gmsg" --json
```

## Route aliases

Aliases are local shortcuts. They are stored in `~/.config/gmsg/routes.json` unless `GMSG_ROUTES_PATH` is set.

```bash
gmsg route set partner "Alex"
gmsg route resolve partner
gmsg send --to partner --text "Draft only" --draft
gmsg route list
gmsg route remove partner
```

Aliases are not stable Google conversation IDs. If Google Messages changes the displayed conversation title, update the alias.

## Configuration

Environment variables:

| Variable | Default | Purpose |
|---|---|---|
| `GMSG_AUTH_MODE` | `lite` | Browser backend: `lite`, `chrome`, `automation`, or `cdp`. |
| `GMSG_ROUTES_PATH` | `~/.config/gmsg/routes.json` | Alias route file. |
| `GMSG_USER_DATA_DIR` | `~/.config/gmsg/chrome-profile` | Isolated browser profile for automation mode. |
| `GMSG_PROFILE_DIRECTORY` | `Default` | Chrome profile directory. |
| `GMSG_CDP_PORT` | `9222` | Chrome DevTools Protocol port for CDP mode. |
| `GMSG_LITE_APP_NAME` | `Google Messages Lite` | macOS Lite wrapper app name. |
| `GMSG_LITE_PROCESS_NAME` | `pake-googlemessageslite` | macOS Lite wrapper process name. |

## Troubleshooting

### `Not paired` or no chats show up

Open <https://messages.google.com/web> in the backend browser and pair your phone again.

For Chrome mode:

```bash
export GMSG_AUTH_MODE=chrome
gmsg status --json
```

For Playwright automation mode:

```bash
export GMSG_AUTH_MODE=automation
gmsg pair
gmsg status --json
```

### macOS blocks automation

Open System Settings and check:

- Privacy & Security → Accessibility
- Privacy & Security → Automation

Allow your terminal app to control Google Chrome and System Events.

### Wrong conversation matched

Use the exact title from `gmsg chats`, then test with `--draft`:

```bash
gmsg chats --limit 20
gmsg send --to "Exact Chat Title" --text "draft test" --draft --json
```

If you use route aliases, update the alias after verifying the correct title.

### Playwright is missing

Install the optional dependency:

```bash
pip install -e '.[playwright]'
playwright install chromium
```

## Safety notes

- Prefer `--draft` when testing routes.
- Verify the target conversation with `history` before first live send.
- Route aliases are local convenience only. They are not stable IDs from Google.
- Browser DOM selectors can break when Google changes Messages for Web.
- Do not put phone numbers, private chat names, auth state, screenshots, or local browser profiles in git.

## Project layout

```text
src/gmsg/cli.py                 # argument parsing and backend dispatch
src/gmsg/config.py              # environment-backed runtime settings
src/gmsg/routes.py              # local route alias storage
src/gmsg/utils.py               # shared normalization / JSON helpers
src/gmsg/backends/chrome.py     # macOS Chrome + AppleScript backend
src/gmsg/backends/lite.py       # macOS Google Messages Lite accessibility backend
src/gmsg/backends/playwright.py # Playwright / CDP backend
```

## Development

```bash
python -m compileall src tests
pytest
PYTHONPATH=src python -m gmsg --help
```

If you installed the dev extras:

```bash
ruff check src tests
```

## License

MIT. See [LICENSE](LICENSE).

Rebuild after a wiped drive: see [RESTORE.md](RESTORE.md).
