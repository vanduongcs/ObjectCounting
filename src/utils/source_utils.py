"""Helpers for identifying and persisting source-specific video settings."""

import json
import os


STREAM_SOURCE_PREFIXES = ("http://", "https://", "rtsp://", "rtmp://")
LAST_USED_KEY = "__last_used__"
LEGACY_KEY = "__legacy__"


def is_stream_source(source):
    if not isinstance(source, str):
        return False
    return source.strip().lower().startswith(STREAM_SOURCE_PREFIXES)


def build_source_key(source, variant=None):
    """Normalize a source string so per-source settings stay stable across sessions."""
    if not isinstance(source, str):
        return None

    value = source.strip()
    if not value:
        return None
    if is_stream_source(value):
        key = value.lower()
    else:
        key = os.path.normcase(os.path.abspath(value))

    if variant in (None, ""):
        return key
    return f"{key}::variant={variant}"


def load_source_region_store(path):
    """Load a `{sources: {key: {rel: [...]}}}` store from disk."""
    try:
        if not path.exists():
            return {}
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}

    if not isinstance(data, dict):
        return {}

    sources = data.get("sources")
    if isinstance(sources, dict):
        return sources

    # Legacy files only stored one global `rel`. Keep it isolated so it is not
    # auto-applied to unrelated sources anymore.
    rel = data.get("rel")
    if _is_valid_rel_region(rel):
        return {LEGACY_KEY: {"rel": list(rel)}}
    return {}


def save_source_region(path, store, source, rel, variant=None):
    """Persist a relative region for one source without overwriting other sources."""
    key = build_source_key(source, variant=variant)
    if key is None or not _is_valid_rel_region(rel):
        return False

    normalized_rel = [float(value) for value in rel]
    next_store = dict(store or {})
    next_store[key] = {"rel": normalized_rel}
    next_store[_build_last_used_key(variant)] = {"rel": normalized_rel}

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"sources": next_store}, ensure_ascii=False),
            encoding="utf-8",
        )
        store.clear()
        store.update(next_store)
        return True
    except Exception:
        return False


def get_source_region(store, source, variant=None, fallback_to_last_used=False):
    """Return the saved relative region for a source, or a fallback if requested."""
    key = build_source_key(source, variant=variant)
    if key is None:
        return None

    rel = _get_rel_from_entry((store or {}).get(key))
    if rel is not None:
        return rel

    if not fallback_to_last_used:
        return None

    fallback_keys = [_build_last_used_key(variant)]
    if variant not in (None, ""):
        fallback_keys.append(_build_last_used_key())
    fallback_keys.append(LEGACY_KEY)

    for fallback_key in fallback_keys:
        rel = _get_rel_from_entry((store or {}).get(fallback_key))
        if rel is not None:
            return rel
    return None


def _build_last_used_key(variant=None):
    if variant in (None, ""):
        return LAST_USED_KEY
    return f"{LAST_USED_KEY}::variant={variant}"


def _get_rel_from_entry(entry):
    if not isinstance(entry, dict):
        return None

    rel = entry.get("rel")
    if _is_valid_rel_region(rel):
        return tuple(float(value) for value in rel)
    return None


def _is_valid_rel_region(rel):
    return isinstance(rel, (list, tuple)) and len(rel) == 4
