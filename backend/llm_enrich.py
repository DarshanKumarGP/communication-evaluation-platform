"""
llm_enrich.py
------------------------------------------------------------
OPTIONAL enhancement layer. The requirements doc recommends an
"LLM API/model" for conversation generation and rubric-based content
evaluation (Section 11), but does not mandate it - the rubric engine
in scoring.py already satisfies every stated requirement on its own
and needs no internet access or API key.

If you want more natural, free-text recruiter feedback instead of
(or alongside) the deterministic rubric feedback, you can enable this
module:

    1. `pip install anthropic`
    2. `export ANTHROPIC_API_KEY=sk-ant-...`
    3. `export ENABLE_LLM_FEEDBACK=1`

When disabled (the default), `enrich_feedback()` simply returns the
rubric-generated strengths/improvements unchanged, so the platform
always works standalone.
"""

import os


def llm_enabled():
    return os.environ.get("ENABLE_LLM_FEEDBACK") == "1" and bool(
        os.environ.get("ANTHROPIC_API_KEY")
    )


def enrich_feedback(strengths, improvements, transcript_snippets):
    """
    Optionally turns the rubric's bullet-point strengths/improvements
    into a short natural-language recruiter summary using Claude.
    Falls back to the rubric bullets untouched on any error, so a
    missing key, no network, or an API hiccup never breaks the
    assessment flow.
    """
    if not llm_enabled():
        return None  # caller keeps using the rubric bullets as-is

    try:
        import anthropic  # imported lazily - optional dependency

        client = anthropic.Anthropic()
        joined_transcript = "\n".join(transcript_snippets)[:4000]
        prompt = (
            "You are helping a recruiter review a candidate communication "
            "assessment. Based on the rubric findings below, write a "
            "2-3 sentence natural-language summary for the recruiter. "
            "Do not invent facts beyond what's given.\n\n"
            f"Strengths noted: {strengths}\n"
            f"Improvements noted: {improvements}\n\n"
            f"Transcript excerpts:\n{joined_transcript}"
        )
        resp = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
        )
        text_blocks = [b.text for b in resp.content if getattr(b, "type", "") == "text"]
        return "\n".join(text_blocks).strip() or None
    except Exception:
        return None
