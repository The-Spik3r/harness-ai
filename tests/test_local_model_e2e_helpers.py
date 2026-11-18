"""Default-suite tests of the local-model E2E helpers (PRD-020 STORY-014).

No `--run-e2e`, no model server and no database: a tiny in-process HTTP server
stands in for the model server. The live run is `tests/e2e/test_local_model.py`.
"""

import contextlib
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from tests._providers import providers_file
from tests.e2e import _local_model as lm


@contextlib.contextmanager
def _server(routes: dict):
    """A server answering GET `path` with `routes[path]` as JSON (404 otherwise); yields its `/v1` base URL."""

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            body = routes.get(self.path)
            if body is None:
                self.send_response(404)
                self.end_headers()
                return
            raw = json.dumps(body).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}/v1"
    finally:
        server.shutdown()
        server.server_close()


def test_registry_yaml_loads_as_a_keyless_internal_estimating_provider(tmp_path, monkeypatch):
    with providers_file(tmp_path, lm.registry_yaml("some/model", "http://localhost:1235/v1"), monkeypatch=monkeypatch) as registry:
        [provider] = registry.providers
        assert provider.name == lm.PROVIDER
        assert provider.trust == "internal"
        assert provider.usage_missing == "estimate"
        assert "some/model" in registry.models_by_id
        assert registry.default_model == "some/model"
        from app.services import provider_registry

        assert provider_registry.api_key_for(provider) is None


def test_probe_accepts_a_listed_model():
    with _server({"/v1/models": {"data": [{"id": "m1"}]}}) as base:
        assert lm.probe(base, "m1") == (True, "")


def test_probe_names_the_model_and_its_env_var_when_absent():
    with _server({"/v1/models": {"data": [{"id": "other"}]}}) as base:
        ok, reason = lm.probe(base, "m1")
    assert ok is False
    assert "m1" in reason and lm.ENV_MODEL in reason and "other" in reason


def test_probe_names_the_url_and_its_env_var_when_unreachable():
    with _server({}) as base:
        pass  # the server is stopped: the port is closed
    ok, reason = lm.probe(base, "m1")
    assert ok is False
    assert f"{base}/models" in reason and lm.ENV_BASE_URL in reason


def test_server_facts_reads_lm_studio_models():
    entry = {"id": "m1", "arch": "gemma", "quantization": "Q4_K_M", "state": "loaded"}
    with _server({"/api/v0/models": {"data": [entry]}}) as base:
        facts = lm.server_facts(base, "m1")
    assert facts["server"] == "lm-studio"
    assert facts["model_info"]["quantization"] == "Q4_K_M"


def test_server_facts_reads_ollama_version_and_digest():
    routes = {"/api/version": {"version": "0.5.1"}, "/api/tags": {"models": [{"name": "m1", "digest": "abc"}]}}
    with _server(routes) as base:
        facts = lm.server_facts(base, "m1")
    assert (facts["server"], facts["version"], facts["digest"]) == ("ollama", "0.5.1", "abc")


def test_server_facts_is_not_exposed_when_nothing_answers():
    with _server({}) as base:
        facts = lm.server_facts(base, "m1")
    assert facts["server"] == lm.NOT_EXPOSED and facts["digest"] == lm.NOT_EXPOSED


def test_local_config_defaults_and_overrides(monkeypatch):
    monkeypatch.delenv(lm.ENV_BASE_URL, raising=False)
    monkeypatch.delenv(lm.ENV_MODEL, raising=False)
    assert lm.local_config() == ("http://localhost:1235/v1", "google/gemma-4-e4b")
    monkeypatch.setenv(lm.ENV_BASE_URL, "http://127.0.0.1:11434/v1/")
    monkeypatch.setenv(lm.ENV_MODEL, "qwen2.5-coder:7b")
    assert lm.local_config() == ("http://127.0.0.1:11434/v1", "qwen2.5-coder:7b")
