"""The check a packaged build runs on itself also passes from source."""

import os
import subprocess
import sys
import tempfile
import unittest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class PackageCheckTest(unittest.TestCase):
    def test_every_feature_loaded_on_first_use_works(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as home:
            done = subprocess.run(
                [sys.executable, "-m", "app", "--check-package"],
                cwd=PROJECT_ROOT, env=dict(os.environ, HELYOSFER_HOME=home),
                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                timeout=180, check=False,
            )
            said = done.stderr.decode("utf-8", "replace")
            self.assertEqual(done.returncode, 0, said)
            self.assertIn("all checks passed", said)
            # The check works on its own throwaway files, not on the profile.
            self.assertEqual(os.listdir(home), [])

    def test_the_check_never_opens_the_interface(self):
        import importlib

        entry = importlib.import_module("app.__main__")
        self.assertEqual(entry.PACKAGE_CHECK_FLAG, "--check-package")


if __name__ == "__main__":
    unittest.main()
