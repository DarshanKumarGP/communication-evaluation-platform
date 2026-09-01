"""
Integration tests for app.py — run with:  python3 -m unittest discover -s tests
Uses Flask's built-in test client, no live server or network required.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import database  # noqa: E402
import app as flask_app_module  # noqa: E402


class TestAssessmentAPI(unittest.TestCase):
    def setUp(self):
        # isolate test DB
        self._orig_db_path = database.DB_PATH
        database.DB_PATH = os.path.join(os.path.dirname(__file__), "test_assessment.db")
        if os.path.exists(database.DB_PATH):
            os.remove(database.DB_PATH)
        database.init_db()
        self.client = flask_app_module.app.test_client()

    def tearDown(self):
        if os.path.exists(database.DB_PATH):
            os.remove(database.DB_PATH)
        database.DB_PATH = self._orig_db_path

    def test_health_check(self):
        resp = self.client.get("/health")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["status"], "ok")

    def test_start_session_returns_greeting_stage(self):
        resp = self.client.post("/assessment/start", json={"candidate_name": "Asha"})
        self.assertEqual(resp.status_code, 201)
        data = resp.get_json()
        self.assertEqual(data["stage"], "greeting")
        self.assertIn("session_id", data)
        self.assertFalse(data["is_final"])

    def test_unknown_session_returns_404(self):
        resp = self.client.post("/assessment/does-not-exist/response", json={"transcript": "hi"})
        self.assertEqual(resp.status_code, 404)

    def test_full_conversation_completes_and_produces_result(self):
        start = self.client.post("/assessment/start", json={"candidate_name": "Rohit"})
        sid = start.get_json()["session_id"]

        answers = [
            "Hello, my name is Rohit and I work in business development.",
            "Good morning, this is Rohit calling from Acme regarding our product requirement.",
            "We need 500 units, our budget is around one lakh, timeline is three weeks.",
            "Could we start with a partial order to meet our first deadline?",
            "Thank you for your time today, I'll follow up with the quotation request.",
        ]
        last = None
        for a in answers:
            last = self.client.post(
                f"/assessment/{sid}/response",
                json={"transcript": a, "input_mode": "text"},
            )
            self.assertEqual(last.status_code, 200)

        self.assertTrue(last.get_json()["is_final"])

        result = self.client.get(f"/assessment/{sid}/result")
        self.assertEqual(result.status_code, 200)
        rd = result.get_json()
        self.assertIn("overall_score_10", rd)
        self.assertIn("pitch_score", rd)
        self.assertIn("vocabulary_score", rd)
        self.assertEqual(len(rd["transcript"]), 5)

    def test_result_before_completion_returns_400(self):
        start = self.client.post("/assessment/start", json={})
        sid = start.get_json()["session_id"]
        result = self.client.get(f"/assessment/{sid}/result")
        self.assertEqual(result.status_code, 400)

    def test_empty_transcript_is_handled_gracefully(self):
        start = self.client.post("/assessment/start", json={})
        sid = start.get_json()["session_id"]
        resp = self.client.post(f"/assessment/{sid}/response", json={"transcript": "", "input_mode": "text"})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.get_json()["analysis"]["low_confidence"])

    def test_list_sessions_endpoint(self):
        self.client.post("/assessment/start", json={"candidate_name": "A"})
        self.client.post("/assessment/start", json={"candidate_name": "B"})
        resp = self.client.get("/assessment/list")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.get_json()["sessions"]), 2)

    def test_analyze_endpoint_standalone(self):
        start = self.client.post("/assessment/start", json={})
        sid = start.get_json()["session_id"]
        resp = self.client.post(
            f"/assessment/{sid}/analyze",
            json={"transcript": "Hello, my name is Test.", "stage": "intro"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn("pitch", resp.get_json()["analysis"])


if __name__ == "__main__":
    unittest.main()
