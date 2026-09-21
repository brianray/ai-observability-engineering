"""Chapter 5: the optional local collector + Jaeger stack.

The last repo-sync PR left one item open: an ``otel-collector.yaml``
paired with a ``docker-compose.yml`` that brings the collector up
alongside Jaeger. Both files exist. These tests check they actually do
what the chapter's text promises, rather than merely being present,
because "the file exists" is how a broken quickstart ships.
"""

from __future__ import annotations

from pathlib import Path

import yaml

COMPOSE = Path("docker-compose.yml")
COLLECTOR = Path("config/otel-collector.yaml")


def _compose() -> dict:
    return yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))


def _collector() -> dict:
    return yaml.safe_load(COLLECTOR.read_text(encoding="utf-8"))


def test_compose_brings_up_the_collector_alongside_jaeger():
    services = _compose()["services"]
    assert "jaeger" in services
    assert "otel-collector" in services
    assert "jaeger" in services["otel-collector"].get("depends_on", [])


def test_compose_mounts_the_collector_config_the_repo_ships():
    collector = _compose()["services"]["otel-collector"]
    mounts = [v.split(":")[0] for v in collector["volumes"]]
    assert f"./{COLLECTOR.as_posix()}" in mounts, (
        "the compose file must mount the config the repo actually ships, or "
        "the quickstart runs against a default config"
    )


def test_the_endpoint_the_readme_tells_readers_to_use_is_published():
    """The README's OTEL_EXPORTER_OTLP_ENDPOINT points at 4318."""
    ports = _compose()["services"]["otel-collector"]["ports"]
    published = {p.split(":")[0] for p in ports}
    assert "4318" in published, "OTLP/HTTP must be reachable from the host"
    assert "16686" in {
        p.split(":")[0] for p in _compose()["services"]["jaeger"]["ports"]
    }, "the Jaeger UI port the README tells readers to open"


def test_the_collector_receives_on_the_published_ports():
    protocols = _collector()["receivers"]["otlp"]["protocols"]
    assert protocols["http"]["endpoint"].endswith(":4318")
    assert protocols["grpc"]["endpoint"].endswith(":4317")


def test_both_pipelines_export_somewhere_reachable_in_the_compose_stack():
    """A pipeline pointing at a host the compose file does not define
    produces a collector that starts, accepts spans, and drops them."""
    collector = _collector()
    exporters = collector["exporters"]
    service_names = set(_compose()["services"])

    for pipeline in collector["service"]["pipelines"].values():
        for exporter_name in pipeline["exporters"]:
            endpoint = exporters[exporter_name].get("endpoint")
            if endpoint is None:
                continue  # debug exporter
            host = endpoint.split("//", 1)[-1].split(":")[0]
            assert host in service_names, (
                f"{exporter_name} exports to {host!r}, which is not a service "
                f"in docker-compose.yml"
            )


def test_the_cost_pipeline_is_unsampled():
    """Chapter 2's claim: a sampled stream cannot be a system of record."""
    pipelines = _collector()["service"]["pipelines"]
    cost = pipelines["traces/cost"]
    assert not any(p.startswith("probabilistic_sampler") for p in cost["processors"])
    assert any(p.startswith("probabilistic_sampler") for p in pipelines["traces/sampled"]["processors"])


def test_payload_attributes_are_stripped_before_export():
    actions = _collector()["processors"]["attributes/redact"]["actions"]
    deleted = {a["key"] for a in actions if a["action"] == "delete"}
    assert "gen_ai.input.messages" in deleted
    assert "gen_ai.output.messages" in deleted


def test_the_chapter_5_module_and_support_package_both_exist():
    """The manuscript cites chapters/ch05_performance.py."""
    assert Path("chapters/ch05_performance.py").exists()
    for name in (
        "rag_pipeline_traced.py",
        "rag_pipeline_broken.py",
        "cross_service_propagation.py",
    ):
        assert Path("chapters/ch05") .joinpath(name).exists()
