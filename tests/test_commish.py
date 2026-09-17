"""The Commish's own contract: the decisions that turn data into advice.

No network and no container: every feed is stubbed, so what is checked here is
this repo's logic — who counts as startable, which bench player is a legal
swap, how a defense's points-allowed rank is built, and which player a typed
name resolves to. The Sleeper/ESPN wire shapes are pinned in the fixtures.

    python3 -m pytest tests/ -q          (or: python3 -m unittest discover tests)
"""
import datetime
import importlib.util
import pathlib
import sys
import unittest

SCRIPT = pathlib.Path(__file__).resolve().parent.parent / "skills" / "commish-coach" / "scripts" / "commish.py"
spec = importlib.util.spec_from_file_location("commish", SCRIPT)
commish = importlib.util.module_from_spec(spec)
sys.modules["commish"] = commish
spec.loader.exec_module(commish)


def player(name, pos, team, inj=None, active=True, espn=None):
    return {"name": name, "pos": pos, "team": team, "inj": inj, "inj_part": None,
            "active": active, "age": 25, "exp": 3, "espn": espn}


DB = {
    "1": player("Stefon Diggs", "WR", "WAS"),
    "2": player("A.J. Brown", "WR", "NE", inj="IR"),
    "3": player("RJ Harvey", "RB", "DEN", inj="Questionable"),
    "4": player("Parker Washington", "WR", "JAX"),
    "5": player("Jahmyr Gibbs", "RB", "DET"),
    "6": player("Geno Smith", "QB", "NYJ"),
    "7": player("Brashard Smith", "RB", "KC"),
    "8": player("Ito Smith", "RB", None, active=False),
    "BUF": player("Buffalo Bills", "DEF", "BUF"),
}


class TestNames(unittest.TestCase):
    def test_full_name_wins(self):
        self.assertEqual(commish.find_player("Stefon Diggs", DB)[0], "1")

    def test_punctuation_and_case_ignored(self):
        self.assertEqual(commish.find_player("aj brown", DB)[0], "2")

    def test_typo_resolves(self):
        self.assertEqual(commish.find_player("Digs", DB)[0], "1")

    def test_ambiguous_last_name_asks(self):
        """Two live Smiths: a guess here starts the wrong player."""
        pid, alternatives = commish.find_player("Smith", DB)
        self.assertIsNone(pid)
        self.assertEqual(len(alternatives), 2)

    def test_ambiguity_resolved_by_my_roster(self):
        pid, _ = commish.find_player("Smith", DB, prefer={"6"})
        self.assertEqual(pid, "6")

    def test_one_word_never_resolves_to_a_player_without_a_team(self):
        """A bare last name must reach live players only; the full name still resolves."""
        pid, alternatives = commish.find_player("Ito", DB)
        self.assertIsNone(pid)
        self.assertEqual(alternatives, [])
        self.assertEqual(commish.find_player("Ito Smith", DB)[0], "8")

    def test_team_defense_by_abbreviation(self):
        self.assertEqual(commish.find_player("BUF", DB)[0], "BUF")


class TestScoring(unittest.TestCase):
    def test_reception_point_picks_the_column(self):
        self.assertEqual(commish.scoring_key({"scoring_settings": {"rec": 1.0}}), "pts_ppr")
        self.assertEqual(commish.scoring_key({"scoring_settings": {"rec": 0.5}}), "pts_half_ppr")
        self.assertEqual(commish.scoring_key({"scoring_settings": {"rec": 0}}), "pts_std")

    def test_missing_scoring_settings_defaults_to_ppr(self):
        self.assertEqual(commish.scoring_key({}), "pts_ppr")
        self.assertEqual(commish.scoring_key(None), "pts_ppr")


class TestDefenseRanks(unittest.TestCase):
    def setUp(self):
        self.weeks = {
            1: [{"player_id": "1", "opponent": "NE", "stats": {"pts_ppr": 20.0}},
                {"player_id": "4", "opponent": "NE", "stats": {"pts_ppr": 10.0}},
                {"player_id": "2", "opponent": "DAL", "stats": {"pts_ppr": 5.0}}],
            2: [{"player_id": "1", "opponent": "NE", "stats": {"pts_ppr": 30.0}},
                {"player_id": "2", "opponent": "DAL", "stats": {"pts_ppr": 7.0}}],
        }
        self.calls = []

        def fake_cached(name, url, max_age):
            self.calls.append(name)
            week = int(name.split("_w")[1].split(".")[0])
            return self.weeks[week]

        self._cached, commish.cached = commish.cached, fake_cached

    def tearDown(self):
        commish.cached = self._cached

    def test_points_allowed_are_per_game_not_per_player(self):
        """NE gave up 30 to WRs in week 1 (two players) and 30 in week 2: 30/game, not 20."""
        ranks = commish.defense_ranks("2026", 3, DB, "pts_ppr")
        rank, average, games, total = ranks[("NE", "WR")]
        self.assertAlmostEqual(average, 30.0)
        self.assertEqual(games, 2)
        self.assertEqual(rank, 1)      # most allowed = easiest matchup
        self.assertEqual(total, 2)

    def test_week_one_has_no_completed_games(self):
        """range(1, 1) is empty, and an empty ranking must not crash a lineup answer."""
        self.assertEqual(commish.defense_ranks("2026", 1, DB, "pts_ppr"), {})
        self.assertEqual(self.calls, [])

    def test_matchup_note_labels_the_extremes(self):
        ranks = commish.defense_ranks("2026", 3, DB, "pts_ppr")
        note = commish.matchup_note("1", DB, {"1": {"opp": "NE"}}, ranks)
        self.assertIn("matchup EASY", note)
        self.assertIn("NE allows 30.0/g to WRs", note)

    def test_matchup_note_is_empty_without_data(self):
        self.assertEqual(commish.matchup_note("1", DB, {"1": {"opp": "SEA"}}, {}), "")


class TestLockIssues(unittest.TestCase):
    """The last-minute reminder: what it flags, what it stays quiet about, and the swap it offers."""

    def setUp(self):
        self.now = datetime.datetime(2026, 9, 20, 16, 0, tzinfo=datetime.timezone.utc)
        self.games = {
            "NE": {"kickoff": "2026-09-20T17:00Z", "state": "pre"},    # in 1h
            "JAX": {"kickoff": "2026-09-20T17:00Z", "state": "pre"},
            "DEN": {"kickoff": "2026-09-20T20:05Z", "state": "pre"},   # in 4h
            "WAS": {"kickoff": "2026-09-20T17:00Z", "state": "pre"},
            "DET": {"kickoff": "2026-09-20T13:00Z", "state": "in"},    # already playing
        }
        self.bundle = {
            "league": {"league_id": "L", "roster_positions": ["WR", "RB", "FLEX", "BN", "BN"],
                       "scoring_settings": {"rec": 1.0}},
            "rosters": [], "names": {},
            "mine": {"roster_id": 1, "starters": ["2", "5", "3"], "players": ["2", "5", "3", "1", "4"], "reserve": []},
        }
        self.proj = {"1": {"pts_ppr": 9.9, "opp": "DAL"}, "2": {"pts_ppr": None, "opp": None},
                     "3": {"pts_ppr": 8.0, "opp": "JAX"}, "4": {"pts_ppr": 9.0, "opp": "SF"},
                     "5": {"pts_ppr": 24.2, "opp": "BUF"}}
        self.saved = (commish.league_bundle, commish.nfl_state, commish.players,
                      commish.projections, commish.kickoffs, datetime.datetime)
        commish.league_bundle = lambda cfg, league_id=None: self.bundle
        commish.nfl_state = lambda: {"season": "2026", "display_week": 3}
        commish.players = lambda: DB
        commish.projections = lambda season, week: self.proj
        commish.kickoffs = lambda week: self.games

        test_now = self.now

        class FrozenDatetime(datetime.datetime):
            @classmethod
            def now(cls, tz=None):
                return test_now

        datetime.datetime = FrozenDatetime

    def tearDown(self):
        (commish.league_bundle, commish.nfl_state, commish.players,
         commish.projections, commish.kickoffs, datetime.datetime) = self.saved

    def test_flags_an_ir_starter_and_offers_a_legal_bench_swap(self):
        rows = commish.lock_issues({}, hours=3)
        self.assertEqual(len(rows), 1)
        slot, issue, locks, swap = rows[0].split("|")
        self.assertEqual(slot, "WR")
        self.assertIn("A.J. Brown is IR", issue)
        self.assertIn("Stefon Diggs", swap)     # WR slot: the WR on the bench, not the RB

    def test_says_nothing_about_a_game_that_already_started(self):
        """Gibbs is playing: nothing the owner can do, so it must not be texted."""
        self.assertFalse(any("Gibbs" in row for row in commish.lock_issues({}, hours=6)))

    def test_questionable_starter_appears_once_his_game_is_inside_the_window(self):
        rows = commish.lock_issues({}, hours=5)
        harvey = [r for r in rows if "Harvey" in r]
        self.assertEqual(len(harvey), 1)
        self.assertIn("check inactives", harvey[0])
        self.assertIn("Parker Washington", harvey[0])   # FLEX takes a WR

    def test_one_bench_player_is_not_offered_for_two_slots(self):
        self.bundle["mine"] = {"roster_id": 1, "starters": ["2", "5", "3"],
                               "players": ["2", "5", "3", "1"], "reserve": []}
        rows = commish.lock_issues({}, hours=5)
        swaps = [row.split("|")[3] for row in rows]
        self.assertIn("Stefon Diggs", swaps[0])
        self.assertIn("no healthy", swaps[1])

    def test_empty_slot_is_flagged(self):
        self.bundle["mine"]["starters"] = ["0", "5", "3"]
        rows = commish.lock_issues({}, hours=3)
        self.assertIn("EMPTY SLOT", rows[0])

    def test_quiet_when_every_starter_is_fine(self):
        self.bundle["mine"] = {"roster_id": 1, "starters": ["1", "5", "4"],
                               "players": ["1", "5", "4"], "reserve": []}
        self.assertEqual(commish.lock_issues({}, hours=3), [])


if __name__ == "__main__":
    unittest.main()
