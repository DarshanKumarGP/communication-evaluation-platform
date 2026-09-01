"""
Unit tests for scoring.py — run with:  python3 -m unittest discover -s tests
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import scoring  # noqa: E402


class TestVocabularyScoring(unittest.TestCase):
    def test_empty_response_scores_zero(self):
        score, details = scoring.score_vocabulary("")
        self.assertEqual(score, 0.0)
        self.assertEqual(details["word_count"], 0)

    def test_strong_professional_response_scores_high(self):
        text = (
            "Good morning, I wanted to discuss the requirement, timeline, "
            "and budget for this procurement so we can finalize a fair "
            "agreement and coordinate the delivery schedule."
        )
        score, details = scoring.score_vocabulary(text)
        self.assertGreater(score, 6.0)
        self.assertGreater(details["professional_terms_used"], 2)

    def test_filler_heavy_response_scores_lower_than_clean(self):
        clean = "I would like to discuss the product requirement and timeline with you."
        filler = "um like I would like to um discuss the like requirement and um timeline"
        clean_score, _ = scoring.score_vocabulary(clean)
        filler_score, _ = scoring.score_vocabulary(filler)
        self.assertLess(filler_score, clean_score)


class TestPitchScoring(unittest.TestCase):
    def test_empty_response_scores_zero(self):
        score, _ = scoring.score_pitch("", stage="intro")
        self.assertEqual(score, 0.0)

    def test_greeting_and_intro_boost_score(self):
        weak = "yeah so I dont know what to say"
        strong = "Hello, my name is Arjun and I am a sales executive with four years of experience."
        weak_score, _ = scoring.score_pitch(weak, stage="intro")
        strong_score, _ = scoring.score_pitch(strong, stage="intro")
        self.assertGreater(strong_score, weak_score)

    def test_scenario_rewards_stated_purpose(self):
        text = (
            "Good morning, this is Arjun calling from Nexa Corp. I am "
            "reaching out regarding our requirement for office furniture. "
            "Could we discuss pricing and timeline? Thank you."
        )
        score, details = scoring.score_pitch(text, stage="scenario")
        self.assertTrue(details["purpose_stated"])
        self.assertGreater(score, 6.0)


class TestTonalityScoring(unittest.TestCase):
    def test_no_audio_features_returns_none(self):
        score, details = scoring.score_tonality(None)
        self.assertIsNone(score)
        self.assertIn("note", details)

    def test_ideal_features_score_high(self):
        features = {
            "duration_sec": 30, "avg_volume_rms": 0.35, "volume_std": 0.12,
            "pitch_variance_hz": 25, "silence_ratio": 0.1,
            "words_per_minute": 135,
        }
        score, _ = scoring.score_tonality(features)
        self.assertGreaterEqual(score, 8.0)

    def test_poor_features_score_low(self):
        features = {
            "duration_sec": 20, "avg_volume_rms": 0.02, "volume_std": 0.35,
            "pitch_variance_hz": 2, "silence_ratio": 0.6,
            "words_per_minute": 50,
        }
        score, _ = scoring.score_tonality(features)
        self.assertLess(score, 5.0)

    def test_too_short_recording_returns_none(self):
        score, details = scoring.score_tonality({"duration_sec": 0.4})
        self.assertIsNone(score)


class TestAggregation(unittest.TestCase):
    def test_aggregate_produces_overall_scores(self):
        r1 = scoring.analyze_response(
            "Hello, my name is Test. I am reaching out regarding our "
            "requirement for supplies. Thank you for your time.",
            "scenario",
            {"duration_sec": 20, "avg_volume_rms": 0.3, "volume_std": 0.1,
             "pitch_variance_hz": 20, "silence_ratio": 0.1, "words_per_minute": 120},
        )
        r2 = scoring.analyze_response(
            "We need about 100 units, budget is flexible, timeline is two weeks.",
            "scenario",
            {"duration_sec": 15, "avg_volume_rms": 0.28, "volume_std": 0.1,
             "pitch_variance_hz": 18, "silence_ratio": 0.12, "words_per_minute": 118},
        )
        result = scoring.aggregate_results([r1, r2])
        self.assertIsNotNone(result["overall_score_10"])
        self.assertTrue(0 <= result["overall_percentage"] <= 100)
        self.assertTrue(len(result["strengths"]) >= 1)
        self.assertTrue(len(result["improvements"]) >= 1)

    def test_aggregate_handles_no_tonality_data(self):
        r1 = scoring.analyze_response("Hello my name is Test, nice to meet you.", "intro", None)
        result = scoring.aggregate_results([r1])
        self.assertIsNone(result["tonality_score"])
        self.assertIsNotNone(result["pitch_score"])
        self.assertIsNotNone(result["vocabulary_score"])


if __name__ == "__main__":
    unittest.main()
