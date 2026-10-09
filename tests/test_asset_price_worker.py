"""The live price subprocess and the yfinance MultiIndex parsing.

The three root causes diagnosed this round are locked here:
  1. When the subprocess was called from the wrong cwd it died with
     `ModuleNotFoundError: services`; cwd=the project root is now passed and
     the error is NOT SWALLOWED (it is logged).
  2. yfinance 1.4.x returns MultiIndex columns even for a SINGLE symbol; both
     asset_service and price_service took a TypeError from
     `float(DataFrame)` on the single-symbol branch and silently dropped the
     price.

There are no tests needing the network -- the yfinance response is imitated with
a fake DataFrame and the subprocess call is mocked.

"""
import os
import subprocess
import unittest
from unittest import mock

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class SubprocessInvocationTest(unittest.TestCase):
    """The contract of fetch_portfolio_with_prices's subprocess call."""

    def _run_isolated(self, fake_proc):
        """Runs the isolated worker branch with subprocess.run mocked."""
        import services.asset_service as asset_service

        captured = {}

        def fake_run(cmd, **kwargs):
            captured["cmd"] = cmd
            captured["kwargs"] = kwargs
            return fake_proc

        import time
        results = []


        with mock.patch.object(asset_service, "_read_cached_portfolio",
                               return_value=None), \
             mock.patch.object(asset_service, "_store_cached_portfolio"), \
             mock.patch("subprocess.run", side_effect=fake_run):
            asset_service.fetch_portfolio_with_prices(
                [{"id": 1, "asset_code": "THYAO.IS", "asset_type": "Hisse",
                  "quantity": 1, "purchase_price": 1.0, "asset_name": "x"}],
                callback=results.append, force_refresh=True,
            )
            deadline = time.monotonic() + 3
            while not results and time.monotonic() < deadline:
                time.sleep(0.02)
        return captured, results

    def test_subprocess_runs_with_project_root_cwd(self):
        """The cwd must be pinned to the project root (the ModuleNotFoundError root cause)."""
        fake_proc = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="", stderr="")
        captured, _ = self._run_isolated(fake_proc)
        self.assertEqual(captured["kwargs"].get("cwd"), PROJECT_ROOT)

    def test_the_request_is_sent_as_utf8_whatever_the_locale(self):
        """Asset kinds carry non-ASCII letters; a locale-encoded request is
        rejected by a child that reads UTF-8, and every price is lost."""
        fake_proc = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="", stderr="")
        captured, _ = self._run_isolated(fake_proc)
        self.assertEqual(captured["kwargs"].get("encoding"), "utf-8")

    def test_the_worker_reads_its_request_as_utf8(self):
        import io as _io
        import json
        import tempfile

        import services.asset_price_worker as worker

        request = [{"id": 1, "asset_code": "USD", "asset_type": "Döviz",
                    "asset_name": "Altın", "quantity": 1, "purchase_price": 1.0}]
        seen = []

        def fake_fetch(assets, callback):
            seen.append(assets)
            callback(assets)

        stdin = mock.Mock()
        stdin.buffer = _io.BytesIO(json.dumps(request, ensure_ascii=False).encode("utf-8"))
        with tempfile.TemporaryDirectory() as folder:
            output = os.path.join(folder, "out.json")
            with mock.patch.object(sys, "stdin", stdin),                  mock.patch.object(sys, "argv", ["worker", output]),                  mock.patch.dict(os.environ),                  mock.patch("services.asset_service.fetch_portfolio_with_prices", fake_fetch):
                worker.main()
            with open(output, encoding="utf-8") as stream:
                self.assertEqual(json.load(stream), request)
        self.assertEqual(seen, [request])

    def test_from_source_the_interpreter_runs_the_worker_module(self):
        from services.asset_service import price_worker_command

        command, folder = price_worker_command("out.json")
        self.assertEqual(
            command, [sys.executable, "-m", "services.asset_price_worker", "out.json"])
        self.assertEqual(folder, PROJECT_ROOT)

    def test_a_packaged_build_starts_itself_with_the_worker_flag(self):
        from services.asset_service import PRICE_WORKER_FLAG, price_worker_command

        program = os.path.join(PROJECT_ROOT, "dist", "Helyosfer", "Helyosfer.exe")
        with mock.patch.object(sys, "frozen", True, create=True),              mock.patch.object(sys, "executable", program):
            command, folder = price_worker_command("out.json")
        self.assertEqual(command, [program, PRICE_WORKER_FLAG, "out.json"])
        self.assertEqual(folder, os.path.dirname(program))

    def test_the_entry_point_hands_the_flag_to_the_worker_without_the_interface(self):
        import importlib

        import services.asset_price_worker as worker
        from services.asset_service import PRICE_WORKER_FLAG

        entry = importlib.import_module("app.__main__")
        self.assertEqual(entry.PRICE_WORKER_FLAG, PRICE_WORKER_FLAG)
        seen = []
        loaded_before = "app.main" in sys.modules
        with mock.patch.object(sys, "argv", ["Helyosfer.exe", PRICE_WORKER_FLAG, "out.json"]),              mock.patch.object(worker, "main", lambda: seen.append(list(sys.argv))):
            self.assertEqual(entry.main(), 0)
        self.assertEqual(seen, [["Helyosfer.exe", "out.json"]])
        self.assertEqual("app.main" in sys.modules, loaded_before)

    def test_subprocess_captures_streams_not_devnull(self):
        """stderr must be visible: PIPE, not DEVNULL."""
        fake_proc = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="", stderr="")
        captured, _ = self._run_isolated(fake_proc)
        self.assertEqual(captured["kwargs"].get("stderr"), subprocess.PIPE)
        self.assertEqual(captured["kwargs"].get("stdout"), subprocess.PIPE)

    def test_nonzero_exit_is_logged_not_swallowed(self):
        """If the subprocess crashes, stderr must be written to the PERSISTENT log.

        This test used to watch `builtins.print`. But the packaged Windows
        application has no console, so
        print output goes nowhere -- saying "it was logged" meant, in practice,
        "it was lost" there. We now verify that it is written to the real
        rotating logger; that file is the only evidence the user can send.
        """
        fake_proc = subprocess.CompletedProcess(
            args=[], returncode=1, stdout="",
            stderr="ModuleNotFoundError: No module named 'services'")
        fake_logger = mock.Mock()
        with mock.patch("utils.logging_config.get_logger",
                        return_value=fake_logger):
            self._run_isolated(fake_proc)

        logged = " ".join(
            str(part)
            for call in fake_logger.error.call_args_list
            for part in call.args
        )
        self.assertIn("ModuleNotFoundError", logged)


class MultiIndexCloseTest(unittest.TestCase):
    """A single-symbol MultiIndex must be read correctly on both price paths."""

    def _single_ticker_frame(self):
        """Imitates the MultiIndex yfinance 1.4.x returns for a SINGLE symbol."""
        import pandas as pd
        columns = pd.MultiIndex.from_tuples(
            [("Close", "THYAO.IS"), ("Open", "THYAO.IS")])
        return pd.DataFrame([[310.0, 300.0], [312.0, 311.0]], columns=columns)

    def test_price_service_reads_single_ticker_multiindex(self):
        from services.price_service import _extract_last_close
        frame = self._single_ticker_frame()

        self.assertEqual(
            _extract_last_close(frame, "THYAO.IS", True), 312.0)

    def test_price_service_download_single_ticker(self):
        import services.price_service as price_service
        frame = self._single_ticker_frame()
        with mock.patch("yfinance.download", return_value=frame):
            self.assertEqual(
                price_service._download_batch(["THYAO.IS"]), {"THYAO.IS": 312.0})

    def test_flat_series_still_works(self):
        """The old yfinance's flat Close must still be readable (a regression)."""
        import pandas as pd
        from services.price_service import _extract_last_close
        flat = pd.DataFrame({"Close": [310.0, 312.0]})
        self.assertEqual(_extract_last_close(flat, "THYAO.IS", True), 312.0)


if __name__ == "__main__":
    unittest.main()
