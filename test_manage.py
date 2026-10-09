from pathlib import Path
import io
import json
import plistlib
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import manage


class ServiceControlTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.plist = self.root / 'LaunchAgents/service.plist'
        self.runtime = self.root / 'state/service.plist'
        self.patches = [patch.object(manage, 'ROOT', self.root),
                        patch.object(manage, 'PLIST', self.plist),
                        patch.object(manage, 'RUNTIME_PLIST', self.runtime)]
        for value in self.patches:
            value.start()
        self.addCleanup(self.temporary.cleanup)
        for value in self.patches:
            self.addCleanup(value.stop)

    def test_enabling_and_disabling_login_does_not_change_running_service(self):
        with patch.object(manage, 'launchctl') as command:
            manage.autostart(True)
            self.assertTrue(self.plist.exists())
            manage.autostart(False)
            self.assertFalse(self.plist.exists())
        command.assert_not_called()

    def test_start_now_does_not_create_a_login_rule(self):
        with patch.object(manage, 'status', side_effect=[
            {'running': False, 'loaded': False, 'state': 'stopped'}, {'running': True}
        ]), patch.object(manage.socket, 'socket'), patch.object(manage, 'launchctl') as command:
            manage.start()
        self.assertTrue(self.runtime.exists())
        self.assertFalse(self.plist.exists())
        command.assert_called_once_with('bootstrap', manage.DOMAIN, str(self.runtime), check=True)

    def test_stop_now_preserves_login_preference(self):
        manage.autostart(True)
        with patch.object(manage, 'status', return_value={'state': 'running', 'busy': False, 'loaded': True}), \
                patch.object(manage, 'launchctl') as command:
            manage.stop()
        self.assertTrue(self.plist.exists())
        command.assert_called_once_with('bootout', manage.TARGET, check=True, timeout=210)

    def test_busy_transcription_cannot_be_stopped(self):
        with patch.object(manage, 'status', return_value={'state': 'busy', 'busy': True, 'loaded': True}), \
                patch.object(manage, 'launchctl') as command:
            with self.assertRaises(RuntimeError):
                manage.stop()
        command.assert_not_called()

    def test_foreign_login_rule_is_preserved(self):
        self.plist.parent.mkdir()
        foreign = {'Label': manage.LABEL, 'ProgramArguments': ['/unrelated/program']}
        self.plist.write_bytes(plistlib.dumps(foreign))
        for enabled in [True, False]:
            with self.subTest(enabled=enabled), self.assertRaises(RuntimeError):
                manage.autostart(enabled)
        self.assertEqual(plistlib.loads(self.plist.read_bytes()), foreign)

    def test_foreign_loaded_process_is_never_considered_owned(self):
        result = subprocess.CompletedProcess([], 0, stdout='program = /unrelated/program\n')
        with patch.object(manage, 'launchctl', return_value=result), self.assertRaises(RuntimeError):
            manage.job()

    def test_compatible_unmanaged_server_is_conflict_and_cannot_be_controlled(self):
        def response(*args, **kwargs):
            return io.BytesIO(json.dumps({'model': manage.MODEL, 'busy': False}).encode())
        with patch.object(manage, 'job', return_value=None), \
                patch.object(manage, 'urlopen', side_effect=response), \
                patch.object(manage, 'launchctl') as command:
            current = manage.status()
            self.assertEqual(current['state'], 'conflict')
            self.assertFalse(current['running'])
            self.assertFalse(current['loaded'])
            with self.assertRaisesRegex(RuntimeError, 'não é controlado'):
                manage.start()
            with self.assertRaisesRegex(RuntimeError, 'não é controlado'):
                manage.stop()
        command.assert_not_called()


if __name__ == '__main__':
    unittest.main()
