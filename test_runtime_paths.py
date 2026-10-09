import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import runtime_paths


class PortableRuntimeTests(unittest.TestCase):
    def test_packaged_tools_relocate_and_state_stays_outside_app(self):
        app = Path('/tmp/Amigo com espaço/Transcrição Local.app/Contents/Helpers/wa-backend')
        spec = importlib.util.spec_from_file_location('isolated_runtime_paths', runtime_paths.__file__)
        module = importlib.util.module_from_spec(spec)
        with patch.object(sys, 'frozen', True, create=True), \
                patch.object(sys, '_MEIPASS', str(app / '_internal'), create=True), \
                patch.object(sys, 'executable', str(app / 'wa-backend')), \
                patch.object(Path, 'home', return_value=Path('/tmp/Amigo')):
            spec.loader.exec_module(module)
            self.assertTrue(module.PACKAGED)
            self.assertEqual(module.WORKER, app / '_internal/bin/speech-worker')
            self.assertEqual(module.ffmpeg_executable(), str(app / '_internal/bin/ffmpeg'))
            self.assertEqual(module.DATA_ROOT, Path('/tmp/Amigo/Library/Application Support/Transcricao Local'))
            self.assertEqual(module.server_arguments()[1:], ['serve', '--port', '5092'])
            self.assertNotIn('.venv', module.server_arguments()[0])

    def test_disk_image_and_translocated_app_cannot_register_service(self):
        for path in ['/Volumes/Transcrição Local/App.app/wa-backend',
                     '/private/var/folders/example/AppTranslocation/App.app/wa-backend']:
            with self.subTest(path=path), patch.object(runtime_paths, 'PACKAGED', True), \
                    patch.object(sys, 'executable', path), self.assertRaisesRegex(RuntimeError, 'Copie'):
                runtime_paths.ensure_installed()

    def test_source_server_keeps_the_existing_configuration(self):
        self.assertFalse(runtime_paths.PACKAGED)
        self.assertEqual(runtime_paths.DATA_ROOT, runtime_paths.SOURCE_ROOT)
        self.assertEqual(runtime_paths.server_arguments(), [
            str(runtime_paths.SOURCE_ROOT / '.venv/bin/python'),
            str(runtime_paths.SOURCE_ROOT / 'server.py'), '--port', '5092'])

    def test_readonly_disk_mounted_outside_volumes_is_also_rejected(self):
        class ReadOnly:
            f_flag = runtime_paths.os.ST_RDONLY
        with patch.object(runtime_paths, 'PACKAGED', True), \
                patch.object(sys, 'executable', '/tmp/Disco/wa-backend'), \
                patch.object(runtime_paths.os, 'statvfs', return_value=ReadOnly()), \
                self.assertRaisesRegex(RuntimeError, 'Copie'):
            runtime_paths.ensure_installed()


if __name__ == '__main__':
    unittest.main()
