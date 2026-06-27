"""Runtime configuration for gmsg."""
from __future__ import annotations

import os
from pathlib import Path

AUTH_STATE = Path.home() / ".config/gmsg/playwright-auth.json"
ROUTES_PATH = Path(os.environ.get("GMSG_ROUTES_PATH", str(Path.home() / ".config/gmsg/routes.json"))).expanduser()
AUTOMATION_USER_DATA_DIR = Path(os.environ.get("GMSG_USER_DATA_DIR", str(Path.home() / ".config/gmsg/chrome-profile"))).expanduser()
REAL_CHROME_USER_DATA_DIR = Path.home() / "Library/Application Support/Google/Chrome"
PROFILE_DIRECTORY = os.environ.get("GMSG_PROFILE_DIRECTORY", "Default")
AUTH_MODE = os.environ.get("GMSG_AUTH_MODE", "lite").lower()  # lite | chrome | automation | cdp
CDP_PORT = int(os.environ.get("GMSG_CDP_PORT", "9222"))
MESSAGES_URL = "https://messages.google.com/web/conversations"
LITE_APP_NAME = os.environ.get("GMSG_LITE_APP_NAME", "Google Messages Lite")
LITE_PROCESS_NAME = os.environ.get("GMSG_LITE_PROCESS_NAME", "pake-googlemessageslite")
