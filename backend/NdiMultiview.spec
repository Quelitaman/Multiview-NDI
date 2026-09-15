# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the NDI Multiview Windows executable.

Build:
    pyinstaller NdiMultiview.spec --clean --noconfirm

Assumes the React frontend has been built into ..\\frontend\\build (run
`yarn build` before invoking PyInstaller).
"""
from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

here = Path(SPECPATH).resolve()
frontend_build = here.parent / "frontend" / "build"

datas = []
if frontend_build.exists():
    datas.append((str(frontend_build), "frontend_build"))

# cyndilib ships compiled cython modules + the NDI runtime shim we need at runtime
datas += collect_data_files("cyndilib")
hiddenimports = collect_submodules("cyndilib")
hiddenimports += [
    "uvicorn.lifespan.on",
    "uvicorn.lifespan.off",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.protocols.websockets.websockets_impl",
    "uvicorn.loops.auto",
    "uvicorn.loops.asyncio",
    "server",
    "ndi_service",
    "layout_store",
]

block_cipher = None


a = Analysis(
    ["launcher.py"],
    pathex=[str(here)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "matplotlib", "pandas", "boto3", "botocore", "cryptography",
        "jose", "oauthlib", "requests_oauthlib", "black", "flake8",
        "mypy", "pytest", "isort", "typer", "sqlalchemy",
    ],
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
    name="NdiMultiview",
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
    icon=None,
)
