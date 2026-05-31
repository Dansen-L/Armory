"""Armory YAML knowledge base loader."""

from __future__ import annotations
import importlib.resources
from pathlib import Path
from typing import Any

try:
    import yaml
    # Prefer the C-accelerated loader (libyaml) when available — it is ~4x faster
    # than the pure-Python SafeLoader.  Fallback to SafeLoader if libyaml is absent.
    try:
        _YAML_LOADER = yaml.CSafeLoader
    except AttributeError:
        try:
            _YAML_LOADER = yaml.CLoader  # type: ignore[attr-defined]
        except AttributeError:
            _YAML_LOADER = yaml.SafeLoader  # type: ignore[assignment]
except ImportError:
    yaml = None  # type: ignore
    _YAML_LOADER = None  # type: ignore


def get_data_dir() -> Path:
    """Return the path to the bundled YAML data directory."""
    try:
        # Python 3.9+ importlib.resources
        ref = importlib.resources.files("armory") / "data"
        return Path(str(ref))
    except Exception:
        return Path(__file__).parent / "data"


def load_class(slug: str) -> dict[str, Any] | None:
    """Load a single vulnerability class from its YAML file.

    Returns the parsed YAML dict or None if the file doesn't exist.
    """
    if yaml is None:
        raise RuntimeError("PyYAML is required: pip install pyyaml")
    yaml_path = get_data_dir() / f"{slug}.yaml"
    if not yaml_path.exists():
        return None
    with open(yaml_path, "rb") as f:  # binary mode required by CLoader
        return yaml.load(f, Loader=_YAML_LOADER)


def load_all_classes() -> list[dict[str, Any]]:
    """Load all bundled vulnerability class YAML files.

    Returns a list of parsed class dicts, sorted by slug.
    """
    if yaml is None:
        raise RuntimeError("PyYAML is required: pip install pyyaml")
    data_dir = get_data_dir()
    classes = []
    for yaml_file in sorted(data_dir.glob("*.yaml")):
        with open(yaml_file, "rb") as f:  # binary mode required by CLoader
            class_data = yaml.load(f, Loader=_YAML_LOADER)
            if class_data:
                classes.append(class_data)
    return classes


def get_all_payloads() -> list[dict[str, Any]]:
    """Return a flat list of all payloads from all built-in classes.

    Each payload dict is augmented with: class_slug, class_name,
    group_slug, group_name, difficulty, source='builtin'.
    """
    all_payloads = []
    for cls in load_all_classes():
        class_slug = cls.get("slug", "")
        class_name = cls.get("name", "")
        class_description = cls.get("description", "")
        class_owasp = cls.get("owasp", "")
        severity_range = cls.get("severity_range", {})
        for group in cls.get("groups", []):
            group_slug = group.get("slug", "")
            group_name = group.get("name", "")
            difficulty = group.get("difficulty", "medium")
            for payload in group.get("payloads", []):
                payload_copy = dict(payload)
                payload_copy["class_slug"] = class_slug
                payload_copy["class_name"] = class_name
                payload_copy["class_description"] = class_description
                payload_copy["class_owasp"] = class_owasp
                payload_copy["group_slug"] = group_slug
                payload_copy["group_name"] = group_name
                payload_copy["difficulty"] = difficulty
                payload_copy["source"] = "builtin"
                payload_copy["severity_range"] = severity_range
                all_payloads.append(payload_copy)
    return all_payloads
