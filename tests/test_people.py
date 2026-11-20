"""Check-in stays on one person, and missed work stacks per language."""
import os
import tempfile
import unittest

_TMP = tempfile.mkdtemp(prefix="jinbu-people-")
os.environ["JINBU_DATA"] = _TMP

from server import db, logic, words as wordbank  # noqa: E402


def _daily(member_id, date=None):
    return db.fetchone(
        "SELECT * FROM daily WHERE member_id=? AND date=?",
        (member_id, date or logic.today_str()),
    )


class PeopleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        wordbank.load()

    def test_english_checkin_does_not_finish_korean_companion(self):
        created = logic.create_room("小王", "koo陸_", None, "cet4")
        english = logic.get_member_by_token(created["token"])
        joined = logic.join_room(created["state"]["room"]["code"], "koo陸_", "korean")
        korean = logic.get_member_by_token(joined["token"])
        self.assertEqual(logic.normalize_plan(korean["study_plan"]), "korean")
        self.assertNotEqual(english["id"], korean["id"])

        today = logic.today_str()
        db.execute("DELETE FROM daily WHERE member_id=? AND date=?", (english["id"], today), commit=True)
        db.execute(
            """INSERT INTO daily (member_id, date, review_target, new_target, quiz_target,
                                   reviewed_due_json, new_introduced_json, quizzes_done, vocab_done,
                                   ko_review_target, ko_new_target, ko_quiz_target)
               VALUES (?, ?, 1, 1, 1, '["w_more"]', '["w_one"]', 1, 0, 8, 8, 1)""",
            (english["id"], today),
            commit=True,
        )
        db.execute("DELETE FROM daily WHERE member_id=? AND date=?", (korean["id"], today), commit=True)
        db.execute(
            """INSERT INTO daily (member_id, date, review_target, new_target, quiz_target,
                                   ko_review_target, ko_new_target, ko_quiz_target)
               VALUES (?, ?, 0, 0, 0, 3, 8, 1)""",
            (korean["id"], today),
            commit=True,
        )
        result = logic.try_checkin(english)
        self.assertTrue(result["ok"])
        mine = _daily(english["id"])
        theirs = _daily(korean["id"])
        self.assertEqual(mine["checkin"], 1)
        self.assertEqual(theirs["checkin"], 0)
        self.assertEqual(theirs["ko_vocab_done"], 0)
        self.assertEqual(theirs["ko_quizzes_done"], 0)
        self.assertEqual(theirs["ko_new_target"], 8)
        korean = logic.get_member_by_token(joined["token"])
        state = logic.room_state(korean)
        self.assertFalse(state["me"]["checkinToday"])
        self.assertTrue(state["partner"]["checkinToday"])
        korean_track = next(track for track in state["me"]["tracks"] if track["id"] == "korean")
        self.assertFalse(korean_track["done"])
        self.assertGreater(korean_track["label"].find("韩"), -1)

    def test_both_plan_english_does_not_mark_korean_done(self):
        created = logic.create_room("甲乙", None, None, "both")
        member = logic.get_member_by_token(created["token"])
        today = logic.today_str()
        db.execute("DELETE FROM daily WHERE member_id=? AND date=?", (member["id"], today), commit=True)
        db.execute(
            """INSERT INTO daily (member_id, date, review_target, new_target, quiz_target,
                                   reviewed_due_json, new_introduced_json, quizzes_done,
                                   ko_review_target, ko_new_target, ko_quiz_target)
               VALUES (?, ?, 0, 0, 1, '[]', '[]', 1, 0, 0, 0)""",
            (member["id"], today),
            commit=True,
        )
        plan = logic.plan_for(member)
        korean = next(track for track in plan["tracks"] if track["id"] == "korean")
        english = next(track for track in plan["tracks"] if track["id"] == "cet4")
        self.assertGreater(korean["newTotal"], 0)
        self.assertFalse(korean["vocabDone"])
        self.assertFalse(plan["checkin"])
        # English targets were a stale 0/0 while words remain, so they are rebuilt too.
        self.assertGreater(english["newTotal"], 0)
        result = logic.try_checkin(logic.get_member_by_token(created["token"]))
        self.assertFalse(result["ok"])
        row = _daily(member["id"])
        self.assertEqual(row["checkin"], 0)
        self.assertEqual(row["ko_vocab_done"], 0)

    def test_missed_work_stacks_per_language_and_caps_at_two_days(self):
        created = logic.create_room("丙", None, None, "both")
        member = logic.get_member_by_token(created["token"])
        yesterday = logic.add_days(logic.today_str(), -1)
        db.execute(
            "UPDATE members SET joined_date=?, last_checkin=NULL WHERE id=?",
            (logic.add_days(yesterday, -3), member["id"]),
            commit=True,
        )
        db.execute(
            """INSERT INTO daily (member_id, date, review_target, new_target, quiz_target,
                                   reviewed_due_json, new_introduced_json,
                                   ko_review_target, ko_new_target, ko_quiz_target,
                                   ko_reviewed_due_json, ko_new_introduced_json)
               VALUES (?, ?, 10, 20, 1, '["w_more","w_one"]', '["w_people"]', 6, 8, 1, '["ko_17298"]', '[]')""",
            (member["id"], yesterday),
            commit=True,
        )
        logic.process_misses(member["room_id"])
        member = logic.get_member_by_token(created["token"])
        self.assertEqual(member["streak"], 0)
        self.assertEqual(member["carry_review"], 8)
        self.assertEqual(member["carry_new"], 19)
        self.assertEqual(member["ko_carry_review"], 5)
        self.assertEqual(member["ko_carry_new"], 8)
        self.assertEqual(logic.CARRY_DAYS, 2)

        plan = logic.plan_for(member)
        english = next(track for track in plan["tracks"] if track["id"] == "cet4")
        korean = next(track for track in plan["tracks"] if track["id"] == "korean")
        self.assertEqual(english["carryNew"], 19)
        self.assertEqual(english["carryReview"], 8)
        self.assertLessEqual(english["newTotal"], 20 + 40)
        self.assertGreaterEqual(english["newTotal"], 20)
        self.assertEqual(korean["carryNew"], 8)
        self.assertNotEqual(english["carryNew"], korean["carryNew"])
        self.assertIn("最多 2 天", plan["requirementText"])

        # A huge leftover is clipped to two normal days, not added without limit.
        db.execute(
            "UPDATE members SET miss_processed_on=NULL, carry_new=0 WHERE id=?",
            (member["id"],),
            commit=True,
        )
        db.execute(
            "UPDATE daily SET new_target=100, new_introduced_json='[]' WHERE member_id=? AND date=?",
            (member["id"], yesterday),
            commit=True,
        )
        logic.process_misses(db.fetchone("SELECT * FROM members WHERE id=?", (member["id"],))["room_id"])
        member = logic.get_member_by_token(created["token"])
        self.assertEqual(member["carry_new"], 40)


if __name__ == "__main__":
    unittest.main()
