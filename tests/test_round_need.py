"""Pass threshold is 3, and earlier 3–4 recalls already count as passed."""
import os
import tempfile
import unittest

_TMP = tempfile.mkdtemp(prefix="jinbu-round-")
os.environ["JINBU_DATA"] = _TMP

from server import db, logic, words as wordbank  # noqa: E402


def _progress(member_id, word_id):
    return db.fetchone(
        "SELECT * FROM word_progress WHERE member_id=? AND word_id=?",
        (member_id, word_id),
    )


class RoundNeedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        wordbank.load()
        cls.created = logic.create_room("甲", None, None, "both")
        cls.member = logic.get_member_by_token(cls.created["token"])

    def test_threshold_and_wrong_answers(self):
        member = logic.get_member_by_token(self.created["token"])
        self.assertEqual(logic.ROUND_NEED, 3)
        self.assertIn("3 次", logic.MEMORY_TEXT)
        self.assertNotIn("5 次", logic.MEMORY_TEXT)
        session = logic.build_session(member, "korean")
        self.assertTrue(session)
        self.assertEqual(session[0]["track"], "korean")
        self.assertEqual(session[0]["word"]["lang"], "ko")
        self.assertEqual(session[0]["roundNeed"], 3)
        state = logic.room_state(member)
        self.assertEqual(state["me"]["plan"]["roundNeed"], 3)

        first = logic.rate_word(member, "w_question", "know")
        self.assertFalse(first["roundComplete"])
        self.assertEqual(first["roundCorrect"], 1)
        self.assertEqual(first["roundNeed"], 3)
        second = logic.rate_word(member, "w_question", "know")
        self.assertFalse(second["roundComplete"])
        self.assertEqual(second["roundCorrect"], 2)
        softened = logic.rate_word(member, "w_question", "hard")
        self.assertFalse(softened["roundComplete"])
        self.assertEqual(softened["roundCorrect"], 1)
        self.assertEqual(_progress(member["id"], "w_question")["reps"], 0)
        reset = logic.rate_word(member, "w_question", "again")
        self.assertFalse(reset["roundComplete"])
        self.assertEqual(reset["roundCorrect"], 0)
        self.assertEqual(_progress(member["id"], "w_question")["lapses"], 1)
        self.assertEqual(_progress(member["id"], "w_question")["interval_days"], 0)

        for expected in (1, 2):
            step = logic.rate_word(member, "w_well", "know")
            self.assertFalse(step["roundComplete"])
            self.assertEqual(step["roundCorrect"], expected)
        passed = logic.rate_word(member, "w_well", "know")
        self.assertTrue(passed["roundComplete"])
        self.assertEqual(passed["roundCorrect"], 3)
        self.assertEqual(passed["interval"], 1)
        stored = _progress(member["id"], "w_well")
        self.assertEqual(stored["reps"], 1)
        self.assertEqual(stored["round_correct"], 0)
        self.assertEqual(stored["interval_days"], 1)
        self.assertEqual(stored["due_ts"], logic.start_of_day_ts(logic.add_days(logic.today_str(), 1)))

        logic.rate_word(member, "ko_17298", "know")
        logic.rate_word(member, "ko_17298", "know")
        ko_reset = logic.rate_word(member, "ko_17298", "again")
        self.assertFalse(ko_reset["roundComplete"])
        self.assertEqual(ko_reset["roundCorrect"], 0)
        for _ in range(2):
            self.assertFalse(logic.rate_word(member, "ko_17294", "know")["roundComplete"])
        ko_pass = logic.rate_word(member, "ko_17294", "know")
        self.assertTrue(ko_pass["roundComplete"])
        self.assertEqual(ko_pass["roundNeed"], 3)

    def test_existing_three_and_four_count_as_passed(self):
        member = logic.get_member_by_token(self.created["token"])
        points_before = member["points_total"] or 0
        today = logic.today_str()
        db.execute("DELETE FROM app_meta WHERE key=?", (logic.ROUND_NEED_META,), commit=True)
        db.execute(
            """INSERT INTO daily (member_id, date, review_target, new_target, quiz_target,
                                   ko_review_target, ko_new_target, ko_quiz_target)
               VALUES (?, ?, 1, 2, 1, 1, 1, 1)
               ON CONFLICT(member_id, date) DO UPDATE SET
                 review_target=1, new_target=2, ko_review_target=1, ko_new_target=1""",
            (member["id"], today),
            commit=True,
        )
        past = 1
        rows = [
            ("w_more", 0, 0, 0, 3, "new"),
            ("w_people", 4, past, 2, 4, "learning"),
            ("w_one", 0, 0, 0, 2, "new"),
            ("w_passage", 30, logic.start_of_day_ts(logic.add_days(today, 30)), 6, 0, "mastered"),
            ("ko_17189", 1, past, 1, 3, "learning"),
        ]
        for word_id, interval, due, reps, correct, status in rows:
            db.execute(
                """INSERT INTO word_progress
                   (member_id, word_id, interval_days, due_ts, reps, lapses, status, round_correct)
                   VALUES (?, ?, ?, ?, ?, 0, ?, ?)
                   ON CONFLICT(member_id, word_id) DO UPDATE SET
                     interval_days=excluded.interval_days, due_ts=excluded.due_ts, reps=excluded.reps,
                     status=excluded.status, round_correct=excluded.round_correct""",
                (member["id"], word_id, interval, due, reps, status, correct),
                commit=True,
            )
        logic.apply_round_need_migration(db.connect())

        fresh = _progress(member["id"], "w_more")
        self.assertEqual(fresh["round_correct"], 0)
        self.assertEqual(fresh["reps"], 1)
        self.assertEqual(fresh["interval_days"], 1)
        self.assertEqual(fresh["status"], "learning")
        self.assertEqual(fresh["introduced_on"], today)
        self.assertGreater(fresh["due_ts"], logic.start_of_day_ts(today))

        review = _progress(member["id"], "w_people")
        self.assertEqual(review["round_correct"], 0)
        self.assertEqual(review["reps"], 3)
        self.assertEqual(review["interval_days"], 7)
        self.assertGreater(review["due_ts"], past)

        kept = _progress(member["id"], "w_one")
        self.assertEqual(kept["round_correct"], 2)
        self.assertEqual(kept["reps"], 0)
        self.assertEqual(kept["interval_days"], 0)

        untouched = _progress(member["id"], "w_passage")
        self.assertEqual(untouched["reps"], 6)
        self.assertEqual(untouched["round_correct"], 0)
        self.assertEqual(untouched["interval_days"], 30)

        korean = _progress(member["id"], "ko_17189")
        self.assertEqual(korean["round_correct"], 0)
        self.assertEqual(korean["reps"], 2)
        self.assertEqual(korean["interval_days"], 2)

        logic.apply_round_need_migration(db.connect())
        self.assertEqual(_progress(member["id"], "w_people")["reps"], 3)
        self.assertEqual(_progress(member["id"], "w_people")["interval_days"], 7)

        member = logic.get_member_by_token(self.created["token"])
        self.assertEqual(member["points_total"] or 0, points_before)
        due, fresh_words, progress = logic.due_and_new(member, "cet4")
        self.assertNotIn("w_more", [w["id"] for w in fresh_words])
        self.assertNotIn("w_people", [w["id"] for w, _ in due])
        self.assertEqual(progress["w_one"]["round_correct"], 2)

        plan = logic.plan_for(member)
        english = next(track for track in plan["tracks"] if track["id"] == "cet4")
        korean_track = next(track for track in plan["tracks"] if track["id"] == "korean")
        self.assertEqual(english["dueDone"], 1)
        self.assertEqual(english["dueLeft"], 0)
        self.assertGreaterEqual(english["newDone"], 1)
        self.assertEqual(korean_track["dueDone"], 1)
        self.assertEqual(korean_track["dueLeft"], 0)

        daily = db.fetchone(
            "SELECT * FROM daily WHERE member_id=? AND date=?",
            (member["id"], today),
        )
        self.assertIn("w_more", daily["new_introduced_json"])
        self.assertIn("w_people", daily["reviewed_due_json"])
        self.assertIn("ko_17189", daily["ko_reviewed_due_json"])
        self.assertNotIn("w_one", daily["new_introduced_json"])

    def test_leftover_three_is_not_wiped_by_again(self):
        member = logic.get_member_by_token(self.created["token"])
        used = {"w_question", "w_well", "w_more", "w_people", "w_one", "w_passage"}
        word_id = next(w["id"] for w in wordbank.all_words() if w["id"] not in used)
        db.execute(
            """INSERT INTO word_progress
               (member_id, word_id, interval_days, due_ts, reps, lapses, status, round_correct)
               VALUES (?, ?, 0, 0, 0, 0, 'new', 4)
               ON CONFLICT(member_id, word_id) DO UPDATE SET round_correct=4, reps=0, interval_days=0, due_ts=0""",
            (member["id"], word_id),
            commit=True,
        )
        result = logic.rate_word(member, word_id, "again")
        self.assertTrue(result["roundComplete"])
        self.assertEqual(result["roundCorrect"], 3)
        stored = _progress(member["id"], word_id)
        self.assertEqual(stored["round_correct"], 0)
        self.assertEqual(stored["reps"], 1)
        self.assertEqual(stored["interval_days"], 1)

    def test_import_settles_old_rounds(self):
        created = logic.create_room("乙", None, None, "cet4")
        member = logic.get_member_by_token(created["token"])
        logic.import_member(
            member,
            {
                "member": {
                    "dailyNew": 20,
                    "reviewCap": 40,
                    "pointsTotal": 3,
                    "streak": 1,
                    "streakBonuses": '{"3":false,"7":false,"14":false}',
                },
                "progress": [
                    {
                        "word_id": "w_more",
                        "interval_days": 0,
                        "due_ts": 0,
                        "reps": 0,
                        "lapses": 0,
                        "status": "new",
                        "round_correct": 4,
                    },
                    {
                        "word_id": "w_one",
                        "interval_days": 2,
                        "due_ts": 5,
                        "reps": 1,
                        "lapses": 0,
                        "status": "learning",
                        "round_correct": 2,
                    },
                ],
            },
        )
        passed = _progress(member["id"], "w_more")
        self.assertEqual(passed["round_correct"], 0)
        self.assertEqual(passed["reps"], 1)
        self.assertEqual(passed["interval_days"], 1)
        kept = _progress(member["id"], "w_one")
        self.assertEqual(kept["round_correct"], 2)
        self.assertEqual(kept["reps"], 1)
        self.assertEqual(kept["interval_days"], 2)
        self.assertEqual(kept["due_ts"], 5)


if __name__ == "__main__":
    unittest.main()
