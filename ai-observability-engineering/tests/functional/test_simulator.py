"""Functional: the simulator itself."""

import json

from simulator.app import main
from simulator.report import render_html, render_json, render_terminal
from simulator.runner import run, select


def test_full_simulation_passes():
    report = run(select())
    assert report.ok, [f"{o.spec.id}: {o.result.violations or o.result.error}" for o in report.failures()]
    assert report.total >= 17
    assert report.total_spans > 0


def test_selection_by_chapter():
    specs = select(chapter=1)
    assert specs and all(s.chapter == 1 for s in specs)


def test_selection_by_pillar():
    specs = select(pillar="risk")
    assert specs and all(s.pillar.value == "risk" for s in specs)


def test_selection_by_example_id():
    specs = select(example_ids=["ch01.traditional_vs_llm_span"])
    assert len(specs) == 1


def test_report_json_round_trips():
    payload = json.loads(render_json(run(select(chapter=1))))
    assert payload["total"] >= 1
    assert "pillar_coverage" in payload
    assert all("status" in e for e in payload["examples"])


def test_report_html_is_self_contained():
    html = render_html(run(select(chapter=1)))
    assert html.startswith("<!doctype html>")
    assert "<script" not in html.lower()
    assert "http://" not in html.replace("http://www.w3.org", "")


def test_terminal_report_mentions_every_chapter_selected():
    text = render_terminal(run(select(chapter=6)), color=False)
    assert "Chapter 06" in text
    assert "Drift Detection" in text


def test_cli_exit_code_is_zero_when_everything_passes(capsys):
    assert main(["run", "--all", "--format", "quiet", "--no-color"]) == 0


def test_cli_returns_two_for_an_empty_selection(capsys):
    assert main(["run", "--example", "does.not.exist"]) == 2


def test_cli_list_and_coverage(capsys):
    assert main(["list"]) == 0
    assert "Chapter 01" in capsys.readouterr().out
    assert main(["coverage"]) == 0
    assert "by_pillar" in capsys.readouterr().out


def test_cli_writes_html_and_json(tmp_path, capsys):
    html_path = tmp_path / "report.html"
    json_path = tmp_path / "report.json"
    code = main(
        [
            "run",
            "--chapter",
            "1",
            "--format",
            "quiet",
            "--html",
            str(html_path),
            "--json-out",
            str(json_path),
        ]
    )
    assert code == 0
    assert html_path.read_text().startswith("<!doctype html>")
    assert json.loads(json_path.read_text())["total"] >= 1


def test_a_broken_example_is_reported_not_raised():
    """The simulator must survive a bad example and name it."""
    from aiobs.pillars import Layer, Pillar
    from chapters.registry import ExampleSpec

    def broken():
        raise RuntimeError("deliberate")

    spec = ExampleSpec(
        chapter=1,
        key="broken",
        title="broken",
        pillar=Pillar.PERFORMANCE,
        layer=Layer.MODEL_AND_INFERENCE,
        func=broken,
    )
    report = run([spec])
    assert not report.ok
    assert report.failures()[0].status == "ERROR"
    assert "deliberate" in report.failures()[0].traceback_text
