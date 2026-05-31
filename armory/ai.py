"""Armory AI integration — Anthropic Claude API calls, streaming, and cache."""

from __future__ import annotations
import hashlib
import json
import os
from datetime import datetime, timezone
from typing import Any, Callable


def get_api_key() -> str | None:
    """Return the Anthropic API key from environment, or None."""
    return os.environ.get("ARMORY_CLAUDE_API_KEY")


def is_ai_available() -> bool:
    """Return True if ARMORY_CLAUDE_API_KEY is set."""
    return bool(get_api_key())


class AIFeatureDisabledError(RuntimeError):
    """Raised when an AI feature is requested but the API key is absent."""
    def __init__(self):
        super().__init__(
            "AI features require ARMORY_CLAUDE_API_KEY environment variable. "
            "Set it with: export ARMORY_CLAUDE_API_KEY='your-api-key'"
        )


def _get_client(api_key: str | None = None):
    """Return an Anthropic client, or raise if unavailable."""
    try:
        import anthropic
    except ImportError:
        raise RuntimeError("anthropic package required: pip install 'armory[ai]'")
    key = api_key or get_api_key()
    if not key:
        raise AIFeatureDisabledError()
    return anthropic.Anthropic(api_key=key)


def _make_cache_key(prompt: str, model: str) -> str:
    """Compute a cache key from prompt + model."""
    return hashlib.sha256(f"{model}:{prompt}".encode()).hexdigest()


def _get_cached(cache_key: str) -> str | None:
    """Return cached AI response or None."""
    try:
        from armory.db import get_connection
        with get_connection() as conn:
            row = conn.execute(
                "SELECT response_text FROM ai_cache WHERE cache_key=?", (cache_key,)
            ).fetchone()
        return row["response_text"] if row else None
    except Exception:
        return None


def _save_cache(cache_key: str, prompt_hash: str, response: str, model: str) -> None:
    """Save AI response to cache."""
    try:
        from armory.db import get_connection
        now = datetime.now(timezone.utc).isoformat()
        with get_connection() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO ai_cache
                   (cache_key, prompt_hash, response_text, model, created_at)
                   VALUES (?,?,?,?,?)""",
                (cache_key, prompt_hash, response, model, now)
            )
    except Exception:
        pass


def explain_payload(
    payload: dict[str, Any],
    api_key: str | None = None,
    model: str = "claude-opus-4-5",
) -> str:
    """Generate a deep explanation of a payload via Claude.

    Returns the explanation text, or empty string if AI unavailable.
    """
    if not is_ai_available() and not api_key:
        return ""
    try:
        prompt = (
            f"Explain in depth how the following penetration testing payload works. "
            f"Cover: the vulnerability mechanism, server/browser-side processing, "
            f"what the attacker gains, and real-world impact.\n\n"
            f"Payload title: {payload.get('title', '')}\n"
            f"Payload string:\n{payload.get('payload_string', '')}\n\n"
            f"Vulnerability class: {payload.get('class_slug', '')}\n"
            f"Attack group: {payload.get('group_slug', '')}\n"
            f"Existing notes: {payload.get('how_it_works', '')}"
        )
        ck = _make_cache_key(prompt, model)
        cached = _get_cached(ck)
        if cached:
            return cached

        client = _get_client(api_key)
        response = client.messages.create(
            model=model,
            max_tokens=2048,
            system=[{
                "type": "text",
                "text": "You are an expert penetration tester and security researcher. "
                        "Provide detailed, accurate technical explanations suitable for "
                        "professional security practitioners. "
                        "Do not over-claim effectiveness or generate real exploits for unauthorized systems.",
                "cache_control": {"type": "ephemeral"},
            }],
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text
        _save_cache(ck, hashlib.sha256(prompt.encode()).hexdigest(), text, model)
        return text
    except Exception as e:
        return f"[AI error: {e}]"


def explain_payload_stream(
    payload: dict[str, Any],
    on_chunk: Callable[[str], None],
    api_key: str | None = None,
    model: str = "claude-opus-4-5",
) -> str:
    """Stream explanation of a payload via Claude, calling on_chunk for each text chunk.

    Returns the full accumulated text (also saves to cache).
    Falls back to cached response (delivered as a single on_chunk call) if available.
    """
    if not is_ai_available() and not api_key:
        on_chunk("[AI unavailable — set ARMORY_CLAUDE_API_KEY]")
        return ""
    try:
        prompt = (
            f"Explain in depth how the following penetration testing payload works. "
            f"Cover: the vulnerability mechanism, server/browser-side processing, "
            f"what the attacker gains, and real-world impact.\n\n"
            f"Payload title: {payload.get('title', '')}\n"
            f"Payload string:\n{payload.get('payload_string', '')}\n\n"
            f"Vulnerability class: {payload.get('class_slug', '')}\n"
            f"Attack group: {payload.get('group_slug', '')}\n"
            f"Existing notes: {payload.get('how_it_works', '')}"
        )
        ck = _make_cache_key(prompt, model)
        cached = _get_cached(ck)
        if cached:
            on_chunk(cached)
            return cached

        client = _get_client(api_key)
        full_text = ""
        buffer = ""
        with client.messages.stream(
            model=model,
            max_tokens=2048,
            system=[{
                "type": "text",
                "text": "You are an expert penetration tester and security researcher. "
                        "Provide detailed, accurate technical explanations suitable for "
                        "professional security practitioners. "
                        "Do not over-claim effectiveness or generate real exploits for unauthorized systems.",
                "cache_control": {"type": "ephemeral"},
            }],
            messages=[{"role": "user", "content": prompt}],
        ) as stream:
            for text_chunk in stream.text_stream:
                full_text += text_chunk
                buffer += text_chunk
                # Emit complete lines to the UI as they arrive
                newline_pos = buffer.rfind("\n")
                if newline_pos >= 0:
                    to_emit = buffer[:newline_pos]
                    if to_emit.strip():
                        on_chunk(to_emit)
                    buffer = buffer[newline_pos + 1:]
        # Flush remaining buffer
        if buffer.strip():
            on_chunk(buffer)
        _save_cache(ck, hashlib.sha256(prompt.encode()).hexdigest(), full_text, model)
        return full_text
    except Exception as e:
        on_chunk(f"[AI error: {e}]")
        return f"[AI error: {e}]"


def generate_variants(
    payload: dict[str, Any],
    context: str = "",
    api_key: str | None = None,
    model: str = "claude-opus-4-5",
) -> list[dict[str, Any]] | str:
    """Generate context-aware payload variants via Claude.

    Returns a list of variant dicts with keys: title, payload_string, how_it_works.
    Returns the raw text string if JSON parsing fails.
    """
    if not is_ai_available() and not api_key:
        return []
    try:
        context_note = f"\nOperator context: {context}" if context else ""
        prompt = (
            f"Generate 3-5 context-aware variants of the following penetration testing payload.{context_note}\n\n"
            f"Original payload:\n"
            f"Title: {payload.get('title', '')}\n"
            f"Payload string: {payload.get('payload_string', '')}\n"
            f"Class: {payload.get('class_slug', '')}\n"
            f"Group: {payload.get('group_slug', '')}\n\n"
            f"Respond EXCLUSIVELY with a JSON array (no surrounding prose) in this exact shape:\n"
            f'[{{"title": "short label (<=60 chars)", "payload_string": "raw attack string", '
            f'"how_it_works": "1-3 sentence explanation of why this variant works"}}]'
        )
        ck = _make_cache_key(prompt, model)
        cached = _get_cached(ck)
        if cached:
            try:
                return json.loads(cached)
            except json.JSONDecodeError:
                return cached

        client = _get_client(api_key)
        response = client.messages.create(
            model=model,
            max_tokens=2048,
            system=[{
                "type": "text",
                "text": "You are an expert penetration tester. Respond only with valid JSON arrays when asked for variants. Do not over-claim effectiveness or generate real exploits for unauthorized systems.",
                "cache_control": {"type": "ephemeral"},
            }],
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text
        _save_cache(ck, hashlib.sha256(prompt.encode()).hexdigest(), text, model)
        try:
            # Find JSON array in response
            start = text.find("[")
            end = text.rfind("]") + 1
            if start >= 0 and end > start:
                return json.loads(text[start:end])
        except json.JSONDecodeError:
            pass
        return text  # Return raw text if parsing fails
    except Exception as e:
        return f"[AI error: {e}]"


def suggest_chain(
    payload: dict[str, Any],
    api_key: str | None = None,
    model: str = "claude-opus-4-5",
) -> str:
    """Suggest a multi-step attack chain using the payload as pivot.

    Returns chain description text, or empty string if AI unavailable.
    """
    if not is_ai_available() and not api_key:
        return ""
    try:
        prompt = (
            f"Propose a multi-step attack chain using this payload as a pivot point.\n\n"
            f"Payload: {payload.get('title', '')}\n"
            f"Payload string: {payload.get('payload_string', '')}\n"
            f"Class: {payload.get('class_slug', '')}\n\n"
            f"Include: chain steps, preconditions for each step, and expected final outcome. "
            f"Format as a numbered list."
        )
        ck = _make_cache_key(prompt, model)
        cached = _get_cached(ck)
        if cached:
            return cached

        client = _get_client(api_key)
        response = client.messages.create(
            model=model,
            max_tokens=2048,
            system=[{
                "type": "text",
                "text": "You are an expert penetration tester and red team operator. Do not over-claim effectiveness or generate real exploits for unauthorized systems.",
                "cache_control": {"type": "ephemeral"},
            }],
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text
        _save_cache(ck, hashlib.sha256(prompt.encode()).hexdigest(), text, model)
        return text
    except Exception as e:
        return f"[AI error: {e}]"


def suggest_chain_stream(
    payload: dict[str, Any],
    on_chunk: Callable[[str], None],
    api_key: str | None = None,
    model: str = "claude-opus-4-5",
) -> str:
    """Stream attack chain suggestion via Claude, calling on_chunk for each text chunk.

    Returns the full accumulated text (also saves to cache).
    """
    if not is_ai_available() and not api_key:
        on_chunk("[AI unavailable — set ARMORY_CLAUDE_API_KEY]")
        return ""
    try:
        prompt = (
            f"Propose a multi-step attack chain using this payload as a pivot point.\n\n"
            f"Payload: {payload.get('title', '')}\n"
            f"Payload string: {payload.get('payload_string', '')}\n"
            f"Class: {payload.get('class_slug', '')}\n\n"
            f"Include: chain steps, preconditions for each step, and expected final outcome. "
            f"Format as a numbered list."
        )
        ck = _make_cache_key(prompt, model)
        cached = _get_cached(ck)
        if cached:
            on_chunk(cached)
            return cached

        client = _get_client(api_key)
        full_text = ""
        buffer = ""
        with client.messages.stream(
            model=model,
            max_tokens=2048,
            system=[{
                "type": "text",
                "text": "You are an expert penetration tester and red team operator. Do not over-claim effectiveness or generate real exploits for unauthorized systems.",
                "cache_control": {"type": "ephemeral"},
            }],
            messages=[{"role": "user", "content": prompt}],
        ) as stream:
            for text_chunk in stream.text_stream:
                full_text += text_chunk
                buffer += text_chunk
                newline_pos = buffer.rfind("\n")
                if newline_pos >= 0:
                    to_emit = buffer[:newline_pos]
                    if to_emit.strip():
                        on_chunk(to_emit)
                    buffer = buffer[newline_pos + 1:]
        if buffer.strip():
            on_chunk(buffer)
        _save_cache(ck, hashlib.sha256(prompt.encode()).hexdigest(), full_text, model)
        return full_text
    except Exception as e:
        on_chunk(f"[AI error: {e}]")
        return f"[AI error: {e}]"


def ai_query(
    question: str,
    class_slug: str | None = None,
    group_slug: str | None = None,
    context_payloads: list[dict[str, Any]] | None = None,
    api_key: str | None = None,
    model: str = "claude-opus-4-5",
) -> str:
    """General-purpose AI query with knowledge base context.

    Returns the response text, or empty string if AI unavailable.
    """
    if not is_ai_available() and not api_key:
        return ""
    try:
        from armory.loader import load_class, load_all_classes

        # Build context
        context_parts = []
        if class_slug:
            cls = load_class(class_slug)
            if cls:
                context_parts.append(
                    f"Vulnerability class: {cls.get('name', class_slug)}\n"
                    f"Description: {cls.get('description', '')}"
                )
                if group_slug:
                    for g in cls.get("groups", []):
                        if g.get("slug") == group_slug:
                            context_parts.append(
                                f"Attack group: {g.get('name', group_slug)}\n"
                                f"Description: {g.get('description', '')}"
                            )
                            payload_titles = [p.get("title") for p in g.get("payloads", [])]
                            context_parts.append(
                                f"Payloads in this group: {', '.join(payload_titles)}"
                            )
                            break
        else:
            classes = load_all_classes()
            class_names = [c.get("name", c.get("slug", "")) for c in classes]
            context_parts.append(f"Available vulnerability classes: {', '.join(class_names)}")

        if context_payloads:
            payload_summary = "\n".join(
                f"- {p.get('title', '')}: {p.get('payload_string', '')[:50]}"
                for p in context_payloads[:10]
            )
            context_parts.append(f"Relevant payloads:\n{payload_summary}")

        kb_context = "\n\n".join(context_parts) if context_parts else "Full knowledge base available."

        prompt = (
            f"You are answering questions about penetration testing techniques using "
            f"the Armory knowledge base.\n\n"
            f"Knowledge base context:\n{kb_context}\n\n"
            f"Question: {question}"
        )
        ck = _make_cache_key(prompt, model)
        cached = _get_cached(ck)
        if cached:
            return cached

        client = _get_client(api_key)
        response = client.messages.create(
            model=model,
            max_tokens=2048,
            system=[{
                "type": "text",
                "text": "You are an expert penetration tester and security researcher with "
                        "deep knowledge of offensive security techniques. Provide accurate, "
                        "practical answers. "
                        "Do not over-claim effectiveness or generate real exploits for unauthorized systems.",
                "cache_control": {"type": "ephemeral"},
            }],
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text
        _save_cache(ck, hashlib.sha256(prompt.encode()).hexdigest(), text, model)
        return text
    except Exception as e:
        return f"[AI error: {e}]"
