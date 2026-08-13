"""Dependency-free domain types shared by detection and state transitions."""

from enum import Enum, auto


class SliderDirection(Enum):
    LEFT = auto()
    RIGHT = auto()
    NEUTRAL = auto()
