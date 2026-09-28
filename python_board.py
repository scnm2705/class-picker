"""Board rules layered on the existing Python picker and its JSON store."""
from __future__ import annotations

import copy
import math
import uuid
from collections import Counter

import python_core as core

DEFAULT_SETTINGS = {"ChestChance": 20.0, "Events": [
    {"Id": "again", "Title": "再掷一次", "Weight": 35.0, "Action": "reroll"},
    {"Id": "teacher", "Title": "老师指定一人", "Weight": 35.0, "Action": "teacher"},
    {"Id": "skip", "Title": "幸运跳过", "Weight": 30.0, "Action": "skip"},
]}
RULE_KEYS = ('VipEnabled', 'VipPerBatch', 'FillVipShortage', 'VipRandomForGroups',
             'KeepAbsenceOnRestart', 'BaseWeight', 'Growth', 'MaxWeight')

DEFAULT_VIEW = {'Follow': True, 'Direct': True, 'Dice': True, 'Move': True, 'Highlight': True,
                'DirectSeconds': 2.0, 'DiceSeconds': 1.6, 'MoveSeconds': 1.2, 'HighlightSeconds': 2.5}


def normalize_view(value):
    value = value if isinstance(value, dict) else {}
    result = dict(DEFAULT_VIEW)
    if value.get('Pace') == .55:
        result.update(DiceSeconds=.9, MoveSeconds=.7)
    result.update({key: value[key] for key in DEFAULT_VIEW if key in value})
    return result


def validate_view(value):
    if not isinstance(value, dict): raise ValueError('显示设置无效。')
    result = normalize_view(value)
    for key in ('Follow', 'Direct', 'Dice', 'Move', 'Highlight'):
        if not isinstance(result[key], bool): raise ValueError('显示选项须为勾选或不勾选。')
    for key in ('DirectSeconds', 'DiceSeconds', 'MoveSeconds', 'HighlightSeconds'):
        duration = result[key]
        if isinstance(duration, bool) or not isinstance(duration, (float, int)) or not math.isfinite(duration) or not .1 <= duration <= 60:
            raise ValueError('每项时长须为 0.1～60 秒。')
    return result


def validate_rules(value):
    if not isinstance(value, dict) or value.get('mode') not in core.MODES:
        raise ValueError('请选择有效的抽取模式。')
    result = {key: value.get(key) for key in RULE_KEYS}
    for key in ('VipEnabled', 'FillVipShortage', 'VipRandomForGroups', 'KeepAbsenceOnRestart'):
        if not isinstance(result[key], bool): raise ValueError('开关设置无效。')
    quota = result['VipPerBatch']
    if isinstance(quota, bool) or not isinstance(quota, int) or not 0 <= quota <= 999:
        raise ValueError('VIP 人数须为 0～999 的整数。')
    for key in ('BaseWeight', 'Growth', 'MaxWeight'):
        result[key] = float(result[key])
        if not math.isfinite(result[key]): raise ValueError('权重须为有限数值。')
    if result['BaseWeight'] <= 0 or result['Growth'] < 0 or result['MaxWeight'] < result['BaseWeight']:
        raise ValueError('基础权重须大于 0，增长不得为负，上限不得低于基础权重。')
    return result


def validate_settings(value):
    if not isinstance(value, dict):
        raise ValueError("宝箱设置格式不正确。")
    probability = float(value.get("ChestChance", 20))
    if not math.isfinite(probability) or not 0 <= probability <= 100:
        raise ValueError("宝箱格概率必须在 0～100% 之间。")
    events = value.get("Events", [])
    if not isinstance(events, list) or not 1 <= len(events) <= 30:
        raise ValueError("请设置 1～30 项宝箱内容。")
    result, used = [], set()
    for event in events:
        title = str(event.get("Title", "")).strip()
        weight = float(event.get("Weight", 0))
        action = event.get("Action", "message")
        identity = str(event.get("Id") or uuid.uuid4().hex)
        if not title or len(title) > 80 or not math.isfinite(weight) or not 0 <= weight <= 100:
            raise ValueError("内容须为 1～80 字，概率须为 0～100%。")
        if action not in {"message", "reroll", "teacher", "skip", "random_student"} or identity in used:
            raise ValueError("内容类型或编号不正确。")
        used.add(identity)
        result.append({"Id": identity, "Title": title, "Weight": weight, "Action": action})
    if abs(sum(e["Weight"] for e in result) - 100) > .001:
        raise ValueError("各项宝箱内容的概率合计须为 100%。")
    return {"ChestChance": probability, "Events": result}


def ensure_board(classroom, mode):
    active = [s for s in classroom["Students"] if not s.get("Archived")]
    game = classroom.setdefault("BoardGame", {"Version": 1, "Settings": copy.deepcopy(DEFAULT_SETTINGS), "Modes": {}})
    game.setdefault("Settings", copy.deepcopy(DEFAULT_SETTINGS))
    state = game.setdefault("Modes", {}).get(mode)
    ids = sorted(s["Id"] for s in active)
    key = [core.classroom_round(classroom, mode), core.classroom_cycle(classroom, mode)]
    if not state or state.get("Key") != key or state.get("RosterIds") != ids:
        students = active[:]
        core.RNG.shuffle(students)
        slots = []
        for i, student in enumerate(students):
            slots.append({"kind": "student", "id": student["Id"]})
            if (i + 1) % 5 == 0 or i == len(students) - 1:
                slots.append({"kind": "chest", "id": uuid.uuid4().hex, "color": "gold" if (i // 5) % 2 else "purple"})
        if slots:
            offset = core.RNG.randrange(len(slots))
            slots = slots[offset:] + slots[:offset]
        state = {"LayoutId": uuid.uuid4().hex, "Key": key, "RosterIds": ids, "Slots": slots, "Position": 0}
        game["Modes"][mode] = state
    return state


def eligible(classroom, mode, exclude=()):
    return {s["Id"]: s for s in classroom["Students"] if not s.get("Archived")
            and not core.is_absent(s) and not core.vip_hold(classroom, s)
            and not core.seen(classroom, mode, s["Id"]) and s["Id"] not in exclude}


def labels(classroom):
    students = [s for s in classroom["Students"] if not s.get("Archived")]
    counts = Counter(s["Name"] for s in students)
    result, used = {}, set()
    for s in students:
        name = s["Name"]
        label = name if counts[name] == 1 else f"{name}（{s.get('Number') or s['Id'][:6]}）"
        if label in used:
            label = f"{name}（{s['Id'][:8]}）"
        used.add(label)
        result[s["Id"]] = label
    return result


def snapshot(classroom, mode):
    state = ensure_board(classroom, mode)
    names = labels(classroom)
    active = [s for s in classroom["Students"] if not s.get("Archived")]
    done = {e["StudentId"] for b in classroom["Batches"] if b.get("Mode") == mode
            and b.get("Round") == core.classroom_round(classroom, mode)
            and b.get("Cycle", 0) == core.classroom_cycle(classroom, mode)
            for e in b["Entries"] if e.get("Valid")}
    slots = [dict(s, name=names.get(s["id"], "")) for s in state["Slots"]]
    last = classroom["Batches"][-1] if classroom["Batches"] else None
    pending = bool(last and core.missing_positions(last) and not last.get("ClosedWithMissing"))
    round_people = {}
    for b in classroom['Batches']:
        if b.get('Mode') != mode or b.get('Round') != core.classroom_round(classroom, mode) or b.get('Cycle', 0) != core.classroom_cycle(classroom, mode): continue
        for e in b['Entries']:
            if not e.get('Valid'): continue
            sid = e['StudentId']
            person = round_people.pop(sid, {'id': sid, 'name': names.get(sid, (core.student_by_id(classroom, sid) or {}).get('Name', '已转出')), 'count': 0, 'vip': False})
            person['count'] += 1; person['vip'] |= bool(e.get('Vip'))
            round_people[sid] = person
    return {"classId": classroom["Id"], "className": f"{classroom.get('Grade', '')} · {classroom['Name']}",
            "mode": mode, "round": core.classroom_round(classroom, mode), "layoutId": state["LayoutId"],
            "slots": slots, "position": state["Position"], "total": len(active), "called": [names.get(i, i) for i in done],
            "eligible": len(eligible(classroom, mode)), "available": [{"id": i, "name": names[i]} for i in eligible(classroom, mode)],
            "waitingVip": [names[s["Id"]] for s in core.vip_candidates(classroom, mode)],
            "settings": copy.deepcopy(classroom["BoardGame"]["Settings"]), "pending": pending,
            "roundPeople": list(reversed(list(round_people.values()))),
            "rules": dict({k: classroom[k] for k in RULE_KEYS}, mode=mode),
            "view": normalize_view(classroom['BoardGame'].get('View')),
            "roster": [{'id': s['Id'], 'name': names.get(s['Id'], s['Name']), 'rawName': s['Name'], 'archived': bool(s.get('Archived')), 'vip': bool(s.get('VipWaiting')), 'absent': core.is_absent(s), 'held': core.vip_hold(classroom, s)} for s in classroom['Students']],
            "events": [dict(e, batchId=b["Id"]) for b in classroom["Batches"] for e in b.get("BoardEvents", [])
                       if not e.get("Handled") and b["Mode"] == mode and b["Round"] == core.classroom_round(classroom, mode)
                       and b.get("Cycle", 0) == core.classroom_cycle(classroom, mode)],
            "history": [{"round": b["Round"], "time": (core.parse_date(b["Time"]) or core.now()).strftime("%H:%M"),
                         "people": [{"name": names.get(e["StudentId"], (core.student_by_id(classroom, e["StudentId"]) or {}).get("Name", "已转出")), "vip": bool(e.get("Vip"))}
                                    for e in b["Entries"] if e.get("Valid")],
                         "events": [{"title": e["Title"]} for e in b.get("BoardEvents", [])],
                         "rolls": [{"steps": r["steps"]} for r in b.get("BoardRolls", [])]}
                        for b in reversed(classroom["Batches"][-200:])]}


def _pending(classroom):
    last = classroom["Batches"][-1] if classroom["Batches"] else None
    if last and core.missing_positions(last) and not last.get("ClosedWithMissing"):
        raise ValueError("上一批仍有缺额，请在原管理界面补抽或结束本批。")


def _event(settings):
    return copy.deepcopy(core.RNG.choices(settings["Events"], weights=[e["Weight"] for e in settings["Events"]], k=1)[0])


def draw(classroom, mode, count):
    if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= 200:
        raise ValueError("骰子数量必须为 1～200 的整数。")
    _pending(classroom)
    core.expire_absence(classroom)
    state = ensure_board(classroom, mode)
    slots = state["Slots"]
    if not slots:
        raise ValueError("名单为空，请先添加学生。")
    shortage = core.vip_shortage(classroom, mode, count)
    if shortage and not classroom.get("FillVipShortage"):
        raise ValueError(f"VIP 可抽 {shortage[0]} 人，需要 {shortage[1]} 人。请调整抽取设置或开启普通补齐。")
    planned = min(count, int(classroom.get("VipPerBatch", 1))) if classroom.get("VipEnabled") else 0
    if count == 1:
        planned = min(planned, len(core.vip_candidates(classroom, mode)))
    need_vip = min(planned, len(core.vip_candidates(classroom, mode)))
    settings = validate_settings(classroom["BoardGame"]["Settings"])
    batch = {"Id": uuid.uuid4().hex, "Time": core.date_json(core.now()), "Mode": mode,
             "Round": core.classroom_round(classroom, mode), "Cycle": core.classroom_cycle(classroom, mode),
             "Count": count, "PlannedVip": planned, "FillVipShortage": bool(classroom.get("FillVipShortage")),
             "ClosedWithMissing": False, "SlotTypes": [], "OrdinaryCandidates": [], "Entries": [],
             "BoardEvents": [], "BoardRolls": []}
    names, used, candidate_ids = labels(classroom), set(), set()
    for slot_number in range(1, count + 1):
        available = eligible(classroom, mode, used)
        reachable = []
        seen_indices = set()
        for steps in range(1, 7):
            index = (state["Position"] + steps) % len(slots)
            if index in seen_indices:
                continue
            seen_indices.add(index)
            item = slots[index]
            if item["kind"] == "chest" or item["id"] in available:
                reachable.append({"steps": steps, "index": index, "slot": item})
        chests = [r for r in reachable if r["slot"]["kind"] == "chest"]
        people = [r for r in reachable if r["slot"]["kind"] == "student"]
        candidate_ids.update(r["slot"]["id"] for r in people if not available[r["slot"]["id"]].get("VipWaiting"))
        force_vip = need_vip > 0
        probability = settings["ChestChance"] / 100
        chest = force_vip or bool(chests and probability > 0 and (not people or core.RNG.random() < probability))
        student, event = None, None
        if chest and chests:
            target = core.RNG.choice(chests)
            if force_vip:
                candidates = core.vip_candidates(classroom, mode, used)
                if not candidates:
                    raise ValueError("VIP 队列已变化，请重新抽取。")
                student = core.choose_vip(classroom, candidates, count == 1)
            else:
                event = _event(settings)
                if event['Action'] == 'random_student':
                    candidates = core.ordinary_candidates(classroom, mode, used)
                    candidate_ids.update(s['Id'] for s in candidates)
                    if candidates:
                        student = core.choose_ordinary(classroom, mode, candidates)
                    else:
                        event['Title'] += '（暂无可参与学生）'
        elif people:
            student = core.choose_ordinary(classroom, mode, [available[r["slot"]["id"]] for r in people])
            target = next(r for r in people if r["slot"]["id"] == student["Id"])
        else:
            raise ValueError(f"第 {slot_number} 颗骰子前方 1～6 格没有可抽姓名；普通宝箱概率为 0 时不能靠宝箱继续。请调整骰子数、概率或开始新一轮。")
        roll = {"from": state["Position"], "to": target["index"], "steps": target["steps"], "kind": target["slot"]["kind"]}
        state["Position"] = target["index"]
        if student:
            vip = bool(student.get("VipWaiting"))
            if vip:
                core.complete_vip(classroom, mode, student)
                need_vip = max(0, need_vip - 1)
            used.add(student["Id"])
            fill = not vip and slot_number <= planned
            batch["SlotTypes"].append("VIP" if vip else "VIP补位" if fill else "普通")
            batch["Entries"].append({"Position": slot_number, "StudentId": student["Id"], "Vip": vip, "Valid": True,
                                     "Source": "宝箱随机学生" if event else "VIP宝箱" if vip and chest else "VIP姓名格" if vip else "普通补位" if fill else "棋盘姓名格", "ReplacesId": None})
            roll["person"] = {"id": student['Id'], "name": names[student["Id"]], "vip": vip}
        if event:
            event.update({"Position": slot_number, "Handled": event["Action"] in {"message", "skip", "random_student"}, "EventId": uuid.uuid4().hex})
            if student: event['ResolvedStudentId'] = student['Id']
            batch["BoardEvents"].append(event)
            if not student: batch["SlotTypes"].append("宝箱事件")
            roll["event"] = dict(event, batchId=batch["Id"])
        batch["BoardRolls"].append(roll)
    batch["OrdinaryCandidates"] = sorted(candidate_ids) if mode == "均衡" else []
    classroom["Batches"].append(batch)
    core.recompute_waits(classroom)
    return batch


class BoardController:
    def __init__(self, store, class_id, mode):
        self.store, self.class_id, self.mode = store, class_id, mode

    def classroom(self):
        value = next((c for c in self.store.data["Classes"] if c["Id"] == self.class_id), None)
        if value is None or self.mode not in core.MODES:
            raise ValueError("班级已变更，请从主界面重新打开棋盘。")
        return value

    def state(self):
        classroom = self.classroom()
        previous = copy.deepcopy(classroom.get("BoardGame"))
        result = snapshot(classroom, self.mode)
        if previous != classroom.get("BoardGame") and not self.store.save():
            if previous is None: classroom.pop("BoardGame", None)
            else: classroom["BoardGame"] = previous
            raise IOError("棋盘布局未能保存：" + str(self.store.last_error))
        return result

    def transaction(self, operation):
        original = self.classroom()
        before, previous_last = copy.deepcopy(original), self.store.data.get("LastClassId")
        working = copy.deepcopy(original)
        result = operation(working)
        original.clear(); original.update(working)
        self.store.data["LastClassId"] = self.class_id if operation.__name__ == "drawing" else previous_last
        if not self.store.save():
            original.clear(); original.update(before)
            self.store.data["LastClassId"] = previous_last
            raise IOError("保存失败，本次操作未提交：" + str(self.store.last_error))
        return result

    def dispatch(self, command, payload):
        if command == "state":
            return self.state()
        def check(c):
            state = ensure_board(c, self.mode)
            if payload.get("layoutId") != state["LayoutId"]:
                raise ValueError("班级、名单或轮次已改变，请刷新棋盘后再试。")
            return state
        if command == "draw":
            def drawing(c):
                state = check(c)
                if payload.get("position") != state["Position"]:
                    raise ValueError("棋子位置已改变，请刷新棋盘。")
                return copy.deepcopy(draw(c, self.mode, payload.get("count")))
            batch = self.transaction(drawing)
            return {"batch": batch, "state": self.state()}
        if command == "settings":
            settings = validate_settings(payload.get("settings"))
            def saving(c):
                check(c); c["BoardGame"]["Settings"] = settings
            self.transaction(saving)
            return self.state()
        if command == 'console':
            rules = validate_rules(payload.get('rules'))
            settings = validate_settings(payload.get('settings'))
            view = validate_view(payload.get('view', {}))
            mode = payload['rules']['mode']
            def configuring(c):
                check(c)
                if mode != self.mode: _pending(c)
                c.update(rules)
                c['BoardGame']['Settings'] = settings
                c['BoardGame']['View'] = view
                ensure_board(c, mode)
            self.transaction(configuring)
            self.mode = mode
            return self.state()
        if command == 'vip':
            def arranging(c):
                check(c)
                student = core.student_by_id(c, payload.get('studentId'))
                if not student or student.get('Archived'): raise ValueError('学生不存在。')
                if payload.get('enabled') is True: core.add_vip(c, student)
                elif payload.get('enabled') is False: student['VipWaiting'] = False
                else: raise ValueError('VIP 状态无效。')
            self.transaction(arranging)
            return self.state()
        if command in {'rename', 'archive'}:
            def editing(c):
                check(c)
                student = core.student_by_id(c, payload.get('studentId'))
                if not student: raise ValueError('学生不存在。')
                if command == 'rename': core.rename_student(c, student['Id'], payload.get('name'))
                else:
                    if not isinstance(payload.get('archived'), bool): raise ValueError('移出状态无效。')
                    student['Archived'] = payload['archived']
                ensure_board(c, self.mode)
            self.transaction(editing)
            return self.state()
        if command == "next-round":
            def advancing(c):
                check(c); _pending(c); core.new_round(c, self.mode); ensure_board(c, self.mode)
            self.transaction(advancing)
            return self.state()
        if command == "resolve-event":
            def resolving(c):
                batch = next((b for b in c["Batches"] if b["Id"] == payload.get("batchId")), None)
                event = next((e for e in (batch or {}).get("BoardEvents", []) if e["EventId"] == payload.get("eventId")), None)
                if not event or event.get("Handled"):
                    raise ValueError("该事件已处理或不存在。")
                if batch["Mode"] != self.mode or batch["Round"] != core.classroom_round(c, self.mode) or batch.get("Cycle", 0) != core.classroom_cycle(c, self.mode):
                    raise ValueError("该事件属于旧轮次，不能再改变当前轮次。")
                if event["Action"] == "teacher":
                    used = {e["StudentId"] for e in batch["Entries"] if e.get("Valid")}
                    student = eligible(c, self.mode, used).get(payload.get("studentId"))
                    if not student:
                        raise ValueError("该学生当前不可参与点名。")
                    vip = bool(student.get("VipWaiting"))
                    if vip: core.complete_vip(c, self.mode, student)
                    batch["Entries"].append({"Position": event["Position"], "StudentId": student["Id"], "Vip": vip,
                                             "Valid": True, "Source": "宝箱老师指定", "ReplacesId": None})
                    batch["SlotTypes"][event["Position"] - 1] = "VIP" if vip else "普通"
                    event["ResolvedStudentId"] = student["Id"]
                event["Handled"] = True; core.recompute_waits(c)
            self.transaction(resolving)
            return self.state()
        raise ValueError("未知操作。")
