"""Test actual Frida argument redirection in a disposable process, without SnowRunner."""
import json
from pathlib import Path
import sys

import frida
import faulthandler

ROOT = Path(__file__).resolve().parents[1]
def source(config):
    return 'const CONFIG=' + json.dumps(config) + ';\n' + '\n'.join(
        (ROOT / 'src' / name).read_text(encoding='utf-8')
        for name in ('vm_scope.js', 'input_agent.js'))


def main():
    faulthandler.dump_traceback_later(25)
    device = frida.get_local_device()
    pid = device.spawn([sys.executable, '-c', 'import time; time.sleep(120)'])
    errors = []
    session = None
    checks = 0
    try:
        session = device.attach(pid)
        device.resume(pid)
        roles = json.loads((ROOT / 'src/input-profile.json').read_text())['callerRoles']
        fixture = session.create_script('const TEST_ROLES=' + json.dumps(roles) + ';\n' +
                                        (ROOT / 'tests/input_fixture.js').read_text())
        fixture.load()
        f = fixture.exports_sync
        info = f.info()
        agent = session.create_script(source({'test': True}))
        agent.on('message', lambda m, d: errors.append(m))
        agent.load()
        a = agent.exports_sync
        # Reject invalid identities before hooking anything.
        bad = dict(info['ids'], mouse=11)
        try:
            a.fixture(info['selector'], info['uiCallback'], info['uiGetter'],
                      info['stringPoolSlot'], info['roles'], bad, info['winch'])
            raise AssertionError('Duplicate identities accepted')
        except frida.RPCException:
            checks += 1
        assert not a.status()['active']
        a.fixture(info['selector'], info['uiCallback'], info['uiGetter'],
                  info['stringPoolSlot'], info['roles'], info['ids'], info['winch'])
        def run(before, requested, axis, *caller):
            a.fixture_preference(before)
            return f.run(before, requested, axis, *caller)
        assert a.status()['mode'] == 'observe'
        assert f.winch_mode(33,1,True)['result'] == 1
        assert f.hover_gate(33,1,1) == {'result':0,'category':33}
        checks += 1
        print('Checking observation', flush=True)
        for before in (11, 22, 33, 44, 55):
            for requested in (11, 22, 33, 44, 55):
                result = run(before, requested, 9876)
                assert result == {'state': [requested, int(before != requested), 1, requested, 9876],
                                  'device': [requested, 9876], 'ui': requested,
                                  'readBack': requested, 'lastError': 0x1234}, result
                checks += 1
        a.mode('ui-mouse-priority')
        print('Checking UI filtering', flush=True)
        for before in (11, 22, 33, 44, 55):
            for requested in (11, 22, 33, 44, 55):
                after = 22 if requested in (33, 44) else requested
                pointer = 22 if requested in (33, 44) else requested
                result = run(before, requested, 12345)
                assert result == {'state': [requested, int(before != requested), 1, requested, 12345],
                                  'device': [requested, 12345], 'ui': after,
                                  'readBack': pointer, 'lastError': 0x1234}, result
                checks += 1
        assert a.status()['redirected'] == 10
        assert a.status()['getterRedirected'] == 10
        print('Checking caller isolation', flush=True)
        for cls, method in [('TruckInputController', 'Update'),
                            ('TruckInputController', 'UpdateSteeringWheelStatus'),
                            ('MrNativeCamera', 'UpdateInputs'),
                            ('Unknown', 'Update'), ('<invalid>', 'Update')]:
            result = run(22, 33, 786, cls, method)
            print('Checked ' + cls + '.' + method, flush=True)
            assert result['readBack'] == 33 and result['ui'] == 22, result
            assert result['state'] == [33, 1, 1, 33, 786], result
            checks += 1
        result = run(22, 33, 786, 'MinimapCameraController', 'UpdateCameraSteeringWheelInputs')
        assert result['readBack'] == 22 and result['state'][0] == 33, result
        checks += 1
        # Live transition trace: GameStateIngame re-reads the device rather
        # than trusting the mouse-valued notification. Seeing wheel makes it
        # call CancelShowMouse; the subsequent mouse notification is suppressed.
        # Its IsKeyboardOrMouse decision must therefore use pointer semantics.
        print('Checking in-game mouse ownership across wheel transitions', flush=True)
        for test_mode in ('observe', 'ui-mouse-priority'):
            a.mode(test_mode)
            a.fixture_preference(22)
            for requested in (11, 22, 33, 22, 33, 44, 22, 55, 11, 22):
                result = f.run(22, requested, 765, 'GameStateIngame',
                               'HandleOnDeviceChanged', 'IsKeyboardOrMouse')
                expected = 22 if test_mode == 'ui-mouse-priority' and requested in (33, 44) else requested
                assert result['readBack'] == expected, (test_mode, requested, result)
                assert result['state'][0] == requested and result['device'] == [requested, 765], result
                assert result['lastError'] == 0x1234, result
                checks += 1
        for cls, method in [('GameStateIngame', 'Subscribe'), ('OtherGameState', 'HandleOnDeviceChanged')]:
            result = run(22, 33, 765, cls, method, 'IsKeyboardOrMouse')
            assert result['readBack'] == 33, result
            checks += 1
        for cls, method in [('HudInteractionPanelUiView', 'SetData')]:
            result = run(22, 33, 123, cls, method)
            assert result['readBack'] == 33 and result['state'][0] == 33, result
            checks += 1
        # The Function menu queries IsGamepad/IsSteeringWheel in CreateWinchData.
        # Returning mouse here hides the wheel-specific attach-winch action.
        # Menu availability must retain wheel ownership across mouse movement,
        # while the view's list focus uses the same preference as its subscription.
        print('Checking attach-winch menu device queries', flush=True)
        for query in ('IsGamepad', 'IsSteeringWheel'):
            for device_id in (11, 22, 33, 44, 55):
                result = run(22, device_id, 234, 'HudInteractionPanelController',
                             'CreateWinchData', query)
                assert result['readBack'] == device_id, (query, result)
                assert result['state'][0] == device_id and result['device'] == [device_id, 234]
                checks += 1
            for wheel in (33, 44):
                a.fixture_preference(22)
                for requested, expected in [(wheel, wheel), (22, wheel), (22, wheel),
                                            (11, 11), (22, 22), (wheel, wheel)]:
                    result = f.run(22, requested, 234, 'HudInteractionPanelController',
                                   'CreateWinchData', query)
                    assert result['readBack'] == expected, (query, requested, result)
                    assert result['state'][0] == requested and result['device'] == [requested, 234]
                    checks += 1
                result = f.run(22, 22, 234, 'HudInteractionPanelUiView', 'SetData')
                assert result['readBack'] == wheel and a.status()['preferredCategory'] in ('wheel', 'supplemental')
                checks += 1
        print('Checking menu rebuild/subscription focus consistency')
        a.fixture_preference(22)
        for requested,expected in [(11,11),(11,11),(33,33),(22,33),(44,44),(22,44),(11,11)]:
            for cls,method in [('UiListAdapter','Subscribe'),('HudInteractionPanelUiView','SetData')]:
                result=f.run(22,requested,456,cls,method)
                assert result['readBack']==expected, (cls,requested,result)
                assert result['state'][0]==requested and result['device']==[requested,456], result
                checks += 1
        # A moving mouse retains wheel hints, but driving and camera retain
        # actual mouse detection. A keyboard selection ends wheel hint ownership.
        for cls, method, retain_wheel in [
                ('TruckInputController', 'Update', False),
                ('TruckInputController', 'UpdateSteeringWheelStatus', False),
                ('HintIconsPool', 'GetCurrentDeviceNames', True),
                ('MouseController', 'CanShowMouseCursor', False),
                ('MrNativeCamera', 'UpdateInputs', False),
                ('Unknown', 'Update', False), ('<invalid>', 'Update', False)]:
            for wheel in (33, 44):
                result = run(wheel, 22, 654, cls, method)
                assert result['ui'] == 22, result
                assert result['readBack'] == (wheel if retain_wheel else 22), result
                assert result['state'] == [22, 1, 1, 22, 654], result
                checks += 1
                result = run(wheel, 11, 321, cls, method)
                assert result['ui'] == 11 and result['readBack'] == 11, result
                assert result['state'] == [11, 1, 1, 11, 321], result
                checks += 1
        # Preference survives multiple separate mouse notifications and is
        # replaced by actual keyboard/wheel input, across consecutive events.
        for query in ('IsMouse', 'IsSteeringWheel'):
            for device_id in (11, 22, 33):
                result = run(22, device_id, 456, 'TruckInputController',
                             'UpdateSteeringWheelStatus', query)
                assert result['readBack'] == device_id, result
                assert result['state'][0] == device_id, result
                checks += 1
        for device_id in (11,22,33,44,55):
            for value in (0,1):
                for approved in (False,True):
                    a.fixture_preference(22)
                    result=f.winch_mode(device_id,value,approved)
                    expected=0 if approved and device_id in (33,44) else value
                    assert result == {'result':expected,'category':device_id,'globalMode':value}, result
                    checks += 1
        a.fixture_preference(33)
        assert f.winch_mode(22,1,True)['result'] == 0
        checks += 1
        print('Checking native winch hover timer isolation', flush=True)
        for device_id in (11,22,33,44,55):
            for eligible in (0,1):
                for timed_out in (0,1):
                    a.fixture_preference(22)
                    expected=eligible if device_id in (33,44) or not timed_out else 0
                    result = f.hover_gate(device_id,eligible,timed_out)
                    assert result == {'result':expected,'category':device_id}, (device_id,eligible,timed_out,result)
                    checks += 1
        for preferred in (11,22,33,44,55):
            a.fixture_preference(preferred)
            assert f.hover_gate(22,1,1)['result'] == (1 if preferred in (33,44) else 0)
            checks += 1
        a.fixture_preference(22)
        for requested, expected, preference in [(33, 33, 'wheel'), (22, 33, 'wheel'),
                (22, 33, 'wheel'), (11, 11, 'keyboard'), (22, 22, 'keyboard'), (33, 33, 'wheel')]:
            result = f.run(22, requested, 123, 'HintIconsPool', 'GetCurrentDeviceNames')
            assert result['readBack'] == expected, result
            assert a.status()['preferredCategory'] == preference, a.status()
            checks += 1
        a.mode('observe')
        assert f.hover_gate(33,1,1)['result'] == 0
        print('Checking redundant UI notification filtering', flush=True)
        sequence=[33,22,33,22,44,22,11,22,33,22,55,22]
        a.fixture_preference(22)
        observed=f.notification_sequence(sequence,123)
        assert [x['signals'] for x in observed] == list(range(1,len(sequence)+1)), observed
        checks += 1
        a.mode('ui-mouse-priority')
        a.fixture_preference(22)
        observed=f.notification_sequence(sequence,123)
        assert [x['signals'] for x in observed] == [1,1,1,1,2,2,3,4,5,5,6,7], observed
        for row in observed:
            assert row['category']==row['requested'] and row['axis']==123, row
            assert row['delivered']==(22 if row['requested'] in (33,44) else row['requested']), row
            assert row['lastError']==0x1234, row
            checks += 1
        # Separate UI listeners must each receive the initial notification.
        a.fixture_preference(33)
        assert f.notification_sequence([33,22],456)[-1]['signals']==1
        checks += 1
        a.mode('observe')
        a.fixture_preference(22)
        assert [x['signals'] for x in f.notification_sequence([33,22,33],1)]==[1,2,3]
        checks += 1
        print('Checking shutdown', flush=True)
        print('Checking Function menu selection cleanup isolation', flush=True)
        assert f.menu_rebuild(33,5,'HudInteractionPanelUiView','SetData')['resets']==0
        checks += 1
        a.mode('ui-mouse-priority')
        for cls,method in [('HudInteractionPanelUiView','SetData'),
                           ('HudInteractionPanelUiView','Other'),('OtherListView','SetData'),
                           ('<invalid>','SetData')]:
            for device_id in (11,22,33,44,55):
                a.fixture_preference(22)
                resets=int(cls=='HudInteractionPanelUiView' and method=='SetData' and device_id in (33,44))
                result=f.menu_rebuild(device_id,5,cls,method)
                assert result=={'selection':-1 if resets else 5,'resets':resets,
                                'highlight':0 if resets else 1,'generation':42,'category':device_id},result
                checks += 1
        a.fixture_preference(33)
        assert f.menu_rebuild(22,5,'HudInteractionPanelUiView','SetData')['resets']==1
        assert f.menu_rebuild(33,-1,'HudInteractionPanelUiView','SetData')['resets']==0
        checks += 2
        # Engine state changes refresh an already active list after a delay.
        # They must retain its selection; cleanup is only for reopening a list
        # made non-focusable by the preceding Deactivate/HidePanel.
        print('Checking selection during active menu refreshes', flush=True)
        for device_id in (11,22,33,44,55):
            for preferred in (22,33):
                a.fixture_preference(preferred)
                result=f.menu_rebuild(device_id,5,'HudInteractionPanelUiView','SetData',1)
                assert result=={'selection':5,'resets':0,'highlight':1,
                                'generation':42,'category':device_id},result
                checks += 1
        a.mode('observe')
        print('Checking wheel navigation focus restoration after camera clicks', flush=True)
        assert f.menu_navigation({})['restores']==0
        checks += 1
        a.mode('ui-mouse-priority')
        print('Checking cursor release only on Functions opening', flush=True)
        for category in (11,22,33,44,55):
            result=f.menu_cursor({'category':category})
            expected=int(category!=55)
            assert result=={'dragging':1-expected,'releases':expected,'category':category,
                            'error':0x1234,'entryError':0x1234},result
            # A subsequent camera click must remain captured even with the menu open.
            result=f.cursor_tick()
            assert result=={'dragging':1,'releases':expected,'error':0x1234,'entryError':0x1234},result
            checks += 2
        for options in ({'opening':False},{'view':'OtherPanel'},{'method':'Other'},
                        {'invalid':True},{'dragging':0},{'enabled':0}):
            a.mode('ui-mouse-priority')
            result=f.menu_cursor(options)
            assert result['releases']==0 and result['dragging']==options.get('dragging',1),result
            checks += 1
        # Consume an already-visible cursor too: a later click is independent.
        f.menu_cursor({'dragging':0})
        assert f.cursor_tick()['releases']==0
        checks += 1
        f.menu_cursor({'enabled':0})
        assert f.cursor_tick()['releases']==1
        checks += 1
        f.menu_cursor({'tick':False})
        import time
        time.sleep(0.55)
        assert f.cursor_tick()['releases']==0
        checks += 1
        f.menu_cursor({'tick':False})
        a.mode('observe')
        a.mode('ui-mouse-priority')
        assert f.cursor_tick()['releases']==0
        checks += 1
        a.mode('observe')
        assert f.menu_cursor({})['releases']==0
        checks += 1
        a.mode('ui-mouse-priority')
        for category in (11,22,33,44,55):
            for key in (37,38,39,40):
                a.fixture_preference(22)
                result=f.menu_navigation({'category':category,'key':key})
                restore=int(category in (33,44))
                expected=5+((1 if key==40 else -1 if key==38 else 0) if restore else 0)
                assert result=={'focus':restore,'restores':restore,'selection':expected,'calls':1,
                    'key':key,'event':5,'entryError':0x1234,'error':0x1234,'category':category},result
                checks += 1
        for options in [{'event':6},{'key':13},{'key':65},{'count':1},{'gate':0},
                        {'focusable':0},{'disabled':1},{'wheelPath':False},{'register':False},
                        {'foreignOwner':True},{'stale':True},{'invalid':True}]:
            result=f.menu_navigation(options)
            assert result['restores']==0 and result['focus']==0 and result['selection']==5,result
            assert result['error']==0x1234 and result['entryError']==0x1234,result
            checks += 1
        result=f.menu_navigation({'repeat':2})
        assert result['restores']==1 and result['selection']==7 and result['calls']==2,result
        result=f.menu_navigation({'focus':1})
        assert result['restores']==0 and result['selection']==6,result
        checks += 2
        a.fixture_preference(33)
        assert f.menu_navigation({'category':22})['restores']==1
        checks += 1
        a.mode('observe')
        assert f.menu_navigation({})['restores']==0
        checks += 1
        print('Checking focus retention during Function menu refresh', flush=True)
        assert f.menu_refresh({})['focus']==0
        checks += 1
        a.mode('ui-mouse-priority')
        for category in (11,22,33,44,55):
            for preferred in (22,33,44):
                for adapter in ('SetData','SetDataAndInitialIndex'):
                    a.fixture_preference(preferred)
                    keep=category in (33,44) or (category==22 and preferred in (33,44))
                    result=f.menu_refresh({'category':category,'adapter':adapter})
                    assert result=={'focus':int(keep),'firstFocus':int(keep),'calls':int(not keep),
                        'selection':5,'generation':42,'error':0x1234 if keep else 0xbeef,
                        'entryError':0 if keep else 0x1234,'category':category},result
                    checks += 1
        for options in [{'focus':0},{'focusable':0},{'disabled':1},{'gate':0},{'selection':-1},
                        {'caller':'OtherPanel'},{'method':'HidePanel'},
                        {'current':'different'},{'current':'nested'},{'current':'invalid'},
                        {'stale':True},{'changedReference':True},{'changedArguments':True},
                        {'changedFunction':True},{'rebuildClosed':True}]:
            result=f.menu_refresh(options)
            assert result['focus']==0 and result['calls']==1,result
            assert result['error']==0xbeef and result['entryError']==0x1234,result
            assert result['generation']==42 and result['category']==33,result
            checks += 1
        result=f.menu_refresh({'value':1})
        assert result['focus']==1 and result['calls']==1,result
        result=f.menu_refresh({'foreignObject':True})
        assert result['focus']==1 and result['calls']==0 and result['error']==0xbeef,result
        result=f.menu_refresh({'repeat':2})
        assert result['firstFocus']==1 and result['focus']==0 and result['calls']==1,result
        checks += 3
        a.mode('observe')
        assert f.menu_refresh({})['focus']==0
        checks += 1
        print('Checking wheel neutral deadzone and engine restart isolation', flush=True)
        residue = -1 / 65536
        assert f.wheel_neutral({})['result'] == abs(residue)
        checks += 1
        a.mode('ui-mouse-priority')
        for category in (11, 22, 33, 44, 55):
            for preferred in (11, 22, 33, 44):
                a.fixture_preference(preferred)
                expected = 0 if category in (33, 44) or (category == 22 and preferred in (33, 44)) else abs(residue)
                result = f.wheel_neutral({'category': category})
                assert result['result'] == expected, result
                assert result['original'] == result['after'] and result['comparisonUnchanged'], result
                assert result['category'] == category and result['calls'] == 1, result
                assert result['entryError'] == result['error'] == 0x1234, result
                checks += 1
        import struct
        f32 = lambda n: struct.unpack('<f', struct.pack('<f', n))[0]
        for value in (0, 1e-8, -1e-8, 1e-6, -1e-6, 1/65536, -1/65536,
                      0.00005, -0.00005, 0.000099, -0.000099,
                      0.0001, -0.0001, 0.001, -0.001, 0.1, -0.1, 1, -1):
            value = f32(value)
            expected = 0 if f32(1e-6) <= abs(value) < f32(0.0001) else abs(value)
            result = f.wheel_neutral({'value': value})
            assert result['result'] == expected, (value, result)
            assert result['original'] == result['after'] and result['comparisonUnchanged'], result
            checks += 1
        for options in ({'count': 2}, {'zero': 0.1}, {'tolerance': 1e-5},
                        {'callerClass': 'Other'}, {'callerMethod': 'Update'}, {'callerPc': 463},
                        {'equalClass': 'Other'}, {'equalMethod': 'Other'}, {'equalPc': 5},
                        {'nativeMethod': 'Other'}, {'nativePc': 1}, {'intervening': True},
                        {'badCode': True}, {'badEqualCode': True}, {'badLength': True},
                        {'inputTag': 1}, {'compareTag': 1}, {'differentInput': True},
                        {'foreignOperand': True}, {'invalid': True}):
            result = f.wheel_neutral(options)
            assert result['result'] == abs(residue), (options, result)
            assert result['original'] == result['after'] and result['comparisonUnchanged'], result
            assert result['error'] == result['entryError'] == 0x1234, result
            checks += 1
        for special in ('nan', 'infinity'):
            result = f.wheel_neutral({'special': special})
            assert result['resultBits'] & 0x7f800000 == 0x7f800000, result
            assert result['after'] == result['original'], result
            checks += 1
        assert a.status()['wheelNeutralFiltered'] > 0
        captured_events = a.drain()
        assert any(e['kind'] == 'wheel-neutral-filter' for e in captured_events)
        assert any(e['kind'] == 'ui-selection' and e['redirected'] for e in captured_events)
        a.mode('observe')
        assert f.wheel_neutral({})['result'] == abs(residue)
        checks += 1
        assert f.run(22, 33, 99)['state'] == [33, 1, 1, 33, 99]
        checks += 1
        assert not a.status()['faults'] and not errors, (a.status(), errors)
        a.stop()
        assert not a.status()['active']
        assert f.menu_cursor({})['releases']==0
        checks += 1
        assert f.wheel_neutral({})['result'] == abs(residue)
        checks += 1
        assert f.menu_refresh({})['focus']==0
        checks += 1
        assert f.menu_navigation({})['restores']==0
        checks += 1
        assert f.winch_mode(33,1,True)['result'] == 1
        assert f.hover_gate(33,1,1)['result'] == 0
        assert f.menu_rebuild(33,5,'HudInteractionPanelUiView','SetData')['resets']==0
        checks += 1
        checks += 1
        assert f.run(22, 33, 77)['state'] == [33, 1, 1, 33, 77]
        checks += 1
        agent.unload()
        fixture.unload()
        print(json.dumps({'passed': True, 'checks': checks,
                          'scope': 'synthetic process; no physical or game validation'}, indent=2))
    finally:
        if session:
            session.detach()
        device.kill(pid)
        faulthandler.cancel_dump_traceback_later()


if __name__ == '__main__':
    main()
