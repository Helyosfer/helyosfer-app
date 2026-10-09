"""Builds the Windows package and checks that it starts.

    python scripts/build_windows.py            build dist/Helyosfer and check it
    python scripts/build_windows.py --zip      also write dist/Helyosfer-<version>-windows.zip
    python scripts/build_windows.py --installer  also compile the installer (needs Inno Setup)

PyInstaller is a build tool, not a dependency of the application:
`pip install pyinstaller` before the first build.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACKAGING = os.path.join(ROOT, "packaging")
DIST = os.path.join(ROOT, "dist")
PROGRAM = os.path.join(DIST, "Helyosfer", "Helyosfer.exe")

sys.path.insert(0, ROOT)
from utils.version import APP_VERSION  # noqa: E402

VERSION_INFO = """\
VSVersionInfo(
  ffi=FixedFileInfo(filevers=({numbers}), prodvers=({numbers})),
  kids=[
    StringFileInfo([StringTable('040904B0', [
      StringStruct('CompanyName', 'Helyosfer'),
      StringStruct('FileDescription', 'Helyosfer'),
      StringStruct('FileVersion', '{version}'),
      StringStruct('InternalName', 'Helyosfer'),
      StringStruct('LegalCopyright', 'Copyright 2026 Helyosfer. Apache License 2.0.'),
      StringStruct('OriginalFilename', 'Helyosfer.exe'),
      StringStruct('ProductName', 'Helyosfer'),
      StringStruct('ProductVersion', '{version}'),
    ])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])]),
  ]
)
"""


def write_version_info() -> None:
    parts = [int(part) for part in APP_VERSION.split(".")[:4] if part.isdigit()]
    parts += [0] * (4 - len(parts))
    os.makedirs(os.path.join(PACKAGING, "build"), exist_ok=True)
    with open(os.path.join(PACKAGING, "build", "version_info.txt"), "w", encoding="utf-8") as out:
        out.write(VERSION_INFO.format(
            numbers=", ".join(str(part) for part in parts), version=APP_VERSION,
        ))


def build() -> None:
    write_version_info()
    subprocess.run(
        [
            sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
            "--distpath", DIST, "--workpath", os.path.join(PACKAGING, "build", "work"),
            os.path.join(PACKAGING, "helyosfer.spec"),
        ],
        cwd=ROOT, check=True,
    )


def folder_size(path: str) -> int:
    return sum(
        os.path.getsize(os.path.join(folder, name))
        for folder, _dirs, names in os.walk(path) for name in names
    )


def check_libraries() -> None:
    """Every library in the package finds the Qt libraries it links against.

    The build leaves out Qt modules the interface does not use. A library
    that is kept but links against one that was dropped would fail to load
    only when its screen is first opened, so the link tables are read here.
    """
    import pefile  # comes with PyInstaller

    folder = os.path.dirname(PROGRAM)
    present, libraries = set(), []
    for parent, _dirs, names in os.walk(folder):
        for name in names:
            if name.lower().endswith((".dll", ".pyd", ".exe")):
                present.add(name.lower())
                libraries.append(os.path.join(parent, name))
    missing = set()
    for path in libraries:
        image = pefile.PE(path, fast_load=True)
        image.parse_data_directories(
            directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_IMPORT"]]
        )
        for entry in getattr(image, "DIRECTORY_ENTRY_IMPORT", []):
            needed = entry.dll.decode("ascii", "replace").lower()
            if needed.startswith(("qt6", "pyside6", "shiboken6")) and needed not in present:
                missing.add(f"{os.path.relpath(path, folder)} needs {needed}")
        image.close()
    if missing:
        raise SystemExit("Libraries the package needs were left out:\n  " + "\n  ".join(sorted(missing)))
    print(f"All {len(libraries)} libraries find the Qt libraries they link against.")


def _window_titles(process_id: int) -> list[str]:
    """Titles of the visible top-level windows that belong to a process."""
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    titles = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def visit(window, _extra):
        owner = wintypes.DWORD()
        user32.GetWindowThreadProcessId(window, ctypes.byref(owner))
        if owner.value == process_id and user32.IsWindowVisible(window):
            text = ctypes.create_unicode_buffer(256)
            user32.GetWindowTextW(window, text, 256)
            titles.append(text.value)
        return True

    user32.EnumWindows(visit, 0)
    return titles


def check_starts(seconds: float = 12.0) -> None:
    """Starts the package on a throwaway profile and expects its window.

    A build that is missing a file or a module closes at once or never shows
    a window. Whatever Qt reports while the first screen loads is collected
    and counts as a failure too: an interface file that could not be loaded
    is reported there and nowhere else.
    """
    home = tempfile.mkdtemp(prefix="helyosfer-package-")
    env = dict(os.environ, HELYOSFER_HOME=home)
    report = os.path.join(home, "startup.txt")
    started = time.monotonic()
    with open(report, "wb") as output:
        process = subprocess.Popen(
            [PROGRAM], env=env, cwd=tempfile.gettempdir(),
            stdin=subprocess.DEVNULL, stdout=output, stderr=output,
        )
        titles: list[str] = []
        try:
            while time.monotonic() - started < seconds and process.poll() is None:
                titles = _window_titles(process.pid) or titles
                time.sleep(0.5)
            code = process.poll()
        finally:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=10)
    with open(report, encoding="utf-8", errors="replace") as text:
        said = text.read().strip()
    shutil.rmtree(home, ignore_errors=True)
    if code is not None:
        raise SystemExit(
            f"The package closed after {time.monotonic() - started:.1f} s with code {code}.\n{said}"
        )
    if "Helyosfer" not in titles:
        raise SystemExit(f"The package ran but showed no window (windows: {titles}).\n{said}")
    if said:
        raise SystemExit(f"The package started with complaints:\n{said}")
    print(f"The package showed its window and stayed up for {seconds:.0f} s without a complaint.")


def check_itself() -> None:
    """Runs the package's own check of the features it loads only on use."""
    done = subprocess.run(
        [PROGRAM, "--check-package"], stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=180, check=False,
        cwd=tempfile.gettempdir(),
    )
    said = done.stderr.decode("utf-8", "replace").strip()
    print(said)
    if done.returncode != 0:
        raise SystemExit("The package failed its own check.")


def check_price_worker() -> None:
    """The package must be able to start itself as the price process."""
    import json

    fd, output = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    home = tempfile.mkdtemp(prefix="helyosfer-package-")
    request = [{"id": 1, "asset_name": "USD", "asset_code": "USD", "asset_type": "D\u00f6viz",
                "purchase_price": 1.0, "quantity": 1.0}]
    try:
        done = subprocess.run(
            [PROGRAM, "--price-worker", output],
            input=json.dumps(request, ensure_ascii=False).encode("utf-8"),
            env=dict(os.environ, HELYOSFER_HOME=home, HELYOSFER_ASSET_PRICE_CHILD="1"),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120, check=False,
        )
        with open(output, encoding="utf-8") as stream:
            text = stream.read()
        answer = json.loads(text) if text.strip() else []
    finally:
        os.unlink(output)
        shutil.rmtree(home, ignore_errors=True)
    if done.returncode != 0 or len(answer) != 1:
        raise SystemExit(
            f"The price process failed (code {done.returncode}): "
            f"{done.stderr.decode('utf-8', 'replace')[-600:]}"
        )
    price = answer[0].get("current_price")
    print("The price process answered:", "no price (offline?)" if price is None else f"USD = {price:.2f}")


def make_zip() -> str:
    target = os.path.join(DIST, f"Helyosfer-{APP_VERSION}-windows")
    path = shutil.make_archive(target, "zip", DIST, "Helyosfer")
    print(f"Wrote {path} ({os.path.getsize(path) / 2**20:.0f} MB).")
    return path


def make_installer() -> None:
    compiler = shutil.which("iscc") or next(
        (candidate for candidate in (
            r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
            r"C:\Program Files\Inno Setup 6\ISCC.exe",
        ) if os.path.exists(candidate)), None,
    )
    if compiler is None:
        raise SystemExit("Inno Setup was not found. Install it, or use --zip.")
    subprocess.run(
        [compiler, f"/DAppVersion={APP_VERSION}", os.path.join(PACKAGING, "installer.iss")],
        cwd=ROOT, check=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--zip", action="store_true")
    parser.add_argument("--installer", action="store_true")
    parser.add_argument("--skip-build", action="store_true", help="check an existing build")
    options = parser.parse_args()

    if sys.platform != "win32":
        raise SystemExit("The Windows package is built on Windows.")
    if not options.skip_build:
        build()
    print(f"dist/Helyosfer is {folder_size(os.path.dirname(PROGRAM)) / 2**20:.0f} MB.")
    check_libraries()
    check_starts()
    check_itself()
    check_price_worker()
    if options.zip:
        make_zip()
    if options.installer:
        make_installer()


if __name__ == "__main__":
    main()
