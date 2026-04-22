import json
import os

import pytest  # type: ignore

from agents import editor as editor_module
from agents.editor import Editor, GEMINI_MAX_RETRIES, GEMINI_MODEL, GEMINI_TIMEOUT_MS


def test_fallback_cluster_handles_missing_metadata(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    editor = Editor("unused.json")
    articles = [
        {
            "id": "1",
            "title": "Article without metadata",
            "url": "https://example.com/1",
            "source": "Example",
            "published_at": "2026-04-22T01:00:00+00:00",
        }
    ]

    clusters = editor._fallback_cluster(articles)

    assert clusters == [{"theme_title": "Other News", "articles": articles}]


def test_editor_loads_api_key_from_dotenv(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    def fake_load_dotenv():
        os.environ["GEMINI_API_KEY"] = "from-dotenv"

    monkeypatch.setattr(editor_module, "load_dotenv", fake_load_dotenv)

    editor = Editor("unused.json")

    assert editor.api_key == "from-dotenv"


def test_call_gemini_uses_configured_model_and_timeout(monkeypatch):
    captured = {}

    class FakeModels:
        def generate_content(self, **kwargs):
            captured.update(kwargs)

            class Response:
                text = '{"ok": true}'

            return Response()

    class FakeClient:
        def __init__(self, api_key):
            captured["api_key"] = api_key
            self.models = FakeModels()

    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(editor_module.genai, "Client", FakeClient)

    response_text = Editor("unused.json")._call_gemini("prompt")

    assert response_text == '{"ok": true}'
    assert captured["api_key"] == "test-key"
    assert captured["model"] == GEMINI_MODEL
    assert captured["contents"] == "prompt"
    assert captured["config"].response_mime_type == "application/json"
    assert captured["config"].http_options.timeout == GEMINI_TIMEOUT_MS


def test_call_gemini_retries_transient_503(monkeypatch):
    calls = {"count": 0}
    sleeps = []

    class FakeModels:
        def generate_content(self, **kwargs):
            calls["count"] += 1
            if calls["count"] < GEMINI_MAX_RETRIES:
                raise RuntimeError("503 UNAVAILABLE")

            class Response:
                text = '{"ok": true}'

            return Response()

    class FakeClient:
        def __init__(self, api_key):
            self.models = FakeModels()

    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(editor_module.genai, "Client", FakeClient)
    monkeypatch.setattr(editor_module.time, "sleep", lambda seconds: sleeps.append(seconds))

    response_text = Editor("unused.json")._call_gemini("prompt")

    assert response_text == '{"ok": true}'
    assert calls["count"] == GEMINI_MAX_RETRIES
    assert sleeps == [2, 4]


def test_run_without_api_key_writes_fallback_output(tmp_path, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.chdir(tmp_path)

    raw_dir = tmp_path / "data" / "raw"
    raw_dir.mkdir(parents=True)
    raw_path = raw_dir / "2026-04-22.json"
    raw_path.write_text(
        json.dumps(
            [
                {
                    "id": "1",
                    "title": "Tinubu signs new bill",
                    "url": "https://example.com/1",
                    "source": "Example",
                    "published_at": "2026-04-22T01:00:00+00:00",
                    "summary_snippet": "A policy update.",
                    "metadata": {"keywords_matched": ["tinubu", "bill"]},
                }
            ]
        ),
        encoding="utf-8",
    )

    output_path = Editor(str(raw_path)).run()
    payload = json.loads((tmp_path / output_path).read_text(encoding="utf-8"))

    assert payload["total_articles_processed"] == 1
    assert payload["metadata"]["ai_model"] == GEMINI_MODEL
    assert payload["metadata"]["ai_timeout_seconds"] == GEMINI_TIMEOUT_MS // 1000
    assert payload["metadata"]["clustering_method"] == "fallback"
    assert payload["metadata"]["lead_selection_method"] == "fallback"
