"""Dynamic game-window discovery.

The application never persists a numeric HWND.  Window handles are refreshed
when the game starts, closes, or recreates its window.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
import unicodedata

import win32gui

from src.settings import GameProfile, settings

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class WindowMatch:
    hwnd: int
    profile: GameProfile
    title: str


def _normalise_title(value: str) -> str:
    return unicodedata.normalize("NFKC", value).casefold().strip()


class WindowLocator:
    def __init__(self, profiles: tuple[GameProfile, ...] | None = None):
        self.profiles = profiles or settings.profiles

    def find(self) -> WindowMatch | None:
        windows: list[tuple[int, str]] = []

        def callback(hwnd: int, _extra: object) -> None:
            if not win32gui.IsWindowVisible(hwnd):
                return
            title = win32gui.GetWindowText(hwnd) or ""
            if title:
                windows.append((hwnd, title))

        win32gui.EnumWindows(callback, None)

        profiles = [
            (
                profile,
                tuple(
                    normalised
                    for alias in profile.title_aliases
                    if (normalised := _normalise_title(alias))
                ),
            )
            for profile in self.profiles
        ]

        # Prefer an exact title match across all profiles.  A generic alias
        # such as "NTE" can otherwise match an unrelated title such as
        # "nte-fishing - Visual Studio Code" before the actual game window.
        for exact in (True, False):
            for profile, aliases in profiles:
                for hwnd, title in windows:
                    normalised = _normalise_title(title)
                    matched = (
                        normalised in aliases
                        if exact
                        else any(alias in normalised for alias in aliases)
                    )
                    if matched:
                        log.info(
                            "Found lang=%s window: hwnd=%d title=%r exact=%s",
                            profile.lang,
                            hwnd,
                            title,
                            exact,
                        )
                        return WindowMatch(hwnd, profile, title)
        return None

    def is_valid(self, match: WindowMatch | None) -> bool:
        if match is None or not win32gui.IsWindow(match.hwnd):
            return False
        if not win32gui.IsWindowVisible(match.hwnd):
            return False
        title = _normalise_title(win32gui.GetWindowText(match.hwnd) or "")
        return any(_normalise_title(alias) in title for alias in match.profile.title_aliases)
