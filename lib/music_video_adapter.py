"""Schema-to-tool field adapters for the music-video-anime pipeline.

This module addresses O-4 (2026-07-20): the HyperFrames tool historically
expected field names that did not match the music-video-anime schemas::

    tool-internal:     asset_manifest["assets"][].{id, path, ...}
                       edit_decisions["cuts"][].{id, source, ...}

    schema-compliant:  asset_manifest["entries"][].{asset_id, path, ...}
                       edit_decisions["cuts"][].{cut_id, asset_id, asset_path, ...}

As of the 2026-07-21 O-4 fix ``tools/video/hyperframes_compose.py`` already
accepts BOTH forms via ``_coerce_asset_entries`` and reads
``at_seconds``/``duration_seconds`` directly. The functions here translate
schema-compliant inputs to the tool's expected field shape for the rare
caller that hands a dict directly to the tool without going through the
registry — saving the agent from writing 30-line adapter shims per run.

Design note: this is a pure-function module with NO ToolResult/dataclass
state. Aligns with the rest of ``lib/`` where each module does one thing.
"""

from __future__ import annotations

from typing import Any


def adapt_asset_manifest_for_tool(asset_manifest: dict) -> dict:
    """Normalize schema-form ``asset_manifest`` to HyperFrames' tool-internal shape.

    Accepts either ``{"assets": [...]}`` (tool's legacy field) or
    ``{"entries": [...]}`` (music_video_asset_manifest schema, keyed by
    ``asset_id``). Returns a copy with ``assets`` populated and each entry's
    ``asset_id`` aliased as ``id`` so the tool's ``asset_lookup[id]`` works.
    """
    assets = asset_manifest.get("assets")
    if assets is None:
        assets = asset_manifest.get("entries", []) or []
    normalized = []
    for entry in assets:
        out = dict(entry)  # preserve all original fields
        out.setdefault("id", out.get("asset_id"))
        normalized.append(out)
    return {**asset_manifest, "assets": normalized}


def adapt_edit_decisions_for_tool(edit_decisions: dict) -> dict:
    """Translate schema-compliant cut fields to tool-internal fields.

    Maps::

        cut_id       -> id
        asset_path   -> source

    Other fields (``beat_anchor``, ``transition_in``, ``transition_out``,
    ``trim``, ``motion``, ``overlay``, ``drift_ms``, ``at_seconds``,
    ``duration_seconds``, ``asset_id``) pass through unchanged.
    """
    adapted_cuts = []
    for cut in edit_decisions.get("cuts", []) or []:
        out = dict(cut)
        if "cut_id" in out and "id" not in out:
            out["id"] = out["cut_id"]
        if "asset_path" in out and "source" not in out:
            out["source"] = out["asset_path"]
        adapted_cuts.append(out)
    return {**edit_decisions, "cuts": adapted_cuts}


def adapt_schema_inputs_to_tool(
    edit_decisions: dict,
    asset_manifest: dict,
) -> tuple[dict, dict]:
    """One-call adapter wrapper. Returns (adapted_edit, adapted_manifest).

    Use this when you would otherwise hand a 30-line shim to the tool. Idempotent
    on inputs already in tool-form.
    """
    return (
        adapt_edit_decisions_for_tool(edit_decisions),
        adapt_asset_manifest_for_tool(asset_manifest),
    )
