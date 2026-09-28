"""Local-only password protection, full backups, reset, and recovery."""
from __future__ import annotations

import copy
import hashlib
import hmac
import json
import os
import tempfile
import uuid
from pathlib import Path

import python_core as core


PASSWORD_ITERATIONS = 260_000
OPTION_NAMES = {
    "history": "抽取历史记录",
    "results": "当前结果及抽取进度",
    "roster": "班级人员名单",
    "classes": "班级",
}


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False,
                                         dir=path.parent, prefix="local-", suffix=".tmp") as stream:
            temporary = Path(stream.name)
            json.dump(payload, stream, ensure_ascii=False, separators=(",", ":"))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary and temporary.exists():
            temporary.unlink()


class LocalProtection:
    """A local salted hash; a fresh installation accepts the initial password admin."""

    def __init__(self, directory: Path):
        self.path = Path(directory) / "protection.json"

    def verify(self, password: str) -> bool:
        if not self.path.exists():
            return hmac.compare_digest(password, "admin")
        record = json.loads(self.path.read_text(encoding="utf-8"))
        if record.get("Version") != 1:
            raise ValueError("本地密码文件格式无法识别。可使用忘记密码流程恢复。")
        salt = bytes.fromhex(record["Salt"])
        expected = bytes.fromhex(record["Hash"])
        iterations = int(record["Iterations"])
        if len(salt) < 16 or len(expected) != 32 or not 100_000 <= iterations <= 2_000_000:
            raise ValueError("本地密码文件无效。可使用忘记密码流程恢复。")
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
        return hmac.compare_digest(actual, expected)

    def _write_password(self, password: str) -> None:
        if len(password) < 4:
            raise ValueError("新密码至少需要 4 个字符。")
        salt = os.urandom(16)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PASSWORD_ITERATIONS)
        _write_json(self.path, {"Version": 1, "Iterations": PASSWORD_ITERATIONS,
                                "Salt": salt.hex(), "Hash": digest.hex()})

    def change_password(self, current: str, new_password: str) -> None:
        if not self.verify(current):
            raise ValueError("当前密码不正确。")
        self._write_password(new_password)

    def reset_to_default(self) -> None:
        self._write_password("admin")


def expanded_options(options: set[str]) -> set[str]:
    if not options or not options <= OPTION_NAMES.keys():
        raise ValueError("请至少选择一项有效的重置内容。")
    result = set(options)
    if "classes" in result:
        result.update(("roster", "history", "results"))
    elif "roster" in result:
        result.update(("history", "results"))
    elif "history" in result:
        result.add("results")
    return result


def target_classes(data: dict, scope: str, class_id: str | None) -> list[dict]:
    if scope == "all":
        if not data["Classes"]:
            raise ValueError("当前没有班级可重置。")
        return list(data["Classes"])
    if scope != "class":
        raise ValueError("重置范围无效。")
    target = next((item for item in data["Classes"] if item["Id"] == class_id), None)
    if target is None:
        raise ValueError("所选班级不存在，请重新选择。")
    return [target]


def reset_preview(data: dict, scope: str, class_id: str | None, options: set[str]) -> str:
    targets = target_classes(data, scope, class_id)
    effective = expanded_options(options)
    names = "、".join(f"{item.get('Grade', '')}·{item.get('Name', '')}" for item in targets[:4])
    if len(targets) > 4:
        names += f"等 {len(targets)} 个班级"
    people = sum(len(item["Students"]) for item in targets)
    batches = sum(len(item["Batches"]) for item in targets)
    lines = [f"范围：{names}", f"涉及：{len(targets)} 个班级、{people} 名人员、{batches} 个历史批次",
             "实际清除：" + "、".join(OPTION_NAMES[key] for key in OPTION_NAMES if key in effective)]
    added = effective - options
    if added:
        lines.append("因数据关联，额外清除：" + "、".join(OPTION_NAMES[key] for key in OPTION_NAMES if key in added))
    lines += ["执行前会在当前数据目录的 backups 文件夹保存完整本地备份。",
              "清除后不能撤销；可用备份恢复。恢复会覆盖恢复时的当前数据。",
              "所有操作仅在本机文件夹完成，不上传，也不联网。"]
    return "\n".join(lines)


def _reset_progress(classroom: dict, keep_history: bool) -> None:
    if "BoardGame" in classroom:
        classroom["BoardGame"]["Modes"] = {}
    for mode in core.MODES:
        classroom[core.ROUND_FIELDS[mode]] = 1
        field = core.CYCLE_FIELDS[mode]
        classroom[field] = int(classroom.get(field, 0)) + 1 if keep_history else 0
    classroom["RoundSerial"] = int(classroom.get("RoundSerial", 0)) + 1
    classroom["WeightStartIndex"] = len(classroom["Batches"]) if keep_history else 0
    core.recompute_waits(classroom)


def reset_data(data: dict, scope: str, class_id: str | None, options: set[str]) -> dict:
    effective = expanded_options(options)
    target_ids = {item["Id"] for item in target_classes(data, scope, class_id)}
    updated = copy.deepcopy(data)
    if "classes" in effective:
        updated["Classes"] = [item for item in updated["Classes"] if item["Id"] not in target_ids]
        if updated.get("LastClassId") in target_ids:
            updated["LastClassId"] = None
        return updated
    for classroom in updated["Classes"]:
        if classroom["Id"] not in target_ids:
            continue
        if "history" in effective:
            classroom["Batches"] = []
        if "roster" in effective:
            classroom["Students"] = []
            classroom["NextVipOrder"] = 1
        if "results" in effective:
            _reset_progress(classroom, keep_history="history" not in effective)
    return updated


class LocalMaintenance:
    def __init__(self, store: core.DataStore):
        self.store = store
        self.directory = store.path.parent
        self.backups = self.directory / "backups"
        self.protection = LocalProtection(self.directory)

    def backup(self, reason: str) -> Path:
        if reason not in ("reset", "forgot", "before_restore"):
            raise ValueError("备份原因无效。")
        stamp = core.now().strftime("%Y%m%d-%H%M%S")
        destination = self.backups / f"{stamp}-{reason}-{uuid.uuid4().hex[:8]}.json"
        _write_json(destination, self.store.data)
        return destination

    def list_backups(self) -> list[Path]:
        if not self.backups.exists():
            return []
        return sorted(self.backups.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True)

    def _save_replacement(self, replacement: dict) -> None:
        previous = self.store.data
        self.store.data = replacement
        if not self.store.save():
            self.store.data = previous
            raise OSError("保存数据失败，原数据未修改：" + str(self.store.last_error))

    def reset(self, scope: str, class_id: str | None, options: set[str], password: str) -> Path:
        if not self.protection.verify(password):
            raise ValueError("保护密码不正确。")
        replacement = reset_data(self.store.data, scope, class_id, options)
        backup_path = self.backup("reset")
        self._save_replacement(replacement)
        return backup_path

    def forget_password(self) -> Path:
        backup_path = self.backup("forgot")
        previous = self.store.data
        self._save_replacement({"Version": 1, "LastClassId": None, "Classes": []})
        try:
            self.protection.reset_to_default()
        except Exception as exc:
            try:
                self._save_replacement(previous)
            except Exception as rollback_exc:
                raise RuntimeError(f"密码重置失败，数据回滚也失败。完整备份保存在 {backup_path}：{rollback_exc}") from exc
            raise RuntimeError("密码重置失败，原数据已恢复。") from exc
        return backup_path

    def restore(self, backup_path: Path, password: str) -> Path:
        if not self.protection.verify(password):
            raise ValueError("保护密码不正确。")
        resolved = Path(backup_path).resolve()
        if resolved.parent != self.backups.resolve() or resolved.suffix.lower() != ".json" or not resolved.is_file():
            raise ValueError("只能恢复当前数据目录 backups 文件夹内的 JSON 备份。")
        replacement = json.loads(resolved.read_text(encoding="utf-8"))
        core.normalize(replacement)
        before_restore = self.backup("before_restore")
        self._save_replacement(replacement)
        return before_restore
