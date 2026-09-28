import copy
import json
import random
import tempfile
import threading
import time
import unittest
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from unittest.mock import patch
import python_core as core
import python_board as board
import python_maintenance as maintenance
from python_board_server import BoardServer
from python_board_window import apply_window_control


class BoardTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = core.DataStore(Path(self.temp.name))
        self.c = core.new_class('测试', '合成班级')
        self.c['Students'] = [core.new_student(f'学生{i:02}', str(i)) for i in range(50)]
        self.c['VipEnabled'] = False
        self.store.data['Classes'] = [self.c]
        self.ctrl = board.BoardController(self.store, self.c['Id'], '不重复')
        self.state = self.ctrl.state()

    def draw(self, count=1):
        state = self.ctrl.state()
        return self.ctrl.dispatch('draw', dict(count=count, layoutId=state['layoutId'], position=state['position']))

    def chance(self, n, action='message'):
        settings = {'ChestChance': n, 'Events': [{'Id': 'custom', 'Title': '分享一个发现', 'Weight': 100, 'Action': action}]}
        return self.ctrl.dispatch('settings', {'layoutId': self.ctrl.state()['layoutId'], 'settings': settings})

    def test_layout_saved_unique_and_chest_reachable(self):
        self.assertEqual(len(self.state['slots']), 60)
        self.assertEqual(len({s['name'] for s in self.state['slots'] if s['kind'] == 'student'}), 50)
        for i in range(60):
            self.assertTrue(any(self.state['slots'][(i + k) % 60]['kind'] == 'chest' for k in range(1, 7)))
        reloaded = core.DataStore(Path(self.temp.name))
        self.assertEqual(board.BoardController(reloaded, self.c['Id'], '不重复').state()['layoutId'], self.state['layoutId'])

    def test_exact_dice_and_probability_extremes(self):
        self.chance(100)
        answer = self.draw(12)
        rolls = answer['batch']['BoardRolls']
        self.assertEqual(len(rolls), 12)
        self.assertEqual(len(answer['batch']['Entries']), 0)
        for r in rolls:
            self.assertTrue(1 <= r['steps'] <= 6)
            self.assertEqual(r['to'], (r['from'] + r['steps']) % 60)
            self.assertEqual(r['kind'], 'chest')
            self.assertEqual(r['event']['Title'], '分享一个发现')
        self.assertEqual(core.missing_positions(answer['batch']), [])
        self.chance(0)
        answer = self.draw(4)
        self.assertEqual(len(answer['batch']['Entries']), 4)
        self.assertTrue(all(r['kind'] == 'student' for r in answer['batch']['BoardRolls']))
        self.assertEqual(len({e['StudentId'] for e in answer['batch']['Entries']}), 4)

    def test_forced_vip_uses_chest_even_zero_chance(self):
        self.chance(0)
        self.c['VipEnabled'] = True
        student = self.c['Students'][0]
        student.update(VipWaiting=True, VipOrder=1)
        result = self.draw()
        self.assertEqual(result['batch']['BoardRolls'][0]['kind'], 'chest')
        self.assertTrue(result['batch']['Entries'][0]['Vip'])
        self.assertFalse(core.student_by_id(self.c, student['Id'])['VipWaiting'])

    def test_direct_vip_name_completes(self):
        self.chance(0)
        state = board.ensure_board(self.c, '不重复')
        index = next(i for i, s in enumerate(state['Slots']) if s['kind'] == 'student')
        student = core.student_by_id(self.c, state['Slots'][index]['id'])
        student.update(VipWaiting=True, VipOrder=1)
        state['Position'] = (index - 1) % 60
        with patch.object(core, 'choose_ordinary', side_effect=lambda c, m, candidates: next(s for s in candidates if s['Id'] == student['Id'])):
            result = self.draw()
        self.assertEqual(result['batch']['BoardRolls'][0]['kind'], 'student')
        self.assertEqual(result['batch']['Entries'][0]['Source'], 'VIP姓名格')
        self.assertFalse(core.student_by_id(self.c, student['Id'])['VipWaiting'])

    def test_save_failure_rolls_back_and_stale_rejected(self):
        before = copy.deepcopy(self.c)
        with patch.object(self.store, 'save', return_value=False):
            with self.assertRaises(IOError): self.draw()
        self.assertEqual(self.c, before)
        with self.assertRaises(ValueError):
            self.ctrl.dispatch('draw', {'layoutId': 'stale', 'position': 0, 'count': 1})
        self.assertEqual(self.c, before)

    def test_teacher_event_resolves_and_absence_becomes_real_gap(self):
        self.chance(100, 'teacher')
        result = self.draw()
        batch, event = result['batch'], result['batch']['BoardEvents'][0]
        sid = self.c['Students'][0]['Id']
        self.ctrl.dispatch('resolve-event', {'batchId': batch['Id'], 'eventId': event['EventId'], 'studentId': sid})
        saved = self.c['Batches'][-1]
        self.assertEqual(core.missing_positions(saved), [])
        self.assertEqual(saved['Entries'][0]['StudentId'], sid)
        saved['Entries'][0]['Valid'] = False
        self.assertEqual(core.missing_positions(saved), [1])

    def test_round_refresh_and_invalid_probabilities(self):
        before = self.ctrl.state()['layoutId']
        state = self.ctrl.dispatch('next-round', {'layoutId': before})
        self.assertNotEqual(state['layoutId'], before)
        self.assertEqual(state['round'], 2)
        self.assertEqual(state['position'], 0)
        for n in [-1, 101, float('nan')]:
            with self.assertRaises(ValueError): self.chance(n)
        settings = copy.deepcopy(board.DEFAULT_SETTINGS)
        settings['Events'][0]['Weight'] = 0
        with self.assertRaises(ValueError): board.validate_settings(settings)

    def test_random_student_chest_uses_original_weighted_candidates(self):
        self.ctrl.mode = '均衡';self.chance(100, 'random_student')
        c=self.c
        c['Students'][0]['Archived']=True
        c['Students'][1]['AbsentIndefinite']=True
        c['VipEnabled']=True;c['VipPerBatch']=0
        c['Students'][2].update(VipWaiting=True,VipOrder=1)
        c['Students'][3].update(VipCompletedMode='均衡',VipCompletedSerial=c['RoundSerial'])
        c['Students'][-1]['WaitCount']=8
        original_choose=core.choose_ordinary
        pools=[]
        def choose(classroom,mode,candidates):
            pools.append([s['Id'] for s in candidates]);self.assertEqual(mode,'均衡')
            with patch.object(core.RNG,'random',return_value=.999999):
                return original_choose(classroom,mode,candidates)
        with patch.object(core,'choose_ordinary',side_effect=choose):result=self.draw()
        batch=result['batch'];roll=batch['BoardRolls'][0]
        self.assertEqual(roll['kind'],'chest');self.assertEqual(roll['person']['id'],c['Students'][-1]['Id'])
        self.assertEqual(len(pools[0]),46)
        self.assertEqual(set(batch['OrdinaryCandidates']),set(pools[0]))
        self.assertEqual(batch['BoardEvents'][0]['ResolvedStudentId'],roll['person']['id'])
        self.assertTrue(batch['BoardEvents'][0]['Handled']);self.assertEqual(core.missing_positions(batch),[])
        batch['Entries'][0]['Valid']=False
        self.assertEqual(core.missing_positions(batch),[1])

    def test_random_student_batch_and_empty_pool(self):
        self.chance(100,'random_student');result=self.draw(4)
        self.assertEqual(len(result['batch']['BoardRolls']),4)
        self.assertEqual(len({e['StudentId'] for e in result['batch']['Entries']}),4)
        self.assertEqual(len(result['state']['roundPeople']),4)
        for s in self.c['Students']:s['AbsentIndefinite']=True
        result=self.draw()
        self.assertEqual(result['batch']['Entries'],[])
        self.assertIn('暂无可参与学生',result['batch']['BoardEvents'][0]['Title'])
        self.assertEqual(core.missing_positions(result['batch']),[])

    def test_rename_archive_restore_preserve_identity_and_history(self):
        self.chance(100,'random_student');batch=self.draw()['batch'];sid=batch['Entries'][0]['StudentId']
        old=copy.deepcopy(core.student_by_id(self.c,sid));layout=self.ctrl.state()['layoutId']
        payload=dict(layoutId=layout,studentId=sid,name='改名测试')
        state=self.ctrl.dispatch('rename',payload)
        self.assertEqual(state['layoutId'],layout);self.assertEqual(state['roundPeople'][0]['name'],'改名测试')
        self.assertEqual(core.student_by_id(self.c,sid),dict(old,Name='改名测试'))
        self.assertEqual(self.c['Batches'][-1],batch)
        before=copy.deepcopy(self.c)
        with patch.object(self.store,'save',return_value=False):
            with self.assertRaises(IOError):self.ctrl.dispatch('rename',dict(payload,name='不能保存'))
        self.assertEqual(self.c,before)
        for name in ('','  ','x\ny','a'*81):
            with self.assertRaises(ValueError):self.ctrl.dispatch('rename',dict(payload,name=name))
        archived=self.ctrl.dispatch('archive',dict(layoutId=layout,studentId=sid,archived=True))
        self.assertEqual(archived['total'],49);self.assertTrue(next(s for s in archived['roster'] if s['id']==sid)['archived'])
        restored=self.ctrl.dispatch('archive',dict(layoutId=archived['layoutId'],studentId=sid,archived=False))
        self.assertEqual(restored['total'],50);self.assertTrue(core.seen(self.c,'不重复',sid))
        other=next(s for s in self.c['Students'] if s['Id']!=sid)
        self.ctrl.dispatch('rename',dict(layoutId=restored['layoutId'],studentId=other['Id'],name='改名测试'))
        names=[s['name'] for s in self.ctrl.state()['slots'] if s['kind']=='student']
        self.assertEqual(len(names),len(set(names)))

    def test_conditional_probability_distribution(self):
        self.ctrl.mode = '普通'
        self.chance(25)
        with patch.object(core, 'RNG', random.Random(7458)):
            chests = sum(board.draw(self.c, '普通', 1)['BoardRolls'][0]['kind'] == 'chest' for _ in range(1000))
        self.assertTrue(210 <= chests <= 290, chests)

    def test_layout_all_small_class_sizes(self):
        for count in range(1, 91):
            c = core.new_class('', '')
            c['Students'] = [core.new_student(str(i)) for i in range(count)]
            slots = board.ensure_board(c, '普通')['Slots']
            self.assertEqual(sum(s['kind'] == 'student' for s in slots), count)
            self.assertEqual(sum(s['kind'] == 'chest' for s in slots), (count + 4) // 5)

    def test_reset_results_clears_position_keeps_box_settings(self):
        self.chance(77)
        self.draw()
        reset = maintenance.reset_data(self.store.data, 'class', self.c['Id'], {'results', 'history'})
        c = reset['Classes'][0]
        self.assertEqual(c['BoardGame']['Modes'], {})
        self.assertEqual(c['BoardGame']['Settings']['ChestChance'], 77)
        self.assertEqual(board.ensure_board(c, '不重复')['Position'], 0)

    def test_console_atomic_settings_and_mode_switch(self):
        state = self.ctrl.state()
        rules = dict(state['rules'], mode='均衡', VipPerBatch=2, VipEnabled=True, BaseWeight=2, Growth=.2, MaxWeight=4)
        settings = dict(state['settings'], ChestChance=30)
        result = self.ctrl.dispatch('console', {'layoutId': state['layoutId'], 'rules': rules, 'settings': settings, 'view': {'Follow': False, 'Pace': .55}})
        self.assertEqual(result['mode'], '均衡')
        self.assertEqual(result['rules']['VipPerBatch'], 2)
        self.assertEqual(result['view'], board.normalize_view({'Follow': False, 'Pace': .55}))
        self.assertEqual(result['settings']['ChestChance'], 30)
        saved = core.DataStore(Path(self.temp.name))
        self.assertEqual(saved.data['Classes'][0]['BoardGame']['View']['DiceSeconds'], .9)
        before = copy.deepcopy(self.c)
        with self.assertRaises(ValueError):
            self.ctrl.dispatch('console', {'layoutId': result['layoutId'], 'rules': dict(rules, BaseWeight=-1), 'settings': settings, 'view': {'Follow': True, 'Pace': 1}})
        self.assertEqual(self.c, before)

    def test_console_vip_and_current_round_people(self):
        state = self.ctrl.state(); sid = self.c['Students'][0]['Id']
        result = self.ctrl.dispatch('vip', {'layoutId': state['layoutId'], 'studentId': sid, 'enabled': True})
        self.assertTrue(next(s for s in result['roster'] if s['id'] == sid)['vip'])
        self.ctrl.dispatch('vip', {'layoutId': state['layoutId'], 'studentId': sid, 'enabled': False})
        self.chance(0)
        first = self.draw()['batch']
        self.assertEqual(len(self.ctrl.state()['roundPeople']), 1)
        duplicate = copy.deepcopy(first);duplicate['Id'] = 'duplicate-for-test'
        self.c['Batches'].append(duplicate)
        self.assertEqual(self.ctrl.state()['roundPeople'][0]['count'], 2)
        duplicate['Entries'][0]['Valid'] = False
        self.assertEqual(self.ctrl.state()['roundPeople'][0]['count'], 1)
        duplicate['ClosedWithMissing'] = True
        old_mode = copy.deepcopy(first);old_mode['Mode'] = '普通';self.c['Batches'].insert(0,old_mode)
        self.assertEqual(self.ctrl.state()['roundPeople'][0]['count'], 1)
        result = self.ctrl.dispatch('next-round', {'layoutId': state['layoutId']})
        self.assertEqual(result['roundPeople'], [])

    def test_presentation_combinations_persist_and_bad_times_rollback(self):
        keys = ('Direct', 'Dice', 'Move', 'Highlight')
        for mask in range(16):
            state = self.ctrl.state()
            view = dict(board.DEFAULT_VIEW, **{key: bool(mask & (1 << i)) for i, key in enumerate(keys)},
                        DirectSeconds=3.4, DiceSeconds=.5, MoveSeconds=2.6, HighlightSeconds=8)
            payload = dict(layoutId=state['layoutId'], rules=state['rules'], settings=state['settings'], view=view)
            self.assertEqual(self.ctrl.dispatch('console', payload)['view'], view)
            loaded = core.DataStore(Path(self.temp.name))
            self.assertEqual(board.BoardController(loaded, self.c['Id'], '不重复').state()['view'], view)
        before = copy.deepcopy(self.c)
        for key in ('DirectSeconds', 'DiceSeconds', 'MoveSeconds', 'HighlightSeconds'):
            for bad in (0, -.5, 61, float('nan'), float('inf'), True, '2'):
                payload['view'] = dict(view, **{key: bad})
                with self.assertRaises(ValueError): self.ctrl.dispatch('console', payload)
                self.assertEqual(self.c, before)

    def test_http_assets_transport_and_request_dedup(self):
        server = BoardServer(Path(__file__).parent / 'board_web', self.ctrl.dispatch)
        self.addCleanup(server.stop)
        done = threading.Event()
        errors = []
        def client():
            try:
                with urlopen(server.url) as r:
                    self.assertIn('V1.0', r.read().decode())
                with self.assertRaises(HTTPError): urlopen(server.origin + '/wrong/index.html')
                body = json.dumps(dict(layoutId=self.state['layoutId'], position=0, count=1, requestId='fixed')).encode()
                url = server.url.replace('index.html', 'api/draw')
                request = Request(url, body, {'Content-Type': 'application/json', 'Origin': server.origin, 'X-Picker-Session': server.token})
                first = json.load(urlopen(request))
                second = json.load(urlopen(request))
                self.assertEqual(first['batch']['Id'], second['batch']['Id'])
                with self.assertRaises(HTTPError):
                    urlopen(Request(url, body, {'Origin': 'https://example.invalid', 'X-Picker-Session': server.token}))
                with self.assertRaises(HTTPError):
                    urlopen(Request(url, body, {'Origin': 'null'}))
                compatible = json.load(urlopen(Request(url, body, {'Origin': 'null', 'X-Picker-Session': server.token})))
                self.assertEqual(first['batch']['Id'], compatible['batch']['Id'])
                self.assertEqual(server.last_request['origin'], 'null')
            except BaseException as exc: errors.append(exc)
            finally: done.set()
        threading.Thread(target=client, daemon=True).start()
        until = time.monotonic() + 10
        while not done.is_set() and time.monotonic() < until:
            server.poll(); time.sleep(.005)
        self.assertTrue(done.is_set())
        if errors: raise errors[0]
        self.assertEqual(len(self.c['Batches']), 1)

    def test_board_window_controls_preserve_size_and_toggle_native_fullscreen(self):
        class FakeWindow:
            def __init__(self): self.calls = []
            def destroy(self): self.calls.append('destroy')
            def toggle_fullscreen(self): self.calls.append('fullscreen')
            def load_url(self, url): self.calls.append(('load', url))
            def show(self): self.calls.append('show')
            def restore(self): self.calls.append('restore')
        window = FakeWindow()
        url, closed = apply_window_control(window, {'action': 'show', 'url': 'http://new'}, 'http://old')
        self.assertEqual((url, closed), ('http://new', False))
        self.assertEqual(window.calls, [('load', 'http://new'), 'show'])
        apply_window_control(window, {'action': 'fullscreen'}, url)
        self.assertEqual(window.calls[-1], 'fullscreen')
        self.assertNotIn('restore', window.calls)


if __name__ == '__main__': unittest.main()
