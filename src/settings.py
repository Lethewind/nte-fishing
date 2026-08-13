"""Application settings loaded from ``.env`` with safe defaults."""

from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")
if getattr(sys, "frozen", False):
    load_dotenv(Path(sys.executable).resolve().parent / ".env")


def _env(name: str, default: str) -> str:
    value = os.getenv(name)
    return default if value is None or value.strip() == "" else value.strip()


def _float(name: str, default: float) -> float:
    try:
        return float(_env(name, str(default)))
    except ValueError:
        return default


def _int(name: str, default: int) -> int:
    try:
        return int(_env(name, str(default)))
    except ValueError:
        return default


def _bool(name: str, default: bool) -> bool:
    return _env(name, str(default)).lower() in {"1", "true", "yes", "on"}


def _list(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    value = os.getenv(name)
    if value is None:
        return default
    return tuple(item.strip() for item in value.split(",") if item.strip()) or default


def _path(name: str, default: Path) -> Path:
    value = Path(_env(name, str(default)))
    return value if value.is_absolute() else ROOT_DIR / value


@dataclass(frozen=True)
class GameProfile:
    lang: str
    title_aliases: tuple[str, ...]
    result_template: Path


@dataclass(frozen=True)
class Settings:
    loop_interval: float
    input_function: str
    input_assignment: str
    send_activation_hints: bool
    show_preview: bool
    startup_delay_sec: int
    bar_y_start_ratio: float
    bar_y_end_ratio: float
    bar_x_start_ratio: float
    bar_x_end_ratio: float
    hook_y_start_ratio: float
    hook_y_end_ratio: float
    hook_x_start_ratio: float
    hook_x_end_ratio: float
    result_search_x_start: float
    result_search_x_end: float
    result_search_y_start: float
    result_search_y_end: float
    result_template_threshold: float
    hook_template: Path
    hook_template_threshold: float
    hook_binary_threshold: int
    idle_press_min_sec: float
    idle_press_max_sec: float
    result_esc_cooldown_sec: float
    fishing_loop_interval: float
    slider_h_low: int
    slider_h_high: int
    slider_s_min: int
    slider_v_min: int
    slider_px_threshold: int
    slider_max_dist_ratio: float
    slider_merge_gap_marker_ratio: float
    marker_template: Path
    marker_template_threshold: float
    profiles: tuple[GameProfile, ...]


def load_settings() -> Settings:
    assets = ROOT_DIR / "assets"
    default_language_title_map: dict[str, tuple[str, ...]] = {
        "zh": ("异环", "異環"),
        "zhtw": ("NTE",),
    }
    languages = tuple(
        dict.fromkeys(
            lang.strip().lower()
            for lang in _list("LANGUAGES", tuple(default_language_title_map))
            if lang.strip()
        )
    )
    language_title_map = {
        lang: _list(
            "WINDOW_TITLES_" + re.sub(r"[^A-Z0-9]+", "_", lang.upper()),
            default_language_title_map.get(lang, (lang,)),
        )
        for lang in languages
    }
    profiles = tuple(
        GameProfile(
            lang=lang,
            title_aliases=titles,
            result_template=assets / f"click_bank_{lang}.png",
        )
        for lang, titles in language_title_map.items()
    )

    return Settings(
        loop_interval=_float("LOOP_INTERVAL", 0.2),
        input_function=_env("INPUT_FUNCTION", "sendmessage").lower(),
        input_assignment=_env("INPUT_ASSIGNMENT", "ad").lower(),
        send_activation_hints=_bool("SEND_ACTIVATION_HINTS", False),
        show_preview=_bool("SHOW_PREVIEW_WINDOW", True),
        startup_delay_sec=_int("STARTUP_DELAY_SEC", 5),
        bar_y_start_ratio=_float("BAR_Y_START_RATIO", 0.03),
        bar_y_end_ratio=_float("BAR_Y_END_RATIO", 0.12),
        bar_x_start_ratio=_float("BAR_X_START_RATIO", 0.28),
        bar_x_end_ratio=_float("BAR_X_END_RATIO", 0.72),
        hook_y_start_ratio=_float("HOOK_Y_START_RATIO", 0.82),
        hook_y_end_ratio=_float("HOOK_Y_END_RATIO", 0.95),
        hook_x_start_ratio=_float("HOOK_X_START_RATIO", 0.89),
        hook_x_end_ratio=_float("HOOK_X_END_RATIO", 0.97),
        result_search_x_start=_float("RESULT_SEARCH_X_START", 0.40),
        result_search_x_end=_float("RESULT_SEARCH_X_END", 0.60),
        result_search_y_start=_float("RESULT_SEARCH_Y_START", 0.85),
        result_search_y_end=_float("RESULT_SEARCH_Y_END", 0.95),
        result_template_threshold=_float("RESULT_TEMPLATE_THRESHOLD", 0.5),
        hook_template=_path("HOOK_TEMPLATE", assets / "hook.png"),
        hook_template_threshold=_float("HOOK_TEMPLATE_THRESHOLD", 0.3),
        hook_binary_threshold=_int("HOOK_BINARY_THRESHOLD", 160),
        idle_press_min_sec=_float("IDLE_PRESS_MIN_SEC", 0.5),
        idle_press_max_sec=_float("IDLE_PRESS_MAX_SEC", 1.0),
        result_esc_cooldown_sec=_float("RESULT_ESC_COOLDOWN_SEC", 3.0),
        fishing_loop_interval=_float("FISHING_LOOP_INTERVAL", 0.033),
        slider_h_low=_int("SLIDER_H_LOW", 75),
        slider_h_high=_int("SLIDER_H_HIGH", 90),
        slider_s_min=_int("SLIDER_S_MIN", 150),
        slider_v_min=_int("SLIDER_V_MIN", 180),
        slider_px_threshold=_int("SLIDER_PX_THRESHOLD", 200),
        slider_max_dist_ratio=_float("SLIDER_MAX_DIST_RATIO", 0.15),
        slider_merge_gap_marker_ratio=_float("SLIDER_MERGE_GAP_MARKER_RATIO", 2.0),
        marker_template=_path("MARKER_TEMPLATE", assets / "marker_template.png"),
        marker_template_threshold=_float("MARKER_TEMPLATE_THRESHOLD", 0.85),
        profiles=profiles,
    )


settings = load_settings()
