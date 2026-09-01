"""
scoring.py
------------------------------------------------------------
Rubric-based Communication Evaluation Engine.

This module scores a candidate's spoken/typed response on the three
parameters explicitly requested by the interviewer:

    1. Pitch / Self-Presentation
    2. Vocabulary
    3. Tonality (derived from audio signal features captured in the
       browser, NOT from the transcript alone)

Design notes
------------
* No external network calls are required for this engine to work -
  it is a deterministic, explainable rubric so that two candidates
  are always scored consistently (Section 13 of the requirements doc).
* An OPTIONAL "LLM enrichment" hook (see llm_enrich.py) can be wired
  in to turn the rubric output into more natural free-text feedback,
  or to double check the rubric score with a language model. The
  platform runs correctly with or without it (Section 16 asks for
  automated vs. human-reviewed calibration before trusting scores
  blindly, so a deterministic baseline is the safer default).
* Regional-accent fairness (Section 10): tonality scoring never
  penalises pitch/frequency register or accent-linked pronunciation.
  It only scores clarity/energy-consistency, pace, and confidence
  proxies (pause ratio, filler ratio) which are accent-neutral.
"""

import re
import statistics
from collections import Counter

# --------------------------------------------------------------------------
# Reference word lists (kept intentionally small & transparent so the
# rubric is auditable - this is an MVP heuristic, see README/PROJECT_REPORT
# for validation guidance before using this in a real hiring decision).
# --------------------------------------------------------------------------

FILLER_WORDS = {
    "um", "uh", "umm", "uhh", "erm", "hmm", "like", "actually", "basically",
    "literally", "you know", "i mean", "sort of", "kind of", "so yeah",
}

HEDGE_WORDS = {
    "maybe", "probably", "i think", "i guess", "not sure", "possibly",
    "kind of", "sort of", "i suppose", "perhaps",
}

GREETING_MARKERS = {
    "hello", "hi", "good morning", "good afternoon", "good evening",
    "greetings", "dear", "hey there",
}

SELF_INTRO_MARKERS = {
    "my name is", "i am", "i'm", "this is", "myself", "i work as",
    "i work at", "i represent", "calling from", "reaching out from",
}

PURPOSE_MARKERS = {
    "i wanted to", "i am reaching out", "i'm reaching out", "the reason",
    "purpose of", "regarding", "in relation to", "i need", "we need",
    "we are looking for", "we require", "requirement", "following up",
}

PROFESSIONAL_VOCAB = {
    "requirement", "proposal", "budget", "timeline", "quotation", "vendor",
    "deliverable", "quality", "specification", "specifications", "pricing",
    "procurement", "collaborate", "partnership", "stakeholder", "priority",
    "priorities", "expectation", "expectations", "schedule", "invoice",
    "negotiate", "agreement", "contract", "scope", "milestone", "feedback",
    "efficient", "professional", "experience", "solution", "strategy",
    "opportunity", "coordinate", "confirm", "clarify", "assist", "support",
    "product", "service", "client", "customer", "team", "project", "manage",
    "organize", "communicate", "resolve", "follow up", "update",
}

CLOSING_MARKERS = {
    "thank you", "thanks", "look forward", "talk soon", "regards",
    "best regards", "appreciate", "let me know", "have a great day",
}

_SENTENCE_SPLIT_RE = re.compile(r"[.!?]+")
_WORD_RE = re.compile(r"[A-Za-z']+")


def _words(text):
    return _WORD_RE.findall(text.lower())


def _contains_any(text_lower, phrase_set):
    return any(p in text_lower for p in phrase_set)


def _count_any(text_lower, phrase_set):
    return sum(text_lower.count(p) for p in phrase_set)


def _clamp(value, lo=0.0, hi=10.0):
    return max(lo, min(hi, value))


# --------------------------------------------------------------------------
# 1) VOCABULARY SCORING
# --------------------------------------------------------------------------

def score_vocabulary(transcript):
    """
    Returns (score_0_to_10: float, details: dict)

    Heuristics used (transparent & explainable, per Section 13):
      - Lexical diversity (type-token ratio) -> variety of words used
      - Average word length -> proxy for word sophistication
      - Professional/business vocabulary hits -> domain-appropriate wording
      - Filler-word ratio -> penalises "um / like / basically" overuse
      - Response length sanity check -> very short answers are graded only
        on observable evidence, never penalised beyond what's observable
        (Section 15, "very short answer" edge case)
    """
    text = (transcript or "").strip()
    words = _words(text)
    text_lower = text.lower()

    if len(words) == 0:
        return 0.0, {
            "note": "No speech/text content detected.",
            "word_count": 0,
        }

    word_count = len(words)
    unique_words = set(words)
    ttr = len(unique_words) / word_count  # type-token ratio, 0..1

    avg_word_len = statistics.mean(len(w) for w in words)

    prof_hits = sum(1 for term in PROFESSIONAL_VOCAB if term in text_lower)
    prof_density = prof_hits / max(1, word_count / 20)  # per ~20 words

    filler_hits = _count_any(text_lower, FILLER_WORDS)
    filler_ratio = filler_hits / word_count

    # --- combine into a 0-10 score ---
    diversity_score = _clamp(ttr * 12)          # rewards varied vocabulary
    length_bonus = _clamp((min(word_count, 60) / 60) * 10)
    prof_score = _clamp(prof_density * 3)
    filler_penalty = _clamp(filler_ratio * 25)
    wordlen_score = _clamp((avg_word_len - 3.2) * 4)

    raw = (
        0.30 * diversity_score
        + 0.20 * length_bonus
        + 0.25 * prof_score
        + 0.15 * wordlen_score
        + 0.10 * 10  # baseline
    ) - filler_penalty

    # Very short answers: score only observable evidence, don't over-punish
    if word_count < 8:
        raw = min(raw, 5.0)

    score = round(_clamp(raw), 1)

    return score, {
        "word_count": word_count,
        "unique_words": len(unique_words),
        "lexical_diversity_ttr": round(ttr, 2),
        "avg_word_length": round(avg_word_len, 2),
        "professional_terms_used": prof_hits,
        "filler_word_count": filler_hits,
    }


# --------------------------------------------------------------------------
# 2) PITCH / SELF-PRESENTATION SCORING
# --------------------------------------------------------------------------

def score_pitch(transcript, stage="scenario"):
    """
    Returns (score_0_to_10: float, details: dict)

    stage = "intro"     -> greeting/self-introduction test (Section 5.1)
    stage = "scenario"  -> vendor/professional communication test (5.2)

    Heuristics used:
      - Greeting present (professional opening)
      - Self-introduction present ("my name is / I am ...")
      - Purpose/requirement clearly stated (only weighted for scenario stage)
      - Structure: multiple sentences (not a single run-on fragment)
      - Confidence proxy: low hedge-word ratio
      - Closing / next-step present (professional wrap-up)
    """
    text = (transcript or "").strip()
    text_lower = text.lower()
    words = _words(text)
    sentences = [s for s in _SENTENCE_SPLIT_RE.split(text) if s.strip()]

    if len(words) == 0:
        return 0.0, {"note": "No speech/text content detected."}

    has_greeting = _contains_any(text_lower, GREETING_MARKERS)
    has_intro = _contains_any(text_lower, SELF_INTRO_MARKERS)
    has_purpose = _contains_any(text_lower, PURPOSE_MARKERS)
    has_closing = _contains_any(text_lower, CLOSING_MARKERS)

    hedge_hits = _count_any(text_lower, HEDGE_WORDS)
    hedge_ratio = hedge_hits / max(1, len(words))

    structure_score = _clamp(min(len(sentences), 4) * 2.2)
    confidence_score = _clamp(10 - hedge_ratio * 40)

    component_hits = sum([has_greeting, has_intro, has_closing])
    if stage == "scenario":
        component_hits += 1.5 if has_purpose else 0  # purpose matters more here
        max_components = 4.5
    else:
        max_components = 3

    presentation_score = _clamp((component_hits / max_components) * 10)

    raw = (
        0.40 * presentation_score
        + 0.30 * structure_score
        + 0.30 * confidence_score
    )

    if len(words) < 8:
        raw = min(raw, 5.0)

    score = round(_clamp(raw), 1)

    return score, {
        "greeting_present": has_greeting,
        "self_introduction_present": has_intro,
        "purpose_stated": has_purpose,
        "professional_closing_present": has_closing,
        "sentence_count": len(sentences),
        "hedge_word_count": hedge_hits,
    }


# --------------------------------------------------------------------------
# 3) TONALITY SCORING  (from browser-computed audio features)
# --------------------------------------------------------------------------
#
# The frontend performs real-time signal processing on the candidate's
# microphone audio using the Web Audio API (see frontend/app.js ->
# AudioAnalyzer) and sends a compact feature summary instead of raw audio:
#
#   {
#     "duration_sec": float,           total speaking time
#     "avg_volume_rms": float 0..1,    average signal energy
#     "volume_std": float 0..1,        energy consistency (steadiness)
#     "pitch_variance_hz": float,      variation in fundamental frequency
#     "silence_ratio": float 0..1,     proportion of long pauses
#     "words_per_minute": float,       speaking pace (needs transcript+time)
#   }
#
# IMPORTANT (Section 10, India-specific requirement): this rubric never
# scores the *absolute* pitch register or accent - only variance/energy/
# pace/pause characteristics, which are accent-neutral indicators of
# delivery clarity and confidence.

def score_tonality(audio_features):
    if not audio_features:
        return None, {
            "note": "No audio features supplied (text-only fallback was "
                     "used) - tonality was not evaluated for this response."
        }

    duration = audio_features.get("duration_sec", 0) or 0
    avg_vol = audio_features.get("avg_volume_rms", 0) or 0
    vol_std = audio_features.get("volume_std", 0) or 0
    pitch_var = audio_features.get("pitch_variance_hz", 0) or 0
    silence_ratio = audio_features.get("silence_ratio", 0) or 0
    wpm = audio_features.get("words_per_minute", 0) or 0

    if duration < 1:
        return None, {"note": "Recording too short to assess tonality."}

    # Clarity / energy: too quiet (mic too far) or clipping is penalised;
    # sweet-spot band around 0.15 - 0.6 normalised RMS.
    if avg_vol <= 0:
        clarity_score = 0
    else:
        clarity_score = _clamp(10 - abs(avg_vol - 0.35) * 18)

    # Steadiness: some variation is natural/expressive; very high volume
    # variance suggests inconsistent mic distance rather than expressiveness,
    # so we reward a moderate, not minimal, std.
    steadiness_score = _clamp(10 - abs(vol_std - 0.12) * 30)

    # Expressiveness: some pitch variance signals engaged/confident
    # delivery vs. a flat monotone; too much can signal erratic delivery.
    expressiveness_score = _clamp(10 - abs(pitch_var - 25) * 0.25)

    # Pace: 110-160 wpm is a comfortable professional speaking pace.
    if wpm <= 0:
        pace_score = 5.0  # unknown, neutral
    elif 110 <= wpm <= 160:
        pace_score = 10.0
    else:
        pace_score = _clamp(10 - abs(wpm - 135) * 0.09)

    # Pauses: some pausing is natural; excessive long-silence ratio may
    # indicate hesitation.
    pause_score = _clamp(10 - silence_ratio * 14)

    raw = (
        0.25 * clarity_score
        + 0.20 * steadiness_score
        + 0.20 * expressiveness_score
        + 0.20 * pace_score
        + 0.15 * pause_score
    )

    score = round(_clamp(raw), 1)

    return score, {
        "duration_sec": round(duration, 1),
        "avg_volume_rms": round(avg_vol, 3),
        "volume_std": round(vol_std, 3),
        "pitch_variance_hz": round(pitch_var, 1),
        "silence_ratio": round(silence_ratio, 2),
        "words_per_minute": round(wpm, 1),
        "component_scores": {
            "clarity": round(clarity_score, 1),
            "steadiness": round(steadiness_score, 1),
            "expressiveness": round(expressiveness_score, 1),
            "pace": round(pace_score, 1),
            "pause_control": round(pause_score, 1),
        },
    }


# --------------------------------------------------------------------------
# Combined per-response analysis
# --------------------------------------------------------------------------

def analyze_response(transcript, stage, audio_features=None):
    """Runs all three rubric scorers on a single candidate response."""
    pitch_score, pitch_details = score_pitch(transcript, stage=stage)
    vocab_score, vocab_details = score_vocabulary(transcript)
    tonality_score, tonality_details = score_tonality(audio_features)

    word_count = vocab_details.get("word_count", 0)
    low_confidence = word_count > 0 and word_count < 5

    return {
        "pitch": {"score": pitch_score, "details": pitch_details},
        "vocabulary": {"score": vocab_score, "details": vocab_details},
        "tonality": {
            "score": tonality_score,
            "details": tonality_details,
        },
        "low_confidence": low_confidence,
    }


# --------------------------------------------------------------------------
# Aggregate final result across all responses in a session
# --------------------------------------------------------------------------

def aggregate_results(per_response_scores):
    """
    per_response_scores: list of dicts returned by analyze_response()
    Returns final category scores (0-10), an overall score (0-30 and %),
    plus short strengths/improvement bullet text - all generated from the
    rubric evidence (no fabricated content, per Section 15 "off-topic
    answer" / "very short answer" edge cases).
    """
    pitch_vals = [r["pitch"]["score"] for r in per_response_scores if r["pitch"]["score"] is not None]
    vocab_vals = [r["vocabulary"]["score"] for r in per_response_scores if r["vocabulary"]["score"] is not None]
    tonality_vals = [r["tonality"]["score"] for r in per_response_scores if r["tonality"]["score"] is not None]

    def avg(vals):
        return round(statistics.mean(vals), 1) if vals else None

    pitch_final = avg(pitch_vals)
    vocab_final = avg(vocab_vals)
    tonality_final = avg(tonality_vals)

    scored_components = [v for v in (pitch_final, vocab_final, tonality_final) if v is not None]
    overall_10 = round(statistics.mean(scored_components), 1) if scored_components else 0.0
    overall_30 = round(sum(scored_components), 1)
    overall_pct = round((overall_10 / 10) * 100, 1)

    strengths, improvements = _generate_feedback(pitch_final, vocab_final, tonality_final, per_response_scores)

    return {
        "pitch_score": pitch_final,
        "vocabulary_score": vocab_final,
        "tonality_score": tonality_final,
        "overall_score_10": overall_10,
        "overall_score_30": overall_30,
        "overall_percentage": overall_pct,
        "strengths": strengths,
        "improvements": improvements,
    }


def _generate_feedback(pitch, vocab, tonality, per_response_scores):
    strengths = []
    improvements = []

    def bucket(val, label):
        if val is None:
            return
        if val >= 7.5:
            strengths.append(f"Strong {label} throughout the conversation.")
        elif val <= 4.5:
            improvements.append(f"{label.capitalize()} needs improvement.")

    bucket(pitch, "self-presentation and pitching")
    bucket(vocab, "vocabulary and word choice")
    bucket(tonality, "vocal delivery and tonality")

    any_greeting = any(r["pitch"]["details"].get("greeting_present") for r in per_response_scores if "greeting_present" in r["pitch"]["details"])
    any_purpose = any(r["pitch"]["details"].get("purpose_stated") for r in per_response_scores if "purpose_stated" in r["pitch"]["details"])
    total_fillers = sum(r["vocabulary"]["details"].get("filler_word_count", 0) for r in per_response_scores)

    if any_greeting:
        strengths.append("Opened conversations with a professional greeting.")
    if any_purpose:
        strengths.append("Clearly stated the purpose/requirement in the vendor scenario.")
    elif any_purpose is False:
        improvements.append("Should state the purpose of the conversation more explicitly and early.")

    if total_fillers >= 4:
        improvements.append("Reduce filler words (um, like, basically) for a more polished delivery.")

    if not strengths:
        strengths.append("Completed the assessment and engaged with both conversation stages.")
    if not improvements:
        improvements.append("Continue practicing structured, concise professional communication.")

    # de-duplicate while preserving order
    strengths = list(dict.fromkeys(strengths))
    improvements = list(dict.fromkeys(improvements))

    return strengths[:5], improvements[:5]
