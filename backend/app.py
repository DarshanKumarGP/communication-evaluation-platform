"""
app.py
------------------------------------------------------------
Flask backend for the Communication Evaluation Platform.

Implements the API endpoints recommended in Section 14 of the
requirements document:

    POST /assessment/start
    POST /assessment/<id>/response
    POST /assessment/<id>/next
    POST /assessment/<id>/analyze
    GET  /assessment/<id>/result
    GET  /health

Also serves the static frontend (frontend/) so the whole platform can
be run with a single command during evaluation/demo.
"""

import os
from flask import Flask, request, jsonify, send_from_directory

import database
import conversation
import scoring
import llm_enrich

BASE_DIR = os.path.dirname(__file__)
FRONTEND_DIR = os.path.join(BASE_DIR, "..", "frontend")

app = Flask(__name__, static_folder=None)


# ---------------------------------------------------------------------
# Minimal CORS support (no flask_cors dependency needed)
# ---------------------------------------------------------------------
@app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return response


@app.route("/assessment/<path:_any>", methods=["OPTIONS"])
def cors_preflight(_any):
    return "", 204


# ---------------------------------------------------------------------
# Static frontend
# ---------------------------------------------------------------------
@app.route("/")
def serve_index():
    return send_from_directory(FRONTEND_DIR, "index.html")


@app.route("/<path:filename>")
def serve_static(filename):
    if os.path.exists(os.path.join(FRONTEND_DIR, filename)):
        return send_from_directory(FRONTEND_DIR, filename)
    return jsonify({"error": "not found"}), 404


# ---------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------
@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "service": "communication-eval-platform"})


# ---------------------------------------------------------------------
# 1) Start a new assessment session
# ---------------------------------------------------------------------
@app.route("/assessment/start", methods=["POST"])
def start_assessment():
    payload = request.get_json(silent=True) or {}
    candidate_name = (payload.get("candidate_name") or "").strip() or None
    duration_target = int(payload.get("duration_target_min", 8) or 8)

    stage = conversation.first_stage()
    session_id = database.create_session(candidate_name, stage, duration_target)
    bot_message = conversation.get_bot_message(stage, candidate_name)

    return jsonify({
        "session_id": session_id,
        "stage": stage,
        "bot_message": bot_message,
        "is_final": conversation.is_terminal(stage),
    }), 201


# ---------------------------------------------------------------------
# 2) Submit a candidate response for the current stage
#    (this also runs analysis + advances the conversation, so the
#    frontend gets everything it needs in one round trip; /analyze and
#    /next are still exposed separately per the spec for flexibility)
# ---------------------------------------------------------------------
@app.route("/assessment/<session_id>/response", methods=["POST"])
def submit_response(session_id):
    session = database.get_session(session_id)
    if not session:
        return jsonify({"error": "session not found"}), 404
    if session["status"] == "completed":
        return jsonify({"error": "session already completed"}), 400

    payload = request.get_json(silent=True) or {}
    transcript = (payload.get("transcript") or "").strip()
    input_mode = payload.get("input_mode", "text")  # "voice" or "text"
    audio_features = payload.get("audio_features")  # optional dict

    current_stage = session["stage"]
    scoring_context = conversation.scoring_context_for(current_stage)

    if not transcript:
        analysis = {
            "pitch": {"score": 0.0, "details": {"note": "Empty response."}},
            "vocabulary": {"score": 0.0, "details": {"note": "Empty response."}},
            "tonality": {"score": None, "details": {"note": "Empty response."}},
            "low_confidence": True,
        }
    else:
        analysis = scoring.analyze_response(
            transcript, scoring_context, audio_features
        )

    question_text = conversation.get_bot_message(current_stage, session["candidate_name"])
    database.add_response(
        session_id, current_stage, question_text, transcript,
        input_mode, audio_features, analysis,
    )

    nxt = conversation.next_stage(current_stage)
    is_final = conversation.is_terminal(nxt)
    database.update_session_stage(
        session_id, nxt, status="completed" if is_final else "in_progress"
    )

    bot_message = conversation.get_bot_message(nxt, session["candidate_name"])

    result_summary = None
    if is_final:
        result_summary = _compute_and_store_result(session_id)

    return jsonify({
        "session_id": session_id,
        "analysis": analysis,
        "next_stage": nxt,
        "bot_message": bot_message,
        "is_final": is_final,
        "result": result_summary,
    })


# ---------------------------------------------------------------------
# 3) Explicitly fetch the next chatbot prompt (spec Section 14)
# ---------------------------------------------------------------------
@app.route("/assessment/<session_id>/next", methods=["POST"])
def next_prompt(session_id):
    session = database.get_session(session_id)
    if not session:
        return jsonify({"error": "session not found"}), 404

    stage = session["stage"]
    bot_message = conversation.get_bot_message(stage, session["candidate_name"])
    return jsonify({
        "session_id": session_id,
        "stage": stage,
        "bot_message": bot_message,
        "is_final": conversation.is_terminal(stage),
    })


# ---------------------------------------------------------------------
# 4) Explicitly analyze an arbitrary transcript against the rubric
#    (useful for testing / recruiter "what-if" checks, spec Section 14)
# ---------------------------------------------------------------------
@app.route("/assessment/<session_id>/analyze", methods=["POST"])
def analyze_only(session_id):
    session = database.get_session(session_id)
    if not session:
        return jsonify({"error": "session not found"}), 404

    payload = request.get_json(silent=True) or {}
    transcript = (payload.get("transcript") or "").strip()
    audio_features = payload.get("audio_features")
    stage = payload.get("stage") or conversation.scoring_context_for(session["stage"])

    analysis = scoring.analyze_response(transcript, stage, audio_features)
    return jsonify({"session_id": session_id, "analysis": analysis})


# ---------------------------------------------------------------------
# 5) Final result for a recruiter to review
# ---------------------------------------------------------------------
@app.route("/assessment/<session_id>/result", methods=["GET"])
def get_result(session_id):
    session = database.get_session(session_id)
    if not session:
        return jsonify({"error": "session not found"}), 404

    result = database.get_result(session_id)
    if not result:
        if session["status"] != "completed":
            return jsonify({
                "error": "assessment not completed yet",
                "stage": session["stage"],
            }), 400
        result = _compute_and_store_result(session_id)

    responses = database.get_responses(session_id)
    transcript_log = [
        {
            "stage": r["stage"],
            "question": r["question"],
            "transcript": r["transcript"],
            "input_mode": r["input_mode"],
        }
        for r in responses
    ]

    return jsonify({
        "session_id": session_id,
        "candidate_name": session["candidate_name"],
        "started_at": session["started_at"],
        "completed_at": session["completed_at"],
        "pitch_score": result["pitch_score"],
        "vocabulary_score": result["vocabulary_score"],
        "tonality_score": result["tonality_score"],
        "overall_score_10": result["overall_score_10"],
        "overall_score_30": result["overall_score_30"],
        "overall_percentage": result["overall_percentage"],
        "strengths": result["strengths"],
        "improvements": result["improvements"],
        "transcript": transcript_log,
        "llm_summary": llm_enrich.enrich_feedback(
            result["strengths"], result["improvements"],
            [t["transcript"] for t in transcript_log if t["transcript"]],
        ),
    })


# ---------------------------------------------------------------------
# Recruiter view: list all sessions (simple dashboard support)
# ---------------------------------------------------------------------
@app.route("/assessment/list", methods=["GET"])
def list_all():
    return jsonify({"sessions": database.list_sessions()})


def _compute_and_store_result(session_id):
    responses = database.get_responses(session_id)
    analyses = [r["analysis"] for r in responses if r["analysis"]]
    result = scoring.aggregate_results(analyses)
    database.save_result(session_id, result)
    return result


if __name__ == "__main__":
    database.init_db()
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.run(host="0.0.0.0", port=port, debug=debug)
