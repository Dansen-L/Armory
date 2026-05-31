"""Armory CLI entry point — Click commands for non-TUI operations."""

from __future__ import annotations
import json
import os
import sys
import csv
import io
import uuid
from datetime import datetime, timezone

import click
import yaml

from armory import db, loader, search as search_module, export as export_module


def _init_db():
    """Initialize database on first use."""
    db.init_db()


def _fmt_table(rows: list[dict], columns: list[str]) -> str:
    """Format a list of dicts as a text table."""
    if not rows:
        return "(no results)"
    widths = {c: len(c) for c in columns}
    for row in rows:
        for c in columns:
            widths[c] = max(widths[c], len(str(row.get(c, ""))))
    sep = "  "
    header = sep.join(c.ljust(widths[c]) for c in columns)
    divider = sep.join("-" * widths[c] for c in columns)
    lines = [header, divider]
    for row in rows:
        lines.append(sep.join(str(row.get(c, "")).ljust(widths[c]) for c in columns))
    return "\n".join(lines)


@click.group(invoke_without_command=True)
@click.version_option(package_name="armory")
@click.option("--class", "class_slug", default=None, help="Open TUI at this vulnerability class.")
@click.option("--group", "group_slug", default=None, help="Open TUI at this group (requires --class).")
@click.option("--theme", default=None, help="TUI color theme.")
@click.pass_context
def cli(ctx, class_slug, group_slug, theme):
    """Armory — Interactive Pentest Payload Dictionary & Knowledge Base.

    Run without arguments to launch the interactive TUI.
    Use subcommands for non-interactive scripting and quick lookups.
    """
    if ctx.invoked_subcommand is None:
        # Validate: --group requires --class
        if group_slug and not class_slug:
            click.echo("Error: --group requires --class.", err=True)
            sys.exit(1)
        # Launch TUI
        _launch_tui(class_slug=class_slug, group_slug=group_slug, theme=theme)


def _launch_tui(class_slug=None, group_slug=None, theme=None):
    """Launch the Textual TUI application."""
    _init_db()
    try:
        from armory.tui.app import ArmoryApp
        app = ArmoryApp(start_class=class_slug, start_group=group_slug, theme=theme)
        app.run()
    except ImportError as e:
        click.echo(f"TUI requires textual: pip install textual  ({e})", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"TUI error: {e}", err=True)
        sys.exit(1)


@cli.command("search")
@click.argument("query")
@click.option("--limit", "-n", default=20, show_default=True, help="Maximum results to return.")
@click.option("--class", "class_slug", default=None, help="Scope search to one vulnerability class slug.")
@click.option("--tag", default=None, help="Filter results to payloads with this tag.")
@click.option("--format", "output_format", default="table",
              type=click.Choice(["table", "json"]), show_default=True, help="Output format.")
def search_cmd(query, limit, class_slug, tag, output_format):
    """Fuzzy search across all payload content.

    QUERY is the search string (natural language or keyword).
    """
    _init_db()
    all_payloads = loader.get_all_payloads()
    # Also add custom payloads from SQLite
    all_payloads.extend(_get_custom_payloads())

    results = search_module.search_payloads(
        query=query,
        payloads=all_payloads,
        limit=limit,
        class_filter=class_slug,
        tag_filter=tag,
    )

    # Log to search history
    try:
        with db.get_connection() as conn:
            conn.execute(
                "INSERT INTO search_history (query, result_count, searched_at) VALUES (?,?,?)",
                (query, len(results), datetime.now(timezone.utc).isoformat())
            )
    except Exception:
        pass

    if output_format == "json":
        data = [
            {
                "payload_id": r.payload_id,
                "title": r.title,
                "class_slug": r.class_slug,
                "group_slug": r.group_slug,
                "payload_string": r.payload_string,
                "how_it_works": r.how_it_works,
                "tags": r.tags,
                "score": r.score,
            }
            for r in results
        ]
        click.echo(json.dumps(data, indent=2))
    else:
        if not results:
            click.echo(f"No results for '{query}'.")
            return
        rows = [
            {
                "class": r.class_slug,
                "group": r.group_slug,
                "title": r.title,
                "summary": (r.how_it_works.split(".")[0][:60] if r.how_it_works else "")
                           .strip(),
                "tags": ", ".join(r.tags[:3]) if r.tags else "",
                "score": f"{r.score:.0f}",
            }
            for r in results
        ]
        click.echo(_fmt_table(rows, ["class", "group", "title", "summary", "tags", "score"]))


@cli.command("info")
@click.argument("class_slug", required=False)
@click.option("--list-all", is_flag=True, default=False,
              help="List all vulnerability classes in a table.")
@click.option("--cve", default=None, metavar="CVE-YYYY-NNNNN",
              help="List all payloads tagged with this CVE reference.")
def info_cmd(class_slug, list_all, cve):
    """Print information about the knowledge base.

    CLASS_SLUG  Show overview for one vulnerability class.
    --list-all  Show table of all classes.
    --cve ID    List payloads tagged with the given CVE.
    """
    _init_db()
    if not class_slug and not list_all and not cve:
        raise click.UsageError("Provide CLASS_SLUG, --list-all, or --cve CVE-ID.")

    if list_all:
        classes = loader.load_all_classes()
        # Build per-class custom payload counts in one query
        with db.get_connection() as conn:
            custom_counts_rows = conn.execute(
                "SELECT class_slug, COUNT(*) as cnt FROM custom_payloads GROUP BY class_slug"
            ).fetchall()
        custom_counts = {row["class_slug"]: row["cnt"] for row in custom_counts_rows}
        rows = []
        for cls in sorted(classes, key=lambda c: c.get("slug", "")):
            groups = cls.get("groups", [])
            slug = cls.get("slug", "")
            builtin_count = sum(len(g.get("payloads", [])) for g in groups)
            payload_count = builtin_count + custom_counts.get(slug, 0)
            sev = cls.get("severity_range", {})
            sev_low = sev.get("low", "")
            sev_high = sev.get("high", "")
            # Extract CVSS score prefix (e.g. "CVSS 4.0" from "CVSS 4.0-5.9 – ...")
            def _cvss_short(s: str) -> str:
                if not s:
                    return ""
                # Take up to the first dash or em-dash separator
                for sep in [" – ", " - ", "–"]:
                    if sep in s:
                        return s.split(sep)[0].strip()
                return s[:12]
            if sev_low and sev_high:
                severity_str = f"{_cvss_short(sev_low)} – {_cvss_short(sev_high)}"
            elif sev_high:
                severity_str = _cvss_short(sev_high)
            else:
                severity_str = ""
            rows.append({
                "slug": slug,
                "name": cls.get("name", ""),
                "groups": str(len(groups)),
                "payloads": str(payload_count),
                "severity": severity_str,
            })
        # Also include custom classes from DB
        with db.get_connection() as conn:
            custom_classes = conn.execute(
                "SELECT slug, name, description FROM custom_classes ORDER BY slug"
            ).fetchall()
            custom_groups_rows = conn.execute(
                "SELECT class_slug, COUNT(*) as cnt FROM custom_groups GROUP BY class_slug"
            ).fetchall()
        custom_group_counts = {row["class_slug"]: row["cnt"] for row in custom_groups_rows}
        for cc in custom_classes:
            slug = cc["slug"]
            # Skip if already in builtin list
            if any(r["slug"] == slug for r in rows):
                continue
            payload_count = custom_counts.get(slug, 0)
            group_count = custom_group_counts.get(slug, 0)
            rows.append({
                "slug": slug,
                "name": cc["name"] + " [custom]",
                "groups": str(group_count),
                "payloads": str(payload_count),
                "severity": "",
            })
        rows.sort(key=lambda r: r["slug"])
        click.echo(_fmt_table(rows, ["slug", "name", "groups", "payloads", "severity"]))
        return

    if cve:
        all_payloads = loader.get_all_payloads()
        all_payloads.extend(_get_custom_payloads())
        matches = [p for p in all_payloads if cve.upper() in [r.upper() for r in p.get("cve_refs", [])]]
        if not matches:
            click.echo(f"No payloads found with CVE reference: {cve}")
            return
        rows = [
            {"class": p.get("class_slug", ""), "group": p.get("group_slug", ""),
             "title": p.get("title", ""), "payload_id": p.get("id", "")}
            for p in matches
        ]
        click.echo(f"Payloads matching {cve}:")
        click.echo(_fmt_table(rows, ["class", "group", "title", "payload_id"]))
        return

    # Single class info — check YAML built-ins, then custom_classes table
    cls = loader.load_class(class_slug)
    _custom_class_mode = False
    if cls is None:
        with db.get_connection() as conn:
            cc_row = conn.execute(
                "SELECT slug, name, description FROM custom_classes WHERE slug=?", (class_slug,)
            ).fetchone()
        if cc_row is None:
            click.echo(f"Error: Unknown vulnerability class '{class_slug}'. "
                       "Use 'armory info --list-all' to see available classes.", err=True)
            sys.exit(1)
        # Build a synthetic class dict from DB data
        with db.get_connection() as conn:
            cg_rows = conn.execute(
                "SELECT slug, name, difficulty FROM custom_groups WHERE class_slug=?", (class_slug,)
            ).fetchall()
        cls = {
            "slug": cc_row["slug"],
            "name": cc_row["name"],
            "owasp": "",
            "description": cc_row["description"] or "",
            "severity_range": {},
            "groups": [{"slug": r["slug"], "name": r["name"], "difficulty": r["difficulty"], "payloads": []} for r in cg_rows],
        }
        _custom_class_mode = True

    name = cls.get("name", class_slug)
    owasp = cls.get("owasp", "")
    description = cls.get("description", "")
    groups = cls.get("groups", [])
    builtin_payload_count = sum(len(g.get("payloads", [])) for g in groups)
    # Add custom payloads for this class
    with db.get_connection() as conn:
        custom_row = conn.execute(
            "SELECT COUNT(*) as cnt FROM custom_payloads WHERE class_slug=?", (class_slug,)
        ).fetchone()
    custom_count = custom_row["cnt"] if custom_row else 0
    total_payloads = builtin_payload_count + custom_count

    all_cves = set()
    for g in groups:
        for p in g.get("payloads", []):
            all_cves.update(p.get("cve_refs", []))

    click.echo(f"\n{name}")
    click.echo("=" * len(name))
    if owasp:
        click.echo(f"OWASP: {owasp}")
    severity = cls.get("severity_range", {})
    if severity:
        sev_low = severity.get("low", "")
        sev_high = severity.get("high", "")
        if sev_low and sev_high:
            click.echo(f"Severity range: {sev_low} – {sev_high}")
        elif sev_high:
            click.echo(f"Severity: up to {sev_high}")
    click.echo()
    if description:
        click.echo(description.strip())
        click.echo()

    click.echo(f"Attack Groups ({len(groups)}):")
    for g in groups:
        diff = g.get("difficulty", "medium")
        click.echo(f"  [{diff:6s}] {g.get('name', '')} ({len(g.get('payloads', []))} payloads)")

    click.echo()
    payload_note = f"{total_payloads}"
    if custom_count:
        payload_note += f" ({builtin_payload_count} built-in + {custom_count} custom)"
    click.echo(f"Payloads: {payload_note}  |  CVE references: {len(all_cves)}")
    if all_cves:
        click.echo(f"CVEs: {', '.join(sorted(all_cves))}")


@cli.command("export")
@click.option("--class", "class_slug", required=True,
              help="Class slug or 'all' to export all classes.")
@click.option("--group", "group_slug", default=None,
              help="Narrow scope to one group (not valid with --class all).")
@click.option("--format", "output_format", required=True,
              type=click.Choice(["txt", "json", "csv", "burp", "ffuf", "markdown"]),
              help="Output format.")
@click.option("--output", "-o", default=None, help="Output file path (default: stdout).")
@click.option("--source", default="all",
              type=click.Choice(["builtin", "custom", "all"]), show_default=True,
              help="Filter by payload source.")
@click.option("--bookmarks", is_flag=True, default=False,
              help="Export only bookmarked payloads.")
@click.option("--filter-tag", default=None, help="Restrict to payloads with this tag.")
@click.option("--min-difficulty", default=None,
              type=click.Choice(["low", "medium", "high", "expert"]),
              help="Minimum difficulty level.")
def export_cmd(class_slug, group_slug, output_format, output, source, bookmarks,
               filter_tag, min_difficulty):
    """Export payloads for use in other tools."""
    _init_db()
    if class_slug == "all" and group_slug:
        raise click.UsageError("--group cannot be used with --class all.")

    # Collect payloads
    if class_slug == "all":
        all_payloads = loader.get_all_payloads()
        if source != "builtin":
            all_payloads.extend(_get_custom_payloads())
        if source == "custom":
            all_payloads = [p for p in all_payloads if p.get("source") == "custom"]
    else:
        cls = loader.load_class(class_slug)
        if cls is None:
            # Try custom classes
            all_payloads = []
            custom = _get_custom_payloads(class_slug=class_slug)
            if not custom:
                click.echo(f"Error: Unknown class '{class_slug}'.", err=True)
                sys.exit(1)
            all_payloads = custom
        else:
            # Validate group_slug before iteration
            if group_slug:
                known_group_slugs = {g.get("slug", "") for g in cls.get("groups", [])}
                if group_slug not in known_group_slugs:
                    click.echo(
                        f"Error: Unknown group '{group_slug}' for class '{class_slug}'. "
                        f"Available groups: {', '.join(sorted(known_group_slugs))}",
                        err=True,
                    )
                    sys.exit(1)
            all_payloads = []
            for g in cls.get("groups", []):
                gslug = g.get("slug", "")
                if group_slug and gslug != group_slug:
                    continue
                for p in g.get("payloads", []):
                    p_copy = dict(p)
                    p_copy["class_slug"] = cls["slug"]
                    p_copy["class_name"] = cls.get("name", cls["slug"])
                    p_copy["class_description"] = cls.get("description", "")
                    p_copy["class_owasp"] = cls.get("owasp", "")
                    p_copy["group_slug"] = gslug
                    p_copy["group_name"] = g.get("name", gslug)
                    p_copy["difficulty"] = g.get("difficulty", "medium")
                    p_copy["source"] = "builtin"
                    p_copy["severity_range"] = cls.get("severity_range", {})
                    all_payloads.append(p_copy)
            if source != "builtin":
                all_payloads.extend(_get_custom_payloads(class_slug=class_slug, group_slug=group_slug))
            if source == "custom":
                all_payloads = [p for p in all_payloads if p.get("source") == "custom"]

    # Apply filters
    if bookmarks:
        bm_ids = _get_bookmark_ids()
        all_payloads = [p for p in all_payloads if p.get("id") in bm_ids]
    if filter_tag:
        all_payloads = [p for p in all_payloads
                        if filter_tag.lower() in [t.lower() for t in p.get("tags", [])]]
    if min_difficulty:
        diff_order = {"low": 0, "medium": 1, "high": 2, "expert": 3}
        min_level = diff_order.get(min_difficulty, 0)
        all_payloads = [p for p in all_payloads
                        if diff_order.get(p.get("difficulty", "medium"), 1) >= min_level]

    result = export_module.export_payloads(
        payloads=all_payloads,
        output_format=output_format,
        class_slug=class_slug,
    )

    if output:
        with open(output, "w", encoding="utf-8") as f:
            f.write(result)
        click.echo(f"Exported {len(all_payloads)} payloads to {output}")
    else:
        click.echo(result, nl=False)


@cli.command("add")
@click.option("--class", "class_slug", required=True, help="Vulnerability class slug.")
@click.option("--group", "group_slug", required=True, help="Attack group slug.")
@click.option("--payload", default=None, help="Raw payload string (prompted if omitted).")
@click.option("--description", default=None,
              help="How-it-works description (opens $EDITOR if omitted).")
@click.option("--tags", default="", help="Comma-separated tag list.")
@click.option("--title", default=None, help="Short title for the payload.")
@click.option("--waf-bypass-notes", "waf_bypass_notes", default="",
              help="WAF bypass notes (used by tier-5 WAF search).")
@click.option("--severity-context", "severity_context", default="",
              help="CVSS severity context string (e.g. 'CVSS 8.5 – RCE via ...').")
@click.option("--cve-refs", "cve_refs", default="",
              help="Comma-separated CVE IDs to attach (e.g. CVE-2021-44228,CVE-2022-22963).")
@click.option("--create-class", "create_class", is_flag=True, default=False,
              help="Auto-create a new custom class if the class slug is unknown.")
@click.option("--create-group", "create_group", is_flag=True, default=False,
              help="Auto-create a new custom group if the group slug is unknown.")
def add_cmd(class_slug, group_slug, payload, description, tags, title,
            waf_bypass_notes, severity_context, cve_refs,
            create_class, create_group):
    """Add a custom payload to the knowledge base."""
    _init_db()

    # Resolve class: built-in YAML → custom_classes table → auto-create (only with --create-class)
    cls = loader.load_class(class_slug)
    now_iso = datetime.now(timezone.utc).isoformat()
    if cls is None:
        with db.get_connection() as conn:
            row = conn.execute(
                "SELECT slug FROM custom_classes WHERE slug=?", (class_slug,)
            ).fetchone()
        if not row:
            if not create_class:
                click.echo(
                    f"Error: Unknown vulnerability class '{class_slug}'. "
                    "Use 'armory info --list-all' to see valid classes, "
                    "or pass --create-class to create a new custom class.",
                    err=True,
                )
                sys.exit(1)
            # Auto-create a new custom class (only reached when --create-class is set)
            class_name = class_slug.replace("-", " ").replace("_", " ").title()
            with db.get_connection() as conn:
                conn.execute(
                    "INSERT INTO custom_classes (slug, name, description, created_at) "
                    "VALUES (?, ?, ?, ?)",
                    (class_slug, class_name, f"Custom class: {class_name}", now_iso)
                )
            click.echo(f"Created new custom class '{class_slug}' ({class_name}).")

    # Resolve group: built-in YAML → custom_groups table → auto-create (only with --create-group)
    known_groups: set[str] = set()
    if cls:
        known_groups = {g.get("slug", "") for g in cls.get("groups", [])}
    if group_slug not in known_groups:
        with db.get_connection() as conn:
            row = conn.execute(
                "SELECT id FROM custom_groups WHERE class_slug=? AND slug=?",
                (class_slug, group_slug),
            ).fetchone()
        if not row:
            if not create_group:
                click.echo(
                    f"Error: Unknown group '{group_slug}' for class '{class_slug}'. "
                    "Pass --create-group to create a new custom group.",
                    err=True,
                )
                sys.exit(1)
            # Auto-create a new custom group (only reached when --create-group is set)
            group_name = group_slug.replace("-", " ").replace("_", " ").title()
            group_id = str(uuid.uuid4())
            with db.get_connection() as conn:
                conn.execute(
                    "INSERT INTO custom_groups (id, class_slug, slug, name, difficulty, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (group_id, class_slug, group_slug, group_name, "medium", now_iso)
                )
            click.echo(f"Created new custom group '{group_slug}' in class '{class_slug}'.")

    if not payload:
        payload = click.prompt("Payload string")

    if not description:
        description = click.edit("# Enter how-it-works description here\n") or ""
        description = "\n".join(
            line for line in description.splitlines() if not line.startswith("#")
        ).strip()

    if not title:
        title = click.prompt("Payload title (short label)", default=payload[:40])

    payload_id = f"custom-{class_slug}-{uuid.uuid4().hex[:8]}"
    tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    cve_list = [c.strip() for c in cve_refs.split(",") if c.strip()] if cve_refs else []
    now = datetime.now(timezone.utc).isoformat()

    with db.get_connection() as conn:
        conn.execute(
            """INSERT INTO custom_payloads
               (id, class_slug, group_slug, title, payload_string, how_it_works,
                prerequisites_json, waf_bypass_notes, severity_context,
                cve_refs_json, tags_json, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                payload_id, class_slug, group_slug, title, payload,
                description, "[]",
                waf_bypass_notes or "",
                severity_context or "",
                json.dumps(cve_list),
                json.dumps(tag_list), now, now
            )
        )

    click.echo(f"Added custom payload with ID: {payload_id}")


@cli.command("delete")
@click.argument("payload_id", required=False)
@click.option("--group", "group_slug", default=None,
              help="Delete a custom group (requires --class).")
@click.option("--class", "class_slug", default=None,
              help="Class slug for group/class deletion.")
@click.option("--yes", "-y", is_flag=True, default=False, help="Skip confirmation prompt.")
def delete_cmd(payload_id, group_slug, class_slug, yes):
    """Delete a custom payload, group, or class.

    PAYLOAD_ID  Delete a specific custom payload by its ID.
    """
    _init_db()
    if not payload_id and not group_slug and not class_slug:
        raise click.UsageError("Provide PAYLOAD_ID, --group with --class, or --class.")

    with db.get_connection() as conn:
        if payload_id:
            # Check it exists and is custom
            row = conn.execute(
                "SELECT id FROM custom_payloads WHERE id=?", (payload_id,)
            ).fetchone()
            if not row:
                click.echo(f"Error: Payload '{payload_id}' not found in custom payloads. "
                           "Built-in payloads are read-only.", err=True)
                sys.exit(1)
            if not yes:
                click.confirm(f"Delete custom payload '{payload_id}'?", abort=True)
            # Cascade delete
            conn.execute("DELETE FROM bookmarks WHERE payload_id=?", (payload_id,))
            conn.execute("DELETE FROM notes WHERE payload_id=?", (payload_id,))
            conn.execute("DELETE FROM history WHERE payload_id=?", (payload_id,))
            conn.execute("DELETE FROM custom_payloads WHERE id=?", (payload_id,))
            click.echo(f"Deleted payload '{payload_id}'.")

        elif group_slug and class_slug:
            # Check it's a custom group
            row = conn.execute(
                "SELECT id FROM custom_groups WHERE class_slug=? AND slug=?",
                (class_slug, group_slug)
            ).fetchone()
            if not row:
                click.echo(
                    f"Error: Group '{group_slug}' in class '{class_slug}' is not a custom group.",
                    err=True
                )
                sys.exit(1)
            if not yes:
                click.confirm(f"Delete custom group '{group_slug}' and all its payloads?", abort=True)
            ids = [r[0] for r in conn.execute(
                "SELECT id FROM custom_payloads WHERE class_slug=? AND group_slug=?",
                (class_slug, group_slug)
            ).fetchall()]
            for pid in ids:
                conn.execute("DELETE FROM bookmarks WHERE payload_id=?", (pid,))
                conn.execute("DELETE FROM notes WHERE payload_id=?", (pid,))
                conn.execute("DELETE FROM history WHERE payload_id=?", (pid,))
            conn.execute(
                "DELETE FROM custom_payloads WHERE class_slug=? AND group_slug=?",
                (class_slug, group_slug)
            )
            conn.execute(
                "DELETE FROM custom_groups WHERE class_slug=? AND slug=?",
                (class_slug, group_slug)
            )
            click.echo(f"Deleted group '{group_slug}' ({len(ids)} payloads).")

        elif class_slug:
            # Check it's custom
            row = conn.execute(
                "SELECT slug FROM custom_classes WHERE slug=?", (class_slug,)
            ).fetchone()
            if not row:
                click.echo(
                    f"Error: Class '{class_slug}' is not a custom class (built-in classes are read-only).",
                    err=True
                )
                sys.exit(1)
            if not yes:
                click.confirm(f"Delete entire custom class '{class_slug}' and all its data?", abort=True)
            ids = [r[0] for r in conn.execute(
                "SELECT id FROM custom_payloads WHERE class_slug=?", (class_slug,)
            ).fetchall()]
            for pid in ids:
                conn.execute("DELETE FROM bookmarks WHERE payload_id=?", (pid,))
                conn.execute("DELETE FROM notes WHERE payload_id=?", (pid,))
                conn.execute("DELETE FROM history WHERE payload_id=?", (pid,))
            conn.execute("DELETE FROM custom_payloads WHERE class_slug=?", (class_slug,))
            conn.execute("DELETE FROM custom_groups WHERE class_slug=?", (class_slug,))
            conn.execute("DELETE FROM custom_classes WHERE slug=?", (class_slug,))
            click.echo(f"Deleted class '{class_slug}' ({len(ids)} payloads).")


@cli.command("import")
@click.option("--file", "file_path", required=True, type=click.Path(exists=True),
              help="YAML or JSON file to import.")
@click.option("--dry-run", is_flag=True, default=False,
              help="Report what would be imported without writing.")
@click.option("--overwrite", is_flag=True, default=False,
              help="Replace existing custom payloads with same ID.")
@click.option("--class", "class_slug", default=None,
              help="Restrict import to payloads belonging to this class.")
def import_cmd(file_path, dry_run, overwrite, class_slug):
    """Import custom payloads from a YAML or JSON file."""
    _init_db()

    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Detect format
    payloads = []
    try:
        if file_path.endswith(".json") or content.lstrip().startswith("["):
            data = json.loads(content)
            if isinstance(data, list):
                payloads = data
            elif isinstance(data, dict):
                # May be a class YAML-style converted to JSON
                for g in data.get("groups", []):
                    for p in g.get("payloads", []):
                        p_copy = dict(p)
                        p_copy.setdefault("class_slug", data.get("slug", ""))
                        p_copy.setdefault("group_slug", g.get("slug", ""))
                        payloads.append(p_copy)
        else:
            data = yaml.safe_load(content)
            if isinstance(data, dict) and "groups" in data:
                # Class-format YAML
                for g in data.get("groups", []):
                    for p in g.get("payloads", []):
                        p_copy = dict(p)
                        p_copy.setdefault("class_slug", data.get("slug", ""))
                        p_copy.setdefault("group_slug", g.get("slug", ""))
                        payloads.append(p_copy)
            elif isinstance(data, list):
                payloads = data
    except (json.JSONDecodeError, yaml.YAMLError) as e:
        click.echo(f"Error: Malformed file: {e}", err=True)
        sys.exit(1)

    if class_slug:
        payloads = [p for p in payloads if p.get("class_slug") == class_slug]

    # Validate class_slugs — reject entire import if any class is unrecognised
    _init_db()
    seen_class_slugs = {p.get("class_slug", "") for p in payloads if p.get("class_slug")}
    for cs in seen_class_slugs:
        if cs and loader.load_class(cs) is None:
            # Check custom_classes too
            with db.get_connection() as conn:
                row = conn.execute(
                    "SELECT slug FROM custom_classes WHERE slug=?", (cs,)
                ).fetchone()
            if not row:
                click.echo(
                    f"Error: Unrecognised class_slug '{cs}'. "
                    "Use 'armory info --list-all' to see valid classes.",
                    err=True,
                )
                sys.exit(1)

    required_keys = {"title", "payload_string", "class_slug", "group_slug", "how_it_works"}
    valid, skipped_dup, skipped_invalid, would_overwrite = [], [], [], []

    with db.get_connection() as conn:
        for p in payloads:
            missing = required_keys - set(p.keys())
            if missing:
                click.echo(
                    f"Error: Payload missing required fields {sorted(missing)}: {p.get('title', '(no title)')}",
                    err=True,
                )
                skipped_invalid.append(p)
                continue
            # Resolve canonical PID:
            # 1. Explicit id field → use it directly.
            # 2. No id → content-fingerprint lookup (class_slug + group_slug + payload_string)
            #    regardless of --overwrite flag, so both skip AND overwrite paths work
            #    correctly for id-less payloads.
            # 3. Still no match → generate a fresh UUID (truly new payload).
            explicit_id = p.get("id")
            if explicit_id:
                pid = explicit_id
            else:
                content_row = conn.execute(
                    "SELECT id FROM custom_payloads "
                    "WHERE class_slug=? AND group_slug=? AND payload_string=?",
                    (p["class_slug"], p["group_slug"], p["payload_string"])
                ).fetchone()
                pid = content_row["id"] if content_row else f"custom-{p['class_slug']}-{uuid.uuid4().hex[:8]}"
            existing = conn.execute(
                "SELECT id FROM custom_payloads WHERE id=?", (pid,)
            ).fetchone()
            if existing and not overwrite:
                skipped_dup.append(p)
            elif existing and overwrite:
                would_overwrite.append((pid, p))
                valid.append((pid, p))
            else:
                valid.append((pid, p))

    # Exit non-zero if any payload had missing required fields
    if skipped_invalid:
        click.echo(
            f"Aborted: {len(skipped_invalid)} payload(s) had missing required fields (see errors above).",
            err=True,
        )
        sys.exit(1)

    if dry_run:
        click.echo(f"Would import: {len(valid)} payloads")
        click.echo(f"Would skip (duplicates): {len(skipped_dup)}")
        click.echo(f"Would overwrite: {len(would_overwrite)}")
        return

    now = datetime.now(timezone.utc).isoformat()
    with db.get_connection() as conn:
        for pid, p in valid:
            existing = conn.execute(
                "SELECT id FROM custom_payloads WHERE id=?", (pid,)
            ).fetchone()
            if existing:
                conn.execute("DELETE FROM custom_payloads WHERE id=?", (pid,))
            tags = p.get("tags", [])
            if isinstance(tags, str):
                tags = [t.strip() for t in tags.split(",") if t.strip()]
            conn.execute(
                """INSERT INTO custom_payloads
                   (id, class_slug, group_slug, title, payload_string, how_it_works,
                    prerequisites_json, waf_bypass_notes, severity_context,
                    cve_refs_json, tags_json, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    pid, p["class_slug"], p["group_slug"], p["title"],
                    p["payload_string"], p["how_it_works"],
                    json.dumps(p.get("prerequisites", [])),
                    p.get("waf_bypass_notes", ""),
                    p.get("severity_context", ""),
                    json.dumps(p.get("cve_refs", [])),
                    json.dumps(tags),
                    now, now
                )
            )

    # valid includes both new inserts AND overwrites; report them separately
    new_count = len(valid) - len(would_overwrite)
    click.echo(
        f"Imported {new_count} new payloads, "
        f"overwritten {len(would_overwrite)}, "
        f"skipped {len(skipped_dup)}."
    )


@cli.command("cheatsheet")
@click.option("--class", "class_slug", required=True, help="Class slug or 'all'.")
@click.option("--output", "-o", default=None, help="Output file path (default: stdout).")
def cheatsheet_cmd(class_slug, output):
    """Emit a condensed cheat sheet to stdout or file.

    Output format (one line per payload):
      [GROUP NAME] :: payload_title :: one-sentence summary
    """
    _init_db()
    if class_slug == "all":
        classes = loader.load_all_classes()
    else:
        cls = loader.load_class(class_slug)
        if cls is None:
            click.echo(f"Error: Unknown class '{class_slug}'.", err=True)
            sys.exit(1)
        classes = [cls]

    lines = []
    for cls in sorted(classes, key=lambda c: c.get("name", "")):
        for group in cls.get("groups", []):
            group_name = group.get("name", group.get("slug", ""))
            header = f"\n=== {cls.get('name', '')} / {group_name} ==="
            lines.append(header)
            for p in group.get("payloads", []):
                title = p.get("title", "")
                how = p.get("how_it_works", "")
                # One sentence summary: take first sentence
                summary = how.strip().split(".")[0].strip() if how else ""
                lines.append(f"[{group_name}] :: {title} :: {summary}.")

        # Merge custom payloads for this class — grouped by group_slug
        custom = _get_custom_payloads(class_slug=cls.get("slug", ""))
        if custom:
            from collections import defaultdict
            custom_by_group: dict[str, list] = defaultdict(list)
            for cp in custom:
                custom_by_group[cp.get("group_slug", "custom")].append(cp)
            for grp_slug, cps in sorted(custom_by_group.items()):
                lines.append(f"\n=== {cls.get('name', '')} / {grp_slug} [custom] ===")
                for cp in cps:
                    title = cp.get("title", "")
                    how = cp.get("how_it_works", "")
                    summary = how.strip().split(".")[0].strip() if how else ""
                    lines.append(f"[{grp_slug}] :: {title} [custom] :: {summary}.")

    content = "\n".join(lines) + "\n"

    if output:
        with open(output, "w", encoding="utf-8") as f:
            f.write(content)
        click.echo(f"Cheatsheet written to {output}")
    else:
        click.echo(content, nl=False)


@cli.command("update")
def update_cmd():
    """Check for knowledge base updates.

    Detects local YAML bundle changes by comparing current payload counts
    against a stored manifest. Reports Added/Changed/No-changes without
    modifying custom_payloads.
    """
    _init_db()
    import hashlib
    from pathlib import Path

    classes = loader.load_all_classes()
    payloads = loader.get_all_payloads()

    # Build current manifest: {class_slug: payload_count}
    current: dict[str, int] = {}
    for cls in classes:
        slug = cls.get("slug", "")
        count = sum(len(g.get("payloads", [])) for g in cls.get("groups", []))
        current[slug] = count

    # Manifest file stored alongside the DB
    manifest_path = db.get_db_path().parent / "kb_manifest.json"

    if not manifest_path.exists():
        # First run — write baseline
        manifest_path.write_text(json.dumps(current, indent=2))
        click.echo(f"KB manifest initialised: {len(classes)} classes, {len(payloads)} payloads")
        return

    # Load previous manifest and compare
    try:
        previous: dict[str, int] = json.loads(manifest_path.read_text())
    except (json.JSONDecodeError, OSError):
        previous = {}

    added_classes = sorted(set(current) - set(previous))
    removed_classes = sorted(set(previous) - set(current))
    changed: list[str] = []
    added_payloads = 0
    changed_payloads = 0

    for slug in current:
        if slug in previous:
            diff = current[slug] - previous[slug]
            if diff > 0:
                changed.append(f"  {slug}: +{diff} payloads")
                changed_payloads += diff
            elif diff < 0:
                changed.append(f"  {slug}: {diff} payloads (removed)")
        else:
            added_payloads += current[slug]

    if not added_classes and not removed_classes and not changed:
        click.echo("KB is up to date (built-in bundle; live network update planned for v2)")
        click.echo(f"  {len(classes)} classes, {len(payloads)} payloads")
    else:
        if added_classes:
            click.echo(f"Added classes: {', '.join(added_classes)} (+{added_payloads} payloads)")
        if removed_classes:
            click.echo(f"Removed classes: {', '.join(removed_classes)}")
        if changed:
            click.echo(f"Changed ({changed_payloads} payloads added):")
            for line in changed:
                click.echo(line)

    # Update manifest to reflect current state
    manifest_path.write_text(json.dumps(current, indent=2))
    click.echo(f"Manifest updated: {len(classes)} classes, {len(payloads)} payloads")


@cli.command("ai-ask")
@click.argument("question")
@click.option("--class", "class_slug", default=None, help="Scope context to one class.")
@click.option("--group", "group_slug", default=None, help="Scope context to one group.")
def ai_ask_cmd(question, class_slug, group_slug):
    """Direct non-TUI AI query. Requires ARMORY_CLAUDE_API_KEY."""
    api_key = os.environ.get("ARMORY_CLAUDE_API_KEY")
    if not api_key:
        raise click.ClickException(
            "AI features require ARMORY_CLAUDE_API_KEY environment variable. "
            "Set it with: export ARMORY_CLAUDE_API_KEY='your-api-key'"
        )
    _init_db()
    from armory.ai import ai_query
    click.echo("Querying Claude...", err=True)
    response = ai_query(
        question=question,
        class_slug=class_slug,
        group_slug=group_slug,
        api_key=api_key,
    )
    click.echo(response)


# Helper functions

def _get_custom_payloads(class_slug: str | None = None,
                          group_slug: str | None = None) -> list[dict]:
    """Fetch custom payloads from SQLite and return as payload dicts."""
    try:
        with db.get_connection() as conn:
            if class_slug and group_slug:
                rows = conn.execute(
                    "SELECT * FROM custom_payloads WHERE class_slug=? AND group_slug=?",
                    (class_slug, group_slug)
                ).fetchall()
            elif class_slug:
                rows = conn.execute(
                    "SELECT * FROM custom_payloads WHERE class_slug=?", (class_slug,)
                ).fetchall()
            else:
                rows = conn.execute("SELECT * FROM custom_payloads").fetchall()

        result = []
        for row in rows:
            result.append({
                "id": row["id"],
                "class_slug": row["class_slug"],
                "class_name": row["class_slug"],
                "group_slug": row["group_slug"],
                "group_name": row["group_slug"],
                "title": row["title"],
                "payload_string": row["payload_string"],
                "how_it_works": row["how_it_works"],
                "prerequisites": json.loads(row["prerequisites_json"] or "[]"),
                "waf_bypass_notes": row["waf_bypass_notes"] or "",
                "severity_context": row["severity_context"] or "",
                "cve_refs": json.loads(row["cve_refs_json"] or "[]"),
                "tags": json.loads(row["tags_json"] or "[]"),
                "source": "custom",
                "difficulty": "medium",
                "date_added": row["created_at"] or "",
                "last_updated": row["updated_at"] or "",
            })
        return result
    except Exception:
        return []


def _get_bookmark_ids() -> set:
    """Return set of bookmarked payload IDs."""
    try:
        with db.get_connection() as conn:
            rows = conn.execute("SELECT payload_id FROM bookmarks").fetchall()
        return {r["payload_id"] for r in rows}
    except Exception:
        return set()


def main():
    """Entry point that launches TUI if no subcommand given."""
    # Check if any recognized subcommand is in argv
    subcommands = {"search", "info", "export", "add", "delete", "import",
                   "cheatsheet", "update", "ai-ask", "--help", "-h",
                   "--version", "-V"}
    if len(sys.argv) > 1 and sys.argv[1] in subcommands:
        cli()
    elif len(sys.argv) == 1:
        # No args — launch TUI
        _init_db()
        _launch_tui()
    else:
        # May have --class, --group, --theme flags
        cli()


if __name__ == "__main__":
    cli()
