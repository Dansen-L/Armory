"""Armory export module — handles all output formats."""

from __future__ import annotations
import csv
import io
import json
from typing import Any


SUPPORTED_FORMATS = ("txt", "json", "csv", "burp", "ffuf", "markdown")
SUPPORTED_SOURCES = ("builtin", "custom", "all")
SUPPORTED_DIFFICULTIES = ("low", "medium", "high", "expert")
DIFFICULTY_ORDER = {d: i for i, d in enumerate(SUPPORTED_DIFFICULTIES)}


def export_payloads(
    payloads: list[dict[str, Any]],
    output_format: str,
    class_slug: str = "all",
) -> str:
    """Export payloads in the requested format and return as string."""
    if output_format not in SUPPORTED_FORMATS:
        raise ValueError(f"Unknown format {output_format!r}. Valid: {SUPPORTED_FORMATS}")

    if output_format in ("txt", "burp", "ffuf"):
        return _export_wordlist(payloads)
    elif output_format == "json":
        return _export_json(payloads, class_slug)
    elif output_format == "csv":
        return _export_csv(payloads)
    elif output_format == "markdown":
        return _export_markdown(payloads, class_slug)
    return ""


def _export_wordlist(payloads: list[dict[str, Any]]) -> str:
    """One raw payload_string per line (txt / burp / ffuf format).

    Embedded CR/LF characters within a payload_string are URL-encoded so that
    the one-payload-per-line invariant is preserved for Burp/ffuf consumption.
    """
    lines = []
    for p in payloads:
        ps = str(p.get("payload_string", "")).strip()
        # URL-encode embedded newlines to maintain one-per-line invariant.
        # Must check \r\n before lone \r or \n to avoid double-encoding.
        ps = ps.replace("\r\n", "%0d%0a").replace("\r", "%0d").replace("\n", "%0a")
        if ps:
            lines.append(ps)
    return "\n".join(lines) + ("\n" if lines else "")


def _export_json(payloads: list[dict[str, Any]], class_slug: str) -> str:
    """JSON array of payload objects; keyed dict when class_slug='all'."""
    serializable = []
    for p in payloads:
        obj = {
            "id": p.get("id", ""),
            "class_slug": p.get("class_slug", ""),
            "class_name": p.get("class_name", p.get("class_slug", "")),
            "group_slug": p.get("group_slug", ""),
            "group_name": p.get("group_name", p.get("group_slug", "")),
            "title": p.get("title", ""),
            "payload_string": p.get("payload_string", ""),
            "how_it_works": p.get("how_it_works", ""),
            "prerequisites": p.get("prerequisites", []),
            "waf_bypass_notes": p.get("waf_bypass_notes", ""),
            "severity_context": p.get("severity_context", ""),
            "cve_refs": p.get("cve_refs", []),
            "tags": p.get("tags", []),
            "difficulty": p.get("difficulty", "medium"),
            "severity_range": p.get("severity_range", {}),
            "source": p.get("source", "builtin"),
            "date_added": p.get("date_added", ""),
            "last_updated": p.get("last_updated", ""),
        }
        serializable.append(obj)

    if class_slug == "all":
        # Group by class
        result: dict[str, list] = {}
        for obj in serializable:
            cs = obj["class_slug"]
            result.setdefault(cs, []).append(obj)
        return json.dumps(result, indent=2)
    else:
        return json.dumps(serializable, indent=2)


def _export_csv(payloads: list[dict[str, Any]]) -> str:
    """CSV with columns: title, payload_string, tags, cve_refs, class_slug, group_slug."""
    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(["title", "payload_string", "tags", "cve_refs", "class_slug", "group_slug"])
    for p in payloads:
        tags = p.get("tags", [])
        if isinstance(tags, list):
            tags_str = ";".join(tags)
        else:
            tags_str = str(tags)
        cve_refs = p.get("cve_refs", [])
        if isinstance(cve_refs, list):
            cve_str = ";".join(cve_refs)
        else:
            cve_str = str(cve_refs)
        writer.writerow([
            p.get("title", ""),
            p.get("payload_string", ""),
            tags_str,
            cve_str,
            p.get("class_slug", ""),
            p.get("group_slug", ""),
        ])
    return output.getvalue()


def _export_markdown(payloads: list[dict[str, Any]], class_slug: str) -> str:
    """Human-readable Markdown cheat sheet organized by attack group."""
    lines = []

    if class_slug == "all":
        # Group by class then group
        by_class: dict[str, dict[str, list]] = {}
        for p in payloads:
            cs = p.get("class_slug", "unknown")
            gs = p.get("group_slug", "unknown")
            by_class.setdefault(cs, {}).setdefault(gs, []).append(p)

        for cs in sorted(by_class):
            class_name = cs
            class_description = ""
            class_owasp = ""
            severity_range: dict = {}
            # Find class-level metadata from the first payload for this slug
            for p in payloads:
                if p.get("class_slug") == cs:
                    class_name = p.get("class_name", cs)
                    class_description = p.get("class_description", "")
                    class_owasp = p.get("class_owasp", "")
                    severity_range = p.get("severity_range", {})
                    break
            lines.append(f"# {class_name}\n")
            _append_class_overview(lines, class_description, class_owasp, severity_range)
            for gs in sorted(by_class[cs]):
                group_name = gs
                for p in by_class[cs][gs]:
                    group_name = p.get("group_name", gs)
                    break
                lines.append(f"## {group_name}\n")
                for p in by_class[cs][gs]:
                    _append_payload_md(lines, p)
    else:
        # Group by attack group
        by_group: dict[str, list] = {}
        for p in payloads:
            gs = p.get("group_slug", "unknown")
            by_group.setdefault(gs, []).append(p)

        if payloads:
            class_name = payloads[0].get("class_name", class_slug)
            class_description = payloads[0].get("class_description", "")
            class_owasp = payloads[0].get("class_owasp", "")
            severity_range = payloads[0].get("severity_range", {})
            lines.append(f"# {class_name}\n")
            _append_class_overview(lines, class_description, class_owasp, severity_range)

        for gs in sorted(by_group):
            group_name = by_group[gs][0].get("group_name", gs)
            lines.append(f"## {group_name}\n")
            for p in by_group[gs]:
                _append_payload_md(lines, p)

    return "\n".join(lines)


def _append_class_overview(
    lines: list[str],
    description: str,
    owasp: str,
    severity_range: dict[str, Any],
) -> None:
    """Emit class-level metadata (description, OWASP mapping, severity range) after the # heading."""
    if description:
        # Strip trailing whitespace/newlines from YAML block scalars
        lines.append(description.strip() + "\n")
    if owasp:
        lines.append(f"**OWASP:** {owasp}\n")
    if severity_range:
        low = severity_range.get("low", "")
        high = severity_range.get("high", "")
        if low or high:
            lines.append("**Severity range:**")
            if low:
                lines.append(f"- Low: {low}")
            if high:
                lines.append(f"- High: {high}")
            lines.append("")


def _append_payload_md(lines: list[str], p: dict[str, Any]) -> None:
    """Append a single payload as Markdown."""
    title = p.get("title", "Untitled")
    payload_string = p.get("payload_string", "")
    how_it_works = p.get("how_it_works", "")
    waf_notes = p.get("waf_bypass_notes", "")
    severity = p.get("severity_context", "")
    cve_refs = p.get("cve_refs", [])
    tags = p.get("tags", [])

    lines.append(f"### {title}\n")
    if payload_string:
        lines.append("```")
        lines.append(payload_string.strip())
        lines.append("```\n")
    if how_it_works:
        lines.append(f"**How it works:** {how_it_works.strip()}\n")
    if waf_notes:
        lines.append(f"**WAF bypass notes:** {waf_notes}\n")
    if severity:
        lines.append(f"**Severity:** {severity}\n")
    if cve_refs:
        lines.append(f"**CVE references:** {', '.join(cve_refs)}\n")
    if tags:
        lines.append(f"**Tags:** {', '.join(tags)}\n")
    lines.append("")
