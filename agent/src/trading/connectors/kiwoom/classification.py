"""Curated read/write classification for Kiwoom REST OpenAPI operations."""

from __future__ import annotations

from src.live.classification import ToolClass

KIWOOM_TOOL_CLASS: dict[str, ToolClass] = {
    "ka10001": ToolClass.READ,
    "ka10004": ToolClass.READ,
    "ka10080": ToolClass.READ,
    "kt00018": ToolClass.READ,
    "kt10000": ToolClass.WRITE,
    "kt10001": ToolClass.WRITE,
    "kt10002": ToolClass.WRITE,
}
