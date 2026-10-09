"""The interface language: English as written, or Turkish.

Interface text is written in English where it is used and looked up here on
its way to the screen:

  * `say("Saved {0}.", name)` for text built in the controllers,
  * `qsTr("...")` in QML, which reaches the same table through `Translator`.

Text the services produce is a different matter. It is written in Turkish and
has an English entry in `ui.i18n`; `tr` gives the English entry, or the text
as it is when the interface is Turkish.

A value handed to a template is never looked up again, so a user's own text
(an account called "Settings") can not be mistaken for interface text.
"""

from __future__ import annotations

import locale
import os

from PySide6.QtCore import QTranslator

from ui import i18n

ENGLISH, TURKISH = "en", "tr"
LANGUAGES = ((ENGLISH, "English"), (TURKISH, "Türkçe"))
OVERRIDE_ENV = "HELYSOFER_LANGUAGE"

_current = ENGLISH


def system_language() -> str:
    """Turkish on a computer set to Turkish, English everywhere else."""
    forced = os.environ.get(OVERRIDE_ENV, "").strip().lower()
    if forced in (ENGLISH, TURKISH):
        return forced
    try:
        name = locale.getlocale()[0] or ""
    except (ValueError, TypeError):
        name = ""
    return TURKISH if name.lower().startswith(("tr", "turkish")) else ENGLISH


def set_language(code: str) -> str:
    """Sets the language of the interface and of the services' own messages."""
    global _current
    _current = code if code in (ENGLISH, TURKISH) else ENGLISH
    i18n.show_source(_current == TURKISH)
    return _current


def language() -> str:
    return _current


def turkish() -> bool:
    return _current == TURKISH


def say(text: str, *values) -> str:
    """Interface text in the current language, with `{0}`, `{1}` filled in.

    The values go in after the lookup and are never looked up themselves.
    """
    if _current == TURKISH:
        from app.turkish import TEXT

        text = TEXT.get(text, text)
    return text.format(*values) if values else text


_MONTHS = {
    ENGLISH: ("January", "February", "March", "April", "May", "June", "July", "August",
              "September", "October", "November", "December"),
    TURKISH: ("Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos",
              "Eylül", "Ekim", "Kasım", "Aralık"),
}
_SHORT_MONTHS = {
    ENGLISH: ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"),
    TURKISH: ("Oca", "Şub", "Mar", "Nis", "May", "Haz", "Tem", "Ağu", "Eyl", "Eki", "Kas", "Ara"),
}


def month_name(month: int) -> str:
    """The name of month 1-12. Kept apart from `say`: English "May" is both
    a full name and an abbreviation, and Turkish tells the two apart."""
    return _MONTHS[_current][month - 1]


def month_short(month: int) -> str:
    return _SHORT_MONTHS[_current][month - 1]


def percent(value: float, digits: int = 0, signed: bool = False) -> str:
    """A percentage as each language writes it: "5,9 %" or "%5,9".

    With `signed` the sign leads in both: "+5,9 %" and "+%5,9".
    """
    number = f"{abs(value):.{digits}f}".replace(".", ",")
    sign = ("−" if value < 0 else "+") if signed else ("−" if value < 0 else "")
    return f"{sign}%{number}" if _current == TURKISH else f"{sign}{number} %"


def later(text: str) -> str:
    """Marks text that is kept in a table and passed to `say` where it is shown.

    It returns the text unchanged. Tables are built once, when a module is
    loaded; what they hold must stay in English until the moment of use, or
    the language chosen later would never reach it.
    """
    return text


def tr(text):
    """A service's Turkish text as the interface shows it."""
    return i18n.tr(text)


def known_to_services(text: str) -> bool:
    """True for text the services wrote, as opposed to something unexpected."""
    return text in i18n.EN


class Translator(QTranslator):
    """Gives QML's `qsTr` the same table `say` uses."""

    def isEmpty(self) -> bool:  # noqa: N802 -- Qt's name
        return False

    def translate(self, context, source, disambiguation=None, n=-1) -> str:
        return say(source) if source else ""
