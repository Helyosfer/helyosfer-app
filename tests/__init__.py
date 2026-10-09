"""Keeps the tests away from the profile of whoever runs them.

`run_tests.py` gives the whole suite a profile of its own. A module run on
its own (`python -m unittest tests.test_app_interface`) had none: it wrote
its log, its interface cache and an encryption key into the real profile
folder, next to the records of the person running it.
"""

import atexit
import os
import shutil
import tempfile

if not os.environ.get("HELYOSFER_HOME"):
    _home = tempfile.mkdtemp(prefix="helyosfer-tests-")
    os.environ["HELYOSFER_HOME"] = _home
    atexit.register(shutil.rmtree, _home, ignore_errors=True)

# Tests read interface text in English, whatever the computer is set to.
os.environ.setdefault("HELYOSFER_LANGUAGE", "en")
