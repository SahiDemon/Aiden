# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs
from pathlib import Path

project_root = Path(SPECPATH).resolve().parent

vosk_binaries = collect_dynamic_libs('vosk')
pvporcupine_data = collect_data_files('pvporcupine')
openwakeword_data = collect_data_files('openwakeword')  # bundles silero_vad.onnx + model resources

a = Analysis(
    [str(project_root / 'src' / 'main.py')],
    pathex=[str(project_root)],
    binaries=vosk_binaries,
    datas=[(str(project_root / source), destination) for source, destination in
           [('config', 'config'), ('dashboard/build', 'dashboard/build'), ('sounds', 'sounds'), ('vosk_models', 'vosk_models'), ('tools', 'tools')]] + pvporcupine_data + openwakeword_data,
    hiddenimports=['engineio.async_drivers.threading'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['webrtcvad'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Aiden',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=[str(project_root / 'overlay' / 'public' / 'icon.ico')],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Aiden',
)
