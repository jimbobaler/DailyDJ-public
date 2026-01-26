import json
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from spotify_automation.taste_profile import (
    apply_constraints,
    is_hard_banned,
    load_taste_profile,
    normalize_text,
    score_track,
)
from spotify_automation.gpt_recommender import TrackCandidate


class TasteProfileTests(unittest.TestCase):
    def setUp(self):
        self.profile = {
            "hard_bans": {"artists": ["florence and the machine"], "tracks": []},
            "avoid": {"artists": ["arctic monkeys"], "tracks": []},
            "boost": {"artists": ["weezer"], "tracks": []},
            "constraints": {
                "max_tracks_per_artist": 1,
                "cooldown_days_same_track": 30,
                "cooldown_days_same_artist": 10,
            },
            "vibe_tags": [],
            "modes": {},
        }
        self.feedback_state = {
            "artist_last_seen": {},
            "track_last_seen": {},
        }

    def test_normalize_text(self):
        self.assertIn("florence and the machine", normalize_text("Florence + The Machine"))

    def test_hard_ban_artist(self):
        self.assertTrue(is_hard_banned("Florence + The Machine", "Dog Days Are Over", self.profile))
        self.assertFalse(is_hard_banned("Weezer", "Buddy Holly", self.profile))

    def test_constraints_max_per_artist(self):
        now = datetime.utcnow()
        tracks = [
            TrackCandidate(track_id="t1", title="Song1", artist="Weezer"),
            TrackCandidate(track_id="t2", title="Song2", artist="Weezer"),
            TrackCandidate(track_id="t3", title="Song3", artist="Other"),
        ]
        filtered = apply_constraints(tracks, self.profile, self.feedback_state, now)
        self.assertEqual(len(filtered), 2)
        self.assertEqual(filtered[0].artist, "Weezer")
        self.assertEqual(filtered[1].artist, "Other")

    def test_score_track_boosts(self):
        now = datetime.utcnow()
        track = TrackCandidate(track_id="t1", title="Song", artist="Weezer")
        score = score_track(track, self.profile, self.feedback_state, now)
        self.assertGreater(score, 0)

    def test_cooldown_blocks_recent(self):
        now = datetime.utcnow()
        state = {
            "artist_last_seen": {"weezer": (now - timedelta(days=1)).isoformat()},
            "track_last_seen": {},
        }
        tracks = [TrackCandidate(track_id="t1", title="Song1", artist="Weezer")]
        filtered = apply_constraints(tracks, self.profile, state, now)
        self.assertEqual(len(filtered), 0)


class GPTSchemaTest(unittest.TestCase):
    def test_reject_out_of_pool_uri(self):
        # simple validator behavior: picks must be within candidate set
        allowed = {"spotify:track:abc", "spotify:track:def"}
        response = json.dumps({"picks": ["spotify:track:abc", "spotify:track:zzz"]})
        picks = json.loads(response)["picks"]
        valid = [uri for uri in picks if uri in allowed]
        self.assertEqual(valid, ["spotify:track:abc"])


if __name__ == "__main__":
    unittest.main()
