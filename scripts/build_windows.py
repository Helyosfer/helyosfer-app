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
import re
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


# What Windows itself sets. The build computer has Python, its packages and
# this repository on the path as well; the computer the package is for has
# none of them, so the checks run without them.
_WINDOWS_ONLY = (
    "SystemRoot", "SystemDrive", "windir", "TEMP", "TMP", "USERPROFILE", "APPDATA",
    "LOCALAPPDATA", "ProgramData", "ALLUSERSPROFILE", "PUBLIC", "ComSpec", "USERNAME",
    "USERDOMAIN", "COMPUTERNAME", "HOMEDRIVE", "HOMEPATH", "OS",
    "NUMBER_OF_PROCESSORS", "PROCESSOR_ARCHITECTURE",
)


def bare_environment(**extra: str) -> dict[str, str]:
    """An environment that names Windows and nothing installed on top of it."""
    env = {name: os.environ[name] for name in _WINDOWS_ONLY if name in os.environ}
    windows = os.environ["SystemRoot"]
    env["PATH"] = os.pathsep.join([os.path.join(windows, "System32"), windows])
    env.update(extra)
    return env


def _loaded_files(process_id: int) -> list[str]:
    """Every program file a running process has loaded."""
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    psapi.EnumProcessModulesEx.argtypes = (
        wintypes.HANDLE, ctypes.POINTER(wintypes.HMODULE), wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD), wintypes.DWORD,
    )
    psapi.GetModuleFileNameExW.argtypes = (
        wintypes.HANDLE, wintypes.HMODULE, wintypes.LPWSTR, wintypes.DWORD,
    )
    query_and_read = 0x0400 | 0x0010
    handle = kernel32.OpenProcess(query_and_read, False, process_id)
    if not handle:
        return []
    try:
        modules = (wintypes.HMODULE * 4096)()
        needed = wintypes.DWORD()
        every_module = 0x03
        if not psapi.EnumProcessModulesEx(
            handle, modules, ctypes.sizeof(modules), ctypes.byref(needed), every_module,
        ):
            return []
        files = []
        for module in modules[: needed.value // ctypes.sizeof(wintypes.HMODULE)]:
            name = ctypes.create_unicode_buffer(1024)
            if psapi.GetModuleFileNameExW(handle, module, name, 1024):
                files.append(name.value)
        return files
    finally:
        kernel32.CloseHandle(handle)


def _borrowed(files: list[str]) -> list[str]:
    """Loaded files the package would not find on a computer without Python.

    Anything from this Python, from a `site-packages` folder or from the
    repository is the build computer's. So is a C++ runtime library found
    outside the package: it is not part of Windows, and a copy in System32
    was put there by some other program's installer.
    """
    package = os.path.normcase(os.path.dirname(PROGRAM)) + os.sep
    foreign = [os.path.normcase(os.path.abspath(path)) + os.sep
               for path in {sys.prefix, sys.base_prefix, ROOT}]
    # vcruntime140.dll, msvcp140_1.dll and the like; msvcp_win.dll is Windows' own.
    runtime = re.compile(r"(vcruntime|msvcp|concrt|vccorlib)\d")
    borrowed = []
    for path in files:
        where = os.path.normcase(os.path.abspath(path))
        if where.startswith(package):
            continue
        name = os.path.basename(where)
        if (any(where.startswith(root) for root in foreign)
                or f"{os.sep}site-packages{os.sep}" in where
                or runtime.match(name)):
            borrowed.append(path)
    return borrowed


def check_starts(seconds: float = 12.0) -> None:
    """Starts the package on a throwaway profile and expects its window.

    A build that is missing a file or a module closes at once or never shows
    a window. Whatever Qt reports while the first screen loads is collected
    and counts as a failure too: an interface file that could not be loaded
    is reported there and nowhere else.

    It runs with nothing but Windows on the path, and every file it has
    loaded by the end is looked at: one taken from the build computer's
    Python would be missing where the package is going.
    """
    home = tempfile.mkdtemp(prefix="helyosfer-package-")
    env = bare_environment(HELYOSFER_HOME=home)
    report = os.path.join(home, "startup.txt")
    started = time.monotonic()
    with open(report, "wb") as output:
        process = subprocess.Popen(
            [PROGRAM], env=env, cwd=tempfile.gettempdir(),
            stdin=subprocess.DEVNULL, stdout=output, stderr=output,
        )
        titles: list[str] = []
        files: list[str] = []
        try:
            while time.monotonic() - started < seconds and process.poll() is None:
                titles = _window_titles(process.pid) or titles
                time.sleep(0.5)
            code = process.poll()
            if code is None:
                files = _loaded_files(process.pid)
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
    if not files:
        raise SystemExit("The files the package loaded could not be listed.")
    borrowed = _borrowed(files)
    if borrowed:
        raise SystemExit(
            "The package loaded files that a computer without Python does not have:\n  "
            + "\n  ".join(borrowed)
        )
    package = os.path.normcase(os.path.dirname(PROGRAM)) + os.sep
    own = sum(os.path.normcase(os.path.abspath(path)).startswith(package) for path in files)
    print(
        f"With only Windows on the path it loaded {len(files)} files: {own} of its own,"
        f" {len(files) - own} of Windows, none from this computer's Python."
    )


def check_itself() -> None:
    """Runs the package's own check of the features it loads only on use."""
    done = subprocess.run(
        [PROGRAM, "--check-package"], stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=180, check=False,
        cwd=tempfile.gettempdir(), env=bare_environment(),
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


# The identity in packaging/installer.iss; Windows lists the program under it.
_INSTALLED_KEY = (
    r"Software\Microsoft\Windows\CurrentVersion\Uninstall"
    r"\{6C1F2B0E-4D0A-4E57-9E0C-6B7D1E5A9F31}_is1"
)


def _installer_compiler() -> str | None:
    """Inno Setup's command-line compiler, wherever it was installed."""
    found = shutil.which("iscc")
    if found:
        return found
    roots = (
        os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
        os.environ.get("ProgramFiles", r"C:\Program Files"),
        # Where it goes when it is installed for one user only.
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs"),
    )
    for root in roots:
        candidate = os.path.join(root, "Inno Setup 6", "ISCC.exe")
        if os.path.exists(candidate):
            return candidate
    return None


def make_installer() -> str:
    compiler = _installer_compiler()
    if compiler is None:
        raise SystemExit("Inno Setup was not found. Install it, or use --zip.")
    done = subprocess.run(
        [compiler, "/Q", f"/DAppVersion={APP_VERSION}", os.path.join(PACKAGING, "installer.iss")],
        cwd=ROOT, check=False, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    if done.returncode != 0:
        raise SystemExit(
            "The installer could not be compiled:\n" + done.stdout.decode("utf-8", "replace")
        )
    path = os.path.join(DIST, f"Helyosfer-{APP_VERSION}-setup.exe")
    print(f"Wrote {path} ({os.path.getsize(path) / 2**20:.0f} MB).")
    return path


def _installed() -> dict | None:
    """How Windows lists an installed Helyosfer, or None when it is not."""
    import winreg

    for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        try:
            with winreg.OpenKey(hive, _INSTALLED_KEY) as key:
                return {
                    name: winreg.QueryValueEx(key, name)[0]
                    for name in ("DisplayName", "DisplayVersion", "InstallLocation")
                }
        except OSError:
            continue
    return None


def _start_menu_entry() -> str:
    return os.path.join(
        os.environ["APPDATA"], "Microsoft", "Windows", "Start Menu", "Programs", "Helyosfer.lnk",
    )


def check_installer(setup: str) -> None:
    """Installs with the installer, checks what it left, and removes it again.

    Compiling proves the script is well formed, not that the result installs
    a program that runs. So it is installed for real, into a folder of its
    own: the program must start from there, Windows must list it with the
    right version and a Start menu entry, and uninstalling must take all of
    that away again.

    A computer that already has Helyosfer installed is left alone: the trial
    would be taken for an upgrade of that installation and then remove it.
    """
    if _installed() is not None:
        print("Helyosfer is installed on this computer, so the installer was not tried.")
        return
    home = tempfile.mkdtemp(prefix="helyosfer-setup-")
    target = os.path.join(home, "Helyosfer")
    log = os.path.join(home, "setup.log")
    quiet = ["/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/SP-"]
    try:
        done = subprocess.run(
            [setup, *quiet, f"/DIR={target}", f"/LOG={log}"], check=False, timeout=600,
        )
        if done.returncode != 0:
            said = ""
            if os.path.exists(log):
                with open(log, encoding="utf-8", errors="replace") as text:
                    said = "".join(text.readlines()[-15:])
            raise SystemExit(f"The installer ended with code {done.returncode}.\n{said}")

        program = os.path.join(target, "Helyosfer.exe")
        listed = _installed()
        problems = []
        if not os.path.exists(program):
            problems.append("the program is not in the folder it was installed to")
        if listed is None:
            problems.append("Windows does not list it as installed")
        elif (listed["DisplayName"], listed["DisplayVersion"]) != ("Helyosfer", APP_VERSION):
            problems.append(f"Windows lists it as {listed['DisplayName']} {listed['DisplayVersion']}")
        if not os.path.exists(_start_menu_entry()):
            problems.append("there is no Start menu entry")
        if not problems:
            ran = subprocess.run(
                [program, "--check-package"], stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=180, check=False,
                cwd=tempfile.gettempdir(), env=bare_environment(),
            )
            if ran.returncode != 0:
                problems.append(
                    "the installed program failed its own check:\n"
                    + ran.stderr.decode("utf-8", "replace").strip()
                )
    finally:
        remover = os.path.join(target, "unins000.exe")
        if os.path.exists(remover):
            subprocess.run([remover, *quiet[:3]], check=False, timeout=300)
            # The remover hands over to a copy of itself and returns early.
            waited = time.monotonic()
            while time.monotonic() - waited < 60 and (
                os.path.exists(target) or _installed() is not None
            ):
                time.sleep(0.5)
    left = [
        what for what, there in (
            ("its folder", os.path.exists(target)),
            ("its entry in the list of installed programs", _installed() is not None),
            ("its Start menu entry", os.path.exists(_start_menu_entry())),
        ) if there
    ]
    shutil.rmtree(home, ignore_errors=True)
    if problems:
        raise SystemExit("The installer does not install a working program:\n  " + "\n  ".join(problems))
    if left:
        raise SystemExit("Uninstalling left behind: " + ", ".join(left) + ".")
    print(
        "The installer was tried: it installed without a question, the program passed its"
        " own check from there, and uninstalling removed everything it had put in place."
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
        check_installer(make_installer())


if __name__ == "__main__":
    main()
