import io
import re
import tokenize
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTACT_EMAIL = "cakirgozmehmetc@proton.me"


def _tracked_source_files():
    excluded = {".git", ".venv", "venv", "build", "dist", "__pycache__"}
    for path in ROOT.rglob("*"):
        if not path.is_file() or excluded.intersection(path.parts):
            continue
        if path.suffix.lower() in {
            ".py", ".md", ".qml", ".yml", ".yaml",
            ".toml", ".txt", ".json",
        } or path.name in {".gitignore", "LICENSE"}:
            yield path


class RepositoryPrivacyTest(unittest.TestCase):
    def test_personal_identity_and_developer_home_paths_are_absent(self):
        forbidden = (
            re.compile("mehmet\\s+cem\\s+" + "çakırgöz", re.IGNORECASE),
            re.compile("mehmet\\s+cem\\s+" + "cakirg[oö]z", re.IGNORECASE),
            re.compile("ck" + "rgz", re.IGNORECASE),
            re.compile(r"/home/c" + r"em(?:/|\\)", re.IGNORECASE),
        )
        findings = []
        for path in _tracked_source_files():
            text = path.read_text(encoding="utf-8", errors="replace")
            for pattern in forbidden:
                if pattern.search(text):
                    findings.append(str(path.relative_to(ROOT)))
                    break
        self.assertEqual(findings, [])

    def test_local_agent_configuration_is_not_part_of_the_repository(self):
        self.assertFalse((ROOT / ".claude" / "settings.local.json").exists())
        ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertIn(".claude/", ignore)



    def test_source_comments_do_not_contain_turkish_characters(self):
        turkish_characters = frozenset("çÇğĞıİöÖşŞüÜ")
        findings = []
        for path in _tracked_source_files():
            if path.suffix.lower() not in {
                ".py", ".qml", ".yml", ".yaml"
            } and path.name not in {".gitignore"}:
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            if path.suffix.lower() == ".py":
                try:
                    tokens = tokenize.generate_tokens(io.StringIO(text).readline)
                    for token in tokens:
                        if token.type == tokenize.COMMENT and (
                            turkish_characters.intersection(token.string)
                        ):
                            findings.append(
                                f"{path.relative_to(ROOT)}:{token.start[0]}"
                            )
                except (tokenize.TokenError, IndentationError):
                    findings.append(f"{path.relative_to(ROOT)}:tokenize")

            marker = "#"
            for number, line in enumerate(text.splitlines(), start=1):
                if line.lstrip().startswith(marker) and (
                    turkish_characters.intersection(line)
                ):
                    finding = f"{path.relative_to(ROOT)}:{number}"
                    if finding not in findings:
                        findings.append(finding)
        self.assertEqual(findings, [])


if __name__ == "__main__":
    unittest.main()
