"""Build the native controller locally, without modifying installed apps."""
from pathlib import Path
import plistlib
import subprocess

ROOT = Path(__file__).resolve().parent
APP = ROOT / 'build/TranscricaoLocal.app'
MACOS = APP / 'Contents/MacOS'
RESOURCES = APP / 'Contents/Resources'
MACOS.mkdir(parents=True, exist_ok=True)
RESOURCES.mkdir(parents=True, exist_ok=True)
subprocess.run(['xcrun', 'swiftc', '-O', '-parse-as-library', '-module-cache-path',
                '/tmp/wa-speech-availability-cache', str(ROOT / 'NativeApp.swift'),
                '-o', str(MACOS / 'TranscricaoLocal')], check=True)
info = {
    'CFBundleIdentifier': 'local.waapple.controller',
    'CFBundleName': 'Transcrição Local',
    'CFBundleDisplayName': 'Transcrição Local',
    'CFBundleExecutable': 'TranscricaoLocal',
    'CFBundlePackageType': 'APPL',
    'CFBundleShortVersionString': '1.0.0',
    'CFBundleVersion': '1',
    'CFBundleIconFile': 'AppIcon',
    'LSMinimumSystemVersion': '27.0',
    'LSApplicationCategoryType': 'public.app-category.utilities',
    'NSHighResolutionCapable': True,
    'WAServerRoot': str(ROOT),
}
(APP / 'Contents/Info.plist').write_bytes(plistlib.dumps(info))
iconset = ROOT / 'build/AppIcon.iconset'
iconset.mkdir(exist_ok=True)
subprocess.run(['swift', '-module-cache-path', '/tmp/wa-speech-availability-cache',
                str(ROOT / 'AppIcon.swift'), str(ROOT / 'build/icon-source.png')], check=True)
for size in [16, 32, 128, 256, 512]:
    for scale in [1, 2]:
        suffix = '@2x' if scale == 2 else ''
        target = iconset / f'icon_{size}x{size}{suffix}.png'
        subprocess.run(['sips', '-z', str(size * scale), str(size * scale),
                        str(ROOT / 'build/icon-source.png'), '--out', str(target)],
                       check=True, stdout=subprocess.DEVNULL)
subprocess.run(['iconutil', '-c', 'icns', str(iconset), '-o', str(RESOURCES / 'AppIcon.icns')], check=True)
subprocess.run(['codesign', '--force', '--sign', '-', '--timestamp=none', str(APP)], check=True)
subprocess.run(['codesign', '--verify', '--strict', str(APP)], check=True)
print(APP)
