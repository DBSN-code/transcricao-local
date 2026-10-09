"""Exercise the app extracted from its DMG with no host Python/Homebrew in PATH."""
from pathlib import Path
import hashlib
import json
import os
import plistlib
import socket
import subprocess
import tempfile
import time
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent.parent
DMG = ROOT / 'dist/Transcricao-Local-1.1.0-arm64.dmg'


def run(args, **kwargs):
    return subprocess.run([str(arg) for arg in args], check=True, capture_output=True, **kwargs)


def multipart(data, filename):
    boundary = 'portable-test-' + os.urandom(12).hex()
    body = bytearray()
    for name, value in [('model', b'apple-speechanalyzer'), ('language', b'pt'),
                        ('response_format', b'json'), ('file', data)]:
        body.extend(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"'.encode())
        if name == 'file':
            body.extend(f'; filename="{filename}"'.encode())
        body.extend(b'\r\n\r\n' + value + b'\r\n')
    body.extend(f'--{boundary}--\r\n'.encode())
    return boundary, bytes(body)


def verify():
    report = {'dmg': DMG.name, 'sha256': hashlib.sha256(DMG.read_bytes()).hexdigest(),
              'architecture': 'arm64', 'minimum_macos': '27.0', 'notarized': False,
              'tests': {}, 'synthetic_formats': {},
              'limits': ['second_mac_not_tested', 'quarantined_download_not_tested',
                         'first_model_download_not_tested', 'login_restart_not_tested']}
    with tempfile.TemporaryDirectory(prefix='wa-installer-test-') as directory:
        base = Path(directory)
        mount = base / 'Disco'
        mount.mkdir()
        mounted = False
        process = None
        try:
            run(['hdiutil', 'attach', '-readonly', '-nobrowse', '-mountpoint', mount, DMG])
            mounted = True
            report['tests']['dmg_mount_readonly'] = True
            original = mount / 'Transcrição Local.app'
            mounted_helper = original / 'Contents/Helpers/wa-backend.app/Contents/MacOS/wa-backend'
            blocked = subprocess.run([str(mounted_helper), 'start', '--json'], capture_output=True)
            assert blocked.returncode == 1 and 'Copie' in json.loads(blocked.stdout)['error']
            report['tests']['cannot_start_from_installation_disk'] = True
            info = plistlib.loads((original / 'Contents/Info.plist').read_bytes())
            assert 'WAServerRoot' not in info
            assert info['LSMinimumSystemVersion'] == '27.0'
            report['tests']['no_project_path_in_info'] = True
            app = base / 'Instalacao Amigo com espaço/Transcrição Local.app'
            run(['/usr/bin/ditto', original, app])
            run(['codesign', '--verify', '--deep', '--strict', app])
            report['tests']['relocated_signature'] = True
            # Unmount before executing, proving no reads depend on the installation disk.
            run(['hdiutil', 'detach', mount])
            mounted = False
            helper = app / 'Contents/Helpers/wa-backend.app/Contents/MacOS/wa-backend'
            tools = app / 'Contents/Helpers/wa-backend.app/Contents/Frameworks/bin'
            fixture = app / 'Contents/Helpers/wa-backend.app/Contents/Frameworks/examples/test.wav'
            assert fixture.is_file()
            assert (app / 'Contents/Resources/Sources/ffmpeg-9.0.2.tar.xz').is_file()
            assert (app / 'Contents/Resources/Licenses/FFmpeg-LGPL-2.1.txt').is_file()
            report['tests']['fixture_and_corresponding_sources_present'] = True
            home = base / 'Usuario de teste'
            home.mkdir()
            env = {'PATH': '/usr/bin:/bin:/usr/sbin:/sbin', 'HOME': str(home), 'LANG': 'pt_BR.UTF-8',
                   'TMPDIR': str(base)}
            run([tools / 'ffmpeg', '-version'], env=env)
            model = json.loads(run([tools / 'speech-worker', '--info'], env=env).stdout)
            assert model['available'] and 'pt_BR' in model['installed_locales']
            report['tests']['native_portuguese_model'] = True
            # Each load command must resolve inside the bundle or to an OS framework.
            count = 0
            for file in app.rglob('*'):
                if file.is_file() and not file.is_symlink():
                    with file.open('rb') as stream:
                        magic = stream.read(4)
                    if magic == b'\xcf\xfa\xed\xfe':
                        loads = run(['otool', '-L', file]).stdout.decode()
                        assert '\n\t/opt/homebrew/' not in loads, str(file)
                        assert '\n\t/Users/' not in loads, str(file)
                        count += 1
            report['tests']['no_homebrew_or_user_dylib_dependencies'] = count
            with socket.socket() as probe:
                probe.bind(('127.0.0.1', 0))
                port = probe.getsockname()[1]
            process = subprocess.Popen([str(helper), 'serve', '--port', str(port)], env=env,
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            health = f'http://127.0.0.1:{port}/health'
            deadline = time.monotonic() + 15
            while True:
                if process.poll() is not None:
                    raise RuntimeError(process.communicate()[1].decode())
                try:
                    with urlopen(health, timeout=1) as response:
                        result = json.load(response)
                    break
                except OSError:
                    if time.monotonic() >= deadline:
                        raise RuntimeError('O servidor empacotado não iniciou.')
                    time.sleep(0.15)
            assert result['on_device'] and result['model'] == 'apple-speechanalyzer'
            report['tests']['frozen_server_with_system_only_path'] = True
            # Fixtures are derived only from the known bundled synthetic phrase.
            import imageio_ffmpeg
            encoder = imageio_ffmpeg.get_ffmpeg_exe()
            audios = {'wav': fixture}
            for extension in ['ogg', 'webm']:
                target = base / ('sample.' + extension)
                run([encoder, '-nostdin', '-loglevel', 'error', '-i', fixture,
                     '-c:a', 'libopus', '-y', target])
                audios[extension] = target
            for extension, audio in audios.items():
                boundary, body = multipart(audio.read_bytes(), audio.name)
                request = Request(f'http://127.0.0.1:{port}/v1/audio/transcriptions', body,
                                  headers={'Content-Type': 'multipart/form-data; boundary=' + boundary,
                                           'Origin': 'chrome-extension://' + 'a' * 32})
                with urlopen(request, timeout=175) as response:
                    value = json.load(response)
                assert 'mensagem de teste em português' in value['text'].lower(), value
                assert value['on_device'] is True
                report['synthetic_formats'][extension] = {'passed': True, 'text': value['text']}
            process.terminate()
            process.communicate(timeout=20)
            assert process.returncode == 0
            process = None
            report['tests']['graceful_shutdown'] = True
        finally:
            if process is not None:
                process.terminate()
                try:
                    process.communicate(timeout=20)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.communicate()
            if mounted:
                run(['hdiutil', 'detach', mount])
    (ROOT / 'dist/verification.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'passed': list(report['tests']), 'formats': list(report['synthetic_formats'])}, ensure_ascii=False))


if __name__ == '__main__':
    verify()
