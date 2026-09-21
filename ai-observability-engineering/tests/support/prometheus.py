"""Validation for the book's Prometheus artifacts.

``promtool`` is the real check and CI runs it. It is not always present
on a contributor's machine, and a check that only runs in CI is a check
that fails late. So there are two layers:

``check_rule_document``
    Structural validation in pure Python. Runs everywhere. Catches the
    mistakes that actually happen: a missing ``expr``, an alert with no
    ``for``, a rule group with no name, a duplicated alert name.

``promtool_check``
    The real parser, skipped when the binary is absent.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

import yaml


def promtool() -> str | None:
    return shutil.which("promtool")


def check_rule_document(path: Path) -> dict:
    """Structural checks on a Prometheus rules file. Raises on a problem."""
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(doc, dict) or "groups" not in doc:
        raise AssertionError(f"{path}: no top-level 'groups' key")

    seen: set[str] = set()
    for group in doc["groups"]:
        if not group.get("name"):
            raise AssertionError(f"{path}: a rule group has no name")
        if not group.get("rules"):
            raise AssertionError(f"{path}: group {group.get('name')!r} has no rules")

        for rule in group["rules"]:
            if not rule.get("expr"):
                raise AssertionError(f"{path}: a rule in {group['name']} has no expr")
            if "alert" not in rule and "record" not in rule:
                raise AssertionError(f"{path}: a rule is neither an alert nor a record")

            name = rule.get("alert") or rule["record"]
            if rule.get("alert"):
                # Duplicate alert names silently shadow each other in
                # most UIs, so this is worth failing on.
                if name in seen:
                    raise AssertionError(f"{path}: duplicate alert name {name!r}")
                seen.add(name)
                if not rule.get("for"):
                    raise AssertionError(
                        f"{path}: alert {name!r} has no 'for'. An instantaneous "
                        "alert on a noisy metric is a muted alert."
                    )
                if not rule.get("labels", {}).get("severity"):
                    raise AssertionError(f"{path}: alert {name!r} has no severity label")
                if not rule.get("annotations", {}).get("summary"):
                    raise AssertionError(f"{path}: alert {name!r} has no summary")
    return doc


def promtool_check(path: Path) -> None:
    """Run the real parser. Caller is responsible for skipping if absent."""
    subprocess.run([promtool(), "check", "rules", str(path)], check=True, capture_output=True)


def promtool_check_expressions(expressions: list[str]) -> None:
    """Parse bare PromQL by wrapping each expression in a throwaway rule."""
    for index, expr in enumerate(expressions):
        doc = {
            "groups": [
                {"name": "parse", "rules": [{"record": f"expr_{index}", "expr": expr}]}
            ]
        }
        with tempfile.NamedTemporaryFile("w", suffix=".yml", delete=False, encoding="utf-8") as tmp:
            yaml.safe_dump(doc, tmp)
            tmp_path = Path(tmp.name)
        try:
            promtool_check(tmp_path)
        finally:
            tmp_path.unlink(missing_ok=True)


def load_promql(path: Path) -> list[str]:
    """Non-comment, non-blank lines from a .promql file."""
    return [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
