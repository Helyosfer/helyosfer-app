import multiprocessing
import tempfile
import unittest
from pathlib import Path

from utils.single_instance import AlreadyRunningError, SingleInstanceLock


def _try_lock(path, queue):
    lock = SingleInstanceLock(path)
    try:
        lock.acquire()
    except AlreadyRunningError:
        queue.put("blocked")
    else:
        queue.put("acquired")
        lock.release()


class SingleInstanceLockTest(unittest.TestCase):
    def _context(self):
        methods = multiprocessing.get_all_start_methods()
        return multiprocessing.get_context(
            "fork" if "fork" in methods else "spawn"
        )

    def test_second_process_cannot_acquire_same_profile(self):
        with tempfile.TemporaryDirectory() as temp:
            path = str(Path(temp) / "instance.lock")
            with SingleInstanceLock(path):
                context = self._context()
                queue = context.Queue()
                process = context.Process(
                    target=_try_lock, args=(path, queue)
                )
                process.start()
                process.join(5)
                self.assertFalse(process.is_alive())
                self.assertEqual(queue.get(timeout=1), "blocked")

    def test_lock_is_recoverable_after_owner_exits(self):
        with tempfile.TemporaryDirectory() as temp:
            path = str(Path(temp) / "instance.lock")
            context = self._context()
            queue = context.Queue()
            process = context.Process(
                target=_try_lock, args=(path, queue)
            )
            process.start()
            process.join(5)
            self.assertEqual(queue.get(timeout=1), "acquired")

            with SingleInstanceLock(path):
                self.assertTrue(Path(path).is_file())

    def test_context_releases_after_exception(self):
        with tempfile.TemporaryDirectory() as temp:
            path = str(Path(temp) / "instance.lock")
            with self.assertRaisesRegex(RuntimeError, "injected"):
                with SingleInstanceLock(path):
                    raise RuntimeError("injected")
            with SingleInstanceLock(path):
                pass


class AlreadyOpenNoticeTest(unittest.TestCase):
    """The notice a second start shows is in the computer's language."""

    def _notice(self, language_code):
        import os
        from unittest import mock

        from app import language, main
        from utils.single_instance import AlreadyRunningError

        shown = []
        before = language.language()
        try:
            with mock.patch.dict(os.environ, {"HELYOSFER_LANGUAGE": language_code}),                     mock.patch("utils.single_instance.SingleInstanceLock.acquire",
                               side_effect=AlreadyRunningError("x")),                     mock.patch("utils.single_instance.notify_already_running", shown.append):
                with self.assertRaises(SystemExit) as stopped:
                    main._acquire_instance_lock()
        finally:
            language.set_language(before)
        self.assertEqual(stopped.exception.code, 2)
        return shown

    def test_it_is_english_on_an_english_computer(self):
        self.assertEqual(self._notice("en"), ["Helyosfer is already open for this user."])

    def test_it_is_turkish_on_a_turkish_computer(self):
        notice = self._notice("tr")
        self.assertEqual(len(notice), 1)
        self.assertIn("zaten", notice[0])
        self.assertNotIn("already", notice[0])


if __name__ == "__main__":
    unittest.main()
