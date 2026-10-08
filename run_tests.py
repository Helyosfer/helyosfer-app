import multiprocessing
import os
import sys
import tempfile
import unittest


for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError, OSError):


        pass


_REAL_STDERR = sys.stderr


os.environ.setdefault("HELYSOFER_HEADLESS", "1")



if "XDG_DATA_HOME" not in os.environ:
    _sandbox = tempfile.mkdtemp(prefix="helysofer-test-xdg-")
    os.environ["XDG_DATA_HOME"] = os.path.join(_sandbox, "data")
    os.environ["XDG_CACHE_HOME"] = os.path.join(_sandbox, "cache")
    os.environ["XDG_STATE_HOME"] = os.path.join(_sandbox, "state")


    os.environ["HELYSOFER_HOME"] = os.path.join(_sandbox, "home")

def main():
    """Runs the test suite and returns the process exit code.

    THE `if __name__ == "__main__"` GUARD IS REQUIRED -- it is not decoration.
    On Windows `multiprocessing` defaults to `spawn`, and every child process
    RE-IMPORTS THE MAIN MODULE. Without the guard, every test that opens a
    child process (tests/test_single_instance.py) ran the whole 599-test suite
    AGAIN inside that child. That is why "Ran 599 tests" appeared THREE TIMES
    in the Windows CI log; the child processes also failed to finish in time,
    so the single-instance tests failed with "process still alive".
    """
    loader = unittest.TestLoader()
    suite = loader.discover("tests")
    runner = unittest.TextTestRunner(verbosity=2, stream=_REAL_STDERR)
    result = runner.run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":


    multiprocessing.freeze_support()
    sys.exit(main())
