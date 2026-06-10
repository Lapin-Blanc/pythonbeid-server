# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for the eid-agent tray application (windowed, onedir).
# Build from the repository root:
#   python -m PyInstaller --noconfirm --clean packaging/eid_agent_tray.spec

import os

from PyInstaller.utils.hooks import collect_all, collect_submodules

spec_dir = SPECPATH  # noqa: F821 - injected by PyInstaller
repo_root = os.path.abspath(os.path.join(spec_dir, ".."))

# uvicorn loads loops/protocols implementations dynamically.
hiddenimports = collect_submodules("uvicorn")

datas = []
binaries = []
# pyscard (smartcard) ships a C extension; pythonbeid may carry data files.
for package in ("pythonbeid", "smartcard"):
    pkg_datas, pkg_binaries, pkg_hidden = collect_all(package)
    datas += pkg_datas
    binaries += pkg_binaries
    hiddenimports += pkg_hidden

a = Analysis(
    [os.path.join(spec_dir, "tray_launcher.py")],
    pathex=[repo_root],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "pytest", "numpy"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    exclude_binaries=True,
    name="eid-agent-tray",
    icon=os.path.join(spec_dir, "eid-agent.ico"),
    console=False,
    upx=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    name="eid-agent-tray",
    upx=False,
)
