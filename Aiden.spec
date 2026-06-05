# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

vosk_binaries = collect_dynamic_libs('vosk')
pvporcupine_data = collect_data_files('pvporcupine')

a = Analysis(
    ['src\\main.py'],
    pathex=[],
    binaries=vosk_binaries,
    datas=[('config', 'config'), ('dashboard/build', 'dashboard/build'), ('sounds', 'sounds'), ('vosk_models', 'vosk_models'), ('tools', 'tools')] + pvporcupine_data,
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
    icon=['overlay\\public\\icon.ico'],
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
