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


PPR = commish_scorer = None  # set below, once the module is loaded


def player(name, pos, team, inj=None, active=True, espn=None):
    return {"name": name, "pos": pos, "team": team, "inj": inj, "inj_part": None,
            "active": active, "age": 25, "exp": 3, "espn": espn}


PPR = commish.scorer(None)   # Sleeper's own PPR column, the no-league default

DB = {
    "1": player("Stefon Diggs", "WR", "WAS"),
    "2": player("A.J. Brown", "WR", "NE", inj="IR"),
    "3": player("RJ Harvey", "RB", "DEN", inj="Questionable"),
    "4": player("Parker Washington", "WR", "JAX"),
    "5": player("Jahmyr Gibbs", "RB", "DET"),
    "6": player("Geno Smith", "QB", "NYJ"),
    "7": player("Brashard Smith", "RB", "KC"),
    "8": player("Ito Smith", "RB", None, active=False),
    "9": player("Micah Simon", "WR", "CAR"),
    "10": player("E.J. Warner", "QB", None),
    "11": player("Amon-Ra St. Brown", "WR", "DET"),
    "12": player("Jonathan Taylor", "RB", "IND"),
    "13": player("Mason Taylor", "TE", "NYJ"),
    "PHI": player("Philadelphia Eagles", "DEF", "PHI"),
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

    def test_a_similar_first_name_is_not_a_match(self):
        """difflib rates 'Micah Parsons' close to 'Micah Simon'; starting Simon loses a week."""
        pid, alternatives = commish.find_player("Micah Parsons", DB)
        self.assertIsNone(pid)
        self.assertTrue(any("Micah Simon" in a for a in alternatives))

    def test_a_defensive_player_never_lands_on_a_teamless_lookalike(self):
        self.assertIsNone(commish.find_player("Fred Warner", DB)[0])

    def test_two_real_players_share_a_surname_so_it_asks(self):
        pid, alternatives = commish.find_player("Jon Taylor", DB)
        self.assertIsNone(pid)
        self.assertTrue(any("Jonathan Taylor" in a for a in alternatives))

    def test_partial_name_everyone_types(self):
        self.assertEqual(commish.find_player("St Brown", DB)[0], "11")
        self.assertEqual(commish.find_player("Amon Ra", DB)[0], "11")

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


class TestLeagueScoring(unittest.TestCase):
    """Sleeper's three precomputed columns cannot express half the leagues on the platform."""

    PLAIN = {"scoring_settings": {"rec": 0.5, "pass_td": 4.0, "rec_td": 6.0, "rush_td": 6.0,
                                  "fgm_20_29": 3.0, "fgm_30_39": 3.0}}
    RICH = {"scoring_settings": {"rec": 0.5, "pass_td": 6.0, "rec_td": 6.0, "rush_td": 6.0,
                                 "bonus_rec_te": 1.0, "rec_fd": 0.5, "rec_yd": 0.1, "pass_yd": 0.04}}

    def test_a_kicker_table_is_not_a_custom_rule(self):
        self.assertFalse(commish.custom_scoring(self.PLAIN))
        self.assertFalse(commish.custom_scoring({}))
        self.assertFalse(commish.custom_scoring(None))

    def test_six_point_passing_tds_and_bonuses_are(self):
        self.assertTrue(commish.custom_scoring(self.RICH))

    def test_a_plain_league_uses_sleepers_own_column(self):
        row = {"stats": {"pts_half_ppr": 12.3, "pts_ppr": 15.0, "rec": 6}}
        self.assertEqual(commish.scorer(self.PLAIN)(row), 12.3)

    def test_a_rich_league_is_scored_on_its_own_settings(self):
        """Sleeper projects the bonus stats themselves, so the settings multiply the line as it comes."""
        row = {"stats": {"pts_half_ppr": 8.8, "rec": 6.0, "rec_yd": 60.0, "rec_fd": 4.0}}
        # 6 catches x 0.5 + 60 yards x 0.1 + 4 first downs x 0.5 = 11.0, not the 8.8 bucket
        self.assertAlmostEqual(commish.scorer(self.RICH)(row), 11.0)

    def test_the_te_premium_reaches_a_tight_end(self):
        te = {"stats": {"rec": 6.0, "rec_yd": 60.0, "rec_fd": 4.0, "bonus_rec_te": 6.0}}
        self.assertAlmostEqual(commish.scorer(self.RICH)(te), 17.0)

    def test_the_label_says_when_it_is_not_plain(self):
        self.assertEqual(commish.scoring_label("pts_half_ppr", self.PLAIN), "Half-PPR")
        self.assertIn("own settings", commish.scoring_label("pts_half_ppr", self.RICH))


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
        ranks = commish.defense_ranks("2026", 3, DB, PPR)
        rank, average, games, total = ranks[("NE", "WR")]
        self.assertAlmostEqual(average, 30.0)
        self.assertEqual(games, 2)
        self.assertEqual(rank, 1)      # most allowed = easiest matchup
        self.assertEqual(total, 2)

    def test_week_one_has_no_completed_games(self):
        """range(1, 1) is empty, and an empty ranking must not crash a lineup answer."""
        self.assertEqual(commish.defense_ranks("2026", 1, DB, PPR), {})
        self.assertEqual(self.calls, [])

    def test_matchup_note_labels_the_extremes(self):
        ranks = commish.defense_ranks("2026", 3, DB, PPR)
        note = commish.matchup_note("1", DB, {"1": {"stats": {}, "opp": "NE"}}, ranks)
        self.assertIn("matchup EASY", note)
        self.assertIn("NE allows 30.0/g to WRs", note)

    def test_matchup_note_is_empty_without_data(self):
        self.assertEqual(commish.matchup_note("1", DB, {"1": {"stats": {}, "opp": "SEA"}}, {}), "")


class TestInjuryNames(unittest.TestCase):
    """ESPN's feed carries defenders too, and today it holds two Justin Jeffersons."""

    def test_the_designation_follows_the_position(self):
        feed = {
            (commish.norm("Justin Jefferson"), "LB"): {"status": "Out", "comment": "linebacker"},
            (commish.norm("Justin Jefferson"), "WR"): {"status": "Active", "comment": "receiver"},
            commish.norm("Stefon Diggs"): {"status": "Active", "comment": "only one of him"},
        }
        db = {"j": player("Justin Jefferson", "WR", "MIN"), "1": DB["1"]}
        self.assertEqual(commish.injury_note("j", db, feed)["comment"], "receiver")
        self.assertEqual(commish.injury_note("1", db, feed)["comment"], "only one of him")


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
        self.proj = {"1": {"stats": {"pts_ppr": 9.9}, "opp": "DAL"}, "2": {"stats": {}, "opp": None},
                     "3": {"stats": {"pts_ppr": 8.0}, "opp": "JAX"}, "4": {"stats": {"pts_ppr": 9.0}, "opp": "SF"},
                     "5": {"stats": {"pts_ppr": 24.2}, "opp": "BUF"}}
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

    def test_an_untracked_position_is_not_an_empty_slot(self):
        """An IDP starter is invisible to this index: silence, not a weekly false alarm."""
        self.bundle["mine"]["starters"] = ["99999", "5", "3"]
        self.bundle["mine"]["players"] = ["99999", "5", "3", "1", "4"]
        self.assertFalse(any("EMPTY SLOT" in row for row in commish.lock_issues({}, hours=3)))

    def test_the_deadline_is_the_earlier_of_the_two_kickoffs(self):
        """Swapping a 4:05pm starter for a 1:00pm bench player has to happen by 1:00pm."""
        self.bundle["league"]["roster_positions"] = ["RB", "WR", "FLEX", "BN", "BN"]
        self.bundle["mine"] = {"roster_id": 1, "starters": ["5", "1", "3"],
                               "players": ["5", "1", "3", "4"], "reserve": []}
        rows = commish.lock_issues({}, hours=5)
        harvey = [r for r in rows if "Harvey" in r][0]
        self.assertIn("Parker Washington", harvey)
        self.assertIn("locks 2026-09-20T17:00Z", harvey)   # JAX kickoff, not DEN's 20:05

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
