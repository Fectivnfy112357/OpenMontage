"""Top-level ``lib`` package for OpenMontage.

Each sibling module exposes one focused concern (checkpoint, pipeline_loader,
media profiles, etc.). Per-pipeline helpers live as flat siblings, e.g.
``lib.music_video_adapter`` for music-video-anime.

The ``__all__`` list below re-exports the music-video-anime helpers so callers
can write ``from lib import music_video_adapter`` instead of
``from lib.music_video_adapter import adapt_edit_decisions_for_tool``. Without
this, agents writing inline ``tools_*.py`` files per run pollute the project
workspace with adapter shims that should live in ``lib/``.
"""

from __future__ import annotations

# Music-video-anime schema <-> tool field adapters. M-7 fix (2026-07-21):
# these helpers exist as flat sibling modules but were not importable via
# ``from lib import ...`` until they were re-exported here.
from lib import (  # noqa: E402  (re-exports for the music-video-anime pipeline)
    music_video_adapter,
    music_video_drift,
    music_video_ids,
    runtime_swap_suggester,
)

__all__ = [
    "music_video_adapter",
    "music_video_drift",
    "music_video_ids",
    "runtime_swap_suggester",
]
