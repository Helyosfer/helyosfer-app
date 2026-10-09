"""Builds the Windows package and checks that it starts.

    python scripts/build_windows.py            build dist/Helysofer and check it
    python scripts/build_windows.py --zip      also write dist/Helysofer-<version>-windows.zip
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
PROGRAM = os.path.join(DIST, "Helysofer", "Helysofer.exe")

sys.path.insert(0, ROOT)
from utils.version import APP_VERSION  # noqa: E402

VERSION_INFO = """\
VSVersionInfo(
  ffi=FixedFileInfo(filevers=({numbers}), prodvers=({numbers})),
  kids=[
    StringFileInfo([StringTable('040904B0', [
      StringStruct('CompanyName', 'Helysofer'),
      StringStruct('FileDescription', 'Helysofer'),
      StringStruct('FileVersion', '{version}'),
      StringStruct('InternalName', 'Helysofer'),
      StringStruct('LegalCopyright', 'Copyright 2026 Helysofer. Apache License 2.0.'),
      StringStruct('OriginalFilename', 'Helysofer.exe'),
      StringStruct('ProductName', 'Helysofer'),
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
            os.path.join(PACKAGING, "helysofer.spec"),
        ],
        cwd=ROOT, check=True,
    )


def folder_size(path: str) -> int:
    return sum(
        os.path.getsize(os.path.join(folder, name))
        for folder, _dirs, names in os.walk(path) for name in names
    )


def check_starts(seconds: float = 12.0) -> None:
    """Starts the package on a throwaway profile and expects it to stay up.

    A build that is missing a file or a module closes at once, with the
    reason in its log; one that is still running after `seconds` got as far
    as showing its window.
    """
    home = tempfile.mkdtemp(prefix="helysofer-package-")
    env = dict(os.environ, HELYSOFER_HOME=home)
    started = time.monotonic()
    process = subprocess.Popen([PROGRAM], env=env, cwd=tempfile.gettempdir())
    try:
        code = process.wait(timeout=seconds)
    except subprocess.TimeoutExpired:
        print(f"The package started and stayed up for {seconds:.0f} s.")
        return
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=10)
        shutil.rmtree(home, ignore_errors=True)
    raise SystemExit(
        f"The package closed after {time.monotonic() - started:.1f} s with code {code}."
    )


def check_price_worker() -> None:
    """The package must be able to start itself as the price process."""
    import json

    fd, output = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    home = tempfile.mkdtemp(prefix="helysofer-package-")
    request = [{"id": 1, "asset_name": "USD", "asset_code": "USD", "asset_type": "D\u00f6viz",
                "purchase_price": 1.0, "quantity": 1.0}]
    try:
        done = subprocess.run(
            [PROGRAM, "--price-worker", output],
            input=json.dumps(request, ensure_ascii=False).encode("utf-8"),
            env=dict(os.environ, HELYSOFER_HOME=home, HELYSOFER_ASSET_PRICE_CHILD="1"),
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
    target = os.path.join(DIST, f"Helysofer-{APP_VERSION}-windows")
    path = shutil.make_archive(target, "zip", DIST, "Helysofer")
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
    print(f"dist/Helysofer is {folder_size(os.path.dirname(PROGRAM)) / 2**20:.0f} MB.")
    check_starts()
    check_price_worker()
    if options.zip:
        make_zip()
    if options.installer:
        make_installer()


if __name__ == "__main__":
    main()
