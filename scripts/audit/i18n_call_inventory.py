#!/usr/bin/env python3
"""An AST inventory of the translation calls -- produces a breakdown whose totals ADD UP.

WHY IT EXISTS: in the first, hand-produced version of this inventory the
numbers did not add up (193 found, 90 converted, 68 left -- 35 calls
unaccounted for). The count is now generated from the code and every row goes
into exactly one bucket; the totals close by construction.

CLASSIFICATION HONESTY: parameter classes are separated as far as they can be
separated RELIABLY with the AST. The "undetermined" bucket is NOT CALLED user
data -- it could hold a counter, a date or a user name, and the AST cannot say.
That bucket is the subject of manual/semantic review.

THE UNIVERSE (explicitly defined):
  * PRODUCTION code only: the `.py` files at the repository root, excluding
    `tests/` and `scripts/` (test/tool code does not produce its own defect).
  * What is counted is the CALL: `tr`/`translate`/`_t`/`app.tr` and the
    template helpers `trf`/`_tf`/`translate_format`.
  * A call enters exactly one bucket.

    python scripts/audit/i18n_call_inventory.py            # summary
    python scripts/audit/i18n_call_inventory.py --json     # machine readable

"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SKIP_DIRS = {".venv", "venv", "build", "dist", ".git", "AppDir", "__pycache__",
             ".mypy_cache", ".hypothesis"}

NON_PRODUCTION = ("tests/", "scripts/")

TRANSLATOR_NAMES = {"tr", "translate", "_t"}
TRANSLATOR_ATTRS = {"tr", "translate"}
TEMPLATE_HELPERS = {"trf", "_tf", "translate_format"}


def production_files():
    for path in sorted(PROJECT_ROOT.rglob("*.py")):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        rel = str(path.relative_to(PROJECT_ROOT)).replace("\\", "/")
        if rel.startswith(NON_PRODUCTION):
            continue
        yield rel, path


def _callee(node):
    func = node.func
    if isinstance(func, ast.Name):
        return func.id, "name"
    if isinstance(func, ast.Attribute):
        return func.attr, "attr"
    return None, None


def _is_translator(node):
    name, kind = _callee(node)
    if kind == "name":
        return name in TRANSLATOR_NAMES
    if kind == "attr":
        return name in TRANSLATOR_ATTRS
    return False


def _is_template_helper(node):
    name, _kind = _callee(node)
    return name in TEMPLATE_HELPERS


def _argument_class(argument, source):
    """Which class does the argument of a `tr()` call fall into?"""
    if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
        return "static-key"
    if isinstance(argument, ast.JoinedStr):
        return "dynamic-fstring"
    if isinstance(argument, ast.BinOp):
        return "dynamic-concat"
    return "variable"


def classify(rel, path):
    """Puts every translation call in the file into a single bucket."""
    source = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    rows = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if _is_template_helper(node):
            template = node.args[0] if node.args else None
            rows.append({
                "file": rel,
                "line": node.lineno,
                "callee": "template-helper",
                "bucket": "template-call",
                "params": len(node.keywords),
                "template": (template.value
                             if isinstance(template, ast.Constant) else None),
            })
            continue
        if not _is_translator(node):
            continue
        if not node.args:
            rows.append({"file": rel, "line": node.lineno,
                         "callee": "translator", "bucket": "no-argument"})
            continue
        rows.append({
            "file": rel,
            "line": node.lineno,
            "callee": "translator",
            "bucket": _argument_class(node.args[0], source),
        })
    return rows


def _user_field_name(node):
    """Does the expression read a RECOGNISED user field?

    Only the forms that can be read from the AST WITH CERTAINTY: `x["name"]`,
    `x.get("name")`, `x.name`. Anything else goes to the "undetermined" class --
    we do not guess and call it user data.
    """
    sys.path.insert(0, str(PROJECT_ROOT))
    from ui.i18n import USER_DATA_FIELDS

    if isinstance(node, ast.Subscript):
        key = node.slice
        if isinstance(key, ast.Constant) and key.value in USER_DATA_FIELDS:
            return str(key.value)
    if isinstance(node, ast.Call):
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr == "get" and node.args:
            first = node.args[0]
            if isinstance(first, ast.Constant) and first.value in USER_DATA_FIELDS:
                return str(first.value)
    if isinstance(node, ast.Attribute) and node.attr in USER_DATA_FIELDS:
        return node.attr
    return None


def parameter_rows():
    """The PARAMETERS of the template calls -- a separate universe, a separate total."""
    rows = []
    for rel, path in production_files():
        source = path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not _is_template_helper(node):
                continue
            for keyword in node.keywords:
                expr = ast.get_source_segment(source, keyword.value) or ""
                expr = " ".join(expr.split())
                translated = (isinstance(keyword.value, ast.Call)
                              and _is_translator(keyword.value))
                formatted = expr.startswith(('f"', "f'"))
                user_field = _user_field_name(keyword.value)


                if translated:
                    bucket = "controlled-label-translated"
                elif user_field:
                    bucket = "user-data-field"
                elif formatted:
                    bucket = "formatted-value"
                else:
                    bucket = "undetermined"
                rows.append({
                    "file": rel,
                    "line": node.lineno,
                    "param": keyword.arg,
                    "expr": expr,
                    "user_field": user_field,
                    "bucket": bucket,
                })
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    calls = []
    for rel, path in production_files():
        calls.extend(classify(rel, path))

    params = parameter_rows()
    templates = {row["template"] for row in calls
                 if row["bucket"] == "template-call" and row["template"]}

    buckets = {}
    for row in calls:
        buckets[row["bucket"]] = buckets.get(row["bucket"], 0) + 1
    param_buckets = {}
    for row in params:
        param_buckets[row["bucket"]] = param_buckets.get(row["bucket"], 0) + 1

    report = {
        "universe": "üretim .py dosyaları (tests/ ve scripts/ hariç)",
        "calls_total": len(calls),
        "call_buckets": buckets,
        "template_calls": buckets.get("template-call", 0),
        "unique_templates": len(templates),
        "parameters_total": len(params),
        "parameter_buckets": param_buckets,
    }

    if args.json:
        print(json.dumps({"report": report, "calls": calls,
                          "parameters": params}, ensure_ascii=False, indent=1))
        return 0

    print(f"EVREN: {report['universe']}")
    print(f"TOPLAM ÇEVİRİ ÇAĞRISI: {report['calls_total']}")
    for bucket, count in sorted(buckets.items(), key=lambda item: -item[1]):
        print(f"  {count:5}  {bucket}")
    print(f"  {'-' * 5}")
    print(f"  {sum(buckets.values()):5}  (toplam — kümeler ayrık)")
    print()
    print(f"BENZERSİZ ŞABLON: {report['unique_templates']}")
    print(f"TOPLAM ŞABLON PARAMETRESİ: {report['parameters_total']}")
    labels = {
        "controlled-label-translated":
            "tr() ile çevrilmiş kontrollü etiket   (AST ile ölçüldü)",
        "user-data-field":
            "tanınan kullanıcı alanı              (AST ile ölçüldü)",
        "formatted-value":
            "biçimlenmiş değer (f-string)         (AST ile ölçüldü)",
        "undetermined":
            "semantiği AST'den belirlenemeyen     (elle sınıflandırılır)",
    }
    for bucket, count in sorted(param_buckets.items(), key=lambda i: -i[1]):
        print(f"  {count:5}  {labels.get(bucket, bucket)}")
    print(f"  {'-' * 5}")
    print(f"  {sum(param_buckets.values()):5}  (toplam — kümeler ayrık)")


    leftover = buckets.get("dynamic-fstring", 0) + buckets.get("dynamic-concat", 0)
    if leftover:
        print(f"\n::error::{leftover} dinamik çeviri çağrısı kaldı")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
