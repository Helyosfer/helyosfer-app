# PyInstaller build description for the Windows package.
#
# Build with `python scripts/build_windows.py`; that script checks the result
# as well. The output is a folder (`dist/Helysofer`), not a single file: a
# single-file build unpacks itself on every start, and the application starts
# itself a second time whenever it fetches prices.

import os

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = os.path.abspath(os.path.join(SPECPATH, os.pardir))
VERSION_FILE = os.path.join(SPECPATH, "build", "version_info.txt")

# Read at run time rather than imported, so they are listed by hand.
datas = [
    (os.path.join(ROOT, "app", "qml"), os.path.join("app", "qml")),
    (os.path.join(ROOT, "assets"), "assets"),
    (os.path.join(ROOT, "LICENSE"), "."),
    (os.path.join(ROOT, "NOTICE"), "."),
    (os.path.join(ROOT, "THIRD_PARTY_NOTICES.md"), "."),
]
datas += collect_data_files("certifi")
datas += collect_data_files("fpdf")

hiddenimports = [
    # Started through the executable's own flag, never imported by the interface.
    "services.asset_price_worker",
    # Chosen by name at run time.
    "keyring.backends.Windows",
    "win32ctypes.core",
]
hiddenimports += collect_submodules("yfinance")

# Nothing in the application uses these; leaving them out keeps the package small.
excludes = [
    "tkinter", "unittest", "pytest", "hypothesis", "mypy", "flake8", "IPython",
    "matplotlib", "scipy", "PyQt5", "PyQt6", "PySide2",
]

analysis = Analysis(
    [os.path.join(ROOT, "app", "__main__.py")],
    pathex=[ROOT],
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=excludes,
    noarchive=False,
)
archive = PYZ(analysis.pure)

program = EXE(
    archive,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="Helysofer",
    icon=os.path.join(ROOT, "assets", "icon.ico"),
    version=VERSION_FILE if os.path.exists(VERSION_FILE) else None,
    console=False,
    upx=False,
)
COLLECT(
    program,
    analysis.binaries,
    analysis.datas,
    name="Helysofer",
    upx=False,
)
