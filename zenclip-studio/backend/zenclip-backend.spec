# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for ZenClip Backend

Build command: pyinstaller zenclip-backend.spec --clean
"""
import sys
from pathlib import Path

block_cipher = None

# Get backend source directory
backend_dir = Path(SPECPATH)

a = Analysis(
    ['src/app_modular.py'],
    pathex=[str(backend_dir)],
    binaries=[],
    datas=[
        # Include static files if they exist
        ('static', 'static'),
        ('templates', 'templates'),
    ],
    hiddenimports=[
        # FastAPI/Uvicorn
        'uvicorn.logging',
        'uvicorn.protocols',
        'uvicorn.protocols.http',
        'uvicorn.protocols.http.auto',
        'uvicorn.protocols.websockets',
        'uvicorn.protocols.websockets.auto',
        'uvicorn.lifespan',
        'uvicorn.lifespan.on',
        # FastAPI
        'fastapi',
        'fastapi.responses',
        'fastapi.staticfiles',
        'fastapi.templating',
        'fastapi.middleware',
        'fastapi.middleware.cors',
        # Pydantic
        'pydantic',
        # Our modules
        'config',
        'routers',
        'routers.health',
        'routers.settings',
        'routers.fonts',
        'routers.gallery',
        'routers.processing',
        'routers.transcript',
        'routers.debug',
        'services.core.job_manager',
        'services.core.job_runner',
        'services.core.gallery_cache',
        'services.core.job_database',
        'services.core.binary_manager',
        'services.core.resource_monitor',
        'services.media.video_cutter',
        'services.media.audio_transcriber',
        'services.ai.llm_analyzer',
        'utils.logger',
        'utils.secret_store',
        'utils.path_validator',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Exclude unnecessary modules to reduce size
        'tkinter',
        'unittest',
        'test',
        'tests',
        'IPython',
        'jupyter',
        'notebook',
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
    name='zenclip-backend',
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
