"""Small JSON-backed settings store: a flat mapping of record name -> dict.

Holds preferences and the local sign-in record. Financial data never lives
here. Every write replaces the file atomically, so a crash mid-write leaves
the previous file intact instead of a truncated one.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading

from utils.app_paths import data_dir

CONFIG_FILENAME = "helysofer_config.json"


def default_config_path() -> str:
    return os.path.join(data_dir(), CONFIG_FILENAME)


class ConfigStore:
    def __init__(self, path: str | None = None):
        self.path = path or default_config_path()
        self._lock = threading.Lock()
        self._data = self._load()

    def _load(self) -> dict:
        try:
            with open(self.path, encoding="utf-8") as handle:
                data = json.load(handle)
        except FileNotFoundError:
            return {}
        if not isinstance(data, dict):
            raise ValueError("Settings file does not contain a JSON object.")
        return data

    def exists(self, key: str) -> bool:
        with self._lock:
            return key in self._data

    def get(self, key: str, default=None) -> dict:
        with self._lock:
            value = self._data.get(key)
            if value is None:
                return {} if default is None else default
            return dict(value)

    def put(self, key: str, **values) -> None:
        with self._lock:
            self._data[key] = dict(values)
            self._write()

    def delete(self, key: str) -> None:
        with self._lock:
            if self._data.pop(key, None) is not None:
                self._write()

    def _write(self) -> None:
        directory = os.path.dirname(self.path) or "."
        os.makedirs(directory, exist_ok=True)
        fd, staged = tempfile.mkstemp(prefix=".helysofer-config-", dir=directory)
        replaced = False
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(self._data, handle, ensure_ascii=False)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(staged, self.path)
            replaced = True
        finally:
            if not replaced and os.path.exists(staged):
                os.unlink(staged)
