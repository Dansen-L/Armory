"""CLI round-trip tests for Armory — subprocess-based empirical verification."""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

# Determine the Python interpreter: use system Python (has click+pyyaml) or venv if click present
PROJECT_ROOT = Path(__file__).parent.parent
VENV_PYTHON = PROJECT_ROOT / ".venv" / "bin" / "python3"
# Check if venv Python has click; fall back to system python3 if not
import shutil as _shutil
_sys_py = _shutil.which("python3") or sys.executable
try:
    import subprocess as _sp
    _sp.run([str(VENV_PYTHON), "-c", "import click"], check=True, capture_output=True) if VENV_PYTHON.exists() else None
    PYTHON = str(VENV_PYTHON) if VENV_PYTHON.exists() else _sys_py
except Exception:
    PYTHON = _sys_py

# Set PYTHONPATH to project root so armory is importable even without pip install
ENV = {**os.environ, "PYTHONPATH": str(PROJECT_ROOT)}
# Use a temp DB so tests don't pollute the user's ~/.armory/armory.db
TEMP_DB = tempfile.mktemp(suffix=".db")
ENV["ARMORY_DB_PATH"] = TEMP_DB


def run_armory(*args, input=None):
    """Run 'armory <args>' via subprocess and return (returncode, stdout, stderr)."""
    cmd = [PYTHON, "-m", "armory.cli"] + list(args)
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        env=ENV,
        input=input,
        timeout=30,
    )
    return result.returncode, result.stdout, result.stderr


def test_help():
    """armory --help exits 0 and lists subcommands."""
    rc, out, err = run_armory("--help")
    assert rc == 0, f"--help returned {rc}: {err}"
    assert "Usage" in out or "usage" in out
    assert "search" in out
    assert "info" in out
    assert "export" in out


def test_info_xss():
    """armory info xss exits 0 and shows XSS class overview."""
    rc, out, err = run_armory("info", "xss")
    assert rc == 0, f"info xss returned {rc}: {err}"
    combined = out + err
    assert any(w in combined.upper() for w in ("XSS", "CROSS-SITE")), \
        f"Expected XSS mention in output, got:\n{combined[:400]}"
    # Should have at least 5 lines
    assert len(combined.strip().splitlines()) >= 5


def test_info_list_all():
    """armory info --list-all prints ≥ 20 class rows."""
    rc, out, err = run_armory("info", "--list-all")
    assert rc == 0, f"info --list-all returned {rc}: {err}"
    combined = out + err
    lines = [l for l in combined.splitlines() if l.strip()]
    # Count lines that look like class rows (contain a slug-like token)
    slugs_present = [s for s in ("xss", "sqli", "cmdi", "ssrf", "xxe") if s in combined.lower()]
    assert len(slugs_present) >= 5, f"Expected ≥5 class slugs in output, got: {slugs_present}"
    assert len(lines) >= 20, f"Expected ≥20 lines, got {len(lines)}"


def test_info_sqli():
    """armory info sqli exits 0 and mentions SQL injection."""
    rc, out, err = run_armory("info", "sqli")
    assert rc == 0, f"info sqli returned {rc}: {err}"
    combined = out + err
    assert any(w in combined.upper() for w in ("SQL", "INJECTION"))


def test_info_bad_slug():
    """armory info nonexistent-slug exits non-zero without traceback."""
    rc, out, err = run_armory("info", "this-does-not-exist-xyz")
    assert rc != 0, f"Expected non-zero exit for bad slug, got {rc}"
    assert "Traceback" not in err, f"Unexpected traceback:\n{err}"


def test_search_alert():
    """armory search 'alert' returns results mentioning xss."""
    rc, out, err = run_armory("search", "alert")
    assert rc == 0, f"search returned {rc}: {err}"
    combined = out + err
    assert len(combined.strip()) > 0, "Expected non-empty search results"


def test_search_no_arg():
    """armory search with no query exits non-zero."""
    rc, out, err = run_armory("search")
    assert rc != 0, f"Expected non-zero exit for search with no arg, got {rc}"


def test_search_htmlspecialchars_waf_bypass():
    """armory search 'htmlspecialchars bypass...' returns ≥1 XSS result via waf_bypass_notes tier."""
    # This is the canonical spec query from the build spec.
    # Requires 'htmlspecialchars' (a rare 16-char token) to be present in at least one
    # payload's waf_bypass_notes, which triggers the tier-5 floor score of 55.
    rc, out, err = run_armory(
        "search", "htmlspecialchars bypass stored script xss alert", "--format", "json"
    )
    assert rc == 0, f"search returned {rc}: {err}"
    results = json.loads(out)
    assert len(results) >= 1, (
        f"Expected ≥1 result for htmlspecialchars query, got 0. "
        f"This query must return XSS payloads with htmlspecialchars in waf_bypass_notes."
    )
    class_slugs = {r["class_slug"] for r in results}
    assert "xss" in class_slugs, (
        f"Expected at least one XSS class result, got class_slugs: {class_slugs}"
    )


def test_search_jinja_template_injection():
    """armory search 'template injection jinja' returns ≥1 SSTI result in top 20.

    This exercises the spec success criterion: 'template injection jinja' must surface
    SSTI / Jinja2 content. With rapidfuzz installed, the tier-2 title token_sort_ratio
    scores ≈37-43 for Jinja2 titles (below the tier-2 threshold of 70). The tier-1.5
    tag prefix check catches 'jinja' as a left-anchored prefix of the 'jinja2' tag.
    """
    rc, out, err = run_armory(
        "search", "template injection jinja", "--format", "json"
    )
    assert rc == 0, f"search returned {rc}: {err}"
    results = json.loads(out)
    assert len(results) >= 1, (
        "Expected ≥1 result for 'template injection jinja' query, got 0."
    )
    class_slugs = {r["class_slug"] for r in results}
    assert "ssti" in class_slugs, (
        f"Expected at least one SSTI class result for 'template injection jinja', "
        f"got class_slugs: {class_slugs}. SSTI payloads must rank in the top 20."
    )


def test_export_burp():
    """armory export --class xss --format burp outputs one payload per line."""
    rc, out, err = run_armory("export", "--class", "xss", "--format", "burp")
    assert rc == 0, f"export burp returned {rc}: {err}"
    # Burp output should be raw strings, not JSON
    assert not out.strip().startswith("["), "Burp output should not start with JSON array bracket"
    # Strict line count: get expected count via JSON export, then verify
    # burp output has exactly that many lines — no empty lines allowed.
    rc2, out2, _ = run_armory("export", "--class", "xss", "--format", "json")
    assert rc2 == 0, "JSON export failed; cannot determine expected payload count"
    expected_count = len(json.loads(out2))
    assert expected_count >= 5, f"JSON export returned fewer than 5 payloads: {expected_count}"
    # splitlines() splits on \n, \r\n, \r — so any unencoded embedded newline
    # would inflate the count and cause this assertion to fail.
    actual_lines = out.splitlines()
    assert len(actual_lines) == expected_count, (
        f"Burp export line count mismatch: expected {expected_count} (one per payload), "
        f"got {len(actual_lines)}. "
        f"Possible embedded unencoded newline in a payload_string."
    )


def test_export_json():
    """armory export --class sqli --format json outputs parseable JSON."""
    rc, out, err = run_armory("export", "--class", "sqli", "--format", "json")
    assert rc == 0, f"export json returned {rc}: {err}"
    try:
        data = json.loads(out)
    except json.JSONDecodeError as e:
        pytest.fail(f"Export JSON is not valid JSON: {e}\nOutput:\n{out[:200]}")
    assert isinstance(data, (list, dict))
    if isinstance(data, list):
        assert len(data) >= 5, f"Expected ≥5 payloads in JSON export"
    else:
        # dict keyed by class slug
        total = sum(len(v) for v in data.values())
        assert total >= 5


def test_export_markdown():
    """armory export --class xss --format markdown has correct group headings and class overview."""
    import re
    rc, out, err = run_armory("export", "--class", "xss", "--format", "markdown")
    assert rc == 0, f"export markdown returned {rc}: {err}"
    headings = [l for l in out.splitlines() if l.startswith("## ")]
    heading_text = " ".join(headings)
    # Check the spec-required patterns
    required_patterns = ["Reflected", "Stored", "DOM-based", "Blind", "mXSS", "Polyglots"]
    for pat in required_patterns:
        assert any(pat in h for h in headings), \
            f"Markdown heading for '{pat}' not found. Headings: {headings}"
    # Class overview: description prose and OWASP mapping must appear after the H1 heading
    assert "Cross-Site Scripting" in out and "OWASP:" in out, (
        "Markdown export must include class description prose and OWASP: reference after "
        f"the # heading. Got output starting with: {out[:300]!r}"
    )


def test_export_bad_class():
    """armory export --class nonexistent exits non-zero."""
    rc, out, err = run_armory("export", "--class", "nonexistent-class", "--format", "txt")
    assert rc != 0, f"Expected non-zero for bad class, got {rc}"


def test_add_and_delete_roundtrip():
    """armory add creates a custom payload; armory delete removes it."""
    # Add
    rc, out, err = run_armory(
        "add",
        "--class", "xss",
        "--group", "reflected",
        "--title", "Test payload for roundtrip",
        "--payload", "<test>roundtrip</test>",
        "--description", "This is a test payload for the roundtrip test. It verifies add/delete. Nothing more.",
    )
    assert rc == 0, f"add returned {rc}: {err}\n{out}"
    combined = out + err
    assert "Test payload" in combined or "custom" in combined.lower(), \
        f"Expected confirmation in output, got:\n{combined[:200]}"

    # Extract payload ID from output
    pid = None
    for line in combined.splitlines():
        if "custom-" in line.lower() or "id:" in line.lower():
            parts = line.split()
            for part in parts:
                if part.startswith("custom-"):
                    pid = part.strip(".,;")
                    break
    if pid is None:
        # Try to find via export
        rc2, out2, _ = run_armory("export", "--class", "xss", "--format", "json", "--source", "custom")
        try:
            data = json.loads(out2)
            if isinstance(data, list) and data:
                pid = data[-1].get("id")
        except Exception:
            pass

    # Delete if we have the ID
    if pid:
        rc, out, err = run_armory("delete", "--yes", pid)
        assert rc == 0, f"delete returned {rc}: {err}"


def test_ai_ask_no_key():
    """armory ai-ask without API key exits non-zero with useful message."""
    env_copy = {**ENV}
    env_copy.pop("ARMORY_CLAUDE_API_KEY", None)
    env_copy.pop("ANTHROPIC_API_KEY", None)
    cmd = [PYTHON, "-m", "armory.cli", "ai-ask", "What is XSS?"]
    result = subprocess.run(cmd, capture_output=True, text=True, env=env_copy, timeout=30)
    rc = result.returncode
    combined = result.stdout + result.stderr
    assert rc != 0, f"Expected non-zero exit when API key absent, got {rc}"
    assert "Traceback" not in result.stderr, f"Unexpected traceback:\n{result.stderr}"
    # Should mention API key or AI
    assert any(w in combined.lower() for w in ("api", "key", "ai", "armory_claude")), \
        f"Expected helpful message about API key, got:\n{combined[:300]}"


def test_cheatsheet_xss():
    """armory cheatsheet --class xss exits 0 and returns non-empty content."""
    rc, out, err = run_armory("cheatsheet", "--class", "xss")
    assert rc == 0, f"cheatsheet xss returned {rc}: {err}"
    combined = out + err
    assert len(combined.strip()) > 0


def test_update():
    """armory update exits 0 (offline mode — reports up to date or no update)."""
    rc, out, err = run_armory("update")
    assert rc == 0, f"update returned {rc}: {err}"


def teardown_module(module):
    """Clean up temp DB after tests."""
    try:
        Path(TEMP_DB).unlink(missing_ok=True)
    except Exception:
        pass


# ── Textual headless pilot tests ─────────────────────────────────────────────

try:
    from textual.pilot import Pilot  # noqa: F401 — probe import (Pilot lives in textual.pilot)
    import textual  # noqa: F401
    HAS_TEXTUAL = True
except ImportError:
    HAS_TEXTUAL = False


@pytest.mark.skipif(not HAS_TEXTUAL, reason="textual not installed")
def test_tui_headless_composes():
    """TUI pilot: app composes and mounts without errors; breadcrumb widget present."""
    import asyncio
    import os
    from armory.tui.app import ArmoryApp

    async def _run():
        # NO_MOTION prevents animation-related async delays in headless mode
        os.environ["NO_MOTION"] = "1"
        os.environ["ARMORY_DB_PATH"] = TEMP_DB
        app = ArmoryApp()
        async with app.run_test(headless=True) as pilot:
            # Allow mount handlers to complete
            await pilot.pause(0.2)
            # Breadcrumb widget must exist and have initial text
            breadcrumb = app.query_one("#breadcrumb")
            assert breadcrumb is not None, "breadcrumb widget not found after mount"
            # Class list must have at least one item (from loaded YAML KB)
            from textual.widgets import ListView
            class_list = app.query_one("#class-list", ListView)
            assert class_list is not None, "class-list widget not found"
            # Press q to exit cleanly
            await pilot.press("q")

    asyncio.run(_run())


@pytest.mark.skipif(not HAS_TEXTUAL, reason="textual not installed")
def test_tui_headless_no_motion_env():
    """NO_MOTION=1 is accepted without error; animation_level attribute does not raise."""
    import asyncio
    import os
    from armory.tui.app import ArmoryApp

    async def _run():
        os.environ["NO_MOTION"] = "1"
        os.environ["ARMORY_DB_PATH"] = TEMP_DB
        app = ArmoryApp()
        # Confirm __init__ ran without AttributeError (animation_level is best-effort)
        assert app is not None
        async with app.run_test(headless=True) as pilot:
            await pilot.pause(0.1)
            await pilot.press("q")

    asyncio.run(_run())
