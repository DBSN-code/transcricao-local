"""Control only this user's transcription service; keep login preference independent."""

import argparse
import json
import os
from pathlib import Path
import plistlib
import re
import socket
import subprocess
import tempfile
import time
from urllib.error import URLError
from urllib.request import urlopen
import runtime_paths

ROOT = runtime_paths.DATA_ROOT
LABEL = 'local.wa-apple-transcriber'
PLIST = Path.home() / 'Library/LaunchAgents' / (LABEL + '.plist')
RUNTIME_PLIST = ROOT / 'state/service.plist'
DOMAIN = f'gui/{os.getuid()}'
TARGET = DOMAIN + '/' + LABEL
ARGS = runtime_paths.server_arguments()
BASE_URL = 'http://127.0.0.1:5092/v1'
MODEL = 'apple-speechanalyzer'


def launchctl(*args, check=False, timeout=5):
    return subprocess.run(['/bin/launchctl', *args], capture_output=True, text=True,
                          check=check, timeout=timeout)


def job():
    result = launchctl('print', TARGET)
    if result.returncode:
        return None
    if f'program = {ARGS[0]}\n' not in result.stdout or f'\n\t\t{ARGS[1]}\n' not in result.stdout:
        raise RuntimeError('Outro programa está usando o nome deste serviço. Ele foi preservado.')
    return result.stdout


def check_ownership():
    for path in [PLIST, RUNTIME_PLIST]:
        if path.exists():
            with path.open('rb') as file:
                config = plistlib.load(file)
            if config.get('Label') != LABEL or config.get('ProgramArguments') != ARGS:
                raise RuntimeError('Existe uma configuração diferente com este nome. Ela foi preservada.')


def configuration():
    return {
        'Label': LABEL, 'ProgramArguments': ARGS, 'WorkingDirectory': str(ROOT),
        'RunAtLoad': True, 'KeepAlive': {'SuccessfulExit': False},
        'ThrottleInterval': 10, 'ExitTimeOut': 200, 'Umask': 0o077,
        'StandardOutPath': str(ROOT / 'logs/server.log'),
        'StandardErrorPath': str(ROOT / 'logs/error.log'),
    }


def write_configuration(path):
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    (ROOT / 'logs').mkdir(mode=0o700, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=LABEL + '.', delete=False) as file:
            temporary = Path(file.name)
            plistlib.dump(configuration(), file)
            file.flush()
            os.fsync(file.fileno())
        temporary.chmod(0o600)
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def status():
    check_ownership()
    loaded = job()
    payload = None
    try:
        with urlopen('http://127.0.0.1:5092/health', timeout=1) as response:
            payload = json.load(response)
    except (URLError, TimeoutError, ValueError, OSError):
        pass
    compatible = isinstance(payload, dict) and payload.get('model') == MODEL
    healthy = compatible and loaded is not None
    state = 'busy' if healthy and payload.get('busy') else 'running' if healthy else 'stopped'
    message = ''
    if payload is not None and not healthy:
        state = 'conflict'
        message = ('Há um servidor na porta 5092 que não é controlado por este aplicativo. Ele foi preservado.'
                   if compatible else 'Outro serviço está usando a porta 5092. Ele foi preservado.')
    elif not healthy and loaded:
        code = re.search(r'last exit code = (\d+)', loaded)
        state = 'error' if code and code[1] != '0' else 'starting'
        if state == 'error':
            message = 'O servidor não iniciou. Consulte as instruções ou tente iniciar novamente.'
    return {'state': state, 'running': healthy, 'busy': bool(healthy and payload.get('busy')),
            'autostart': PLIST.exists(), 'loaded': loaded is not None,
            'url': BASE_URL, 'model': MODEL, 'message': message}


def start():
    runtime_paths.ensure_installed()
    current = status()
    if current['running']:
        return
    if current['state'] == 'conflict':
        raise RuntimeError(current['message'])
    with socket.socket() as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind(('127.0.0.1', 5092))
        except OSError:
            raise RuntimeError('A porta 5092 já está em uso. O outro serviço foi preservado.')
    check_ownership()
    write_configuration(RUNTIME_PLIST)
    if current['loaded']:
        launchctl('kickstart', TARGET, check=True)
    else:
        launchctl('bootstrap', DOMAIN, str(RUNTIME_PLIST), check=True)
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        current = status()
        if current['running']:
            return
        if current['state'] == 'error':
            raise RuntimeError(current['message'])
        time.sleep(0.15)
    raise RuntimeError('O servidor ainda não respondeu. Aguarde alguns segundos e tente novamente.')


def stop():
    current = status()
    if current['state'] == 'conflict':
        raise RuntimeError(current['message'])
    if current['busy']:
        raise RuntimeError('Há um áudio sendo transcrito. Aguarde terminar para parar o servidor.')
    if current['loaded']:
        launchctl('bootout', TARGET, check=True, timeout=210)


def autostart(enabled):
    if enabled:
        runtime_paths.ensure_installed()
    check_ownership()
    if enabled:
        write_configuration(PLIST)
    elif PLIST.exists():
        PLIST.unlink()
    # Changing the login file never starts or stops the loaded service.


def test_transcription():
    current = status()
    if not current['running'] or current['busy']:
        raise RuntimeError('Inicie o servidor e aguarde os outros áudios antes de testar.')
    with tempfile.TemporaryDirectory(prefix='wa-ui-test-') as directory:
        source = Path(directory) / 'example.aiff'
        audio = Path(directory) / 'example.wav'
        sentence = 'Olá, esta é uma mensagem de teste em português. A transcrição funciona no meu computador.'
        if runtime_paths.PACKAGED:
            # Ship a synthetic fixture so friends do not need an installed TTS voice.
            audio.write_bytes((runtime_paths.RESOURCE_ROOT / 'examples/test.wav').read_bytes())
        else:
            subprocess.run(['/usr/bin/say', '-v', 'Luciana (Português (Brasil))', '-o', str(source), sentence],
                           capture_output=True, check=True, timeout=30)
            subprocess.run([runtime_paths.ffmpeg_executable(), '-nostdin', '-hide_banner', '-loglevel', 'error',
                            '-i', str(source), '-ac', '1', '-ar', '16000', '-c:a', 'pcm_s16le', '-y', str(audio)],
                           capture_output=True, check=True, timeout=20)
        boundary = 'wa-native-test-' + os.urandom(12).hex()
        body = bytearray()
        for name, value, filename in [
            ('model', MODEL.encode(), None), ('language', b'pt', None),
            ('response_format', b'json', None), ('file', audio.read_bytes(), 'example.wav')
        ]:
            body.extend(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"'.encode())
            if filename:
                body.extend(f'; filename="{filename}"\r\nContent-Type: audio/wav'.encode())
            body.extend(b'\r\n\r\n' + value + b'\r\n')
        body.extend(f'--{boundary}--\r\n'.encode())
        from urllib.request import Request
        request = Request(BASE_URL + '/audio/transcriptions', data=bytes(body),
                          headers={'Content-Type': 'multipart/form-data; boundary=' + boundary})
        with urlopen(request, timeout=175) as response:
            result = json.load(response)
        if not isinstance(result.get('text'), str) or not result['text'].strip():
            raise RuntimeError('O teste não retornou texto. Tente novamente.')
        return result['text']


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['start', 'stop', 'disable', 'status', 'autostart', 'test', 'models', 'prepare-model'])
    parser.add_argument('value', nargs='?', choices=['on', 'off'])
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args()
    try:
        extra = {}
        if args.action == 'start':
            start()
        elif args.action in {'stop', 'disable'}:
            stop()
            if args.action == 'disable':
                autostart(False)
        elif args.action == 'autostart':
            if args.value is None:
                raise RuntimeError('Escolha on ou off para o início automático.')
            autostart(args.value == 'on')
        elif args.action == 'test':
            extra['test_text'] = test_transcription()
        elif args.action in {'models', 'prepare-model'}:
            arguments = ['--info'] if args.action == 'models' else ['--install', 'pt_BR']
            result = subprocess.run([str(runtime_paths.WORKER), *arguments], capture_output=True,
                                    text=True, timeout=10 if args.action == 'models' else 900)
            if result.returncode:
                try:
                    message = json.loads(result.stdout)['error']['message']
                except (ValueError, KeyError, TypeError):
                    message = 'Não foi possível preparar o português. Confira a conexão e tente novamente.'
                raise RuntimeError(message)
            extra['models'] = json.loads(result.stdout)
        output = {**status(), **extra}
        if args.json:
            print(json.dumps(output, ensure_ascii=False))
        else:
            messages = {'running': 'Servidor funcionando em ' + BASE_URL,
                        'busy': 'Servidor transcrevendo um áudio.', 'stopped': 'Servidor parado.',
                        'starting': 'Servidor iniciando.', 'error': output['message'], 'conflict': output['message']}
            print(messages[output['state']])
            print('Início automático: ' + ('ativado.' if output['autostart'] else 'desativado.'))
    except (RuntimeError, OSError, ValueError, subprocess.SubprocessError) as error:
        message = str(error) if isinstance(error, RuntimeError) else 'Não foi possível concluir a ação. Consulte as instruções ou tente novamente.'
        if args.json:
            print(json.dumps({'error': message}, ensure_ascii=False))
            raise SystemExit(1)
        parser.exit(1, message + '\n')


if __name__ == '__main__':
    main()
