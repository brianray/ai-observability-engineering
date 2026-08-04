"""Report rendering: terminal, JSON, and a self-contained HTML file."""

from __future__ import annotations

import html
import json
from datetime import datetime, timezone

from chapters.registry import CHAPTER_TITLES, PART_FOR_CHAPTER

from .runner import SimulationReport

GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
DIM = "\033[2m"
BOLD = "\033[1m"
RESET = "\033[0m"

_STATUS_COLOR = {"PASS": GREEN, "VIOLATION": YELLOW, "ERROR": RED}


def render_terminal(report: SimulationReport, color: bool = True, verbose: bool = False) -> str:
    def c(text: str, code: str) -> str:
        return f"{code}{text}{RESET}" if color else text

    lines: list[str] = []
    lines.append(c("AI Observability Engineering: example simulation", BOLD))
    lines.append("")

    for chapter, outcomes in report.by_chapter().items():
        lines.append(
            c(f"Chapter {chapter:02d}  {CHAPTER_TITLES[chapter]}", BOLD)
            + c(f"   [{PART_FOR_CHAPTER[chapter]}]", DIM)
        )
        for outcome in outcomes:
            marker = {"PASS": "PASS", "VIOLATION": "WARN", "ERROR": "FAIL"}[outcome.status]
            listing = f"Listing {outcome.spec.listing}" if outcome.spec.listing else "-"
            lines.append(
                "  "
                + c(f"{marker:<5}", _STATUS_COLOR[outcome.status])
                + f"{outcome.spec.key:<34}"
                + c(f"{listing:<14}", DIM)
                + f"{len(outcome.result.spans):>3} spans"
                + f"{outcome.result.total_tokens:>8} tok"
                + f"  ${outcome.result.total_cost_usd:>9.6f}"
                + c(f"{outcome.duration_ms:>9.1f} ms", DIM)
            )
            for violation in outcome.result.violations:
                lines.append("        " + c(violation, YELLOW))
            if outcome.result.error is not None:
                lines.append("        " + c(f"{type(outcome.result.error).__name__}: {outcome.result.error}", RED))
                if verbose and outcome.traceback_text:
                    for tb_line in outcome.traceback_text.rstrip().splitlines():
                        lines.append("        " + c(tb_line, DIM))
        lines.append("")

    lines.append(c("Pillar coverage (declared / observed on spans)", BOLD))
    for pillar, counts in report.pillar_coverage().items():
        flag = "" if counts["observed"] else c("   no spans tagged", YELLOW)
        lines.append(f"  {pillar:<18}{counts['declared']:>3} / {counts['observed']:<3}{flag}")
    lines.append("")

    lines.append(c("Layer coverage (declared / observed on spans)", BOLD))
    for layer, counts in report.layer_coverage().items():
        flag = "" if counts["observed"] else c("   no spans tagged", YELLOW)
        lines.append(f"  {layer:<32}{counts['declared']:>3} / {counts['observed']:<3}{flag}")
    lines.append("")

    summary = (
        f"{report.passed}/{report.total} examples passed  |  "
        f"{report.total_spans} spans ({report.total_llm_spans} LLM)  |  "
        f"{report.total_tokens} tokens  |  "
        f"${report.total_cost_usd:.6f} simulated  |  "
        f"{report.duration_ms:.0f} ms"
    )
    lines.append(c(summary, GREEN if report.ok else RED))
    return "\n".join(lines)


def render_json(report: SimulationReport, indent: int = 2) -> str:
    payload = report.to_dict()
    payload["generated_at"] = datetime.now(timezone.utc).isoformat()
    return json.dumps(payload, indent=indent, sort_keys=False)


_HTML_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AI Observability Engineering: simulation report</title>
<style>
  :root {{
    --bg: #0f1115; --panel: #171a21; --line: #262b36;
    --text: #e6e9ef; --muted: #8b93a3;
    --pass: #4ade80; --warn: #fbbf24; --fail: #f87171; --accent: #7dd3fc;
  }}
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; background: var(--bg); color: var(--text);
         font: 14px/1.55 ui-monospace, SFMono-Regular, Menlo, monospace; }}
  .wrap {{ max-width: 1080px; margin: 0 auto; padding: 40px 24px 80px; }}
  h1 {{ font-size: 20px; letter-spacing: -0.01em; margin: 0 0 4px; }}
  .sub {{ color: var(--muted); margin-bottom: 28px; }}
  .cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 12px; margin-bottom: 32px; }}
  .card {{ background: var(--panel); border: 1px solid var(--line);
           border-radius: 6px; padding: 14px 16px; }}
  .card .n {{ font-size: 22px; }}
  .card .l {{ color: var(--muted); font-size: 12px; text-transform: uppercase;
              letter-spacing: 0.08em; }}
  h2 {{ font-size: 13px; text-transform: uppercase; letter-spacing: 0.1em;
        color: var(--muted); margin: 32px 0 10px; font-weight: 500; }}
  table {{ width: 100%; border-collapse: collapse; }}
  th {{ text-align: left; color: var(--muted); font-weight: 500;
        border-bottom: 1px solid var(--line); padding: 6px 8px; font-size: 12px; }}
  td {{ padding: 6px 8px; border-bottom: 1px solid var(--line); vertical-align: top; }}
  tr.chapter td {{ background: #12151b; color: var(--accent); padding-top: 14px; }}
  .num {{ text-align: right; }}
  .PASS {{ color: var(--pass); }} .VIOLATION {{ color: var(--warn); }}
  .ERROR {{ color: var(--fail); }}
  .msg {{ color: var(--warn); font-size: 12px; padding-left: 8px; }}
  .bar {{ height: 6px; background: var(--line); border-radius: 3px; overflow: hidden; }}
  .bar > i {{ display: block; height: 100%; background: var(--accent); }}
  footer {{ color: var(--muted); margin-top: 40px; font-size: 12px; }}
</style>
</head>
<body><div class="wrap">
<h1>AI Observability Engineering</h1>
<div class="sub">Example simulation report &middot; generated {generated}</div>
<div class="cards">{cards}</div>
<h2>Examples</h2>
<table><thead><tr>
<th>Status</th><th>Example</th><th>Listing</th>
<th class="num">Spans</th><th class="num">Tokens</th>
<th class="num">Cost</th><th class="num">Time</th>
</tr></thead><tbody>{rows}</tbody></table>
<h2>Pillar coverage</h2><table><tbody>{pillars}</tbody></table>
<h2>Layer coverage</h2><table><tbody>{layers}</tbody></table>
<footer>Companion repository for <em>AI Observability Engineering: Operating
Intelligent Systems in Production</em>. All figures are simulated against the
offline mock provider; no model API was called.</footer>
</div></body></html>
"""


def _card(label: str, value: str) -> str:
    return f'<div class="card"><div class="n">{html.escape(value)}</div>' \
           f'<div class="l">{html.escape(label)}</div></div>'


def _coverage_rows(coverage: dict[str, dict[str, int]]) -> str:
    if not coverage:
        return ""
    peak = max(max(c["declared"], c["observed"]) for c in coverage.values()) or 1
    rows = []
    for name, counts in coverage.items():
        width = int(100 * counts["observed"] / peak)
        note = "" if counts["observed"] else " &middot; no spans tagged"
        rows.append(
            f'<tr><td>{html.escape(name)}</td>'
            f'<td style="width:55%"><div class="bar"><i style="width:{width}%"></i></div></td>'
            f'<td class="num">{counts["declared"]} declared / {counts["observed"]} observed{note}</td></tr>'
        )
    return "".join(rows)


def render_html(report: SimulationReport) -> str:
    data = report.to_dict()
    cards = "".join(
        [
            _card("examples passed", f"{report.passed}/{report.total}"),
            _card("spans emitted", str(report.total_spans)),
            _card("llm spans", str(report.total_llm_spans)),
            _card("tokens", f"{report.total_tokens:,}"),
            _card("simulated cost", f"${report.total_cost_usd:.4f}"),
            _card("wall time", f"{report.duration_ms:.0f} ms"),
        ]
    )

    rows: list[str] = []
    for chapter, outcomes in report.by_chapter().items():
        rows.append(
            f'<tr class="chapter"><td colspan="7">Chapter {chapter:02d} &middot; '
            f"{html.escape(CHAPTER_TITLES[chapter])}</td></tr>"
        )
        for o in outcomes:
            listing = o.spec.listing or "&mdash;"
            rows.append(
                f'<tr><td class="{o.status}">{o.status}</td>'
                f"<td>{html.escape(o.spec.title)}<br>"
                f'<span style="color:var(--muted)">{html.escape(o.spec.id)}</span></td>'
                f"<td>{listing}</td>"
                f'<td class="num">{len(o.result.spans)}</td>'
                f'<td class="num">{o.result.total_tokens}</td>'
                f'<td class="num">${o.result.total_cost_usd:.6f}</td>'
                f'<td class="num">{o.duration_ms:.1f} ms</td></tr>'
            )
            for violation in o.result.violations:
                rows.append(f'<tr><td></td><td colspan="6" class="msg">{html.escape(violation)}</td></tr>')
            if o.result.error is not None:
                rows.append(
                    f'<tr><td></td><td colspan="6" class="msg ERROR">'
                    f"{html.escape(type(o.result.error).__name__)}: "
                    f"{html.escape(str(o.result.error))}</td></tr>"
                )

    return _HTML_TEMPLATE.format(
        generated=html.escape(data["generated_at"] if "generated_at" in data else datetime.now(timezone.utc).isoformat()),
        cards=cards,
        rows="".join(rows),
        pillars=_coverage_rows(report.pillar_coverage()),
        layers=_coverage_rows(report.layer_coverage()),
    )
