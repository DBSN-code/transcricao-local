"""Build a relocatable ARM64 macOS 27 app and a read-only drag-to-install DMG."""
from pathlib import Path
import hashlib
import json
import os
import plistlib
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
VERSION = '1.1.0'
WORK = ROOT / 'build/release'
APP = WORK / 'Transcrição Local.app'
CONTENTS = APP / 'Contents'
RESOURCES = CONTENTS / 'Resources'
DIST = ROOT / 'dist'
SOURCE = ROOT / 'build/vendor/ffmpeg-9.0.2'


def run(arguments, **kwargs):
    subprocess.run([str(value) for value in arguments], check=True, **kwargs)


def build():
    if not (SOURCE / 'ffmpeg').is_file():
        raise SystemExit('Execute packaging/build_ffmpeg.sh primeiro.')
    WORK.mkdir(parents=True, exist_ok=True)
    DIST.mkdir(exist_ok=True)
    worker = WORK / 'speech-worker'
    run(['xcrun', 'swiftc', '-O', '-parse-as-library', '-target', 'arm64-apple-macos27.0',
         '-module-cache-path', '/tmp/wa-speech-availability-cache',
         ROOT / 'SpeechWorker.swift', '-o', worker])
    fixture = WORK / 'test.wav'
    run(['/usr/bin/say', '-v', 'Luciana (Português (Brasil))', '-o', WORK / 'test.aiff',
         'Olá, esta é uma mensagem de teste em português. A transcrição funciona no meu computador.'])
    run([SOURCE / 'ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error',
         '-i', WORK / 'test.aiff', '-ac', '1', '-ar', '16000', '-c:a', 'pcm_s16le', '-y', fixture])
    spec = WORK / 'wa-backend.spec'
    spec.write_text(f'''
a = Analysis([{str(ROOT / 'backend_entry.py')!r}], pathex=[{str(ROOT)!r}],
    binaries=[({str(worker)!r}, 'bin'), ({str(SOURCE / 'ffmpeg')!r}, 'bin')],
    datas=[({str(fixture)!r}, 'examples')], hiddenimports=[], excludes=['imageio_ffmpeg'], noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='wa-backend',
    debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
    console=True, target_arch='arm64', codesign_identity=None)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='wa-backend')
app = BUNDLE(coll, name='wa-backend.app', bundle_identifier='local.waapple.backend',
    info_plist={{'LSBackgroundOnly': True}})
''')
    run([sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean',
         '--distpath', WORK / 'backend', '--workpath', WORK / 'pyinstaller', spec], cwd=ROOT)
    # This is our generated build path only; never replace an installed app here.
    if APP.exists():
        shutil.rmtree(APP)
    (CONTENTS / 'MacOS').mkdir(parents=True)
    RESOURCES.mkdir()
    (CONTENTS / 'Helpers').mkdir()
    backend_app = CONTENTS / 'Helpers/wa-backend.app'
    shutil.copytree(WORK / 'backend/wa-backend.app', backend_app, symlinks=True)
    run(['xcrun', 'swiftc', '-O', '-parse-as-library', '-target', 'arm64-apple-macos27.0',
         '-module-cache-path', '/tmp/wa-speech-availability-cache',
         ROOT / 'NativeApp.swift', '-o', CONTENTS / 'MacOS/TranscricaoLocal'])
    # Reuse the existing canonical SF Symbols icon.
    shutil.copy2(ROOT / 'build/TranscricaoLocal.app/Contents/Resources/AppIcon.icns', RESOURCES)
    info = {
        'CFBundleIdentifier': 'local.waapple.controller', 'CFBundleName': 'Transcrição Local',
        'CFBundleDisplayName': 'Transcrição Local', 'CFBundleExecutable': 'TranscricaoLocal',
        'CFBundlePackageType': 'APPL', 'CFBundleShortVersionString': VERSION, 'CFBundleVersion': '2',
        'CFBundleIconFile': 'AppIcon', 'CFBundleDevelopmentRegion': 'pt-BR',
        'CFBundleLocalizations': ['pt-BR'], 'CFBundleSupportedPlatforms': ['MacOSX'],
        'LSMinimumSystemVersion': '27.0', 'LSApplicationCategoryType': 'public.app-category.utilities',
        'NSHighResolutionCapable': True,
    }
    (CONTENTS / 'Info.plist').write_bytes(plistlib.dumps(info))
    shutil.copy2(ROOT / 'packaging/LEIA-ME.txt', RESOURCES)
    licenses = RESOURCES / 'Licenses'
    licenses.mkdir()
    shutil.copy2(SOURCE / 'COPYING.LGPLv2.1', licenses / 'FFmpeg-LGPL-2.1.txt')
    sources = RESOURCES / 'Sources'
    sources.mkdir()
    for name in ['NativeApp.swift', 'SpeechWorker.swift', 'AppIcon.swift', 'server.py', 'manage.py',
                 'runtime_paths.py', 'backend_entry.py']:
        shutil.copy2(ROOT / name, sources)
    shutil.copy2(ROOT / 'build/vendor/ffmpeg-9.0.2.tar.xz', sources)
    shutil.copy2(ROOT / 'packaging/build_ffmpeg.sh', sources)
    (sources / 'FFmpeg-build.txt').write_text(
        'FFmpeg 9.0.2, fontes oficiais sem alterações. Receita: build_ffmpeg.sh.\n'
        'SHA256 do arquivo fonte: ' + hashlib.sha256((sources / 'ffmpeg-9.0.2.tar.xz').read_bytes()).hexdigest() + '\n'
        'Fontes: https://ffmpeg.org/releases/ffmpeg-9.0.2.tar.xz\n'
        'Execute a receita a partir deste projeto, com as fontes em build/vendor/ffmpeg-9.0.2.\n')
    copy_runtime_licenses(licenses)
    (licenses / 'LEIA-ME.txt').write_text(
        'Transcrição Local usa Python, PyInstaller e FFmpeg como componentes separados.\n'
        'FFmpeg: LGPL 2.1 ou posterior, fonte completa e receita em ../Sources.\n'
        'Python: licença PSF e avisos históricos. PyInstaller: GPL com exceção para os executáveis gerados.\n'
        'As bibliotecas do runtime e seus avisos estão nas subpastas deste diretório.\n'
        'Não há uso do Python/Homebrew do computador de destino.\n')
    # PyInstaller signs the runtime leaves; seal the native nested bundle next.
    run(['codesign', '--force', '--sign', '-', '--timestamp=none', backend_app])
    run(['codesign', '--force', '--sign', '-', '--timestamp=none', APP])
    run(['codesign', '--verify', '--deep', '--strict', APP])
    image_root = WORK / 'disk'
    if image_root.exists():
        shutil.rmtree(image_root)
    image_root.mkdir()
    shutil.copytree(APP, image_root / APP.name, symlinks=True)
    (image_root / 'Aplicativos').symlink_to('/Applications', target_is_directory=True)
    shutil.copy2(ROOT / 'packaging/LEIA-ME.txt', image_root)
    dmg = DIST / f'Transcricao-Local-{VERSION}-arm64.dmg'
    run(['hdiutil', 'create', '-ov', '-volname', 'Transcrição Local', '-srcfolder', image_root,
         '-format', 'UDZO', dmg])
    run(['hdiutil', 'verify', dmg])
    shutil.copy2(ROOT / 'packaging/LEIA-ME.txt', DIST / 'LEIA-ME.txt')
    (DIST / 'SHA256.txt').write_text(hashlib.sha256(dmg.read_bytes()).hexdigest() + '  ' + dmg.name + '\n')
    print(dmg)


def copy_runtime_licenses(destination):
    # Collect notices from the exact local build inputs, not unrelated installed packages.
    import importlib.metadata
    for name in ['pyinstaller', 'altgraph', 'macholib', 'packaging', 'pyinstaller-hooks-contrib']:
        distribution = importlib.metadata.distribution(name)
        for file in distribution.files or []:
            if any(word in file.name.upper() for word in ['COPYING', 'LICENSE', 'NOTICE']):
                target = destination / name / file.name
                target.parent.mkdir(exist_ok=True)
                shutil.copy2(distribution.locate_file(file), target)
    python_cellar = Path(sys.base_prefix).resolve().parents[3]
    # Homebrew's Python framework links system libraries plus these build dependencies.
    candidates = [python_cellar]
    for name in ['openssl@3', 'mpdecimal', 'xz', 'zstd', 'gettext', 'libffi', 'libexpat', 'sqlite']:
        path = Path('/opt/homebrew/opt') / name
        if path.exists():
            candidates.append(path.resolve())
    for path in candidates:
        for file in path.rglob('*'):
            if file.is_file() and file.name.upper().startswith(('LICENSE', 'COPYING', 'NOTICE')):
                relative = file.relative_to(path)
                target = destination / path.parent.name / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(file, target)


if __name__ == '__main__':
    build()
