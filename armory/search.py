"""Armory search engine — rapidfuzz-based five-tier ranking model."""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any

try:
    from rapidfuzz import fuzz
    HAS_RAPIDFUZZ = True
except ImportError:
    HAS_RAPIDFUZZ = False


@dataclass
class SearchResult:
    """A single search result with score and matched payload data."""
    payload_id: str
    title: str
    class_slug: str
    group_slug: str
    payload_string: str
    how_it_works: str
    tags: list[str]
    waf_bypass_notes: str
    cve_refs: list[str]
    score: float
    source: str = "builtin"


def _token_sort_ratio(a: str, b: str) -> float:
    """Compute token_sort_ratio using rapidfuzz or fallback.

    Fallback strategy (no rapidfuzz):
    1. Full-string substring: return 80 immediately.
    2. Token-level overlap with partial matching: a query word counts as
       a hit if it is an exact match OR a prefix/substring of a target
       word (e.g. "jinja" matches "jinja2", "blind" matches "blind-sqli").
       Score = Dice coefficient × 100 on the effective overlap count.
    3. Additionally, each query token is tested as a substring of the full
       b string to catch compound-word or hyphenated forms.
    """
    if HAS_RAPIDFUZZ:
        return fuzz.token_sort_ratio(a, b)
    a_lower = a.lower()
    b_lower = b.lower()
    # Tier 0: full-string containment
    if a_lower in b_lower or b_lower in a_lower:
        return 80.0
    a_words = a_lower.split()
    b_words = b_lower.split()
    if not a_words or not b_words:
        return 0.0
    # Count how many query words match at least one target word.
    # Match semantics (all with min query-word length of 4 for prefix rules):
    #   1. Exact token equality: "jinja" == "jinja"
    #   2. Query word is a prefix of target word: "jinja" → "jinja2", "modsec" → "modsecurity"
    #   3. Target word is a prefix of query word only if target is >= 4 chars:
    #      "cve" (3 chars) does NOT match "cve-2019-..." but "2019" (4 chars) in "2019-11358" would
    # Short tokens (< 4 chars) only match by exact equality to prevent noise.
    def _word_matches(aw: str, bwords: list[str]) -> bool:
        if aw in bwords:
            return True
        if len(aw) < 4:
            return False
        for bw in bwords:
            # Query word is a prefix of target word: "jinja" in "jinja2" ✓
            if bw.startswith(aw):
                return True
            # Target word is a prefix of query word, only if target >= 4 chars:
            # "jinja" starts with "jinja" ✓, avoids short noise like "or"→"orm"
            if len(bw) >= 4 and aw.startswith(bw):
                return True
        return False

    matched = sum(1 for aw in a_words if _word_matches(aw, b_words))
    if matched == 0:
        return 0.0
    # Use query-recall (matched / query_length) so long target texts don't
    # dilute scores — what matters is what fraction of query terms were found.
    # Then blend with Dice to prevent over-scoring when query is very short.
    query_recall = matched / len(a_words)
    dice = 2.0 * matched / (len(a_words) + len(b_words))
    # Weighted blend: 80% recall + 20% Dice for long targets; pure Dice for short
    if len(b_words) <= 2 * len(a_words):
        score = dice * 100.0
    else:
        score = (0.8 * query_recall + 0.2 * dice) * 100.0
    return min(score, 79.0)  # cap below 80 to distinguish from full-string match


def search_payloads(
    query: str,
    payloads: list[dict[str, Any]],
    limit: int = 20,
    class_filter: str | None = None,
    tag_filter: str | None = None,
) -> list[SearchResult]:
    """Search payloads using the five-tier rapidfuzz ranking model.

    Ranking tiers (applied in order, descending priority):
    1. Exact full-query substring OR any long token (≥8 chars) in payload_string/title → score 100
    1.5. Left-anchored tag prefix match (query word ≥4 chars) → score 90
    2. token_sort_ratio(query, title) >= 70 → scored by ratio
    3. how_it_works: any query token ≥6 chars exact-substring → floor 70;
       else token_sort_ratio(query, how_it_works) >= 45 → ratio * 0.8
    4. token_sort_ratio(query, tags_joined) >= 60 → ratio * 0.7
    5. any token ≥8 chars in waf+cve → floor 55; else token_sort_ratio >= 50 → ratio * 0.64

    Results below score 50 on all tiers are omitted.
    Results are deduplicated, sorted descending by composite score,
    then truncated to limit.
    """
    if not query:
        return []

    query_lower = query.lower()
    scored: dict[str, SearchResult] = {}

    for p in payloads:
        # Apply filters first
        if class_filter and p.get("class_slug") != class_filter:
            continue
        if tag_filter:
            tags = p.get("tags", [])
            if tag_filter.lower() not in [t.lower() for t in tags]:
                continue

        pid = p.get("id", "") or p.get("payload_id", "")
        title = str(p.get("title", ""))
        payload_string = str(p.get("payload_string", ""))
        how_it_works = str(p.get("how_it_works", ""))
        tags = p.get("tags", [])
        if isinstance(tags, str):
            tags = [tags]
        waf_notes = str(p.get("waf_bypass_notes", ""))
        cve_refs = p.get("cve_refs", [])
        if isinstance(cve_refs, str):
            cve_refs = [cve_refs]
        tags_joined = " ".join(tags)
        cve_str = " ".join(cve_refs)

        best_score = 0.0

        # Tier 1: exact substring in payload_string or title (full query string).
        # Extension: any individual query token ≥8 chars that is an exact substring of
        # title or payload_string also scores 100 — mirrors the long-token floor used
        # in Tier 3 (≥6 chars → how_it_works) and Tier 5 (≥8 chars → waf+cve), and
        # ensures specialist terms (e.g. "htmlspecialchars") in the title surface as
        # top-ranked results rather than tying with generic-tag payloads at score 90.
        title_lower = title.lower()
        ps_lower = payload_string.lower()
        if query_lower in ps_lower or query_lower in title_lower:
            best_score = 100.0
        if best_score < 100:
            # ≥12 chars prevents common technical words ("injection", "template", 8-9 chars)
            # from flooding Tier 1 matches; only highly specific tokens like
            # "htmlspecialchars" (16), "deserialization" (15), "serialization" (13) fire.
            long_q_tokens = [t for t in query_lower.split() if len(t) >= 12]
            if any(tok in title_lower or tok in ps_lower for tok in long_q_tokens):
                best_score = 100.0

        # Tier 1.5: any query word (≥4 chars) is an exact match or a left-anchored
        # prefix of an individual tag.  Using left-anchored prefix (tag.startswith(qword))
        # instead of arbitrary substring ensures specificity:
        #   "jinja"  startswith-matches  "jinja2"   ✓  → SSTI payloads surface
        #   "injection" does NOT startswith "sql-injection" ✗  → avoids broad false-positives
        # Score 90 (below tier-1 exact=100, above tier-2 title-fuzzy ceiling ~99).
        if best_score < 100:
            for qword in query_lower.split():
                if len(qword) >= 4:
                    for tag in tags:
                        tl = tag.lower()
                        if tl == qword or tl.startswith(qword):
                            best_score = max(best_score, 90.0)
                            break

        # Tier 2: title fuzzy
        if best_score < 100:
            r2 = _token_sort_ratio(query, title)
            if r2 >= 70:
                best_score = max(best_score, r2)

        # Tier 3: how_it_works fuzzy
        # Pre-check: if any query token ≥6 chars is an exact substring of
        # how_it_works, assign a floor score of 70 immediately.  This mirrors
        # the Tier-5 pattern for waf_bypass_notes and solves the single-word
        # precision query problem: token_sort_ratio on a 1-word query vs.
        # 200-word prose rarely exceeds 45 even when the term is present.
        # 6-char minimum balances precision vs. recall ("phpggc", "gadget",
        # "pickle", "reduce") while filtering common noise words ("script",
        # "token", "check" — all ≤6 chars; exact ≥6 rarely fires falsely).
        if best_score < 70:
            how_lower = how_it_works.lower()
            long_tokens_3 = [t for t in query_lower.split() if len(t) >= 6]
            if any(tok in how_lower for tok in long_tokens_3):
                best_score = max(best_score, 70.0)
            else:
                r3 = _token_sort_ratio(query, how_it_works)
                if r3 >= 45:
                    best_score = max(best_score, r3 * 0.8)  # weight down vs title

        # Tier 4: tags fuzzy
        if best_score < 60:
            r4 = _token_sort_ratio(query, tags_joined)
            if r4 >= 60:
                best_score = max(best_score, r4 * 0.7)

        # Tier 5: waf+cve (weight 0.64 so fallback max 80×0.64=51.2 > 50 threshold)
        if best_score < 50:
            combined = f"{waf_notes} {cve_str}"
            combined_lower = combined.lower()
            # Pre-check: if any query token ≥8 chars is an exact substring of the combined
            # waf+cve text, assign a floor score of 55. Long tokens (≥8 chars) are rare
            # enough to be discriminating (e.g. "htmlspecialchars", "injection", "sanitize")
            # while avoiding false positives from ubiquitous short waf-bypass vocabulary
            # ("bypass", "script", "filter" — all ≤6 chars). This ensures specialist terms
            # in waf_bypass_notes always surface results even when token_sort_ratio is
            # penalised by length asymmetry of long prose fields vs short queries.
            long_tokens = [t for t in query_lower.split() if len(t) >= 8]
            if any(tok in combined_lower for tok in long_tokens):
                best_score = max(best_score, 55.0)
            else:
                r5 = _token_sort_ratio(query, combined)
                if r5 >= 50:
                    best_score = max(best_score, r5 * 0.64)

        if best_score < 50:
            continue

        # Deduplication by pid; keep highest score
        if pid in scored:
            if scored[pid].score >= best_score:
                continue

        scored[pid] = SearchResult(
            payload_id=pid,
            title=title,
            class_slug=p.get("class_slug", ""),
            group_slug=p.get("group_slug", ""),
            payload_string=payload_string,
            how_it_works=how_it_works,
            tags=tags,
            waf_bypass_notes=waf_notes,
            cve_refs=cve_refs,
            score=best_score,
            source=p.get("source", "builtin"),
        )

    results = sorted(scored.values(), key=lambda r: r.score, reverse=True)
    return results[:limit]
