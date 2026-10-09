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
    # `unittest` stays: the PDF library imports it when it is first used.
    "tkinter", "pytest", "hypothesis", "mypy", "flake8", "IPython",
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

# The Qt hook collects every Qt Quick module and style that is installed. The
# interface uses the Basic style and none of the modules below, and Windows
# draws through Direct3D, so the software OpenGL library is never loaded.
# `scripts/build_windows.py` checks afterwards that no library that is kept
# still needs one that was dropped.
UNUSED_STYLES = ("FluentWinUI3", "Fusion", "Imagine", "Material", "Universal")
UNUSED_LIBRARIES = (
    "opengl32sw.dll", "Qt6Test.dll", "Qt6QuickTest.dll", "Qt6Sql.dll",
    "Qt6QmlLocalStorage.dll", "Qt6QuickParticles.dll", "Qt6QuickTimeline.dll",
    "Qt6QuickTimelineBlendTrees.dll", "Qt6QuickVectorImage.dll",
    "Qt6QuickVectorImageGenerator.dll", "Qt6QuickVectorImageHelpers.dll",
) + tuple(
    f"Qt6QuickControls2{style}{suffix}.dll"
    for style in UNUSED_STYLES for suffix in ("", "StyleImpl")
)
UNUSED_FOLDERS = (
    "PySide6/translations/", "PySide6/plugins/qmltooling/", "PySide6/qml/QtTest/",
    "PySide6/qml/QtQuick/LocalStorage/", "PySide6/qml/QtQuick/Particles/",
    "PySide6/qml/QtQuick/Timeline/", "PySide6/qml/QtQuick/VectorImage/",
    "PySide6/qml/QtQuick/VirtualKeyboard/",
) + tuple(f"PySide6/qml/QtQuick/Controls/{style}/" for style in UNUSED_STYLES)


def kept(entry):
    target = entry[0].replace("\\", "/")
    if target.startswith("PySide6/") and target.rsplit("/", 1)[-1] in UNUSED_LIBRARIES:
        return False
    return not any(target.startswith(folder) for folder in UNUSED_FOLDERS)


analysis.binaries = [entry for entry in analysis.binaries if kept(entry)]
analysis.datas = [entry for entry in analysis.datas if kept(entry)]

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
