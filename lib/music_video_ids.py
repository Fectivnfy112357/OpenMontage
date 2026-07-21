"""Shared id-pattern checks for music-video-anime artifacts.

The ``music_video_*`` JSON schemas (see ``schemas/artifacts/music_video_*.schema.json``)
enforce these id patterns via JSON Schema's ``pattern`` keyword::

    scenes[i].id                    -> ^s[0-9]{3,}$
    asset_manifest.entries[i].scene_id -> ^s[0-9]{3,}$
    asset_manifest.entries[i].asset_id -> ^a[0-9]{3,}$
    edit_decisions.cuts[i].cut_id   -> ^c[0-9]{3,}$

Without this helper, every stage director has to repeat the regex inline AND
emit cryptic ``ValidationError: 's1' does not match '^s[0-9]{3,}$'`` errors.
This module centralizes the patterns and provides ``check_*_id`` / ``describe_*``
for human-friendly error messages.

Usage::

    from lib.music_video_ids import check_scene_id

    err = check_scene_id("s1")  # -> "scene_id 's1' must match ^s[0-9]{3,}$ (sNNN)"
    if err:
        return ToolResult(success=False, error=err)
"""

from __future__ import annotations

import re

_SCENE_ID = re.compile(r"^s[0-9]{3,}$")
_ASSET_ID = re.compile(r"^a[0-9]{3,}$")
_CUT_ID = re.compile(r"^c[0-9]{3,}$")


def check_scene_id(value: str) -> str | None:
    """Return a human-readable error if ``value`` is not a valid scene id, else None."""
    if not value or not _SCENE_ID.match(value):
        return f"scene_id {value!r} must match ^s[0-9]{{3,}}$ (sNNN, e.g. 's001')"
    return None


def check_asset_id(value: str) -> str | None:
    """Return a human-readable error if ``value`` is not a valid asset id, else None."""
    if not value or not _ASSET_ID.match(value):
        return f"asset_id {value!r} must match ^a[0-9]{{3,}}$ (aNNN, e.g. 'a001')"
    return None


def check_cut_id(value: str) -> str | None:
    """Return a human-readable error if ``value`` is not a valid cut id, else None."""
    if not value or not _CUT_ID.match(value):
        return f"cut_id {value!r} must match ^c[0-9]{{3,}}$ (cNNN, e.g. 'c001')"
    return None


def check_music_video_id(kind: str, value: str) -> str | None:
    """Dispatch to the right checker by ``kind`` ('scene' | 'asset' | 'cut')."""
    if kind == "scene":
        return check_scene_id(value)
    if kind == "asset":
        return check_asset_id(value)
    if kind == "cut":
        return check_cut_id(value)
    raise ValueError(f"unknown music_video id kind: {kind!r}")
