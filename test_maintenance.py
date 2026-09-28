"""Destructive flows are tested only in temporary directories."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import python_core as core
import python_maintenance as maintenance


class MaintenanceTest(unittest.TestCase):
    def make_store(self, directory: Path) -> core.DataStore:
        store = core.DataStore(directory)
        classroom = core.new_class("测试", "一班")
        classroom["VipEnabled"] = False
        classroom["Students"] = [core.new_student("甲", "01"), core.new_student("乙", "02")]
        core.draw(classroom, "均衡", 1)
        store.data["Classes"].append(classroom)
        store.data["LastClassId"] = classroom["Id"]
        self.assertTrue(store.save())
        return store

    def test_results_reset_keeps_history_and_restarts_weight(self):
        classroom = core.new_class("测试", "一班")
        classroom["VipEnabled"] = False
        classroom["Students"] = [core.new_student("甲"), core.new_student("乙")]
        core.draw(classroom, "均衡", 1)
        data = {"Version": 1, "LastClassId": classroom["Id"], "Classes": [classroom]}
        result = maintenance.reset_data(data, "class", classroom["Id"], {"results"})
        changed = result["Classes"][0]
        self.assertEqual(len(changed["Batches"]), 1)
        self.assertEqual(changed["WeightStartIndex"], 1)
        self.assertEqual(changed["BalancedRound"], 1)
        self.assertEqual(changed["BalancedCycle"], 1)
        self.assertTrue(all(s["WaitCount"] == 0 for s in changed["Students"]))
        core.normalize(result)
        self.assertTrue(all(s["WaitCount"] == 0 for s in changed["Students"]))
        self.assertEqual(len(classroom["Batches"]), 1)

    def test_dependent_reset_options_and_scope(self):
        first, second = core.new_class("测试", "一班"), core.new_class("测试", "二班")
        first["Students"].append(core.new_student("甲"))
        second["Students"].append(core.new_student("乙"))
        data = {"Version": 1, "LastClassId": first["Id"], "Classes": [first, second]}
        self.assertEqual(maintenance.expanded_options({"history"}), {"history", "results"})
        self.assertEqual(maintenance.expanded_options({"roster"}), {"roster", "history", "results"})
        changed = maintenance.reset_data(data, "class", first["Id"], {"roster"})
        self.assertEqual(changed["Classes"][0]["Students"], [])
        self.assertEqual(len(changed["Classes"][1]["Students"]), 1)
        self.assertEqual(len(data["Classes"][0]["Students"]), 1)
        removed = maintenance.reset_data(data, "class", first["Id"], {"classes"})
        self.assertEqual(len(removed["Classes"]), 1)
        self.assertIsNone(removed["LastClassId"])
        all_removed = maintenance.reset_data(data, "all", None, {"classes"})
        self.assertEqual(all_removed["Classes"], [])

    def test_local_password_backup_reset_and_restore(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            store = self.make_store(directory)
            service = maintenance.LocalMaintenance(store)
            self.assertTrue(service.protection.verify("admin"))
            service.protection.change_password("admin", "secret123")
            self.assertFalse(service.protection.verify("admin"))
            self.assertTrue(service.protection.verify("secret123"))
            self.assertNotIn("secret123", (directory / "protection.json").read_text(encoding="utf-8"))
            with self.assertRaises(ValueError):
                service.reset("all", None, {"classes"}, "wrong")
            self.assertFalse(service.list_backups())
            original_id = store.data["Classes"][0]["Id"]
            backup = service.reset("all", None, {"classes"}, "secret123")
            self.assertEqual(store.data["Classes"], [])
            self.assertTrue(backup.is_file())
            self.assertEqual(len(json.loads(backup.read_text(encoding="utf-8"))["Classes"]), 1)
            before_restore = service.restore(backup, "secret123")
            self.assertTrue(before_restore.is_file())
            self.assertEqual(store.data["Classes"][0]["Id"], original_id)

    def test_forgot_password_preserves_recoverable_backup(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = self.make_store(Path(temporary))
            service = maintenance.LocalMaintenance(store)
            service.protection.change_password("admin", "changed987")
            backup = service.forget_password()
            self.assertEqual(store.data["Classes"], [])
            self.assertTrue(service.protection.verify("admin"))
            self.assertFalse(service.protection.verify("changed987"))
            self.assertTrue(backup.is_file())
            service.restore(backup, "admin")
            self.assertEqual(len(store.data["Classes"]), 1)

    def test_restore_rejects_outside_backup_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            store = self.make_store(directory)
            service = maintenance.LocalMaintenance(store)
            outside = directory / "data_python.json"
            with self.assertRaises(ValueError):
                service.restore(outside, "admin")

    def test_backup_failure_cannot_clear_data(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = self.make_store(Path(temporary))
            service = maintenance.LocalMaintenance(store)
            with patch.object(service, "backup", side_effect=OSError("模拟备份失败")):
                with self.assertRaises(OSError):
                    service.reset("all", None, {"classes"}, "admin")
            self.assertEqual(len(store.data["Classes"]), 1)
            self.assertEqual(len(core.DataStore(Path(temporary)).data["Classes"]), 1)

    def test_forgot_password_failure_rolls_back_data(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            store = self.make_store(directory)
            service = maintenance.LocalMaintenance(store)
            service.protection.change_password("admin", "changed987")
            with patch.object(service.protection, "reset_to_default", side_effect=OSError("模拟密码写入失败")):
                with self.assertRaises(RuntimeError):
                    service.forget_password()
            self.assertEqual(len(store.data["Classes"]), 1)
            self.assertEqual(len(core.DataStore(directory).data["Classes"]), 1)
            self.assertTrue(service.protection.verify("changed987"))
            self.assertTrue(service.list_backups())


if __name__ == "__main__":
    unittest.main()
