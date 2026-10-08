"""The permanent gate forbidding DYNAMIC text being handed to the translation functions.

WHY IT EXISTS: the defect was not a single wrong line but a HABIT -- the caller
built the f-string first and then handed it to the translation. Because `tr()`
has stopped replacing substrings, user data is no longer corrupted; but if
dynamic text keeps being handed to the translation, the sentence stays SILENTLY
untranslated (text with no exact entry in the dictionary falls back to the
source). Both defects come from the same root: parameters being embedded into
the text BEFORE the translation.

This suite pins three things at once:

  1. the results of `_t(f"...")`, `translate(f"...")`, `app.tr(f"...")`,
     `"a" + b` and `"%s" % x` MAY NOT be handed to the translation functions,
  2. EVERY `trf` template in the code base exists in the EN dictionary and the
     two languages' placeholder SETS are identical,
  3. every template really renders (no missing or extra parameter).

The exemption list is NARROW and JUSTIFIED; there is no "for now" exemption --
the right solution for a dynamic call is to move to a parameterised helper.

"""

import ast
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SKIP_DIRS = {".venv", "venv", "build", "dist", ".git", "AppDir", "__pycache__",
             ".mypy_cache", ".hypothesis", "node_modules"}


TRANSLATION_NAMES = {"tr", "translate", "_t"}
TRANSLATION_ATTRS = {"tr", "translate"}


TEMPLATE_HELPERS = {"trf", "_tf", "translate_format"}


ALLOWLIST = {

    "tests/test_i18n_static_gate.py",

    "tests/test_i18n.py",
    "tests/test_i18n_user_data.py",
    "tests/test_chart_localization.py",
}


def python_files():
    for path in sorted(PROJECT_ROOT.rglob("*.py")):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        yield path


def relative(path):
    return str(path.relative_to(PROJECT_ROOT)).replace("\\", "/")


def is_translation_call(node):
    func = node.func
    if isinstance(func, ast.Name):
        return func.id in TRANSLATION_NAMES
    if isinstance(func, ast.Attribute):
        return func.attr in TRANSLATION_ATTRS
    return False


def is_template_helper(node):
    func = node.func
    if isinstance(func, ast.Name):
        return func.id in TEMPLATE_HELPERS
    if isinstance(func, ast.Attribute):
        return func.attr in TEMPLATE_HELPERS
    return False


def dynamic_kind(argument):
    """Returns the reason if the argument is NOT "a constant string at compile time"."""
    if isinstance(argument, ast.JoinedStr):
        return "f-string"
    if isinstance(argument, ast.BinOp):
        if isinstance(argument.op, ast.Add):
            return "string birleştirme"
        if isinstance(argument.op, ast.Mod):
            return "%-formatlama"
        return "aritmetik ifade"
    if isinstance(argument, ast.Call):
        func = argument.func
        if isinstance(func, ast.Attribute) and func.attr in ("format", "join"):
            return f"str.{func.attr}()"
    return None


def controlled_sources_in_expression(node, declared):
    """The declared controlled sources READ (in a Load context) in the expression.

    The `Store` context is deliberately excluded: `_DEAD = 1` is a definition,
    not a USE. The old measurement did not separate these, and a name that was
    only assigned could show itself as live.
    """
    found = set()
    for sub in ast.walk(node):
        if isinstance(sub, ast.Name) and isinstance(sub.ctx, ast.Load):
            identifier = sub.id
        elif isinstance(sub, ast.Attribute) and isinstance(sub.ctx, ast.Load):
            identifier = sub.attr
        else:
            continue
        if identifier in declared:
            found.add(identifier)
    return found


def controlled_sources_in_template_parameters(tree, declared):
    """ONLY those appearing in `trf`/`_tf`/`translate_format` KEYWORD expressions.

    The contract's claim is NOT "this name appears somewhere in the code base"
    but "this name enters a template parameter and the gate therefore protects
    it". The measurement is limited to template calls for that reason.

    This narrowing closes two old holes at once:
      * the contract's OWN DEFINITION is now naturally excluded -- a `frozenset`
        literal is not a template parameter, and because the entries are string
        constants they produce no `Name`/`Attribute` either,
      * comments, docstrings and string literals are not identifiers in the
        AST.
    """
    found = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not is_template_helper(node):
            continue
        for keyword in node.keywords:
            found |= controlled_sources_in_expression(keyword.value, declared)
    return found


def unused_label_sources(names):
    """Sources declared and never seen IN A TEMPLATE PARAMETER.

    `declared - sources_seen_in_template_parameters`.
    """
    declared = set(names)
    seen = set()
    for path in python_files():
        if relative(path).startswith("tests/"):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        seen |= controlled_sources_in_template_parameters(tree, declared)
    return sorted(declared - seen)


class NoDynamicTextReachesTheTranslatorTest(unittest.TestCase):
    def test_no_dynamic_expression_is_passed_to_a_translation_function(self):
        offenders = []
        for path in python_files():
            name = relative(path)
            if name in ALLOWLIST:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call) or not node.args:
                    continue
                if not is_translation_call(node):
                    continue
                kind = dynamic_kind(node.args[0])
                if kind:
                    offenders.append(f"{name}:{node.lineno} — {kind}")

        self.assertEqual(
            offenders, [],
            "Çeviri fonksiyonuna dinamik metin veriliyor. Doğru çözüm "
            "muafiyet değil, parametreli yardımcıdır:\n"
            "    _tf(\"{name} aboneliği durduruldu.\", name=payment['name'])\n"
            + "\n".join(offenders),
        )

    def test_template_helpers_only_receive_constant_templates(self):
        """`trf`'s TEMPLATE must be constant too -- otherwise it cannot be looked up in the dictionary."""
        offenders = []
        for path in python_files():
            name = relative(path)
            if name in ALLOWLIST:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call) or not node.args:
                    continue
                if not is_template_helper(node):
                    continue
                template = node.args[0]
                if not (isinstance(template, ast.Constant)
                        and isinstance(template.value, str)):
                    offenders.append(f"{name}:{node.lineno}")
        self.assertEqual(offenders, [])

    def test_the_gate_actually_catches_the_forbidden_shapes(self):
        """Does the gate HAVE TEETH -- are the forbidden patterns really caught?"""
        samples = {
            'f-string': 'toast(_t(f"{name} eklendi"))',
            'string birleştirme': 'toast(_t("Hata: " + detail))',
            '%-formatlama': 'toast(_t("Hata: %s" % detail))',
            'str.format()': 'toast(_t("Hata: {}".format(detail)))',
        }
        for expected, source in samples.items():
            with self.subTest(shape=expected):
                tree = ast.parse(source)
                calls = [
                    node for node in ast.walk(tree)
                    if isinstance(node, ast.Call) and is_translation_call(node)
                ]
                self.assertEqual(len(calls), 1, source)
                self.assertEqual(dynamic_kind(calls[0].args[0]), expected)

    def test_a_static_call_is_not_flagged(self):
        tree = ast.parse('toast(_t("Hesap eklendi."))')
        call = next(
            node for node in ast.walk(tree)
            if isinstance(node, ast.Call) and is_translation_call(node)
        )
        self.assertIsNone(dynamic_kind(call.args[0]))


def collect_templates():
    """Every `trf` template in the code base and where it is used."""
    templates = {}
    for path in python_files():
        name = relative(path)
        if name in ALLOWLIST:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not node.args:
                continue
            if not is_template_helper(node):
                continue
            template = node.args[0]
            if isinstance(template, ast.Constant) and isinstance(template.value, str):
                templates.setdefault(template.value, []).append(
                    f"{name}:{node.lineno}"
                )
    return templates


class ControlledValuesReachTheTranslatorTest(unittest.TestCase):
    """A controlled Turkish label may not enter a template RAW.

    THE MEASURED DEFECT: the `trf()` contract was right, but the production
    calls handed the enum value raw -- "Select Type: Hisse", "Add New Altın",
    "Gold Type: Gram Altın", "Type: Döviz".

    AUTOMATIC CLASSIFICATION IS NOT RELIABLE: whether an expression is user data
    or a label cannot be known without looking at the source. So the gate DOES
    NOT GUESS but applies AN EXPLICIT CONTRACT: known label SOURCES
    (`ui.i18n.CONTROLLED_LABEL_SOURCES`) have to pass through `tr()` on their
    way into a `trf` parameter. The list is narrow and maintained by hand; it
    produces no false positives because it contains only names that really do
    produce labels.
    """

    def _controlled_source(self, node):
        """Does the expression read from a known LABEL SOURCE?"""
        from ui.i18n import CONTROLLED_LABEL_SOURCES

        names = set()
        for child in ast.walk(node):
            if isinstance(child, ast.Name):
                names.add(child.id)
            elif isinstance(child, ast.Attribute):
                names.add(child.attr)
        hit = names & set(CONTROLLED_LABEL_SOURCES)
        return sorted(hit)[0] if hit else None

    def _is_translated(self, node):
        """Is the expression WRAPPED in a `tr()`/`_t()` call?"""
        if not isinstance(node, ast.Call):
            return False
        func = node.func
        name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
        return name in TRANSLATION_NAMES

    def test_controlled_labels_are_translated_before_substitution(self):
        offenders = []
        for path in python_files():
            name = relative(path)
            if name in ALLOWLIST or name.startswith("tests/"):
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call) or not is_template_helper(node):
                    continue
                for keyword in node.keywords:
                    if self._is_translated(keyword.value):
                        continue
                    source = self._controlled_source(keyword.value)
                    if source:
                        offenders.append(
                            f"{name}:{node.lineno} — {keyword.arg} "
                            f"({source} etiket kaynağı, tr() ile sarılmalı)"
                        )
        self.assertEqual(
            offenders, [],
            "Kontrollü Türkçe etiket şablona HAM giriyor; İngilizce cümlenin "
            "ortasında Türkçe kalır:\n" + "\n".join(offenders),
        )

    def test_the_controlled_source_check_has_teeth(self):
        """Does the gate really catch it -- exercised with the defect itself.

        The example is built with a LIVE source (`asset_type`): exercising it
        with a name not in the contract would be a misleading claim of "teeth",
        because the gate would not see that name anyway.
        """
        broken = ast.parse('_tf("Tür Seç: {t}", t=asset_type)')
        call = next(node for node in ast.walk(broken)
                    if isinstance(node, ast.Call) and is_template_helper(node))
        keyword = call.keywords[0]
        self.assertFalse(self._is_translated(keyword.value))
        self.assertEqual(self._controlled_source(keyword.value), "asset_type")

    def test_a_translated_controlled_source_is_accepted(self):
        fixed = ast.parse('_tf("Tür Seç: {t}", t=_t(asset_type))')
        call = next(node for node in ast.walk(fixed)
                    if isinstance(node, ast.Call) and is_template_helper(node))
        self.assertTrue(self._is_translated(call.keywords[0].value))

    def test_user_data_is_not_flagged_as_a_controlled_label(self):
        """There must be no false positive: a user name is not a label source."""
        tree = ast.parse('_tf("{name} eklendi", name=payment["name"])')
        call = next(node for node in ast.walk(tree)
                    if isinstance(node, ast.Call) and is_template_helper(node))
        self.assertIsNone(self._controlled_source(call.keywords[0].value))


    def test_a_name_that_is_only_assigned_is_not_alive(self):
        """`_DEAD = 1` is a definition, not a USE."""
        tree = ast.parse("_OLU = 1")
        self.assertEqual(
            controlled_sources_in_template_parameters(tree, {"_OLU"}), set()
        )

        assign = tree.body[0]
        self.assertEqual(
            controlled_sources_in_expression(assign.targets[0], {"_OLU"}),
            set(),
        )

    def test_a_read_outside_a_template_parameter_is_not_alive(self):
        """A read outside a template parameter is not live as far as THIS CONTRACT goes."""
        tree = ast.parse("x = _SOURCE_LABELS")
        self.assertEqual(
            controlled_sources_in_template_parameters(
                tree, {"_SOURCE_LABELS"}),
            set(),
        )

    def test_the_dictionary_definition_itself_is_not_alive(self):
        """`_SOURCE_LABELS = {...}` cannot show itself as live."""
        tree = ast.parse('_SOURCE_LABELS = {"a": "b"}')
        self.assertEqual(
            controlled_sources_in_template_parameters(
                tree, {"_SOURCE_LABELS"}),
            set(),
        )

    def test_a_translated_template_parameter_is_alive(self):
        tree = ast.parse('_tf("{x}", x=_t(_SOURCE_LABELS.get(k, k)))')
        self.assertEqual(
            controlled_sources_in_template_parameters(
                tree, {"_SOURCE_LABELS"}),
            {"_SOURCE_LABELS"},
        )

    def test_a_raw_template_parameter_is_alive_but_fails_the_safety_gate(self):
        """Liveness and SAFETY are separate questions.

        A source handed in raw IS LIVE as far as the contract goes (it enters a
        template parameter), but the main gate REFUSES it because it is not
        wrapped in `tr()`. Confusing the two would lead to thinking raw usage is
        "already protected".
        """
        tree = ast.parse('_tf("{x}", x=_SOURCE_LABELS.get(k, k))')

        self.assertEqual(
            controlled_sources_in_template_parameters(
                tree, {"_SOURCE_LABELS"}),
            {"_SOURCE_LABELS"},
        )

        call = next(node for node in ast.walk(tree)
                    if isinstance(node, ast.Call) and is_template_helper(node))
        keyword = call.keywords[0]
        self.assertFalse(self._is_translated(keyword.value))
        self.assertEqual(self._controlled_source(keyword.value),
                         "_SOURCE_LABELS")

    def test_an_attribute_read_inside_a_template_parameter_is_alive(self):
        tree = ast.parse('_tf("{x}", x=_t(self._asset_selected_type))')
        self.assertEqual(
            controlled_sources_in_template_parameters(
                tree, {"_asset_selected_type"}),
            {"_asset_selected_type"},
        )

    def test_a_name_only_in_a_comment_or_string_is_not_alive(self):
        """Yorum, docstring ve string literali KULLANIM SAYILMAZ."""
        source = "\n".join([
            '"""Docstring içinde _SADECE_YORUMDA gecen bir ad."""',
            "# Yorumda da _SADECE_YORUMDA var.",
            'ETIKET = "_SADECE_YORUMDA"',
            '_tf("{x}", x="_SADECE_YORUMDA")',
        ])
        self.assertEqual(
            controlled_sources_in_template_parameters(
                ast.parse(source), {"_SADECE_YORUMDA"}),
            set(),
        )


class TemplateCatalogueTest(unittest.TestCase):
    def test_every_template_has_an_english_entry(self):
        from ui.i18n import EN

        missing = sorted(set(collect_templates()) - set(EN))
        self.assertEqual(
            missing, [],
            "Bu şablonların İngilizce karşılığı yok; kullanıcı İngilizce "
            "arayüzde Türkçe cümle görür:\n" + "\n".join(map(repr, missing)),
        )

    def test_placeholder_sets_match_between_turkish_and_english(self):
        """The placeholder SET must be the same; the ORDER is free.

        A missing placeholder swallows the value silently, while an extra one
        raises `TranslationTemplateError` at render time. Both show the user a
        broken sentence; the gate catches both here.
        """
        from ui.i18n import EN, placeholders

        mismatched = []
        for source, english in EN.items():
            if placeholders(source) != placeholders(english):
                mismatched.append(
                    f"{source!r}: TR={sorted(placeholders(source))} "
                    f"EN={sorted(placeholders(english))}"
                )
        self.assertEqual(mismatched, [], "\n".join(mismatched))

    def test_every_template_renders_in_english(self):
        """Does every template really render (no missing or extra parameter)?

        This makes it impossible to see `trf` raise
        `TranslationTemplateError` for the first time in production: every
        template is exercised here with dummy values.
        """
        from ui.i18n import placeholders, trf

        for template in sorted(collect_templates()):
            params = {name: "X" for name in placeholders(template)}
            for language in ("en",):
                with self.subTest(template=template, language=language):
                    rendered = trf(template, language=language, **params)
                    self.assertNotIn("{", rendered.replace("{X}", ""))

    def test_a_template_placeholder_never_leaks_into_the_output(self):
        from ui.i18n import EN, placeholders, trf

        for source in EN:
            names = placeholders(source)
            if not names:
                continue
            rendered = trf(source, language="en",
                           **{name: f"<{name}>" for name in names})
            for name in names:
                self.assertIn(f"<{name}>", rendered)


class UserDataNeverReachesTheTranslatorTest(unittest.TestCase):
    """A name the USER SUPPLIED may not enter the translation -- at source level.

    A behaviour test cannot catch this on its own: because `tr()` now does an
    exact match, most names come back unchanged anyway. But if the SAME key is
    in the dictionary ("Nakit", "Ayarlar", "Gelir") the name IS still
    translated. So the call itself is forbidden.

    The check is the AST and NOT A TEXT SEARCH: the `_t(acc["name"])` example
    appearing in a docstring (where the defect is explained) produced a false
    positive.
    """

    @property
    def USER_FIELDS(self):
        """The contract's SINGLE source is `ui.i18n.USER_DATA_FIELDS`.

        The test keeping its own copy left the door open for the two lists to
        drift apart silently; the inventory tool reads the same source.
        """
        from ui.i18n import USER_DATA_FIELDS

        return USER_DATA_FIELDS

    def _user_field(self, argument):
        """Does the expression read a user field?"""
        if isinstance(argument, ast.Subscript):
            key = argument.slice
            if isinstance(key, ast.Constant) and key.value in self.USER_FIELDS:
                return str(key.value)
        if isinstance(argument, ast.Call):
            func = argument.func
            if (isinstance(func, ast.Attribute) and func.attr == "get"
                    and argument.args):
                first = argument.args[0]
                if (isinstance(first, ast.Constant)
                        and first.value in self.USER_FIELDS):
                    return str(first.value)
        if isinstance(argument, ast.Attribute):
            if argument.attr in self.USER_FIELDS:
                return argument.attr
        return None

    def test_no_module_translates_a_user_supplied_name(self):
        offenders = []
        for path in python_files():
            name = relative(path)
            if name.startswith("tests/"):
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call) or not node.args:
                    continue
                if not is_translation_call(node):
                    continue
                field = self._user_field(node.args[0])
                if field:
                    offenders.append(f"{name}:{node.lineno} — {field}")
        self.assertEqual(
            offenders, [],
            "Kullanıcının verdiği ad çeviri fonksiyonuna giriyor:\n"
            + "\n".join(offenders),
        )

    def test_the_user_field_check_has_teeth(self):
        tree = ast.parse('label = _t(acc["name"])')
        call = next(node for node in ast.walk(tree)
                    if isinstance(node, ast.Call) and is_translation_call(node))
        self.assertEqual(self._user_field(call.args[0]), "name")

    def test_enum_labels_are_still_allowed(self):
        """A type label is an ENUM: translating it is right and the gate must not block it."""
        tree = ast.parse('label = _t(acc["type_label"])')
        call = next(node for node in ast.walk(tree)
                    if isinstance(node, ast.Call) and is_translation_call(node))
        self.assertIsNone(self._user_field(call.args[0]))


if __name__ == "__main__":
    unittest.main()
