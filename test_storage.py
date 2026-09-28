"""Storage location migration tests use temporary directories only."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import python_core as core
import python_maintenance as maintenance
import python_storage as storage


class StorageTest(unittest.TestCase):
    def make_data(self, base: Path) -> Path:
        source = base / "data"
        store = core.DataStore(source)
        store.data["Classes"].append(core.new_class("测试", "一班"))
        self.assertTrue(store.save())
        service = maintenance.LocalMaintenance(store)
        service.protection.change_password("admin", "secret123")
        service.backup("reset")
        (source / "data.json").write_text("legacy", encoding="utf-8")
        return source

    def test_migration_copies_all_data_and_keeps_original(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary) / "program"
            base.mkdir()
            source = self.make_data(base)
            target = Path(temporary) / "new_data"
            target.mkdir()
            result = storage.migrate_directory(base, source, target)
            self.assertEqual(result, target)
            self.assertEqual(storage.configured_directory(base), target)
            self.assertEqual(len(core.DataStore(target).data["Classes"]), 1)
            self.assertTrue(maintenance.LocalProtection(target).verify("secret123"))
            self.assertTrue(list((target / "backups").glob("*.json")))
            self.assertEqual((target / "data.json").read_bytes(), (source / "data.json").read_bytes())
            self.assertTrue((source / "data_python.json").is_file())
            self.assertTrue((source / "protection.json").is_file())

    def test_relative_location_moves_with_program(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary) / "program"
            base.mkdir()
            source = self.make_data(base)
            target = base / "saved_data"
            storage.migrate_directory(base, source, target)
            config = json.loads((base / storage.CONFIG_NAME).read_text(encoding="utf-8"))
            self.assertEqual(config["DataDirectory"], "saved_data")
            moved = Path(temporary) / "moved_program"
            base.rename(moved)
            self.assertEqual(storage.configured_directory(moved), moved / "saved_data")

    def test_reject_existing_data_and_missing_configured_location(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary) / "program"
            base.mkdir()
            source = self.make_data(base)
            target = Path(temporary) / "occupied"
            target.mkdir()
            (target / "note.txt").write_text("retain", encoding="utf-8")
            with self.assertRaises(ValueError):
                storage.migrate_directory(base, source, target)
            self.assertEqual((target / "note.txt").read_text(encoding="utf-8"), "retain")
            self.assertFalse((base / storage.CONFIG_NAME).exists())
            (base / storage.CONFIG_NAME).write_text('{"Version":1,"DataDirectory":"missing"}', encoding="utf-8")
            with self.assertRaises(RuntimeError):
                storage.configured_directory(base)
            self.assertTrue((source / "data_python.json").is_file())

    def test_copy_failure_does_not_switch_location(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary) / "program"
            base.mkdir()
            source = self.make_data(base)
            target = Path(temporary) / "new_data"
            with patch.object(storage.shutil, "copytree", side_effect=OSError("simulated copy failure")):
                with self.assertRaises(OSError):
                    storage.migrate_directory(base, source, target)
            self.assertEqual(storage.configured_directory(base), source)
            self.assertTrue((source / "data_python.json").is_file())


if __name__ == "__main__":
    unittest.main()
