import json
import tempfile
import unittest
from pathlib import Path

from spotify_automation.gpt_recommender import (
    GPTRecommendation,
    GPTRequestBuilder,
    GPTResponseParser,
    RecommendationContext,
    RulePreferences,
    TrackCandidate,
    log_recommendations,
    merge_gpt_recommendations,
    run_gpt_recommender,
)


class GPTRecommenderTests(unittest.TestCase):
    def setUp(self):
        self.context = RecommendationContext(
            user_profile={"mood": "energetic mornings"},
            rules={"banned_artists": ["the killers"]},
            listening_history=[
                TrackCandidate(track_id="hist1", title="Song A", artist="Artist A"),
                TrackCandidate(
                    track_id="hist2",
                    title="Song B",
                    artist="Artist B",
                    energy_tag="monday",
                ),
            ],
            track_pool=[
                TrackCandidate(
                    track_id="cand1",
                    title="Pool Song",
                    artist="Pool Artist",
                    energy_tag="tuesday",
                ),
                TrackCandidate(track_id="cand2", title="Cut", artist="Another"),
            ],
            rule_preferences=RulePreferences(
                banned_artists=["the killers"],
                reduce_frequency_artists=["Artist B"],
                increase_weight_artists=["Pool Artist"],
            ),
        )

    def test_request_builder_formats_prompt(self):
        builder = GPTRequestBuilder(
            self.context,
            playlist_name="My Daily DJ",
            timezone_hint="UTC",
        )
        prompt = builder.build(discovery_target=2, total_tracks=20)

        self.assertIn('playlist called "My Daily DJ"', prompt)
        self.assertIn("- mood: energetic mornings", prompt)
        self.assertIn("recommendations", prompt)
        self.assertIn("Return ONLY valid JSON", prompt)

    def test_response_parser_handles_json(self):
        parser = GPTResponseParser()
        response = """
        ```json
        {
            "recommendations": [
                {
                    "title": "Discovery",
                    "artist": "Fresh Artist",
                    "reason": "Matches upbeat vibe",
                    "spotify_track_id": "cand1",
                    "energy_tag": "friday",
                    "confidence": 0.73
                }
            ]
        }
        ```
        """
        recs = parser.parse(response)
        self.assertEqual(len(recs), 1)
        self.assertEqual(recs[0].artist, "Fresh Artist")
        self.assertAlmostEqual(recs[0].confidence, 0.73)
        self.assertEqual(recs[0].energy_tag, "friday")

    def test_merge_gpt_recommendations_prefers_discovery(self):
        base_tracks = [
            TrackCandidate(
                track_id="base1", title="Base Song 1", artist="Base Artist 1"
            ),
            TrackCandidate(
                track_id="base2", title="Base Song 2", artist="Base Artist 2"
            ),
        ]
        track_pool = base_tracks + [
            TrackCandidate(
                track_id="cand1", title="Discovery Song", artist="Pool Artist"
            ),
        ]
        gpt_recs = [
            GPTRecommendation(
                title="Discovery Song",
                artist="Pool Artist",
                reason="Adds variety",
                spotify_track_id="cand1",
                confidence=0.9,
            )
        ]

        final_tracks, warnings = merge_gpt_recommendations(
            base_tracks=base_tracks,
            track_pool=track_pool,
            gpt_recommendations=gpt_recs,
            total_limit=2,
            discovery_ratio=0.5,
        )

        self.assertEqual(len(final_tracks), 2)
        self.assertEqual(final_tracks[0].track_id, "cand1")
        self.assertFalse(warnings)

    def test_merge_applies_rule_preferences(self):
        prefs = RulePreferences(
            increase_weight_artists=["Another"],
            reduce_frequency_artists=["Pool Artist"],
        )
        base_tracks = [
            TrackCandidate(track_id="base1", title="Base Song 1", artist="Pool Artist"),
            TrackCandidate(track_id="base2", title="Fav", artist="Another"),
        ]
        final_tracks, _ = merge_gpt_recommendations(
            base_tracks=base_tracks,
            track_pool=base_tracks,
            gpt_recommendations=[],
            total_limit=2,
            discovery_ratio=0.0,
            rule_preferences=prefs,
        )
        self.assertEqual(final_tracks[0].artist, "Another")

    def test_log_recommendations_appends_jsonl(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "history.jsonl"
            tracks = [
                TrackCandidate(
                    track_id="track1",
                    title="Song",
                    artist="Artist",
                    metadata={"gpt_reason": "test"},
                )
            ]
            log_recommendations(tracks, path, run_label="unit-test")
            contents = path.read_text().strip().splitlines()
            self.assertEqual(len(contents), 1)
            payload = json.loads(contents[0])
            self.assertEqual(payload["track_id"], "track1")
            self.assertEqual(payload["run_label"], "unit-test")

    def test_run_gpt_recommender_flow(self):
        class DummyClient:
            def __init__(self, payload: str):
                self.payload = payload
                self.prompt = None

            def complete(self, prompt: str) -> str:
                self.prompt = prompt
                return self.payload

        base_tracks = [
            TrackCandidate(track_id="cand1", title="Pool Song", artist="Pool Artist"),
            TrackCandidate(track_id="cand2", title="Cut", artist="Another"),
        ]
        payload = json.dumps(
            {
                "recommendations": [
                    {
                        "title": "Pool Song",
                        "artist": "Pool Artist",
                        "spotify_track_id": "cand1",
                        "reason": "Still fresh",
                        "confidence": 0.9,
                    }
                ]
            }
        )
        client = DummyClient(payload)
        result = run_gpt_recommender(
            context=self.context,
            base_tracks=base_tracks,
            playlist_name="My Daily DJ",
            timezone_hint="UTC",
            total_limit=2,
            discovery_ratio=0.5,
            completion_client=client,
        )
        self.assertEqual(len(result.tracks), 2)
        self.assertTrue(result.gpt_recommendations)
        self.assertFalse(result.warnings)
        self.assertIn("playlist called \"My Daily DJ\"", client.prompt)


if __name__ == "__main__":
    unittest.main()
