"""
database.py
------------------------------------------------------------
Lightweight SQLite persistence layer (Section 11 recommends
PostgreSQL or SQLite for MVP - SQLite requires zero setup, so it is
used here; swapping to PostgreSQL later only requires changing the
connection function).
"""

import sqlite3
import json
import os
import uuid
from datetime import datetime, timezone

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "assessment.db")


def _now():
    return datetime.now(timezone.utc).isoformat()


def get_conn():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_conn()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            candidate_name TEXT,
            stage TEXT NOT NULL,
            status TEXT NOT NULL,
            duration_target_min INTEGER DEFAULT 8,
            started_at TEXT NOT NULL,
            completed_at TEXT
        );

        CREATE TABLE IF NOT EXISTS responses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            stage TEXT NOT NULL,
            question TEXT,
            transcript TEXT,
            input_mode TEXT,
            audio_features TEXT,
            analysis TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (session_id) REFERENCES sessions(id)
        );

        CREATE TABLE IF NOT EXISTS results (
            session_id TEXT PRIMARY KEY,
            pitch_score REAL,
            vocabulary_score REAL,
            tonality_score REAL,
            overall_score_10 REAL,
            overall_score_30 REAL,
            overall_percentage REAL,
            strengths TEXT,
            improvements TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (session_id) REFERENCES sessions(id)
        );
        """
    )
    conn.commit()
    conn.close()


def create_session(candidate_name, stage, duration_target_min=8):
    session_id = str(uuid.uuid4())
    conn = get_conn()
    conn.execute(
        "INSERT INTO sessions (id, candidate_name, stage, status, "
        "duration_target_min, started_at) VALUES (?, ?, ?, ?, ?, ?)",
        (session_id, candidate_name, stage, "in_progress",
         duration_target_min, _now()),
    )
    conn.commit()
    conn.close()
    return session_id


def get_session(session_id):
    conn = get_conn()
    row = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def update_session_stage(session_id, stage, status="in_progress"):
    conn = get_conn()
    completed_at = _now() if status == "completed" else None
    conn.execute(
        "UPDATE sessions SET stage = ?, status = ?, "
        "completed_at = COALESCE(?, completed_at) WHERE id = ?",
        (stage, status, completed_at, session_id),
    )
    conn.commit()
    conn.close()


def add_response(session_id, stage, question, transcript, input_mode,
                  audio_features, analysis):
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO responses (session_id, stage, question, transcript, "
        "input_mode, audio_features, analysis, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            session_id, stage, question, transcript, input_mode,
            json.dumps(audio_features) if audio_features else None,
            json.dumps(analysis) if analysis else None,
            _now(),
        ),
    )
    conn.commit()
    response_id = cur.lastrowid
    conn.close()
    return response_id


def get_responses(session_id):
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM responses WHERE session_id = ? ORDER BY id ASC",
        (session_id,),
    ).fetchall()
    conn.close()
    out = []
    for r in rows:
        d = dict(r)
        d["audio_features"] = json.loads(d["audio_features"]) if d["audio_features"] else None
        d["analysis"] = json.loads(d["analysis"]) if d["analysis"] else None
        out.append(d)
    return out


def save_result(session_id, result):
    conn = get_conn()
    conn.execute(
        "INSERT INTO results (session_id, pitch_score, vocabulary_score, "
        "tonality_score, overall_score_10, overall_score_30, "
        "overall_percentage, strengths, improvements, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(session_id) DO UPDATE SET "
        "pitch_score=excluded.pitch_score, "
        "vocabulary_score=excluded.vocabulary_score, "
        "tonality_score=excluded.tonality_score, "
        "overall_score_10=excluded.overall_score_10, "
        "overall_score_30=excluded.overall_score_30, "
        "overall_percentage=excluded.overall_percentage, "
        "strengths=excluded.strengths, improvements=excluded.improvements",
        (
            session_id, result["pitch_score"], result["vocabulary_score"],
            result["tonality_score"], result["overall_score_10"],
            result["overall_score_30"], result["overall_percentage"],
            json.dumps(result["strengths"]), json.dumps(result["improvements"]),
            _now(),
        ),
    )
    conn.commit()
    conn.close()


def get_result(session_id):
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM results WHERE session_id = ?", (session_id,)
    ).fetchone()
    conn.close()
    if not row:
        return None
    d = dict(row)
    d["strengths"] = json.loads(d["strengths"]) if d["strengths"] else []
    d["improvements"] = json.loads(d["improvements"]) if d["improvements"] else []
    return d


def list_sessions():
    conn = get_conn()
    rows = conn.execute(
        "SELECT id, candidate_name, stage, status, started_at, completed_at "
        "FROM sessions ORDER BY started_at DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
