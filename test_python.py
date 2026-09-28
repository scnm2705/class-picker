"""Focused checks for the Python test edition; uses only temporary files."""
import json
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

import python_core as core


def add_students(classroom, count):
    students = [core.new_student(f"测试学生{i:02d}", f"T{i:03d}") for i in range(1, count + 1)]
    classroom["Students"].extend(students)
    return students


class PickerRulesTest(unittest.TestCase):
    def test_new_class_preferences(self):
        classroom = core.new_class("测试", "一班")
        self.assertTrue(classroom["VipEnabled"])
        self.assertTrue(classroom["FillVipShortage"])
        self.assertTrue(classroom["AutoCurrentDetail"])

    def test_vip_shortage_default_and_saved_preference(self):
        classroom = core.new_class("测试", "一班")
        add_students(classroom, 3)
        classroom["VipPerBatch"] = 2
        self.assertEqual(core.vip_shortage(classroom, "普通", 3), (0, 2))
        self.assertIsNone(core.preview(classroom, "普通", 3))
        batch = core.draw(classroom, "普通", 3)
        self.assertEqual(sum(entry["Source"] == "普通补位" for entry in batch["Entries"]), 2)
        legacy = core.new_class("测试", "旧班")
        legacy.pop("FillVipShortage")
        saved_off = core.new_class("测试", "已关闭")
        saved_off["FillVipShortage"] = False
        core.normalize({"Version": 1, "LastClassId": None, "Classes": [legacy, saved_off]})
        self.assertTrue(legacy["FillVipShortage"])
        self.assertFalse(saved_off["FillVipShortage"])

    def test_batch_uniqueness_and_no_repeat(self):
        classroom = core.new_class("测试", "一班")
        classroom["VipEnabled"] = False
        add_students(classroom, 4)
        batch = core.draw(classroom, "不重复", 4)
        self.assertEqual(len({e["StudentId"] for e in batch["Entries"]}), 4)
        self.assertIsNotNone(core.preview(classroom, "不重复", 1))
        core.new_round(classroom, "不重复")
        self.assertIsNone(core.preview(classroom, "不重复", 1))

    def test_vip_fill_and_return_after_round(self):
        classroom = core.new_class("测试", "一班")
        students = add_students(classroom, 5)
        core.add_vip(classroom, students[0])
        classroom["VipEnabled"] = True
        classroom["VipPerBatch"] = 2
        classroom["FillVipShortage"] = False
        self.assertIsNotNone(core.preview(classroom, "普通", 3))
        classroom["FillVipShortage"] = True
        batch = core.draw(classroom, "普通", 3)
        self.assertEqual(sum(e["Vip"] for e in batch["Entries"]), 1)
        self.assertEqual(sum(e["Source"] == "普通补位" for e in batch["Entries"]), 1)
        self.assertTrue(core.vip_hold(classroom, students[0]))
        core.new_round(classroom, "普通")
        self.assertFalse(core.vip_hold(classroom, students[0]))

    def test_vip_returns_when_another_mode_starts_new_round(self):
        classroom = core.new_class("测试", "一班")
        students = add_students(classroom, 3)
        core.add_vip(classroom, students[0])
        classroom["VipEnabled"] = True
        core.draw(classroom, "普通", 1)
        self.assertTrue(core.vip_hold(classroom, students[0]))
        core.new_round(classroom, "均衡")
        self.assertFalse(core.vip_hold(classroom, students[0]))
        self.assertIn(students[0], core.ordinary_candidates(classroom, "普通"))

    def test_legacy_completed_vip_migrates_after_other_round(self):
        classroom = core.new_class("测试", "一班")
        students = add_students(classroom, 3)
        core.add_vip(classroom, students[0])
        classroom["VipEnabled"] = True
        core.draw(classroom, "普通", 1)
        classroom["VipEnabled"] = False
        core.draw(classroom, "均衡", 1)
        classroom["BalancedRound"] = 2
        core.draw(classroom, "均衡", 1)
        classroom.pop("RoundSerial")
        for student in classroom["Students"]:
            student.pop("VipCompletedSerial", None)
        data = {"Version": 1, "LastClassId": None, "Classes": [classroom]}
        core.normalize(data)
        self.assertFalse(core.vip_hold(classroom, students[0]))

    def test_single_without_vip_is_plain_ordinary(self):
        classroom = core.new_class("测试", "一班")
        add_students(classroom, 2)
        classroom["VipEnabled"] = True
        batch = core.draw(classroom, "普通", 1)
        self.assertEqual(batch["PlannedVip"], 0)
        self.assertEqual(batch["Entries"][0]["Source"], "普通池")

    def test_vip_waiting_positions_restart_at_one(self):
        classroom = core.new_class("测试", "一班")
        first, second, third = add_students(classroom, 3)
        core.add_vip(classroom, first)
        classroom["VipEnabled"] = True
        core.draw(classroom, "普通", 1)
        self.assertEqual(core.vip_queue_positions(classroom), {})
        core.add_vip(classroom, second)
        self.assertGreater(second["VipOrder"], 1)
        self.assertEqual(core.vip_queue_positions(classroom)[second["Id"]], 1)
        core.add_vip(classroom, third)
        self.assertEqual(core.vip_queue_positions(classroom)[third["Id"]], 2)
        core.move_vip(classroom, third, -1)
        self.assertEqual(core.vip_queue_positions(classroom)[third["Id"]], 1)
        self.assertEqual(core.vip_queue_positions(classroom)[second["Id"]], 2)

    def test_balanced_absence_replacement_once(self):
        classroom = core.new_class("测试", "一班")
        classroom["VipEnabled"] = False
        add_students(classroom, 4)
        batch = core.draw(classroom, "均衡", 2)
        self.assertEqual(sum(s["WaitCount"] == 1 for s in classroom["Students"]), 2)
        selected = core.student_by_id(classroom, batch["Entries"][0]["StudentId"])
        core.set_absent(classroom, selected, None, True)
        self.assertEqual(core.missing_positions(batch), [1])
        with self.assertRaises(ValueError):
            core.draw(classroom, "均衡", 1)
        core.replace_missing(classroom, batch)
        self.assertEqual(core.missing_positions(batch), [])
        self.assertEqual(sum(e["Valid"] for e in batch["Entries"]), 2)
        self.assertLessEqual(max(s["WaitCount"] for s in classroom["Students"]), 1)

    def test_reset_round_keeps_history_and_clears_old_seen(self):
        classroom = core.new_class("测试", "一班")
        classroom["VipEnabled"] = False
        add_students(classroom, 2)
        core.draw(classroom, "不重复", 2)
        core.reset_round(classroom, "不重复")
        self.assertEqual(classroom["NoRepeatRound"], 1)
        self.assertEqual(classroom["NoRepeatCycle"], 1)
        self.assertEqual(len(classroom["Batches"]), 1)
        self.assertIsNone(core.preview(classroom, "不重复", 2))
        second = core.draw(classroom, "不重复", 2)
        self.assertEqual(second["Round"], 1)
        self.assertEqual(second["Cycle"], 1)

    def test_reset_round_targets_only_selected_mode(self):
        classroom = core.new_class("测试", "一班")
        classroom["VipEnabled"] = False
        add_students(classroom, 3)
        core.draw(classroom, "普通", 1)
        core.new_round(classroom, "普通")
        core.new_round(classroom, "均衡")
        core.reset_round(classroom, "普通")
        self.assertEqual(classroom["NormalRound"], 1)
        self.assertEqual(classroom["NormalCycle"], 1)
        self.assertEqual(classroom["BalancedRound"], 2)
        self.assertEqual(classroom["BalancedCycle"], 0)
        self.assertEqual(len(classroom["Batches"]), 1)
        self.assertEqual(classroom["Batches"][0]["Mode"], "普通")

    def test_legacy_migration_and_local_time(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            classroom = core.new_class("测试", "一班")
            student = add_students(classroom, 1)[0]
            student["AbsentUntil"] = core.date_json(core.now() + timedelta(hours=2))
            old = directory / "data.json"
            old.write_text(json.dumps({"Version": 1, "LastClassId": None, "Classes": [classroom]}, ensure_ascii=False), encoding="utf-8")
            original = old.read_bytes()
            store = core.DataStore(directory)
            self.assertTrue(store.migrated_from_legacy)
            self.assertTrue(core.is_absent(store.data["Classes"][0]["Students"][0]))
            self.assertTrue(store.save())
            self.assertEqual(old.read_bytes(), original)
            self.assertTrue((directory / "data_python.json").exists())
            self.assertTrue(store.save())
            self.assertTrue((directory / "data_python.json.bak").exists())


if __name__ == "__main__":
    unittest.main()
