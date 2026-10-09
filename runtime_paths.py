"""Locate immutable bundled tools separately from this user's writable state."""
from pathlib import Path
import os
import sys

PACKAGED = bool(getattr(sys, 'frozen', False))
SOURCE_ROOT = Path(__file__).resolve().parent
RESOURCE_ROOT = Path(sys._MEIPASS) if PACKAGED else SOURCE_ROOT
DATA_ROOT = (Path.home() / 'Library/Application Support/Transcricao Local') if PACKAGED else SOURCE_ROOT
WORKER = RESOURCE_ROOT / 'bin/speech-worker'


def server_arguments():
    if PACKAGED:
        return [str(Path(sys.executable).resolve()), 'serve', '--port', '5092']
    return [str(SOURCE_ROOT / '.venv/bin/python'), str(SOURCE_ROOT / 'server.py'), '--port', '5092']


def ffmpeg_executable():
    if PACKAGED:
        return str(RESOURCE_ROOT / 'bin/ffmpeg')
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def ensure_installed():
    if PACKAGED:
        executable = str(Path(sys.executable).resolve())
        if (executable.startswith('/Volumes/') or '/AppTranslocation/' in executable
                or os.statvfs(executable).f_flag & os.ST_RDONLY):
            raise RuntimeError('Copie Transcrição Local para a pasta Aplicativos e abra essa cópia antes de iniciar o servidor.')
