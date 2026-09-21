#!/usr/bin/env bash
set -euo pipefail

rules_file="chapters/ch08/dashboard_rules.yml"

promtool check rules "$rules_file"

python - <<'PY'
from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

import yaml

queries_path = Path("chapters/ch08/dashboard_queries.promql")
expressions = [
    line.strip()
    for line in queries_path.read_text(encoding="utf-8").splitlines()
    if line.strip() and not line.strip().startswith("#")
]

for index, expr in enumerate(expressions):
    rule_doc = {
        "groups": [
            {
                "name": "parse_dashboard_queries",
                "rules": [{"record": f"dashboard_expr_{index}", "expr": expr}],
            }
        ]
    }
    with tempfile.NamedTemporaryFile("w", suffix=".yml", delete=False, encoding="utf-8") as tmp:
        yaml.safe_dump(rule_doc, tmp)
        tmp_path = Path(tmp.name)
    try:
        subprocess.run(["promtool", "check", "rules", str(tmp_path)], check=True)
    finally:
        tmp_path.unlink(missing_ok=True)
PY
