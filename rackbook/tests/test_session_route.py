"""
Characterisation tests for the session routes in main.py:
  GET  /active-blocks/{id}/session   (planned weights per source)
  POST /active-blocks/{id}/session   (set logging, e1RM write)

Pins CURRENT behaviour so the notation/load-rule refactor cannot silently change it.
Tests marked expectedFailure describe intended behaviour that is currently broken; they
flip to "unexpected success" when the bug is fixed — remove the decorator then.

Runs against a throwaway SQLite DB (DB_PATH) — no network.
"""
import json
import os
import shutil
import sys
import tempfile
import unittest
import warnings

# Starlette's TestClient leaves anyio memory streams to the GC; the warnings bury real output.
warnings.filterwarnings("ignore", category=ResourceWarning)

# DB_PATH must exist before main is imported (load_dotenv does not override env vars).
_IMPORT_DIR = tempfile.mkdtemp()
os.environ["RACKBOOK_DB_PATH"] = os.path.join(_IMPORT_DIR, "import.db")
# These tests pin planned weights computed from the BUILT-IN whole-percent RPE table, not the user's own.
os.environ["RPE_CHART_PATH"] = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "rpe_chart.csv")

from fastapi.testclient import TestClient  # noqa: E402

from rackbook import main  # noqa: E402
from rackbook.database import get_db  # noqa: E402


def _set(reps, rpe=None, amrap=False, joker=False, jump=None, **extra):
    s = {"reps": reps, "target_rpe": rpe, "is_amrap": amrap, "is_joker": joker}
    if jump is not None:
        s["joker_jump_pct"] = jump
    s.update(extra)
    return s


class SessionRouteCase(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["RACKBOOK_DB_PATH"] = os.path.join(self.tmp, "test.db")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.client = TestClient(main.app)
        self.client.__enter__()  # runs lifespan -> init_db() on the fresh DB
        self.addCleanup(self.client.__exit__, None, None, None)

        self.program_id = self._exec(
            "INSERT INTO programs (name, total_weeks) VALUES ('P', 3)"
        )
        self.micro_id = self._exec(
            "INSERT INTO microcycles (program_id, cycle_number) VALUES (?, 1)",
            (self.program_id,),
        )
        self.day_id = self._exec(
            "INSERT INTO days (block_id, day_number) VALUES (?, 1)", (self.micro_id,)
        )
        self.tiers = {}

    # ── helpers ───────────────────────────────────────────────────────────────

    def _exec(self, sql, params=(), ignore_checks=False):
        conn = get_db()
        try:
            if ignore_checks:
                conn.execute("PRAGMA ignore_check_constraints = ON")
            cur = conn.execute(sql, params)
            conn.commit()
            return cur.lastrowid
        finally:
            conn.close()

    def _query(self, sql, params=()):
        conn = get_db()
        try:
            return [dict(r) for r in conn.execute(sql, params).fetchall()]
        finally:
            conn.close()

    def _tier(self, behaviour="free"):
        if behaviour not in self.tiers:
            self.tiers[behaviour] = self._exec(
                "INSERT INTO tiers (program_id, name, behaviour) VALUES (?, ?, ?)",
                (self.program_id, behaviour, behaviour),
                ignore_checks=True,  # legacy behaviours ('percentage') predate the CHECK
            )
        return self.tiers[behaviour]

    def _slot(self, sets=None, source=None, hevy_id="sq", name="Squat",
              tier="free", wave_extra=None, day_id=None, source_extra=None):
        wave = {"sets": sets or []}
        wave.update(wave_extra or {})
        sp = None
        if source is not None:
            sp = {"source": source}
            sp.update(source_extra or {})
        return self._exec(
            """
            INSERT INTO exercise_slots
                (day_id, tier_id, hevy_exercise_id, hevy_exercise_name, slot_order,
                 wave_params, source_params)
            VALUES (?, ?, ?, ?, 0, ?, ?)
            """,
            (day_id or self.day_id, self._tier(tier), hevy_id, name,
             json.dumps(wave), json.dumps(sp) if sp is not None else None),
        )

    def _start_block(self):
        r = self.client.post("/active-blocks", json={"program_id": self.program_id})
        self.assertEqual(200, r.status_code)
        return r.json()["id"]

    def _log_e1rm(self, block_id, slot_id, e1rm_kg, logged_at="2026-01-01 00:00:00"):
        self._exec(
            "INSERT INTO e1rm_log (active_block_id, exercise_slot_id, e1rm_kg, source, logged_at)"
            " VALUES (?, ?, ?, 'amrap', ?)",
            (block_id, slot_id, e1rm_kg, logged_at),
        )

    def _setting(self, key, value):
        self._exec("INSERT OR REPLACE INTO app_settings (key, value) VALUES (?, ?)", (key, str(value)))

    def _session(self, block_id):
        r = self.client.get(f"/active-blocks/{block_id}/session")
        self.assertEqual(200, r.status_code, r.text)
        return r.json()

    def _planned(self, block_id, slot_index=0):
        return [s["planned_weight_kg"] for s in self._session(block_id)["slots"][slot_index]["sets"]]


# ═════════════════════════════════════════════════════════════════════════════
# GET session — planned weights
# ═════════════════════════════════════════════════════════════════════════════

class TestPlannedWeights(SessionRouteCase):

    RPE_LIST = [_set(5, 6), _set(5, 7), _set(5, 8)]  # chart: .77 / .80 / .83

    def test_tm_source_uses_e1rm_times_wm_pct(self):
        slot = self._slot(self.RPE_LIST, "tm", source_extra={"wm_pct": 0.9})
        block = self._start_block()
        self._log_e1rm(block, slot, 200.0)  # baseline 180
        self.assertEqual([137.5, 145.0, 150.0], self._planned(block))

    def test_tm_source_first_set_weight_is_first_non_joker_set(self):
        slot = self._slot(self.RPE_LIST, "tm", source_extra={"wm_pct": 0.9})
        block = self._start_block()
        self._log_e1rm(block, slot, 200.0)
        self.assertEqual(137.5, self._session(block)["slots"][0]["first_set_weight_kg"])

    def test_tm_source_falls_back_to_tm_setting_when_no_e1rm_logged(self):
        slot = self._slot(self.RPE_LIST, "tm", source_extra={"wm_pct": 0.9})
        block = self._start_block()
        self._setting(f"tm_{slot}", 150)  # baseline 135
        self.assertEqual([105.0, 107.5, 112.5], self._planned(block))

    def test_tm_source_wm_pct_falls_back_to_setting_then_default(self):
        slot = self._slot(self.RPE_LIST, "tm")  # no wm_pct in source_params
        block = self._start_block()
        self._log_e1rm(block, slot, 200.0)
        self.assertEqual([137.5, 145.0, 150.0], self._planned(block))  # default 0.90
        self._setting(f"wm_pct_{slot}", 85)  # baseline 170
        self.assertEqual([130.0, 135.0, 140.0], self._planned(block))

    def test_tm_source_with_no_e1rm_and_no_setting_has_null_weights(self):
        self._slot(self.RPE_LIST, "tm", source_extra={"wm_pct": 0.9})
        block = self._start_block()
        self.assertEqual([None, None, None], self._planned(block))

    def test_e1rm_source_uses_raw_e1rm(self):
        slot = self._slot(self.RPE_LIST, "e1rm")
        block = self._start_block()
        self._log_e1rm(block, slot, 200.0)
        self.assertEqual([155.0, 160.0, 165.0], self._planned(block))

    def test_e1rm_is_shared_across_slots_with_the_same_exercise(self):
        other_day = self._exec(
            "INSERT INTO days (block_id, day_number) VALUES (?, 2)", (self.micro_id,)
        )
        other_slot = self._slot([_set(5, 8)], "e1rm", day_id=other_day)
        self._slot(self.RPE_LIST, "e1rm")
        block = self._start_block()
        self._log_e1rm(block, other_slot, 200.0)  # logged on a different slot, same exercise
        self.assertEqual([155.0, 160.0, 165.0], self._planned(block))

    def test_latest_e1rm_wins(self):
        slot = self._slot(self.RPE_LIST, "e1rm")
        block = self._start_block()
        self._log_e1rm(block, slot, 100.0, "2026-01-01 00:00:00")
        self._log_e1rm(block, slot, 200.0, "2026-01-02 00:00:00")
        self.assertEqual([155.0, 160.0, 165.0], self._planned(block))

    def test_ddp_source_uses_last_non_joker_actual_weight_and_ignores_increment(self):
        # increment_kg is parsed from "DDP+2.5" but the route does not apply it today.
        slot = self._slot(self.RPE_LIST, "ddp", source_extra={"increment_kg": 2.5})
        block = self._start_block()
        self._exec(
            "INSERT INTO session_log (active_block_id, exercise_slot_id, week_number, day_number,"
            " set_number, set_type, actual_weight_kg, reps) VALUES (?, ?, 1, 1, 1, 'working', 100.0, 5)",
            (block, slot),
        )
        self.assertEqual([77.5, 80.0, 82.5], self._planned(block))

    def test_ddp_source_with_no_history_has_null_weights(self):
        self._slot(self.RPE_LIST, "ddp")
        self.assertEqual([None, None, None], self._planned(self._start_block()))

    def test_free_source_has_null_weights(self):
        self._slot([_set(10), _set(10)], "free")
        self.assertEqual([None, None], self._planned(self._start_block()))

    def test_rpe_missing_from_chart_gives_null_weight(self):
        slot = self._slot([_set(5, 8.25)], "e1rm")
        block = self._start_block()
        self._log_e1rm(block, slot, 200.0)
        self.assertEqual([None], self._planned(block))

    def test_jokers_step_from_previous_planned_weight(self):
        slot = self._slot(
            [_set(3, 8), _set(1, joker=True, jump=0.10), _set(1, joker=True, jump=0.15)],
            "tm", source_extra={"wm_pct": 0.9},
        )
        block = self._start_block()
        self._log_e1rm(block, slot, 200.0)  # baseline 180; 3@8 = .88 -> 157.5
        self.assertEqual([157.5, 172.5, 197.5], self._planned(block))
        slot_json = self._session(block)["slots"][0]
        self.assertTrue(slot_json["jokers_enabled"])
        self.assertEqual(157.5, slot_json["first_set_weight_kg"])

    def test_joker_without_jump_pct_defaults_to_10_percent(self):
        slot = self._slot([_set(3, 8), _set(1, joker=True)], "tm", source_extra={"wm_pct": 0.9})
        block = self._start_block()
        self._log_e1rm(block, slot, 200.0)
        self.assertEqual([157.5, 172.5], self._planned(block))

    def test_amrap_flag_and_per_set_fields(self):
        slot = self._slot([_set(5, 6), _set(5, 8, amrap=True)], "e1rm")
        block = self._start_block()
        self._log_e1rm(block, slot, 200.0)
        out = self._session(block)["slots"][0]
        self.assertTrue(out["is_amrap"])
        self.assertEqual([0.77, 0.83], [s["rpe_percentage"] for s in out["sets"]])
        self.assertEqual([False, True], [s["is_amrap"] for s in out["sets"]])

    def test_only_current_cycle_and_day_slots_are_returned(self):
        self._slot([_set(5, 6)], "e1rm", name="Today")
        day2 = self._exec("INSERT INTO days (block_id, day_number) VALUES (?, 2)", (self.micro_id,))
        self._slot([_set(5, 6)], "e1rm", name="Tomorrow", day_id=day2)
        block = self._start_block()
        names = [s["exercise_name"] for s in self._session(block)["slots"]]
        self.assertEqual(["Today"], names)

    def test_legacy_percentage_tier_uses_wave_params_percentages_and_bbb(self):
        # Pre-source_params programs: tier behaviour 'percentage', percentages by cycle number.
        slot = self._slot(
            [], None, tier="percentage",
            wave_extra={"percentages": [0.75, 0.80, 0.85], "bbb_percentages": [0.65, 0.70, 0.75]},
        )
        block = self._start_block()
        self._setting(f"tm_{slot}", 200)  # baseline 200 * 0.90 = 180
        out = self._session(block)["slots"][0]
        self.assertEqual(135.0, out["first_set_weight_kg"])  # week 1: 180 * .75
        self.assertEqual(117.5, out["bbb_weight_kg"])        # week 1: 180 * .65

    def test_legacy_fixed_tier_uses_wave_params_weight(self):
        self._slot([_set(5)], None, tier="fixed", wave_extra={"weight_kg": 61.3})
        out = self._session(self._start_block())["slots"][0]
        self.assertEqual(62.5, out["first_set_weight_kg"])
        self.assertEqual([62.5], [s["planned_weight_kg"] for s in out["sets"]])

    @unittest.expectedFailure
    def test_bbb_pct_sets_from_text_import_get_a_planned_weight(self):
        # KNOWN GAP: "5x10 @.65 e1RM" imports sets carrying bbb_pct, but the session route never
        # reads bbb_pct, so planned weights are null. Intended: baseline * 0.65 = 130.0.
        bbb = [_set(10, None, bbb_pct=0.65, bbb_source="e1rm") for _ in range(5)]
        slot = self._slot(bbb, "e1rm")
        block = self._start_block()
        self._log_e1rm(block, slot, 200.0)
        self.assertEqual([130.0] * 5, self._planned(block))


# ═════════════════════════════════════════════════════════════════════════════
# POST session — logging and e1RM write
# ═════════════════════════════════════════════════════════════════════════════

def _log(slot, number, set_type, weight, reps, rpe=None, target=None):
    return {"slot_id": slot, "set_number": number, "set_type": set_type,
            "actual_weight_kg": weight, "reps": reps, "actual_rpe": rpe, "target_rpe": target}


class TestSessionLogging(SessionRouteCase):

    def setUp(self):
        super().setUp()
        self.slot = self._slot([_set(5, 8)], "e1rm")
        self.block = self._start_block()

    def _post(self, sets):
        return self.client.post(f"/active-blocks/{self.block}/session", json={"sets": sets})

    def _e1rm_rows(self):
        return self._query("SELECT e1rm_kg, source FROM e1rm_log WHERE active_block_id = ?", (self.block,))

    def test_empty_sets_rejected(self):
        self.assertEqual(422, self._post([]).status_code)

    def test_slot_outside_program_rejected(self):
        self.assertEqual(400, self._post([_log(9999, 1, "working", 100, 5)]).status_code)

    def test_inactive_block_rejected(self):
        self.client.delete(f"/active-blocks/{self.block}")
        self.assertEqual(400, self._post([_log(self.slot, 1, "working", 100, 5)]).status_code)

    def test_logged_weights_round_to_2_5_and_set_type_is_lowercased(self):
        r = self._post([_log(self.slot, 1, "WORKING", 101.3, 5, rpe=7, target=7)])
        self.assertEqual(200, r.status_code)
        row = self._query("SELECT * FROM session_log")[0]
        self.assertEqual(102.5, row["actual_weight_kg"])
        self.assertEqual("working", row["set_type"])
        self.assertEqual((1, 1), (row["week_number"], row["day_number"]))
        self.assertEqual((5, 7.0, 7.0), (row["reps"], row["actual_rpe"], row["target_rpe"]))

    def test_main_set_with_rpe_writes_epley_e1rm(self):
        self._post([_log(self.slot, 1, "main", 100, 5, rpe=8)])
        self.assertEqual([{"e1rm_kg": 117.5, "source": "amrap"}], self._e1rm_rows())  # 116.67 -> 117.5

    def test_highest_set_number_is_the_e1rm_anchor_even_if_lighter(self):
        self._post([_log(self.slot, 1, "main", 100, 5, rpe=8), _log(self.slot, 2, "main", 90, 8, rpe=9)])
        self.assertEqual(115.0, self._e1rm_rows()[0]["e1rm_kg"])  # 90 x 8 = 114 -> 115

    def test_main_set_without_rpe_writes_no_e1rm(self):
        self._post([_log(self.slot, 1, "main", 100, 5)])
        self.assertEqual([], self._e1rm_rows())

    def test_qualifying_joker_is_averaged_in(self):
        self._post([
            _log(self.slot, 1, "main", 100, 5, rpe=8),
            _log(self.slot, 2, "joker", 112.5, 1, rpe=9),  # 3.6% off the 116.67 anchor
        ])
        self.assertEqual([{"e1rm_kg": 115.0, "source": "joker_avg"}], self._e1rm_rows())

    def test_joker_outside_5_percent_band_is_excluded(self):
        self._post([
            _log(self.slot, 1, "main", 100, 5, rpe=8),
            _log(self.slot, 2, "joker", 105, 1, rpe=9),  # 10% below the anchor
        ])
        self.assertEqual([{"e1rm_kg": 117.5, "source": "amrap"}], self._e1rm_rows())

    def test_joker_without_rpe_is_excluded(self):
        self._post([
            _log(self.slot, 1, "main", 100, 5, rpe=8),
            _log(self.slot, 2, "joker", 112.5, 1),
        ])
        self.assertEqual([{"e1rm_kg": 117.5, "source": "amrap"}], self._e1rm_rows())

    def test_logged_e1rm_feeds_the_next_session_plan(self):
        self._post([_log(self.slot, 1, "main", 100, 5, rpe=8)])  # e1RM 117.5
        self.assertEqual([97.5], self._planned(self.block))  # 117.5 * .83 = 97.5

    def test_amrap_set_type_sent_by_the_ui_updates_e1rm(self):
        # index.html sends set_type 'working' / 'amrap' / 'joker' (never 'main'). The route used to
        # count only 'main' sets, so a real session never wrote an e1RM.
        self._post([_log(self.slot, 1, "amrap", 100, 5, rpe=8)])
        self.assertEqual(117.5, self._e1rm_rows()[0]["e1rm_kg"])

    def test_working_sets_do_not_write_e1rm(self):
        self._post([_log(self.slot, 1, "working", 100, 5, rpe=8)])
        self.assertEqual([], self._e1rm_rows())

    def test_manual_e1rm_rounds_and_appears_in_history(self):
        r = self.client.post(f"/active-blocks/{self.block}/e1rm", json={"slot_id": self.slot, "e1rm_kg": 201.3})
        self.assertEqual(204, r.status_code)
        history = self.client.get(f"/active-blocks/{self.block}/e1rm").json()
        self.assertEqual([("manual", 202.5)], [(h["source"], h["e1rm_kg"]) for h in history])


if __name__ == "__main__":
    unittest.main()
