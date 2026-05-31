"""Armory TUI — Three-pane Textual application for interactive payload navigation."""

from __future__ import annotations
import json
import os
from datetime import datetime, timezone
from typing import Any

try:
    from textual.app import App, ComposeResult
    from textual.binding import Binding
    from textual.containers import Horizontal, Vertical, Container
    from textual.widgets import (
        Header, Footer, ListView, ListItem, Label, Static,
        Input, Button, TextArea, RichLog, TabbedContent, TabPane
    )
    from textual.screen import ModalScreen, Screen
    from textual.reactive import reactive
    from textual import events
    from rich.syntax import Syntax as RichSyntax
    HAS_TEXTUAL = True
except ImportError:
    HAS_TEXTUAL = False

from armory import loader, db
from armory.search import search_payloads


CSS = """
ArmoryApp {
    background: $surface;
}

#sidebar {
    width: 25%;
    min-width: 20;
    border-right: solid $accent;
    background: $panel;
}

#main-panel {
    width: 45%;
    border-right: solid $accent;
}

#detail-panel {
    width: 30%;
    background: $panel;
}

#breadcrumb {
    background: $accent;
    color: $text;
    padding: 0 1;
    height: 1;
}

#status-bar {
    background: $primary;
    color: $text;
    padding: 0 1;
    height: 1;
}

.panel-title {
    background: $primary;
    color: $text;
    padding: 0 1;
    text-style: bold;
    height: 1;
}

#sidebar-tabs {
    height: 1fr;
}

#tab-classes {
    height: 1fr;
    padding: 0;
}

#tab-bookmarks {
    height: 1fr;
    padding: 0;
}

#class-list {
    height: 1fr;
}

#bookmarks-list {
    height: 1fr;
}

#recent-list {
    height: 10;
    border-top: solid $accent;
}

#item-list {
    height: 1fr;
}

#tag-filter-bar {
    height: 1;
    background: $surface-darken-1;
    padding: 0 1;
}

#detail-tabs {
    height: 1fr;
}

#tab-detail {
    height: 1fr;
    padding: 0;
}

#tab-waf {
    height: 1fr;
    padding: 0;
}

#detail-content {
    height: 1fr;
    overflow-y: scroll;
    padding: 1;
}

#waf-content {
    height: 1fr;
    overflow-y: scroll;
    padding: 1;
}

.custom-marker {
    color: $warning;
}

/* Difficulty colour tokens — WCAG AA compliant per-theme */
/* Dark theme: use App.-dark-mode descendant selector (textual 0.47+ / 8.x compatible) */
App.-dark-mode .diff-low {
    color: #22c55e;
}
App.-dark-mode .diff-medium {
    color: #eab308;
}
App.-dark-mode .diff-high {
    color: #f97316;
}
App.-dark-mode .diff-expert {
    color: #ef4444;
}

/* Light theme — green-700/amber-700/orange-700/red-700 tokens.
   Note: spec text said amber-600 (#d97706, ~3.19:1 on white) but that fails
   WCAG AA for normal text (requires 4.5:1).  Upgraded to amber-700 (#b45309,
   ~4.74:1 on white) to satisfy the spec's own "WCAG AA" accessibility claim. */
App.-light-mode .diff-low {
    color: #15803d;
}
App.-light-mode .diff-medium {
    color: #b45309;
}
App.-light-mode .diff-high {
    color: #c2410c;
}
App.-light-mode .diff-expert {
    color: #b91c1c;
}

HelpModal {
    align: center middle;
}

#help-box {
    width: 70;
    height: 40;
    border: thick $accent;
    background: $panel;
    padding: 1;
}

SearchOverlay {
    align: center middle;
}

#search-box {
    width: 80%;
    height: 50%;
    border: thick $accent;
    background: $panel;
    padding: 1;
}

#search-input {
    margin-bottom: 0;
}

#search-filters {
    height: 3;
    margin-bottom: 1;
}

#search-filters .filter-label {
    width: auto;
    padding: 0 1;
    content-align: center middle;
}

#filter-class, #filter-diff, #filter-tag {
    width: 1fr;
}

#search-results {
    height: 1fr;
}

NoteModal {
    align: center middle;
}

#note-box {
    width: 70%;
    height: 40%;
    border: thick $accent;
    background: $panel;
    padding: 1;
}

#note-area {
    height: 1fr;
    margin-bottom: 1;
}

TagCloudModal {
    align: center middle;
}

#tag-box {
    width: 60%;
    height: 50%;
    border: thick $accent;
    background: $panel;
    padding: 1;
}

#tag-list {
    height: 1fr;
}

HistoryModal {
    align: center middle;
}

#history-box {
    width: 70%;
    height: 60%;
    border: thick $accent;
    background: $panel;
    padding: 1;
}

#history-list {
    height: 1fr;
}

VariantsModal {
    align: center middle;
}

#variants-box {
    width: 80%;
    height: 70%;
    border: thick $accent;
    background: $panel;
    padding: 1;
}

#variants-list {
    height: 1fr;
}

BookmarksPanel {
    height: 1fr;
}

/* ── Hacker theme — neon green on near-black terminal ──────────────── */
.hacker-theme {
    background: #0d0d0d;
}
.hacker-theme #sidebar {
    background: #0a0a0a;
    border-right: solid #00ff41;
}
.hacker-theme #main-panel {
    border-right: solid #00cc33;
}
.hacker-theme #detail-panel {
    background: #0a0a0a;
}
.hacker-theme .panel-title {
    background: #003300;
    color: #00ff41;
    text-style: bold;
}
.hacker-theme #breadcrumb {
    background: #001a00;
    color: #00ff41;
}
.hacker-theme #status-bar {
    background: #001a00;
    color: #00cc33;
}
.hacker-theme Label {
    color: #00ff41;
}
.hacker-theme Static {
    color: #00dd38;
}

/* CRT scanline overlay — Unicode block character texture (hacker theme only) */
#scanline-overlay {
    display: none;
    height: 1;
    background: #0d0d0d;
    color: #003300;
}
.hacker-theme #scanline-overlay {
    display: block;
    height: 1;
    background: #0d0d0d;
    color: #003300;
}
"""


if HAS_TEXTUAL:

    class HelpModal(ModalScreen):
        """Help modal showing all keybindings."""

        BINDINGS = [Binding("escape", "dismiss", "Close"), Binding("q", "dismiss", "Close")]

        def compose(self) -> ComposeResult:
            with Container(id="help-box"):
                yield Label("Armory — Keyboard Shortcuts", classes="panel-title")
                yield Static(HELP_TEXT)

        def action_dismiss(self):
            self.dismiss()


    class SearchOverlay(ModalScreen):
        """Search overlay for fuzzy payload search with history recall.

        Filter chips (class / difficulty / tag) narrow results after scoring.
        Leave any filter blank to disable that filter.
        Ctrl+A: AI search fallback (routes query to Claude when 0 results or for richer context).
        """

        BINDINGS = [
            Binding("escape", "dismiss", "Close"),
            Binding("ctrl+a", "ai_search", "AI Search"),
        ]

        def __init__(self):
            super().__init__()
            self._results = []
            self._history: list[str] = []
            self._history_idx = -1

        def compose(self) -> ComposeResult:
            with Container(id="search-box"):
                yield Label("Search Payloads (↑/↓ = history)", classes="panel-title")
                yield Input(placeholder="Search...", id="search-input")
                # Filter chips row: class / difficulty / tag
                with Horizontal(id="search-filters"):
                    yield Label("Class:", classes="filter-label")
                    yield Input(placeholder="e.g. xss", id="filter-class")
                    yield Label("Diff:", classes="filter-label")
                    yield Input(placeholder="low/medium/high/expert", id="filter-diff")
                    yield Label("Tag:", classes="filter-label")
                    yield Input(placeholder="e.g. blind", id="filter-tag")
                yield ListView(id="search-results")

        def on_mount(self) -> None:
            self.query_one("#search-input", Input).focus()
            # Load search history
            try:
                with db.get_connection() as conn:
                    rows = conn.execute(
                        "SELECT query FROM search_history ORDER BY searched_at DESC LIMIT 20"
                    ).fetchall()
                self._history = [row["query"] for row in rows]
            except Exception:
                self._history = []

        def on_key(self, event: events.Key) -> None:
            """Handle keys inside the search overlay."""
            inp = self.query_one("#search-input", Input)
            if event.key == "up":
                if self._history:
                    self._history_idx = min(self._history_idx + 1, len(self._history) - 1)
                    inp.value = self._history[self._history_idx]
                    inp.cursor_position = len(inp.value)
                event.prevent_default()
            elif event.key == "down":
                if self._history_idx > 0:
                    self._history_idx -= 1
                    inp.value = self._history[self._history_idx]
                    inp.cursor_position = len(inp.value)
                elif self._history_idx == 0:
                    self._history_idx = -1
                    inp.value = ""
                event.prevent_default()
            elif event.key == "ctrl+a":
                # AI search fallback: intercept ctrl+a before Input "select all" fires
                event.prevent_default()
                self.action_ai_search()

        def _get_filter_values(self) -> tuple[str, str, str]:
            """Return (class_filter, diff_filter, tag_filter) from filter inputs."""
            try:
                cls_f = self.query_one("#filter-class", Input).value.strip().lower()
                diff_f = self.query_one("#filter-diff", Input).value.strip().lower()
                tag_f = self.query_one("#filter-tag", Input).value.strip().lower()
            except Exception:
                cls_f = diff_f = tag_f = ""
            return cls_f, diff_f, tag_f

        def on_input_changed(self, event: Input.Changed) -> None:
            # Determine query from the main search input (other inputs are filters)
            try:
                query = self.query_one("#search-input", Input).value
            except Exception:
                return
            if len(query) < 2:
                self.query_one("#search-results", ListView).clear()
                return
            all_payloads = loader.get_all_payloads()
            # Include custom payloads from SQLite so they appear in overlay search
            try:
                with db.get_connection() as _conn:
                    _rows = _conn.execute("SELECT * FROM custom_payloads").fetchall()
                for _row in _rows:
                    all_payloads.append({
                        "id": _row["id"],
                        "class_slug": _row["class_slug"],
                        "class_name": _row["class_slug"],
                        "group_slug": _row["group_slug"],
                        "group_name": _row["group_slug"],
                        "title": _row["title"],
                        "payload_string": _row["payload_string"],
                        "how_it_works": _row["how_it_works"] or "",
                        "waf_bypass_notes": _row["waf_bypass_notes"] or "",
                        "tags": json.loads(_row["tags_json"] or "[]"),
                        "source": "custom",
                    })
            except Exception:
                pass
            results = search_payloads(query, all_payloads, limit=50)
            # Apply filter chips (post-scoring; no score inflation)
            cls_f, diff_f, tag_f = self._get_filter_values()
            if cls_f:
                results = [r for r in results if cls_f in r.class_slug.lower()]
            if diff_f:
                results = [r for r in results
                           if r.score > 0  # keep scored results
                           and diff_f in [p.get("difficulty", "").lower()
                                          for p in all_payloads if p.get("id") == r.payload_id]]
            if tag_f:
                results = [r for r in results
                           if any(tag_f in t.lower() for t in r.tags)]
            results = results[:15]
            lv = self.query_one("#search-results", ListView)
            lv.clear()
            for r in results:
                # No id= on ListItems — IDs must be unique across the entire DOM;
                # re-using them after clear() causes DuplicateIds errors in textual 8.x.
                # Items are accessed by positional index in on_list_view_selected.
                lv.append(ListItem(Label(f"[{r.class_slug}] {r.title}")))
            self._results = results
            # Zero-result hint: nudge operator toward AI search when available
            if not results:
                from armory.ai import is_ai_available
                if is_ai_available():
                    self.app.notify(
                        "No results — press Ctrl+A for AI-assisted search",
                        severity="information",
                        timeout=4,
                    )
                else:
                    self.app.notify("No results found.", severity="information", timeout=3)

        def on_input_submitted(self, event: Input.Submitted) -> None:
            """Save to search_history when user presses Enter in the main search input."""
            # Only save history for the main search input, not for filter chips
            if event.input.id == "search-input":
                query = event.value.strip()
                if query:
                    self._save_search_query(query, len(self._results))

        def on_list_view_selected(self, event: ListView.Selected) -> None:
            if hasattr(self, "_results"):
                idx = list(self.query_one("#search-results", ListView).children).index(event.item)
                if idx < len(self._results):
                    result = self._results[idx]
                    # Save query to search_history
                    query = self.query_one("#search-input", Input).value
                    self._save_search_query(query, len(self._results))
                    self.dismiss(result)

        def _save_search_query(self, query: str, result_count: int) -> None:
            """Persist the search query to search_history table."""
            if not query:
                return
            try:
                with db.get_connection() as conn:
                    conn.execute(
                        "INSERT INTO search_history (query, result_count, searched_at) VALUES (?,?,?)",
                        (query, result_count, datetime.now(timezone.utc).isoformat())
                    )
            except Exception:
                pass

        async def action_ai_search(self) -> None:
            """Ctrl+A: route current query to Claude AI for a richer semantic search response.

            Runs the blocking ai_query() call inside a thread executor so that
            the Textual event loop is never blocked.  Pattern mirrors
            action_explain_payload / action_waf_bypass_advisor.
            """
            from armory.ai import is_ai_available
            try:
                query = self.query_one("#search-input", Input).value.strip()
            except Exception:
                query = ""
            if not query:
                self.notify("Enter a search query first.", severity="warning")
                return
            if not is_ai_available():
                self.notify("Set ARMORY_CLAUDE_API_KEY to use AI-assisted search.", severity="warning")
                return
            # Show progress indicator on the main thread before launching executor
            try:
                lv = self.query_one("#search-results", ListView)
                lv.clear()
                lv.append(ListItem(Label("[yellow]AI search in progress…[/yellow]")))
            except Exception:
                pass
            # Run the blocking ai_query in a thread so the event loop stays responsive
            try:
                from armory.ai import ai_query
                import asyncio
                loop = asyncio.get_event_loop()
                answer = await loop.run_in_executor(None, lambda: ai_query(question=query))
                # Back on the main thread — safe to mutate widgets directly
                lv = self.query_one("#search-results", ListView)
                lv.clear()
                # Display the AI answer as a single result item
                lv.append(ListItem(Label(f"[AI] {answer[:120]}")))
            except Exception as e:
                self.notify(f"AI search error: {e}", severity="error")

        def action_dismiss(self):
            # Save current query to history when overlay is closed via Esc
            try:
                query = self.query_one("#search-input", Input).value.strip()
                if query:
                    self._save_search_query(query, len(self._results))
            except Exception:
                pass
            self.dismiss(None)


    class BookmarkModal(ModalScreen):
        """Simple modal to confirm bookmark."""

        BINDINGS = [Binding("escape", "dismiss", "Cancel")]

        def __init__(self, payload_id: str, title: str):
            super().__init__()
            self._payload_id = payload_id
            self._title = title

        def compose(self) -> ComposeResult:
            with Container(id="help-box"):
                yield Label("Bookmark", classes="panel-title")
                yield Static(f"Bookmark '{self._title}'?")
                with Horizontal():
                    yield Button("Yes", id="yes", variant="primary")
                    yield Button("No", id="no")

        def on_button_pressed(self, event: Button.Pressed) -> None:
            self.dismiss(event.button.id == "yes")

        def action_dismiss(self):
            self.dismiss(False)


    class NoteModal(ModalScreen):
        """Modal for editing personal notes on a payload."""

        BINDINGS = [
            Binding("escape", "dismiss_note", "Cancel"),
            Binding("ctrl+s", "save_note", "Save"),
        ]

        def __init__(self, payload_id: str, existing_note: str = ""):
            super().__init__()
            self._payload_id = payload_id
            self._existing_note = existing_note

        def compose(self) -> ComposeResult:
            with Container(id="note-box"):
                yield Label(f"Note — {self._payload_id}  (Ctrl+S to save, Esc to cancel)",
                            classes="panel-title")
                yield TextArea(self._existing_note, id="note-area")
                with Horizontal():
                    yield Button("Save (Ctrl+S)", id="save-btn", variant="primary")
                    yield Button("Cancel", id="cancel-btn")

        def on_mount(self) -> None:
            self.query_one("#note-area", TextArea).focus()

        def on_button_pressed(self, event: Button.Pressed) -> None:
            if event.button.id == "save-btn":
                self.action_save_note()
            else:
                self.action_dismiss_note()

        def action_save_note(self) -> None:
            text = self.query_one("#note-area", TextArea).text
            self.dismiss(text)

        def action_dismiss_note(self) -> None:
            self.dismiss(None)


    class TagCloudModal(ModalScreen):
        """Tag cloud modal showing most-used tags in current scope.

        Keys:
          Enter / click — toggle tag selection
          O             — cycle between OR and AND logic
          Esc           — apply filter and close
        """

        BINDINGS = [
            Binding("escape", "dismiss", "Apply & Close"),
            Binding("o", "toggle_mode", "Toggle OR/AND"),
        ]

        def __init__(self, tags: list[tuple[str, int]], active_tags: set[str],
                     tag_mode: str = "OR"):
            super().__init__()
            self._tags = tags
            self._active_tags = set(active_tags)
            self._mode = tag_mode  # "OR" | "AND"

        def compose(self) -> ComposeResult:
            with Container(id="tag-box"):
                yield Label(
                    "Tag Filter  (Enter=toggle  O=OR/AND  Esc=apply)",
                    classes="panel-title"
                )
                yield Static(f"Mode: {self._mode}", id="tag-mode-label")
                yield ListView(id="tag-list")

        def on_mount(self) -> None:
            self._refresh_list()

        def _refresh_list(self) -> None:
            lv = self.query_one("#tag-list", ListView)
            lv.clear()
            # No id= on ListItems — IDs must be unique across the DOM in textual 8.x.
            # Tag identity is tracked by positional index into self._tags[:40].
            for tag, count in self._tags[:40]:
                marker = "✓ " if tag in self._active_tags else "  "
                lv.append(ListItem(Label(f"{marker}[bold]{tag}[/bold] ({count})")))
            try:
                self.query_one("#tag-mode-label", Static).update(f"Mode: {self._mode}")
            except Exception:
                pass

        def on_list_view_selected(self, event: ListView.Selected) -> None:
            # Toggle the selected tag — look up by positional index
            try:
                idx = list(self.query_one("#tag-list", ListView).children).index(event.item)
            except ValueError:
                return
            if idx < len(self._tags):
                tag_key = self._tags[idx][0]
                if tag_key in self._active_tags:
                    self._active_tags.discard(tag_key)
                else:
                    self._active_tags.add(tag_key)
                self._refresh_list()

        def action_toggle_mode(self) -> None:
            """Cycle between OR and AND logic."""
            self._mode = "AND" if self._mode == "OR" else "OR"
            self._refresh_list()

        def action_dismiss(self) -> None:
            # Return (active_tags, mode) tuple so caller can update both
            self.dismiss((self._active_tags, self._mode))


    class HistoryModal(ModalScreen):
        """Browsable history modal with jump-to support (G key)."""

        BINDINGS = [Binding("escape", "dismiss", "Close")]

        def __init__(self, history_rows: list):
            super().__init__()
            self._rows = history_rows

        def compose(self) -> ComposeResult:
            with Container(id="history-box"):
                yield Label("View History  (Enter to jump to payload)", classes="panel-title")
                yield ListView(id="history-list")

        def on_mount(self) -> None:
            lv = self.query_one("#history-list", ListView)
            for row in self._rows:
                # No id= on ListItems — textual 8.x requires unique IDs across the DOM;
                # the same payload can appear multiple times in history so IDs collide.
                # Access is by positional index in on_list_view_selected.
                lv.append(ListItem(
                    Label(
                        f"[cyan]{row['class_slug']}[/cyan]/"
                        f"{row['group_slug']} — "
                        f"[dim]{row['payload_id']}[/dim] "
                        f"({row['viewed_at'][:10]})"
                    )
                ))

        def on_list_view_selected(self, event: ListView.Selected) -> None:
            # Identify the row by index and return its data
            children = list(self.query_one("#history-list", ListView).children)
            idx = children.index(event.item)
            if 0 <= idx < len(self._rows):
                self.dismiss(self._rows[idx])

        def action_dismiss(self) -> None:
            self.dismiss(None)


    class ContextInputModal(ModalScreen):
        """Modal for collecting operator context before AI variant generation."""

        BINDINGS = [
            Binding("escape", "dismiss_cancel", "Cancel"),
            Binding("ctrl+s", "submit_context", "Submit"),
        ]

        def compose(self) -> ComposeResult:
            with Container(id="note-box"):
                yield Label(
                    "Describe your target context (WAF, framework, encoding restrictions)  "
                    "  Ctrl+S to submit • Esc to cancel",
                    classes="panel-title",
                )
                yield Input(
                    placeholder="e.g. Cloudflare WAF, Angular frontend, output inside href attribute",
                    id="context-input",
                )
                with Horizontal():
                    yield Button("Generate Variants (Ctrl+S)", id="submit-btn", variant="primary")
                    yield Button("Cancel", id="cancel-btn")

        def on_mount(self) -> None:
            self.query_one("#context-input", Input).focus()

        def on_button_pressed(self, event: Button.Pressed) -> None:
            if event.button.id == "submit-btn":
                self.action_submit_context()
            else:
                self.action_dismiss_cancel()

        def action_submit_context(self) -> None:
            ctx = self.query_one("#context-input", Input).value.strip()
            self.dismiss(ctx)

        def action_dismiss_cancel(self) -> None:
            self.dismiss(None)


    class VariantsModal(ModalScreen):
        """Modal displaying AI-generated payload variants with S-key save."""

        BINDINGS = [
            Binding("escape", "dismiss", "Close"),
            Binding("s", "save_variant", "Save selected"),
        ]

        def __init__(self, variants: list[dict], base_payload: dict):
            super().__init__()
            self._variants = variants
            self._base_payload = base_payload
            self._selected_idx = -1

        def compose(self) -> ComposeResult:
            with Container(id="variants-box"):
                yield Label("AI Variants  (Enter to preview, S to save as custom)", classes="panel-title")
                yield ListView(id="variants-list")
                yield RichLog(id="variant-detail", highlight=True, markup=True)

        def on_mount(self) -> None:
            lv = self.query_one("#variants-list", ListView)
            for i, v in enumerate(self._variants):
                # No id= kwarg — avoids DuplicateIds errors on rapid modal re-push
                # (every other dynamic ListView in this file uses the same pattern).
                # on_list_view_selected resolves the variant by positional index.
                lv.append(ListItem(
                    Label(f"[{i+1}] {v.get('title', 'Variant')}")
                ))

        def on_list_view_selected(self, event: ListView.Selected) -> None:
            # Positional index: same defensive pattern used by class/group/payload lists
            try:
                lv = self.query_one("#variants-list", ListView)
                idx = list(lv.children).index(event.item)
                self._selected_idx = idx
                v = self._variants[idx]
                detail = self.query_one("#variant-detail", RichLog)
                detail.clear()
                detail.write(f"[bold cyan]{v.get('title', '')}[/bold cyan]")
                detail.write("")
                detail.write(f"[green]{v.get('payload_string', '')}[/green]")
                detail.write("")
                detail.write(v.get("how_it_works", ""))
                detail.write("")
                detail.write("[dim]Press S to save this variant as a custom payload[/dim]")
            except (ValueError, IndexError):
                pass

        def action_save_variant(self) -> None:
            """Save the selected variant as a custom payload."""
            if self._selected_idx < 0 or self._selected_idx >= len(self._variants):
                return
            v = self._variants[self._selected_idx]
            try:
                from armory.db import get_connection
                now = datetime.now(timezone.utc).isoformat()
                import uuid as _uuid
                pid = f"custom-variant-{_uuid.uuid4().hex[:12]}"
                with get_connection() as conn:
                    conn.execute(
                        """INSERT INTO custom_payloads
                           (id, class_slug, group_slug, title, payload_string, how_it_works,
                            created_at, updated_at)
                           VALUES (?,?,?,?,?,?,?,?)""",
                        (
                            pid,
                            self._base_payload.get("class_slug", ""),
                            self._base_payload.get("group_slug", ""),
                            v.get("title", ""),
                            v.get("payload_string", ""),
                            v.get("how_it_works", ""),
                            now,
                            now,
                        )
                    )
                detail = self.query_one("#variant-detail", RichLog)
                detail.write(f"\n[bold green]✓ Saved as custom payload: {pid}[/bold green]")
            except Exception as e:
                self.app.notify(f"Save error: {e}", severity="error")

        def action_dismiss(self) -> None:
            self.dismiss(None)


    # ── Syntax lexer helper ────────────────────────────────────────────────────

    _SLUG_LEXER_MAP: dict[str, str] = {
        "xss": "html",
        "sqli": "sql",
        "cmdi": "bash",
        "ssti": "html",
        "xxe": "xml",
        "path-traversal": "bash",
        "file-upload": "text",
        "ssrf": "http",
        "cors": "http",
        "csrf": "html",
        "deserialization": "python",
        "prototype-pollution": "javascript",
        "graphql": "graphql",
        "idor": "http",
        "auth-bypass": "http",
        "mass-assignment": "json",
        "open-redirect": "http",
        "host-header": "http",
        "http-smuggling": "http",
        "business-logic": "text",
    }

    def _slug_to_lexer(class_slug: str) -> str:
        """Return a Pygments lexer name appropriate for the given class slug."""
        return _SLUG_LEXER_MAP.get(class_slug.lower(), "text")


    # ── In-TUI custom payload add modal ───────────────────────────────────────

    class AddPayloadModal(ModalScreen):
        """Modal for adding a new custom payload from the TUI group view.

        Accepts an optional list of group slugs for the current class so the
        operator can pick the target group even when _current_group is None
        (i.e. they pressed A from the class-level groups list without having
        previously drilled into a specific group).
        """

        BINDINGS = [
            Binding("escape", "dismiss_cancel", "Cancel"),
            Binding("ctrl+s", "submit_payload", "Save"),
        ]

        def __init__(self, class_slug: str, group_slug: str,
                     available_groups: list[str] | None = None):
            super().__init__()
            self._class_slug = class_slug
            self._group_slug = group_slug          # pre-fill; "" = unknown
            self._available_groups = available_groups or []

        def compose(self) -> ComposeResult:
            grp_hint = (
                f"Groups: {', '.join(self._available_groups)}" if self._available_groups
                else "e.g. reflected"
            )
            with Container(id="note-box"):
                yield Label(
                    f"Add Custom Payload — class: {self._class_slug}  "
                    f"(Ctrl+S save · Esc cancel)",
                    classes="panel-title",
                )
                yield Label("Group slug:")
                yield Input(
                    value=self._group_slug,
                    placeholder=grp_hint,
                    id="add-group",
                )
                yield Label("Title:")
                yield Input(placeholder="Short descriptive title", id="add-title")
                yield Label("Payload string:")
                yield Input(placeholder="The raw attack string", id="add-payload")
                yield Label("Description / how it works:")
                yield Input(placeholder="One sentence explanation", id="add-desc")
                yield Label("Tags (comma-separated):")
                yield Input(placeholder="e.g. reflected,dom,no-csp", id="add-tags")
                with Horizontal():
                    yield Button("Save (Ctrl+S)", id="save-btn", variant="primary")
                    yield Button("Cancel", id="cancel-btn")

        def on_mount(self) -> None:
            # Focus group field if empty; otherwise jump straight to title
            grp_inp = self.query_one("#add-group", Input)
            if not grp_inp.value.strip():
                grp_inp.focus()
            else:
                self.query_one("#add-title", Input).focus()

        def on_button_pressed(self, event: Button.Pressed) -> None:
            if event.button.id == "save-btn":
                self.action_submit_payload()
            else:
                self.action_dismiss_cancel()

        def action_submit_payload(self) -> None:
            group = self.query_one("#add-group", Input).value.strip()
            title = self.query_one("#add-title", Input).value.strip()
            payload_str = self.query_one("#add-payload", Input).value.strip()
            desc = self.query_one("#add-desc", Input).value.strip()
            tags_raw = self.query_one("#add-tags", Input).value.strip()
            if not title or not payload_str:
                self.app.notify("Title and payload string are required.", severity="warning")
                return
            if not group:
                group = self._available_groups[0] if self._available_groups else "custom"
            tags = [t.strip() for t in tags_raw.split(",") if t.strip()] if tags_raw else []
            self.dismiss({
                "title": title,
                "payload_string": payload_str,
                "description": desc,
                "tags": tags,
                "group_slug": group,
            })

        def action_dismiss_cancel(self) -> None:
            self.dismiss(None)


    # ── In-TUI custom payload delete confirm modal ────────────────────────────

    class ConfirmDeleteModal(ModalScreen):
        """Simple confirmation modal for deleting a custom payload."""

        BINDINGS = [Binding("escape", "dismiss_no", "Cancel")]

        def __init__(self, payload_id: str, title: str):
            super().__init__()
            self._payload_id = payload_id
            self._title = title

        def compose(self) -> ComposeResult:
            with Container(id="help-box"):
                yield Label("Delete Custom Payload", classes="panel-title")
                yield Static(f"Delete '[bold]{self._title}[/bold]'?  This cannot be undone.")
                with Horizontal():
                    yield Button("Delete", id="yes-btn", variant="error")
                    yield Button("Cancel", id="cancel-btn")

        def on_button_pressed(self, event: Button.Pressed) -> None:
            self.dismiss(event.button.id == "yes-btn")

        def action_dismiss_no(self):
            self.dismiss(False)


    class ArmoryApp(App):
        """Main Armory TUI application."""

        CSS = CSS

        BINDINGS = [
            Binding("q", "quit", "Quit"),
            Binding("?", "show_help", "Help"),
            Binding("/", "search", "Search"),
            Binding("b", "bookmark", "Bookmark"),
            Binding("y", "copy_payload", "Copy"),
            Binding("ctrl+y", "copy_full_detail", "Copy Full"),
            Binding("j", "cursor_down", "Down", show=False),
            Binding("k", "cursor_up", "Up", show=False),
            Binding("escape", "go_back", "Back"),
            Binding("h", "show_history", "History", show=False),
            Binding("g", "jump_from_history", "Jump", show=False),
            Binding("r", "show_recent", "Recent", show=False),
            Binding("n", "edit_note", "Note"),
            Binding("e", "explain_payload", "AI Explain"),
            Binding("v", "generate_variants", "AI Variants"),
            Binding("c", "chain_suggest", "AI Chain"),
            Binding("w", "waf_bypass_advisor", "WAF Advisor"),
            Binding("t", "show_tag_cloud", "Tags"),
            Binding("a", "add_custom_payload", "Add [custom]", show=False),
            Binding("x", "delete_custom_payload", "Delete [custom]", show=False),
        ]

        # Navigation state
        _current_view: str = "classes"  # classes | groups | payloads | detail
        _current_class: dict | None = None
        _current_group: dict | None = None
        _current_payload: dict | None = None
        _kb_classes: list = []
        _payloads: list = []
        _active_tags: set = set()
        _tag_mode: str = "OR"  # "OR" | "AND" — controls multi-tag filter logic
        # Parallel data lists for positional lookup in on_list_view_selected
        # (IDs are removed from dynamic ListItems in textual 8.x to avoid DuplicateIds)
        _sorted_class_list: list = []
        _current_groups_list: list = []
        _recent_rows: list = []

        def __init__(self, start_class: str | None = None,
                     start_group: str | None = None,
                     theme: str | None = None):
            super().__init__()
            self._start_class = start_class
            self._start_group = start_group
            # Resolve effective theme (CLI flag takes precedence over env var)
            effective_theme = theme or os.environ.get("ARMORY_THEME")
            self._hacker_theme = (effective_theme == "hacker")
            if effective_theme and effective_theme != "hacker":
                # Textual's App.theme property requires internal token names
                # ("textual-dark", "textual-light"), not user-facing labels.
                _THEME_MAP = {"dark": "textual-dark", "light": "textual-light"}
                textual_token = _THEME_MAP.get(effective_theme, effective_theme)
                try:
                    self.theme = textual_token
                except Exception:
                    pass
            # Disable animations when NO_MOTION=1 (accessibility / CI headless mode)
            if os.environ.get("NO_MOTION") == "1":
                try:
                    self.animation_level = "none"
                except AttributeError:
                    pass  # Older Textual version without animation_level API

        def compose(self) -> ComposeResult:
            yield Header(show_clock=True)
            yield Static("Classes", id="breadcrumb")
            # CRT-scanline texture: Unicode block character row, visible in hacker theme only
            yield Static("░▒░▒░▒░▒░▒░▒░▒░▒░▒░▒░▒░▒░▒░▒░▒░▒░▒░▒░▒░▒░▒░▒░▒░▒░▒░▒░▒░▒░▒░▒░▒░▒",
                         id="scanline-overlay")
            with Horizontal():
                with Vertical(id="sidebar"):
                    with TabbedContent(id="sidebar-tabs"):
                        with TabPane("📚 Classes", id="tab-classes"):
                            yield ListView(id="class-list")
                            yield Label("🕐 Recent", classes="panel-title")
                            yield ListView(id="recent-list")
                        with TabPane("🔖 Bookmarks", id="tab-bookmarks"):
                            yield ListView(id="bookmarks-list")
                with Vertical(id="main-panel"):
                    yield Label("Attack Groups / Payloads", id="main-title", classes="panel-title")
                    yield Static("", id="tag-filter-bar")
                    yield ListView(id="item-list")
                with Vertical(id="detail-panel"):
                    with TabbedContent(id="detail-tabs"):
                        with TabPane("📄 Detail", id="tab-detail"):
                            yield RichLog(id="detail-content", highlight=True, markup=True)
                        with TabPane("🛡 WAF Bypass", id="tab-waf"):
                            yield RichLog(id="waf-content", highlight=True, markup=True)
            yield Static(
                "/ search  B bookmark  Y copy  N note  E AI  W WAF  T tags  ? help  q quit",
                id="status-bar"
            )
            yield Footer()

        def on_mount(self) -> None:
            db.init_db()
            # Apply hacker theme CSS class if requested
            if self._hacker_theme:
                self.add_class("hacker-theme")
            self._kb_classes = loader.load_all_classes()
            self._load_class_list()
            self._refresh_recent_list()
            self._refresh_bookmarks_list()
            # Apply start_class if specified
            if self._start_class:
                cls = loader.load_class(self._start_class)
                if cls:
                    self._current_class = cls
                    self._current_view = "groups"
                    self._load_group_list(cls)
                    if self._start_group:
                        for g in cls.get("groups", []):
                            if g.get("slug") == self._start_group:
                                self._current_group = g
                                self._current_view = "payloads"
                                self._load_payload_list(g)
                                break

        def _update_status_bar(self, payload_count: int | None = None, context: str = "") -> None:
            """Refresh status bar with payload count for current scope and AI availability."""
            try:
                from armory.ai import is_ai_available
                ai_status = "AI: ready" if is_ai_available() else "AI: unavailable"
            except Exception:
                ai_status = "AI: unavailable"
            count_str = f"{payload_count} payloads | " if payload_count is not None else ""
            ctx_str = f"{context} | " if context else ""
            hints = "/ search  B bookmark  Y copy  N note  E AI  T tags  ? help  q quit"
            try:
                self.query_one("#status-bar", Static).update(
                    f"{count_str}{ctx_str}{ai_status} | {hints}"
                )
            except Exception:
                pass

        def _load_class_list(self) -> None:
            """Populate sidebar with vulnerability classes."""
            lv = self.query_one("#class-list", ListView)
            lv.clear()
            total_payloads = 0
            # Keep sorted class list for positional lookup in on_list_view_selected
            self._sorted_class_list = sorted(self._kb_classes, key=lambda c: c.get("name", ""))
            for cls in self._sorted_class_list:
                count = sum(len(g.get("payloads", [])) for g in cls.get("groups", []))
                total_payloads += count
                slug = cls.get("slug", "")
                # No id= — IDs must be unique across DOM in textual 8.x;
                # class is identified by positional index into _sorted_class_list.
                lv.append(ListItem(Label(f"{cls.get('name', slug)} ({count})")))
            self._update_status_bar(total_payloads, "all classes")

        def _refresh_recent_list(self) -> None:
            """Refresh the sidebar Recent section from history table."""
            try:
                with db.get_connection() as conn:
                    rows = conn.execute(
                        "SELECT payload_id, class_slug, group_slug FROM history "
                        "ORDER BY viewed_at DESC LIMIT 10"
                    ).fetchall()
                # Store rows for positional lookup in on_list_view_selected
                self._recent_rows = list(rows)
                lv = self.query_one("#recent-list", ListView)
                lv.clear()
                for row in rows:
                    label = f"[cyan]{row['class_slug']}[/cyan] {row['payload_id']}"
                    # No id= — same payload can appear multiple times in history
                    lv.append(ListItem(Label(label)))
            except Exception:
                self._recent_rows = []

        def _refresh_bookmarks_list(self) -> None:
            """Refresh the sidebar Bookmarks tab from the bookmarks table."""
            try:
                with db.get_connection() as conn:
                    rows = conn.execute(
                        "SELECT payload_id, class_slug, group_slug, label, created_at "
                        "FROM bookmarks ORDER BY created_at DESC"
                    ).fetchall()
                lv = self.query_one("#bookmarks-list", ListView)
                lv.clear()
                # Parallel list for positional lookup in on_list_view_selected
                # (mirrors _recent_rows) so selecting a bookmark opens its payload.
                self._bookmark_rows = list(rows)
                if not rows:
                    lv.append(ListItem(
                        Label("[dim]No bookmarks yet — press B on a payload[/dim]"),
                        id="bm-empty"
                    ))
                else:
                    for row in rows:
                        label_text = f"[cyan]{row['class_slug']}[/cyan] {row['label'] or row['payload_id']}"
                        # No id= — bookmark payload_id would collide on re-render
                        lv.append(ListItem(Label(label_text)))
            except Exception:
                pass

        def _load_group_list(self, cls: dict) -> None:
            """Populate main panel with attack groups."""
            self.query_one("#main-title", Label).update(f"Groups — {cls.get('name', '')}")
            self.query_one("#breadcrumb", Static).update(
                f"Classes → {cls.get('name', '')}"
            )
            lv = self.query_one("#item-list", ListView)
            lv.clear()
            # Store groups list for positional lookup in on_list_view_selected
            self._current_groups_list = cls.get("groups", [])
            for g in self._current_groups_list:
                count = len(g.get("payloads", []))
                diff = g.get("difficulty", "medium")
                diff_class = f"diff-{diff}"
                # No id= — IDs must be unique across DOM; group identified by index.
                # Use classes= so that the CSS .diff-{level} color rules apply.
                lv.append(ListItem(
                    Label(
                        f"[{diff:6}] {g.get('name', '')} ({count} payloads)",
                        classes=diff_class
                    )
                ))
            self._current_class = cls
            self._current_view = "groups"
            total_in_class = sum(len(g.get("payloads", [])) for g in cls.get("groups", []))
            self._update_status_bar(total_in_class, cls.get("name", ""))

        def _load_payload_list(self, group: dict) -> None:
            """Populate main panel with payloads in a group."""
            cls_name = self._current_class.get("name", "") if self._current_class else ""
            self.query_one("#main-title", Label).update(f"Payloads — {group.get('name', '')}")
            self.query_one("#breadcrumb", Static).update(
                f"Classes → {cls_name} → {group.get('name', '')}"
            )
            lv = self.query_one("#item-list", ListView)
            lv.clear()
            group_slug = group.get("slug", "")
            class_slug = self._current_class.get("slug", "") if self._current_class else ""
            # Merge YAML built-in payloads with custom payloads from SQLite
            builtin_payloads = []
            for p in group.get("payloads", []):
                p_copy = dict(p)
                p_copy.setdefault("class_slug", class_slug)
                p_copy.setdefault("group_slug", group_slug)
                p_copy.setdefault("source", "builtin")
                builtin_payloads.append(p_copy)
            # Append custom payloads for this class+group from SQLite
            custom_payloads: list[dict] = []
            try:
                with db.get_connection() as _conn:
                    _rows = _conn.execute(
                        "SELECT * FROM custom_payloads WHERE class_slug=? AND group_slug=?",
                        (class_slug, group_slug)
                    ).fetchall()
                import json as _json
                for _row in _rows:
                    custom_payloads.append({
                        "id": _row["id"],
                        "class_slug": _row["class_slug"],
                        "group_slug": _row["group_slug"],
                        "title": _row["title"] + " [custom]",
                        "payload_string": _row["payload_string"],
                        "how_it_works": _row["how_it_works"],
                        "prerequisites": _json.loads(_row["prerequisites_json"] or "[]"),
                        "waf_bypass_notes": _row["waf_bypass_notes"] or "",
                        "severity_context": _row["severity_context"] or "",
                        "cve_refs": _json.loads(_row["cve_refs_json"] or "[]"),
                        "tags": _json.loads(_row["tags_json"] or "[]"),
                        "source": "custom",
                        "difficulty": "medium",
                        "date_added": _row["created_at"] or "",
                        "last_updated": _row["updated_at"] or "",
                    })
            except Exception:
                pass
            self._payloads = builtin_payloads + custom_payloads
            # Apply tag filter if active — respects AND/OR mode (_tag_mode)
            if self._active_tags:
                p_tags_set = set(self._active_tags)
                if self._tag_mode == "AND":
                    self._payloads = [
                        p for p in self._payloads
                        if p_tags_set.issubset(set(p.get("tags", [])))
                    ]
                else:  # OR (default)
                    self._payloads = [
                        p for p in self._payloads
                        if p_tags_set.intersection(set(p.get("tags", [])))
                    ]
                mode_label = f"[{self._tag_mode}]"
                tag_bar_text = f"Tags {mode_label}: " + ", ".join(sorted(self._active_tags))
            else:
                tag_bar_text = "No tag filter active  (T to filter)"
            self.query_one("#tag-filter-bar", Static).update(tag_bar_text)
            for p in self._payloads:
                # No id= — IDs must be unique across DOM; payload identified by index
                # into self._payloads (already used in on_list_view_selected).
                lv.append(ListItem(Label(p.get("title", "?"))))
            self._current_group = group
            self._current_view = "payloads"
            self._update_status_bar(len(self._payloads), group.get("name", ""))

        def _show_payload_detail(self, payload: dict) -> None:
            """Show payload details in the right pane (Detail + WAF tabs)."""
            # Switch to Detail tab when a new payload is selected
            try:
                detail_tabs = self.query_one("#detail-tabs", TabbedContent)
                detail_tabs.active = "tab-detail"
            except Exception:
                pass

            detail = self.query_one("#detail-content", RichLog)
            detail.clear()
            detail.write(f"[bold cyan]{payload.get('title', 'Untitled')}[/bold cyan]")
            detail.write("")
            payload_str = payload.get("payload_string", "")
            if payload_str:
                detail.write("[bold]Payload:[/bold]")
                _lexer = _slug_to_lexer(payload.get("class_slug", ""))
                try:
                    syntax_obj = RichSyntax(payload_str, _lexer, theme="monokai",
                                            word_wrap=True, background_color="default")
                    detail.write(syntax_obj)
                except Exception:
                    detail.write(f"[green]{payload_str}[/green]")
                detail.write("")
            how = payload.get("how_it_works", "")
            if how:
                detail.write("[bold]How it works:[/bold]")
                detail.write(how.strip())
                detail.write("")
            prereqs = payload.get("prerequisites", [])
            if prereqs:
                detail.write("[bold]Prerequisites:[/bold]")
                for pr in prereqs:
                    detail.write(f"  • {pr}")
                detail.write("")
            severity = payload.get("severity_context", "")
            if severity:
                detail.write("[bold]Severity:[/bold]")
                detail.write(severity)
                detail.write("")
            cves = payload.get("cve_refs", [])
            if cves:
                # Render CVEs as clickable NVD hyperlinks (terminal OSC 8 via Rich link markup)
                cve_links = []
                for cve in cves:
                    cve_id = cve.strip()
                    nvd_url = f"https://nvd.nist.gov/vuln/detail/{cve_id}"
                    cve_links.append(f"[link={nvd_url}]{cve_id}[/link]")
                detail.write(f"[bold]CVE references:[/bold] {', '.join(cve_links)}")
                detail.write("")
            tags = payload.get("tags", [])
            if tags:
                detail.write(f"[bold]Tags:[/bold] {', '.join(tags)}")
            date_added = payload.get("date_added", "")
            last_updated = payload.get("last_updated", "")
            if date_added or last_updated:
                detail.write("")
                if date_added:
                    detail.write(f"[dim]Added: {date_added}[/dim]")
                if last_updated and last_updated != date_added:
                    detail.write(f"[dim]Updated: {last_updated}[/dim]")
            source = payload.get("source", "builtin")
            if source == "custom":
                detail.write("\n[bold yellow][custom][/bold yellow]")
            # Show personal note if any
            pid = payload.get("id", "")
            note_text = self._get_note(pid)
            if note_text:
                detail.write("")
                detail.write("[bold magenta]📝 Personal Note:[/bold magenta]")
                detail.write(note_text)
            detail.write("")
            detail.write("[dim]Y=copy  Ctrl+Y=copy-all  B=bookmark  N=note  E=AI  V=variants  C=chain  ?=help[/dim]")

            # Populate WAF Bypass tab
            waf_log = self.query_one("#waf-content", RichLog)
            waf_log.clear()
            waf = payload.get("waf_bypass_notes", "")
            waf_log.write(f"[bold cyan]{payload.get('title', 'Untitled')}[/bold cyan]")
            waf_log.write("")
            waf_log.write("[bold]WAF Bypass Notes[/bold]")
            waf_log.write("[dim]─" * 40 + "[/dim]")
            if waf:
                waf_log.write(waf.strip())
            else:
                waf_log.write("[dim]No WAF bypass notes for this payload.[/dim]")
            # Per-WAF structured breakdown (waf_notes_by_product optional key)
            waf_by_product = payload.get("waf_notes_by_product", [])
            if waf_by_product:
                waf_log.write("")
                waf_log.write("[bold]Per-WAF Product Breakdown[/bold]")
                waf_log.write("[dim]─" * 40 + "[/dim]")
                for entry in waf_by_product:
                    waf_name = entry.get("waf", "Unknown WAF")
                    blocked = entry.get("blocked", "unknown")
                    bypass = entry.get("bypass", "")
                    alt = entry.get("alt", "")
                    # Colour-code block status
                    if blocked is True or blocked == "true":
                        status_tag = "[bold red]BLOCKED[/bold red]"
                    elif blocked is False or blocked == "false":
                        status_tag = "[bold green]NOT BLOCKED[/bold green]"
                    else:
                        status_tag = f"[bold yellow]{str(blocked).upper()}[/bold yellow]"
                    waf_log.write(f"[bold]{waf_name}[/bold]  {status_tag}")
                    if bypass:
                        waf_log.write(f"  [dim]Bypass:[/dim] {bypass}")
                    if alt:
                        waf_log.write(f"  [dim]Alt:[/dim] {alt}")
                    waf_log.write("")
            else:
                waf_log.write("")
                waf_log.write("[dim]Note: bypass notes above are general-context (not per-WAF product).[/dim]")
                waf_log.write("[dim]Press W to get AI-powered WAF bypass analysis for this payload.[/dim]")

            self._current_payload = payload
            # G4: advance to "detail" view state for proper Esc navigation
            self._current_view = "detail"
            # G8: 4th breadcrumb level — Classes → Class → Group → Payload title
            try:
                cls_name = self._current_class.get("name", "") if self._current_class else ""
                grp_name = self._current_group.get("name", "") if self._current_group else ""
                self.query_one("#breadcrumb", Static).update(
                    f"Classes → {cls_name} → {grp_name} → {payload.get('title', '')}"
                )
            except Exception:
                pass
            # Log to history
            self._log_history(payload)

        def _get_note(self, payload_id: str) -> str:
            """Retrieve personal note for a payload from DB."""
            if not payload_id:
                return ""
            try:
                with db.get_connection() as conn:
                    row = conn.execute(
                        "SELECT note_text FROM notes WHERE payload_id=? ORDER BY updated_at DESC LIMIT 1",
                        (payload_id,)
                    ).fetchone()
                return row["note_text"] if row else ""
            except Exception:
                return ""

        def _log_history(self, payload: dict) -> None:
            """Record payload view in history table with LRU trim at 500 entries."""
            try:
                with db.get_connection() as conn:
                    conn.execute(
                        "INSERT INTO history (payload_id, class_slug, group_slug, viewed_at) VALUES (?,?,?,?)",
                        (
                            payload.get("id", ""),
                            payload.get("class_slug", ""),
                            payload.get("group_slug", ""),
                            datetime.now(timezone.utc).isoformat()
                        )
                    )
                    # LRU trim — keep only the 500 most recent entries
                    conn.execute(
                        "DELETE FROM history WHERE id NOT IN "
                        "(SELECT id FROM history ORDER BY viewed_at DESC LIMIT 500)"
                    )
            except Exception:
                pass
            # Refresh recent list in sidebar
            self._refresh_recent_list()

        # ── Event handlers ──────────────────────────────────────────────────

        def on_list_view_selected(self, event: ListView.Selected) -> None:
            """Handle selection in any ListView — all lists use positional index."""
            lv_id = event.list_view.id

            if lv_id == "class-list":
                # Positional lookup into _sorted_class_list
                children = list(event.list_view.children)
                try:
                    idx = children.index(event.item)
                except ValueError:
                    return
                cls_list = getattr(self, "_sorted_class_list", [])
                if 0 <= idx < len(cls_list):
                    cls = cls_list[idx]
                    self._load_group_list(cls)
                    self._current_view = "groups"

            elif lv_id == "item-list":
                if self._current_view == "groups" and self._current_class:
                    # Positional lookup into _current_groups_list
                    children = list(event.list_view.children)
                    try:
                        idx = children.index(event.item)
                    except ValueError:
                        return
                    groups = getattr(self, "_current_groups_list", self._current_class.get("groups", []))
                    if 0 <= idx < len(groups):
                        self._load_payload_list(groups[idx])

                elif self._current_view in ("payloads", "detail"):
                    # Also fire in "detail" view: after opening a payload the
                    # list is still visible, so selecting another payload opens
                    # it directly — no ESC first (consistent with the bookmarks
                    # list and the bookmark action, which already allow "detail").
                    children = list(event.list_view.children)
                    try:
                        idx = children.index(event.item)
                    except ValueError:
                        return
                    if 0 <= idx < len(self._payloads):
                        p = self._payloads[idx]
                        if self._current_class:
                            p = dict(p)
                            p["class_slug"] = self._current_class.get("slug", "")
                            p["group_slug"] = self._current_group.get("slug", "") if self._current_group else ""
                        self._show_payload_detail(p)

            elif lv_id == "recent-list":
                # Positional lookup into _recent_rows
                children = list(event.list_view.children)
                try:
                    idx = children.index(event.item)
                except ValueError:
                    return
                recent = getattr(self, "_recent_rows", [])
                if 0 <= idx < len(recent):
                    self._jump_to_payload_id(recent[idx]["payload_id"])

            elif lv_id == "bookmarks-list":
                # Resolve the selected bookmark to its payload via the same path
                # recent-list uses — so Enter opens the payload detail and the
                # copy / note / AI actions (which need _current_payload) work.
                children = list(event.list_view.children)
                try:
                    idx = children.index(event.item)
                except ValueError:
                    return
                bms = getattr(self, "_bookmark_rows", [])
                if 0 <= idx < len(bms):
                    self._jump_to_payload_id(bms[idx]["payload_id"])

        def _jump_to_payload_id(self, payload_id: str) -> None:
            """Navigate to a payload by its ID across all classes."""
            # Try to find the payload in the loaded classes
            for cls in self._kb_classes:
                for g in cls.get("groups", []):
                    for p in g.get("payloads", []):
                        if p.get("id") == payload_id:
                            self._load_group_list(cls)
                            self._load_payload_list(g)
                            p_copy = dict(p)
                            p_copy["class_slug"] = cls.get("slug", "")
                            p_copy["group_slug"] = g.get("slug", "")
                            self._show_payload_detail(p_copy)
                            return
            # YAML lookup failed — check custom_payloads in SQLite
            try:
                with db.get_connection() as _conn:
                    _row = _conn.execute(
                        "SELECT * FROM custom_payloads WHERE id=?",
                        (payload_id,)
                    ).fetchone()
                if _row:
                    p_custom = {
                        "id": _row["id"],
                        "class_slug": _row["class_slug"],
                        "class_name": _row["class_slug"],
                        "group_slug": _row["group_slug"],
                        "group_name": _row["group_slug"],
                        "title": _row["title"] + " [custom]",
                        "payload_string": _row["payload_string"],
                        "how_it_works": _row["how_it_works"] or "",
                        "waf_bypass_notes": _row["waf_bypass_notes"] or "",
                        "severity_context": _row["severity_context"] or "",
                        "cve_refs": json.loads(_row["cve_refs_json"] or "[]"),
                        "tags": json.loads(_row["tags_json"] or "[]"),
                        "source": "custom",
                    }
                    self._show_payload_detail(p_custom)
                    return
            except Exception:
                pass
            self.notify(f"Payload not found: {payload_id}", severity="warning")

        # ── Actions ─────────────────────────────────────────────────────────

        def action_go_back(self) -> None:
            """Navigate back one level — four levels: detail → payloads → groups → classes."""
            if self._current_view == "detail":
                # Return to payload list (do not discard navigation context)
                self._current_view = "payloads"
                # Clear detail pane and restore payload-list breadcrumb
                try:
                    self.query_one("#detail-content", RichLog).clear()
                    self.query_one("#waf-content", RichLog).clear()
                except Exception:
                    pass
                cls_name = self._current_class.get("name", "") if self._current_class else ""
                grp_name = self._current_group.get("name", "") if self._current_group else ""
                try:
                    self.query_one("#breadcrumb", Static).update(
                        f"Classes → {cls_name} → {grp_name}"
                    )
                except Exception:
                    pass
            elif self._current_view == "payloads":
                self._current_view = "groups"
                if self._current_class:
                    self._load_group_list(self._current_class)
            elif self._current_view == "groups":
                self._current_view = "classes"
                self._current_class = None
                try:
                    self.query_one("#breadcrumb", Static).update("Classes")
                    self.query_one("#main-title", Label).update("Attack Groups / Payloads")
                    self.query_one("#item-list", ListView).clear()
                    self.query_one("#detail-content", RichLog).clear()
                except Exception:
                    pass

        def action_show_help(self) -> None:
            """Show help modal."""
            self.push_screen(HelpModal())

        def action_search(self) -> None:
            """Open search overlay."""
            def handle_result(result):
                if result is not None:
                    # Try YAML lookup first
                    found = False
                    cls = loader.load_class(result.class_slug)
                    if cls:
                        for g in cls.get("groups", []):
                            if g.get("slug") == result.group_slug:
                                for p in g.get("payloads", []):
                                    if p.get("id") == result.payload_id:
                                        self._load_group_list(cls)
                                        self._load_payload_list(g)
                                        p_copy = dict(p)
                                        p_copy["class_slug"] = result.class_slug
                                        p_copy["group_slug"] = result.group_slug
                                        self._show_payload_detail(p_copy)
                                        found = True
                                        break
                                if found:
                                    break
                    if not found:
                        # Custom payload — look up in SQLite
                        try:
                            with db.get_connection() as _conn:
                                _row = _conn.execute(
                                    "SELECT * FROM custom_payloads WHERE id=?",
                                    (result.payload_id,)
                                ).fetchone()
                            if _row:
                                p_custom = {
                                    "id": _row["id"],
                                    "class_slug": _row["class_slug"],
                                    "class_name": _row["class_slug"],
                                    "group_slug": _row["group_slug"],
                                    "group_name": _row["group_slug"],
                                    "title": _row["title"] + " [custom]",
                                    "payload_string": _row["payload_string"],
                                    "how_it_works": _row["how_it_works"] or "",
                                    "waf_bypass_notes": _row["waf_bypass_notes"] or "",
                                    "severity_context": _row["severity_context"] or "",
                                    "cve_refs": json.loads(_row["cve_refs_json"] or "[]"),
                                    "tags": json.loads(_row["tags_json"] or "[]"),
                                    "source": "custom",
                                }
                                self._show_payload_detail(p_custom)
                        except Exception:
                            pass
            self.push_screen(SearchOverlay(), handle_result)

        def action_bookmark(self) -> None:
            """Open bookmarks panel (from nav) or toggle bookmark (from payload detail)."""
            # From payload detail or payload list: toggle bookmark on current payload
            if self._current_view in ("payloads", "detail") and self._current_payload is not None:
                self._toggle_bookmark(self._current_payload)
                return
            # From nav context (classes/groups): switch sidebar to bookmarks tab
            self._open_bookmarks_panel()

        def _open_bookmarks_panel(self) -> None:
            """Switch sidebar focus to the Bookmarks tab."""
            try:
                tabs = self.query_one("#sidebar-tabs", TabbedContent)
                tabs.active = "tab-bookmarks"
                self._refresh_bookmarks_list()
                # Focus the bookmarks list for keyboard navigation
                self.query_one("#bookmarks-list", ListView).focus()
            except Exception as e:
                self.notify(f"Bookmarks panel error: {e}", severity="error")

        def _toggle_bookmark(self, payload: dict) -> None:
            """Toggle bookmark on a specific payload."""
            pid = payload.get("id", "")
            try:
                with db.get_connection() as conn:
                    existing = conn.execute(
                        "SELECT id FROM bookmarks WHERE payload_id=?", (pid,)
                    ).fetchone()
                    if existing:
                        conn.execute("DELETE FROM bookmarks WHERE payload_id=?", (pid,))
                        self.notify(f"Removed bookmark: {payload.get('title', '')}")
                    else:
                        conn.execute(
                            "INSERT INTO bookmarks (payload_id, class_slug, group_slug, label, created_at) VALUES (?,?,?,?,?)",
                            (
                                pid,
                                payload.get("class_slug", ""),
                                payload.get("group_slug", ""),
                                payload.get("title", ""),
                                datetime.now(timezone.utc).isoformat()
                            )
                        )
                        self.notify(f"Bookmarked: {payload.get('title', '')}")
                # Refresh sidebar bookmarks list in case it's visible
                self._refresh_bookmarks_list()
            except Exception as e:
                self.notify(f"Bookmark error: {e}", severity="error")

        def action_copy_payload(self) -> None:
            """Copy payload string to clipboard."""
            if self._current_payload is None:
                self.notify("Select a payload first.", severity="warning")
                return
            payload_str = self._current_payload.get("payload_string", "")
            try:
                import pyperclip
                pyperclip.copy(payload_str)
                self.notify(f"Copied to clipboard: {payload_str[:40]}...")
            except Exception:
                self.notify(f"Payload: {payload_str}")

        def action_copy_full_detail(self) -> None:
            """Copy full payload detail (title + payload + how_it_works) to clipboard."""
            if self._current_payload is None:
                self.notify("Select a payload first.", severity="warning")
                return
            p = self._current_payload
            text = (
                f"Title: {p.get('title', '')}\n"
                f"Payload: {p.get('payload_string', '')}\n\n"
                f"How it works:\n{p.get('how_it_works', '')}\n"
            )
            try:
                import pyperclip
                pyperclip.copy(text)
                self.notify("Full detail copied to clipboard.")
            except Exception:
                self.notify(f"Detail: {text[:80]}...")

        def action_edit_note(self) -> None:
            """Open note editor for current payload."""
            if self._current_payload is None:
                self.notify("Select a payload first.", severity="warning")
                return
            pid = self._current_payload.get("id", "")
            existing = self._get_note(pid)

            def handle_note(note_text):
                if note_text is None:
                    return  # Cancelled
                try:
                    with db.get_connection() as conn:
                        existing_row = conn.execute(
                            "SELECT id FROM notes WHERE payload_id=?", (pid,)
                        ).fetchone()
                        now = datetime.now(timezone.utc).isoformat()
                        if existing_row:
                            conn.execute(
                                "UPDATE notes SET note_text=?, updated_at=? WHERE payload_id=?",
                                (note_text, now, pid)
                            )
                        else:
                            conn.execute(
                                "INSERT INTO notes (payload_id, note_text, created_at, updated_at) VALUES (?,?,?,?)",
                                (pid, note_text, now, now)
                            )
                    self.notify("Note saved.")
                    # Refresh detail view to show the updated note
                    self._show_payload_detail(self._current_payload)
                except Exception as e:
                    self.notify(f"Note error: {e}", severity="error")

            self.push_screen(NoteModal(pid, existing), handle_note)

        async def action_explain_payload(self) -> None:
            """Fetch AI explanation in a thread, streaming chunks progressively to detail panel."""
            if self._current_payload is None:
                self.notify("Select a payload first.", severity="warning")
                return
            from armory.ai import is_ai_available, explain_payload_stream
            if not is_ai_available():
                self.notify("Set ARMORY_CLAUDE_API_KEY to use AI features.", severity="warning")
                return
            detail = self.query_one("#detail-content", RichLog)
            detail.write("")
            detail.write("[bold yellow]🤖 AI Explanation  ⏳ streaming…[/bold yellow]")
            payload_ref = self._current_payload

            def stream_task():
                """Run in executor thread — streams chunks to detail panel via call_from_thread."""
                def on_chunk(text: str) -> None:
                    self.call_from_thread(detail.write, text)
                explain_payload_stream(payload_ref, on_chunk)

            try:
                import asyncio
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, stream_task)
            except Exception as e:
                detail.write(f"[red]AI error: {e}[/red]")

        def action_generate_variants(self) -> None:
            """Prompt for operator context then generate AI payload variants (non-blocking)."""
            if self._current_payload is None:
                self.notify("Select a payload first.", severity="warning")
                return
            from armory.ai import is_ai_available, generate_variants
            if not is_ai_available():
                self.notify("Set ARMORY_CLAUDE_API_KEY to use AI features.", severity="warning")
                return

            payload_ref = self._current_payload  # capture before modal

            async def _run_variants(context_str: str) -> None:
                import asyncio
                self.notify("Generating variants… (this may take a moment)")
                try:
                    loop = asyncio.get_event_loop()
                    variants = await loop.run_in_executor(
                        None, generate_variants, payload_ref, context_str
                    )
                    if isinstance(variants, str):
                        self.notify(f"AI returned raw text: {variants[:60]}", severity="warning")
                        return
                    if not variants:
                        self.notify("No variants returned.", severity="warning")
                        return
                    self.push_screen(VariantsModal(variants, payload_ref), lambda _: None)
                except Exception as e:
                    self.notify(f"AI error: {e}", severity="error")

            def handle_context(context_str: str | None) -> None:
                """Called after operator submits or cancels the context modal."""
                if context_str is None:
                    return  # Cancelled
                import asyncio
                asyncio.ensure_future(_run_variants(context_str))

            self.push_screen(ContextInputModal(), handle_context)

        async def action_chain_suggest(self) -> None:
            """Generate attack chain suggestion via AI, streaming chunks progressively."""
            if self._current_payload is None:
                self.notify("Select a payload first.", severity="warning")
                return
            from armory.ai import is_ai_available, suggest_chain_stream
            if not is_ai_available():
                self.notify("Set ARMORY_CLAUDE_API_KEY to use AI features.", severity="warning")
                return
            detail = self.query_one("#detail-content", RichLog)
            detail.write("")
            detail.write("[bold yellow]🔗 Attack Chain  ⏳ streaming…[/bold yellow]")
            payload_ref = self._current_payload

            def stream_task():
                """Run in executor thread — streams chain chunks to detail panel."""
                def on_chunk(text: str) -> None:
                    self.call_from_thread(detail.write, text)
                suggest_chain_stream(payload_ref, on_chunk)

            try:
                import asyncio
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, stream_task)
            except Exception as e:
                detail.write(f"[red]AI error: {e}[/red]")

        async def action_waf_bypass_advisor(self) -> None:
            """W key: request AI WAF bypass advisory for the current payload, stream into WAF tab."""
            if self._current_payload is None:
                self.notify("Select a payload first.", severity="warning")
                return
            from armory.ai import is_ai_available, ai_query
            if not is_ai_available():
                self.notify("Set ARMORY_CLAUDE_API_KEY to enable WAF Bypass Advisor.", severity="warning")
                return
            # Switch to WAF tab and prepare output
            try:
                self.query_one("#detail-tabs", TabbedContent).active = "tab-waf"
            except Exception:
                pass
            waf_log = self.query_one("#waf-content", RichLog)
            waf_log.write("")
            waf_log.write("[bold yellow]🛡 WAF Bypass Advisor  ⏳ querying AI…[/bold yellow]")
            payload_ref = self._current_payload

            def advisor_task():
                """Run in executor thread — calls ai_query and streams result line-by-line."""
                question = (
                    f"Provide a detailed WAF bypass advisory for this penetration testing payload.\n\n"
                    f"Payload title: {payload_ref.get('title', '')}\n"
                    f"Payload string: {payload_ref.get('payload_string', '')}\n"
                    f"Vulnerability class: {payload_ref.get('class_slug', '')}\n"
                    f"Existing WAF notes: {payload_ref.get('waf_bypass_notes', '')}\n\n"
                    f"Cover: common WAF detection patterns for this payload, encoding/obfuscation "
                    f"bypass techniques, vendor-specific quirks (ModSecurity, Cloudflare, AWS WAF, "
                    f"Akamai), and recommended evasion approach for a penetration test."
                )
                result = ai_query(
                    question,
                    class_slug=payload_ref.get("class_slug"),
                )
                for line in result.splitlines():
                    self.call_from_thread(waf_log.write, line)

            try:
                import asyncio
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, advisor_task)
            except Exception as e:
                waf_log.write(f"[red]AI error: {e}[/red]")

        def action_show_tag_cloud(self) -> None:
            """Show tag cloud modal for current scope."""
            # Aggregate tags from current scope (payloads in view or all payloads)
            if self._current_view in ("payloads", "detail") and self._current_group:
                scope_payloads = self._current_group.get("payloads", [])
            elif self._current_view in ("groups", "classes") and self._current_class:
                scope_payloads = [
                    p for g in self._current_class.get("groups", [])
                    for p in g.get("payloads", [])
                ]
            else:
                scope_payloads = loader.get_all_payloads()

            tag_counts: dict[str, int] = {}
            for p in scope_payloads:
                for tag in p.get("tags", []):
                    tag_counts[tag] = tag_counts.get(tag, 0) + 1
            sorted_tags = sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)

            def handle_tags(result):
                # Result is (selected_tags_set, mode_str) from TagCloudModal.action_dismiss
                if result is None:
                    return
                if isinstance(result, tuple):
                    selected_tags, new_mode = result
                else:
                    selected_tags, new_mode = result, self._tag_mode
                self._active_tags = selected_tags
                self._tag_mode = new_mode
                # Refresh payload list if we're in payload view
                if self._current_view in ("payloads", "detail") and self._current_group:
                    self._load_payload_list(self._current_group)
                tag_bar = ", ".join(sorted(selected_tags)) if selected_tags else "No filter"
                mode_str = f" [{new_mode}]" if selected_tags else ""
                self.notify(f"Tag filter{mode_str}: {tag_bar}" if selected_tags else "Tag filter cleared")

            self.push_screen(
                TagCloudModal(sorted_tags, self._active_tags, self._tag_mode),
                handle_tags
            )

        def action_show_history(self) -> None:
            """Open browsable history modal with jump-to (G key)."""
            try:
                with db.get_connection() as conn:
                    rows = conn.execute(
                        "SELECT payload_id, class_slug, group_slug, viewed_at FROM history "
                        "ORDER BY viewed_at DESC LIMIT 50"
                    ).fetchall()
                rows_list = [dict(r) for r in rows]
            except Exception as e:
                self.notify(f"History error: {e}", severity="error")
                return

            def handle_jump(row):
                if row is not None:
                    self._jump_to_payload_id(row["payload_id"])

            self.push_screen(HistoryModal(rows_list), handle_jump)

        def action_jump_from_history(self) -> None:
            """Alias — G key opens history for jump-to."""
            self.action_show_history()

        def action_show_recent(self) -> None:
            """Show recent history (alias for H)."""
            self.action_show_history()

        def action_cursor_down(self) -> None:
            """Move cursor down in focused list."""
            try:
                if self._current_view == "classes":
                    self.query_one("#class-list", ListView).action_cursor_down()
                else:
                    self.query_one("#item-list", ListView).action_cursor_down()
            except Exception:
                pass

        def action_cursor_up(self) -> None:
            """Move cursor up in focused list."""
            try:
                if self._current_view == "classes":
                    self.query_one("#class-list", ListView).action_cursor_up()
                else:
                    self.query_one("#item-list", ListView).action_cursor_up()
            except Exception:
                pass

        def action_add_custom_payload(self) -> None:
            """A key — add a custom payload to the current class/group (groups view only)."""
            if self._current_view != "groups":
                self.notify("Press A from the group list to add a custom payload.", severity="information")
                return
            class_slug = self._current_class.get("slug", "") if self._current_class else ""
            # Pre-fill group from _current_group if the user drilled in and came back;
            # otherwise the modal shows a group selector listing all available groups.
            group_slug = self._current_group.get("slug", "") if self._current_group else ""
            # Collect available group slugs from the current class for the selector hint
            available_groups: list[str] = []
            if self._current_class:
                available_groups = [
                    g.get("slug", "") for g in self._current_class.get("groups", [])
                    if g.get("slug")
                ]
            if not class_slug:
                self.notify("Navigate to a class group before adding a payload.", severity="warning")
                return

            def handle_new_payload(result):
                if result is None:
                    return
                import uuid as _uuid
                from datetime import datetime, timezone
                now = datetime.now(timezone.utc).isoformat()
                pid = f"custom-{_uuid.uuid4().hex[:8]}"
                tags = result.get("tags", [])
                # Use group from modal result (operator may have typed/changed it)
                chosen_group = result.get("group_slug") or group_slug or "custom"
                try:
                    with db.get_connection() as conn:
                        conn.execute(
                            """INSERT INTO custom_payloads
                               (id, class_slug, group_slug, title, payload_string,
                                how_it_works, tags_json, created_at, updated_at)
                               VALUES (?,?,?,?,?,?,?,?,?)""",
                            (
                                pid,
                                class_slug,
                                chosen_group,
                                result["title"],
                                result["payload_string"],
                                result.get("description", "Custom payload added via TUI."),
                                json.dumps(tags),
                                now,
                                now,
                            ),
                        )
                    self.notify(f"Saved custom payload: {pid}", severity="information")
                    # Refresh payload list if in group view
                    if self._current_group:
                        self._load_payload_list(self._current_group)
                except Exception as e:
                    self.notify(f"Error saving payload: {e}", severity="error")

            self.push_screen(
                AddPayloadModal(class_slug, group_slug, available_groups=available_groups),
                handle_new_payload,
            )

        def action_delete_custom_payload(self) -> None:
            """X key — delete the current custom payload (detail view, custom source only)."""
            if self._current_view != "detail" or not self._current_payload:
                self.notify("Navigate to a custom payload's detail view, then press X.", severity="information")
                return
            if self._current_payload.get("source") != "custom":
                self.notify("Only custom payloads can be deleted from the TUI.", severity="warning")
                return

            pid = self._current_payload.get("id", "")
            title = self._current_payload.get("title", pid)

            def handle_confirm(confirmed):
                if not confirmed:
                    return
                try:
                    with db.get_connection() as conn:
                        # Cascade: remove bookmarks, notes, history for this payload
                        conn.execute("DELETE FROM bookmarks WHERE payload_id=?", (pid,))
                        conn.execute("DELETE FROM notes WHERE payload_id=?", (pid,))
                        conn.execute("DELETE FROM history WHERE payload_id=?", (pid,))
                        conn.execute("DELETE FROM custom_payloads WHERE id=?", (pid,))
                    self.notify(f"Deleted: {title}", severity="information")
                    # Navigate back to the group/payload list
                    self.action_go_back()
                except Exception as e:
                    self.notify(f"Error deleting payload: {e}", severity="error")

            self.push_screen(
                ConfirmDeleteModal(pid, title),
                handle_confirm,
            )

        def action_quit(self) -> None:
            """Quit the application."""
            self.exit()

else:
    # Fallback when textual is not installed
    class ArmoryApp:
        def __init__(self, start_class=None, start_group=None, theme=None):
            pass

        def run(self):
            raise ImportError(
                "textual package required for TUI. Install with: pip install textual"
            )


HELP_TEXT = """
NAVIGATION
  ↑/↓ or j/k        Move cursor within the focused pane
  Tab / Shift+Tab   Move focus between panes/sections
  Enter             Select item / drill down
  Escape            Go back one level
  q                 Quit application

SEARCH
  /             Open search overlay (↑/↓ = cycle prior queries)
  Type to search, Enter to navigate to result

PAYLOAD ACTIONS
  Y             Copy payload string to clipboard
  Ctrl+Y        Copy full detail (title + payload + explanation)
  B             Toggle bookmark on current payload
  N             Edit personal note for current payload

AI FEATURES (requires ARMORY_CLAUDE_API_KEY)
  E             Explain payload deeper (streams into detail panel)
  V             Generate payload variants (shows variant modal; S to save)
  C             Suggest attack chain
  W             WAF Bypass Advisor — AI analysis streamed into WAF tab
  Ctrl+A        AI-assisted search in search overlay (also auto-hints on 0 results)

CUSTOM PAYLOAD MANAGEMENT
  A             Add custom payload (from the group list view)
                  Modal prompts for group, title, payload string, description, tags
  X             Delete custom payload (from payload detail view; custom payloads only)
                  Requires confirmation; cascades bookmarks/notes/history

VIEW
  H / G         Open history modal (Enter to jump to payload)
  T             Tag cloud / tag filter
  ?             Show this help

BOOKMARKS
  B             Toggle bookmark on current payload
  Bookmarked payloads accessible via 'armory export --bookmarks'
"""
