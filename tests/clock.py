"""A clock the tests can move.

The application reads the time through `datetime.now()` and `date.today()`
in many places. Inside `Clock`, every one of them answers with the moment the
test chose, so weeks of use can be played through in a second.

SQLite's own `date('now')` is not moved. Only a few read-only views use it;
a test that ends its run on the real day sees them agree with the rest.
"""

from __future__ import annotations

import datetime as _real
import sys
import types


# The application's own packages; nothing outside them is given the stand-ins.
_APPLICATION = ("app", "database", "services", "ui", "utils")


class _Stands(type):
    """Lets real dates count as instances of the stand-in classes."""

    def __instancecheck__(cls, obj):
        return isinstance(obj, cls._original)

    def __subclasscheck__(cls, other):
        return issubclass(other, cls._original)


class Clock:
    def __init__(self, start: _real.datetime):
        self.now = start
        clock = self

        class Date(_real.date, metaclass=_Stands):
            _original = _real.date

            # Whatever is built through the stand-in is a plain date, so it
            # behaves as one everywhere, the database driver included.
            def __new__(cls, *args, **kwargs):
                return _real.date(*args, **kwargs)

            @classmethod
            def today(cls):
                return clock.now.date()

        class DateTime(_real.datetime, metaclass=_Stands):
            _original = _real.datetime

            def __new__(cls, *args, **kwargs):
                return _real.datetime(*args, **kwargs)

            @classmethod
            def now(cls, tz=None):
                return clock.now if tz is None else clock.now.astimezone(tz)

            @classmethod
            def today(cls):
                return clock.now

            @classmethod
            def utcnow(cls):
                return clock.now.astimezone(_real.timezone.utc).replace(tzinfo=None)

        module = types.ModuleType("datetime")
        module.__dict__.update(_real.__dict__)
        module.date, module.datetime = Date, DateTime
        self._stand_ins = {_real: module, _real.date: Date, _real.datetime: DateTime}
        self._originals = {id(stand_in): original for original, stand_in in self._stand_ins.items()}

    # -- moving ----------------------------------------------------------------
    def move_to(self, moment) -> None:
        if not isinstance(moment, _real.datetime):
            moment = _real.datetime.combine(moment, self.now.time())
        self.now = moment

    def advance(self, days: int = 1) -> None:
        self.now += _real.timedelta(days=days)

    @property
    def today(self) -> _real.date:
        return self.now.date()

    # -- installing --------------------------------------------------------------
    @staticmethod
    def _swap(table, everywhere: bool) -> None:
        for name, module in list(sys.modules.items()):
            if module is None or name == __name__ or name == "datetime":
                continue
            if not everywhere and name.split(".")[0] not in _APPLICATION:
                continue
            namespace = getattr(module, "__dict__", None)
            if not isinstance(namespace, dict):
                continue
            for key, value in list(namespace.items()):
                try:
                    replacement = table(value)
                except TypeError:
                    continue
                if replacement is not None:
                    namespace[key] = replacement

    def __enter__(self):
        by_identity = {id(original): stand_in for original, stand_in in self._stand_ins.items()}
        self._swap(lambda value: by_identity.get(id(value)), everywhere=False)
        sys.modules["datetime"] = self._stand_ins[_real]
        return self

    def __exit__(self, *_exc):
        sys.modules["datetime"] = _real
        # Modules first imported while the clock was in place took the
        # stand-ins too; the sweep covers them as well.
        self._swap(lambda value: self._originals.get(id(value)), everywhere=True)
        return False
