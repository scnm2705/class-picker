"""Offline class picker rules and disk persistence.

The JSON field names intentionally match TEST 0.4 so existing U-disk data loads.
"""
from __future__ import annotations

import copy
import json
import math
import os
import random
import re
import shutil
import tempfile
import uuid
from datetime import datetime
from pathlib import Path


MODES = ("不重复", "普通", "均衡")
ROUND_FIELDS = {"不重复": "NoRepeatRound", "普通": "NormalRound", "均衡": "BalancedRound"}
CYCLE_FIELDS = {"不重复": "NoRepeatCycle", "普通": "NormalCycle", "均衡": "BalancedCycle"}
RNG = random.SystemRandom()
DOTNET_DATE = re.compile(r"^/Date\((-?\d+)(?:[+-]\d+)?\)/$")


def now() -> datetime:
    return datetime.now().astimezone()


def parse_date(value) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value.astimezone() if value.tzinfo else value.astimezone()
    match = DOTNET_DATE.match(str(value))
    if match:
        return datetime.fromtimestamp(int(match.group(1)) / 1000).astimezone()
    parsed = datetime.fromisoformat(str(value))
    return parsed.astimezone() if parsed.tzinfo else parsed.astimezone()


def date_json(value: datetime | None) -> str | None:
    if value is None:
        return None
    return f"/Date({int(value.timestamp() * 1000)})/"


def new_class(grade: str, name: str) -> dict:
    return {
        "Id": uuid.uuid4().hex, "Grade": grade, "Name": name,
        "DefaultMode": "不重复", "NoRepeatRound": 1, "NormalRound": 1,
        "BalancedRound": 1, "NoRepeatCycle": 0, "NormalCycle": 0,
        "BalancedCycle": 0, "RoundSerial": 0, "VipEnabled": True, "VipPerBatch": 1,
        "FillVipShortage": True, "VipRandomForGroups": False,
        "KeepAbsenceOnRestart": True, "BaseWeight": 1.0,
        "Growth": 0.05, "MaxWeight": 2.0, "NextVipOrder": 1,
        "AutoCurrentDetail": True, "WeightStartIndex": 0,
        "Students": [], "Batches": [],
    }


def new_student(name: str, number: str = "", archived: bool = False) -> dict:
    return {
        "Id": uuid.uuid4().hex, "Name": name, "Number": number,
        "Archived": archived, "AbsentUntil": None, "AbsentIndefinite": False,
        "VipOrder": 0, "VipWaiting": False, "VipCompletedMode": None,
        "VipCompletedRound": 0, "VipCompletedCycle": 0,
        "VipCompletedSerial": 0, "WaitCount": 0,
    }


def _reconstruct_round_serial(classroom: dict) -> tuple[int, dict[str, int]]:
    """Infer explicit round transitions in pre-serial data without changing history."""
    observed: dict[str, tuple[int, int]] = {}
    completion_serial: dict[str, int] = {}
    serial = 0
    for batch in classroom["Batches"]:
        mode = batch.get("Mode")
        if mode not in MODES:
            continue
        state = (int(batch.get("Cycle", 0)), int(batch.get("Round", 1)))
        if mode in observed and observed[mode] != state:
            serial += 1
        observed[mode] = state
        for entry in batch.get("Entries", []):
            if entry.get("Valid") and entry.get("Vip"):
                completion_serial[entry["StudentId"]] = serial
    for mode in MODES:
        current = (classroom_cycle(classroom, mode), classroom_round(classroom, mode))
        last = observed.get(mode, (0, 1))
        if current > last:
            serial += 1
    return serial, completion_serial


def normalize(data: dict) -> None:
    if data.get("Version") != 1 or not isinstance(data.get("Classes"), list):
        raise ValueError("无法识别的数据版本；原文件不会被覆盖。")
    for classroom in data["Classes"]:
        needs_serial_migration = "RoundSerial" not in classroom
        classroom.setdefault("Students", [])
        classroom.setdefault("Batches", [])
        classroom.setdefault("NoRepeatRound", 1)
        classroom.setdefault("NormalRound", 1)
        classroom.setdefault("BalancedRound", 1)
        classroom.setdefault("NoRepeatCycle", 0)
        classroom.setdefault("NormalCycle", 0)
        classroom.setdefault("BalancedCycle", 0)
        classroom.setdefault("DefaultMode", "不重复")
        classroom.setdefault("AutoCurrentDetail", True)
        classroom["WeightStartIndex"] = min(
            max(0, int(classroom.get("WeightStartIndex", 0))), len(classroom["Batches"])
        )
        classroom.setdefault("VipEnabled", False)
        classroom.setdefault("VipPerBatch", 1)
        classroom.setdefault("FillVipShortage", True)
        classroom.setdefault("VipRandomForGroups", False)
        classroom.setdefault("KeepAbsenceOnRestart", True)
        classroom.setdefault("BaseWeight", 1.0)
        classroom.setdefault("Growth", 0.05)
        classroom.setdefault("MaxWeight", 2.0)
        classroom.setdefault("NextVipOrder", 1)
        for student in classroom["Students"]:
            student.setdefault("Number", "")
            student.setdefault("Archived", False)
            student.setdefault("AbsentUntil", None)
            student.setdefault("AbsentIndefinite", False)
            student.setdefault("VipWaiting", False)
            student.setdefault("VipOrder", 0)
            student.setdefault("VipCompletedMode", None)
            student.setdefault("VipCompletedRound", 0)
            student.setdefault("VipCompletedCycle", 0)
            student.setdefault("WaitCount", 0)
            if not classroom["KeepAbsenceOnRestart"]:
                student["AbsentUntil"] = None
                student["AbsentIndefinite"] = False
        for batch in classroom["Batches"]:
            batch.setdefault("Cycle", 0)
            batch.setdefault("ClosedWithMissing", False)
            batch.setdefault("Entries", [])
            batch.setdefault("OrdinaryCandidates", [])
            batch.setdefault("SlotTypes", [])
            batch.setdefault("FillVipShortage", False)
        if needs_serial_migration:
            serial, completed_at = _reconstruct_round_serial(classroom)
            classroom["RoundSerial"] = serial
            for student in classroom["Students"]:
                student["VipCompletedSerial"] = completed_at.get(student["Id"], serial)
        else:
            for student in classroom["Students"]:
                student.setdefault("VipCompletedSerial", classroom["RoundSerial"])
        expire_absence(classroom)
        recompute_waits(classroom)


class DataStore:
    def __init__(self, directory: Path):
        self.path = directory / "data_python.json"
        legacy_path = directory / "data.json"
        self.last_saved: datetime | None = None
        self.last_error: str | None = None
        source = self.path if self.path.exists() else legacy_path
        self.migrated_from_legacy = not self.path.exists() and legacy_path.exists()
        if source.exists():
            try:
                self.data = json.loads(source.read_text(encoding="utf-8-sig"))
                normalize(self.data)
            except Exception as exc:
                raise RuntimeError(
                    "数据文件读取失败。请保留原始数据和备份；不会自动覆盖。\n" + str(exc)
                ) from exc
        else:
            self.data = {"Version": 1, "LastClassId": None, "Classes": []}

    def save(self) -> bool:
        temporary: Path | None = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", newline="", delete=False,
                dir=self.path.parent, prefix="data-", suffix=".tmp"
            ) as stream:
                temporary = Path(stream.name)
                json.dump(self.data, stream, ensure_ascii=False, separators=(",", ":"))
                stream.flush()
                os.fsync(stream.fileno())
            if self.path.exists():
                shutil.copy2(self.path, self.path.with_name("data_python.json.bak"))
            os.replace(temporary, self.path)
            self.last_saved = now()
            self.last_error = None
            return True
        except Exception as exc:
            self.last_error = str(exc)
            return False
        finally:
            if temporary and temporary.exists():
                try:
                    temporary.unlink()
                except OSError:
                    pass


def classroom_round(classroom: dict, mode: str) -> int:
    return int(classroom.get(ROUND_FIELDS[mode], 1))


def classroom_cycle(classroom: dict, mode: str) -> int:
    return int(classroom.get(CYCLE_FIELDS[mode], 0))


def student_by_id(classroom: dict, student_id: str) -> dict | None:
    return next((s for s in classroom["Students"] if s["Id"] == student_id), None)


def rename_student(classroom: dict, student_id: str, name: str) -> None:
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 80 or any(ord(c) < 32 for c in name):
        raise ValueError('姓名须为 1～80 字，不能包含换行或控制字符。')
    student = student_by_id(classroom, student_id)
    if not student: raise ValueError('学生不存在。')
    student['Name'] = name.strip()


def is_absent(student: dict, at: datetime | None = None) -> bool:
    if student.get("AbsentIndefinite", False):
        return True
    until = parse_date(student.get("AbsentUntil"))
    return bool(until and until > (at or now()))


def expire_absence(classroom: dict, at: datetime | None = None) -> bool:
    changed = False
    current = at or now()
    for student in classroom["Students"]:
        until = parse_date(student.get("AbsentUntil"))
        if until and until <= current:
            student["AbsentUntil"] = None
            changed = True
    return changed


def vip_hold(classroom: dict, student: dict) -> bool:
    mode = student.get("VipCompletedMode")
    if mode not in MODES:
        return False
    return int(student.get("VipCompletedSerial", 0)) >= int(classroom.get("RoundSerial", 0))


def seen(classroom: dict, mode: str, student_id: str) -> bool:
    if mode != "不重复":
        return False
    current_round, current_cycle = classroom_round(classroom, mode), classroom_cycle(classroom, mode)
    return any(
        batch.get("Mode") == mode
        and int(batch.get("Round", 0)) == current_round
        and int(batch.get("Cycle", 0)) == current_cycle
        and any(e.get("Valid") and e.get("StudentId") == student_id for e in batch.get("Entries", []))
        for batch in classroom["Batches"]
    )


def vip_candidates(classroom: dict, mode: str, exclude=()) -> list[dict]:
    excluded = set(exclude)
    return sorted(
        (
            s for s in classroom["Students"]
            if not s.get("Archived") and s.get("VipWaiting") and not is_absent(s)
            and not seen(classroom, mode, s["Id"]) and s["Id"] not in excluded
        ),
        key=lambda s: int(s.get("VipOrder", 0)),
    )


def vip_queue_positions(classroom: dict) -> dict[str, int]:
    """One-based positions of current waiting tasks, independent of stable sort keys."""
    waiting = sorted(
        (s for s in classroom["Students"] if s.get("VipWaiting")),
        key=lambda s: int(s.get("VipOrder", 0)),
    )
    return {student["Id"]: index for index, student in enumerate(waiting, 1)}


def ordinary_candidates(classroom: dict, mode: str, exclude=()) -> list[dict]:
    excluded = set(exclude)
    return [
        s for s in classroom["Students"]
        if not s.get("Archived") and (not s.get("VipWaiting") or not classroom.get("VipEnabled"))
        and not vip_hold(classroom, s) and not is_absent(s)
        and not seen(classroom, mode, s["Id"]) and s["Id"] not in excluded
    ]


def weight(classroom: dict, student: dict) -> float:
    return min(
        float(classroom.get("MaxWeight", 2)),
        float(classroom.get("BaseWeight", 1))
        + float(classroom.get("Growth", 0.05)) * max(0, int(student.get("WaitCount", 0))),
    )


def choose_ordinary(classroom: dict, mode: str, candidates: list[dict]) -> dict:
    if not candidates:
        raise ValueError("没有可参与的普通人员。")
    if mode != "均衡":
        return RNG.choice(candidates)
    total = sum(weight(classroom, s) for s in candidates)
    point = RNG.random() * total
    for student in candidates:
        point -= weight(classroom, student)
        if point < 0:
            return student
    return candidates[-1]


def choose_vip(classroom: dict, candidates: list[dict], single: bool) -> dict:
    if not candidates:
        raise ValueError("没有可参与的VIP人员。")
    return RNG.choice(candidates) if not single and classroom.get("VipRandomForGroups") else candidates[0]


def missing_positions(batch: dict) -> list[int]:
    valid = {int(e["Position"]) for e in batch.get("Entries", []) if e.get("Valid")}
    valid.update(int(e["Position"]) for e in batch.get("BoardEvents", []) if not e.get("ResolvedStudentId"))
    return [p for p in range(1, int(batch.get("Count", 0)) + 1) if p not in valid]


def vip_shortage(classroom: dict, mode: str, count: int) -> tuple[int, int] | None:
    """Available and requested VIP counts for a group draw, if short."""
    if count <= 1 or not classroom.get("VipEnabled"):
        return None
    planned = min(count, int(classroom.get("VipPerBatch", 1)))
    available = len(vip_candidates(classroom, mode))
    return (available, planned) if available < planned else None


def preview(classroom: dict, mode: str, count: int) -> str | None:
    if count < 1:
        return "人数必须为正整数。"
    if not any(not s.get("Archived") for s in classroom["Students"]):
        return "名单为空，请先导入学生。"
    vip_count = len(vip_candidates(classroom, mode))
    ordinary_count = len(ordinary_candidates(classroom, mode))
    planned = min(count, int(classroom.get("VipPerBatch", 1))) if classroom.get("VipEnabled") else 0
    if count == 1 and classroom.get("VipEnabled"):
        planned = min(1, vip_count)
    if vip_shortage(classroom, mode, count) and not classroom.get("FillVipShortage"):
        return f"VIP可参与 {vip_count} 人，少于设置的 {planned} 人。请调整VIP安排或开启普通补齐。"
    actual_vip = min(vip_count, planned)
    if ordinary_count < count - actual_vip:
        return f"普通池可参与 {ordinary_count} 人，不足以完成本批 {count} 人。请调整人数、缺席或开启下一轮。"
    return None


def complete_vip(classroom: dict, mode: str, student: dict) -> None:
    student["VipWaiting"] = False
    student["VipCompletedMode"] = mode
    student["VipCompletedRound"] = classroom_round(classroom, mode)
    student["VipCompletedCycle"] = classroom_cycle(classroom, mode)
    student["VipCompletedSerial"] = int(classroom.get("RoundSerial", 0))


def draw(classroom: dict, mode: str, count: int) -> dict:
    expire_absence(classroom)
    last = classroom["Batches"][-1] if classroom["Batches"] else None
    if last and missing_positions(last) and not last.get("ClosedWithMissing"):
        raise ValueError("上一批仍有缺额，请先补抽或明确结束本批。")
    issue = preview(classroom, mode, count)
    if issue:
        raise ValueError(issue)
    planned = min(count, int(classroom.get("VipPerBatch", 1))) if classroom.get("VipEnabled") else 0
    if count == 1 and classroom.get("VipEnabled"):
        planned = min(1, len(vip_candidates(classroom, mode)))
    batch = {
        "Id": uuid.uuid4().hex, "Time": date_json(now()), "Mode": mode,
        "Round": classroom_round(classroom, mode), "Cycle": classroom_cycle(classroom, mode),
        "Count": count, "PlannedVip": planned,
        "FillVipShortage": bool(classroom.get("FillVipShortage")),
        "ClosedWithMissing": False, "SlotTypes": [], "OrdinaryCandidates": [], "Entries": [],
    }
    used: list[str] = []
    vip_total = min(planned, len(vip_candidates(classroom, mode))) if classroom.get("VipEnabled") else 0
    for pos in range(1, vip_total + 1):
        student = choose_vip(classroom, vip_candidates(classroom, mode, used), count == 1)
        batch["SlotTypes"].append("VIP")
        batch["Entries"].append({"Position": pos, "StudentId": student["Id"], "Vip": True,
                                 "Valid": True, "Source": "VIP", "ReplacesId": None})
        used.append(student["Id"])
        complete_vip(classroom, mode, student)
    ordinary = ordinary_candidates(classroom, mode, used)
    if count > vip_total and mode == "均衡":
        batch["OrdinaryCandidates"] = [s["Id"] for s in ordinary]
    for pos in range(vip_total + 1, count + 1):
        student = choose_ordinary(classroom, mode, [s for s in ordinary if s["Id"] not in used])
        fill = pos <= planned
        batch["SlotTypes"].append("VIP补位" if fill else "普通")
        batch["Entries"].append({"Position": pos, "StudentId": student["Id"], "Vip": False,
                                 "Valid": True, "Source": "普通补位" if fill else "普通池", "ReplacesId": None})
        used.append(student["Id"])
    classroom["Batches"].append(batch)
    recompute_waits(classroom)
    return batch


def recompute_waits(classroom: dict) -> None:
    lookup = {s["Id"]: s for s in classroom["Students"]}
    for student in classroom["Students"]:
        student["WaitCount"] = 0
    start = min(max(0, int(classroom.get("WeightStartIndex", 0))), len(classroom["Batches"]))
    for batch in classroom["Batches"][start:]:
        if batch.get("Mode") != "均衡":
            continue
        selected = {
            e["StudentId"] for e in batch.get("Entries", [])
            if e.get("Valid") and not e.get("Vip")
        }
        if not selected:
            continue
        invalid = {e["StudentId"] for e in batch.get("Entries", []) if not e.get("Valid")}
        for student_id in set(batch.get("OrdinaryCandidates") or []):
            student = lookup.get(student_id)
            if student is None or student_id in invalid:
                continue
            student["WaitCount"] = 0 if student_id in selected else student["WaitCount"] + 1
        for student_id in selected:
            if student_id in lookup:
                lookup[student_id]["WaitCount"] = 0


def set_absent(classroom: dict, student: dict, until: datetime | None, indefinite: bool) -> None:
    student["AbsentUntil"] = date_json(until)
    student["AbsentIndefinite"] = indefinite
    if classroom["Batches"]:
        batch = classroom["Batches"][-1]
        for entry in batch["Entries"]:
            if entry["StudentId"] == student["Id"] and entry.get("Valid"):
                entry["Valid"] = False
                batch["ClosedWithMissing"] = False
                if entry.get("Vip"):
                    student["VipWaiting"] = True
                    student["VipCompletedMode"] = None
                    student["VipCompletedRound"] = 0
                    student["VipCompletedCycle"] = 0
                    student["VipCompletedSerial"] = 0
                batch["OrdinaryCandidates"] = [x for x in batch.get("OrdinaryCandidates", []) if x != student["Id"]]
    recompute_waits(classroom)


def replacement_issue(classroom: dict, batch: dict) -> str | None:
    used = [e["StudentId"] for e in batch["Entries"] if e.get("Valid")]
    for position in missing_positions(batch):
        needs_vip = batch["SlotTypes"][position - 1] == "VIP"
        vip = vip_candidates(classroom, batch["Mode"], used)
        if needs_vip and vip:
            used.append(vip[0]["Id"])
            continue
        if needs_vip and not batch.get("FillVipShortage"):
            return f"第 {position} 位缺少可参与VIP；此批未开启普通补齐。"
        ordinary = ordinary_candidates(classroom, batch["Mode"], used)
        if not ordinary:
            return f"第 {position} 位没有可参与的普通人员。"
        used.append(ordinary[0]["Id"])
    return None


def replace_missing(classroom: dict, batch: dict) -> None:
    if batch.get("ClosedWithMissing"):
        raise ValueError("本批已明确结束，不能再补抽。")
    issue = replacement_issue(classroom, batch)
    if issue:
        raise ValueError(issue)
    for position in missing_positions(batch):
        used = [e["StudentId"] for e in batch["Entries"] if e.get("Valid")]
        needs_vip = batch["SlotTypes"][position - 1] == "VIP"
        vip = vip_candidates(classroom, batch["Mode"], used)
        chosen_vip = needs_vip and bool(vip)
        if chosen_vip:
            student = choose_vip(classroom, vip, batch["Count"] == 1)
            complete_vip(classroom, batch["Mode"], student)
        else:
            ordinary = ordinary_candidates(classroom, batch["Mode"], used)
            if batch["Mode"] == "均衡":
                batch["OrdinaryCandidates"] = list(dict.fromkeys(batch.get("OrdinaryCandidates", []) + [s["Id"] for s in ordinary]))
            student = choose_ordinary(classroom, batch["Mode"], ordinary)
        invalid = next((e for e in reversed(batch["Entries"]) if e["Position"] == position and not e.get("Valid")), None)
        batch["Entries"].append({
            "Position": position, "StudentId": student["Id"], "Vip": chosen_vip,
            "Valid": True, "Source": "VIP补抽" if chosen_vip else "普通补位" if needs_vip else "普通补抽",
            "ReplacesId": invalid["StudentId"] if invalid else None,
        })
    recompute_waits(classroom)


def new_round(classroom: dict, mode: str) -> None:
    classroom[ROUND_FIELDS[mode]] = classroom_round(classroom, mode) + 1
    classroom["RoundSerial"] = int(classroom.get("RoundSerial", 0)) + 1


def reset_round(classroom: dict, mode: str) -> None:
    """Start a new cycle at round 1 while retaining every historical batch."""
    classroom[CYCLE_FIELDS[mode]] = classroom_cycle(classroom, mode) + 1
    classroom[ROUND_FIELDS[mode]] = 1
    classroom["RoundSerial"] = int(classroom.get("RoundSerial", 0)) + 1


def add_vip(classroom: dict, student: dict) -> None:
    if student.get("VipWaiting"):
        return
    if vip_hold(classroom, student):
        raise ValueError("该学生本轮已完成VIP，请等下一轮。")
    student["VipWaiting"] = True
    student["VipOrder"] = int(classroom.get("NextVipOrder", 1))
    classroom["NextVipOrder"] = student["VipOrder"] + 1


def move_vip(classroom: dict, student: dict, direction: int) -> None:
    queue = sorted((s for s in classroom["Students"] if s.get("VipWaiting")), key=lambda s: s.get("VipOrder", 0))
    if student not in queue:
        return
    index = queue.index(student)
    target = index + direction
    if 0 <= target < len(queue):
        student["VipOrder"], queue[target]["VipOrder"] = queue[target]["VipOrder"], student["VipOrder"]
