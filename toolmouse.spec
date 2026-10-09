# -*- mode: python ; coding: utf-8 -*-

import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

hidden_imports = [
    'colorama',
    'keyboard',
    'PIL',
    'PIL.Image',
    'PIL.ImageGrab',
    'google.genai',
    'pydantic',
    'pydantic.deprecated',
    'pydantic.deprecated.json',
    'core',
    'core.screen_capture',
    'core.sheets_config',
    'core.updater',
    'core.ai_client',
    'ui',
    'ui.overlay',
    'ui.setup_window',
]

# Thêm tất cả submodules của google.genai và pydantic để khi lazy import không bị thiếu
hidden_imports += collect_submodules('google.genai')
hidden_imports += collect_submodules('pydantic')

datas = []
try:
    datas += collect_data_files('google.genai')
except Exception:
    pass

a = Analysis(
    ['main.py'],
    pathex=['.'],
    binaries=[],
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'matplotlib',
        'scipy',
        'pandas',
        'numpy',
        'pytest',
        'unittest',
        'jupyter',
        'IPython',
        'torch',
        'cv2',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='ToolMouse',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
