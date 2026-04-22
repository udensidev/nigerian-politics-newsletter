import json
import subprocess

import pytest  # type: ignore

from agents import formatter as formatter_module
from agents.formatter import Formatter


def valid_payload():
    return {
        "date": "2026-04-22",
        "processed_at": "2026-04-22T03:00:38.901348+00:00",
        "total_articles_processed": 2,
        "lead_story": {
            "id": "lead-1",
            "title": "Tinubu sacks Edun, Dangiwa",
            "summary": "A cabinet shake-up signals a shift in policy direction.",
            "url": "https://example.com/lead",
            "source": "Daily Trust",
            "published_at": "2026-04-22T01:42:08+00:00",
        },
        "themes": [
            {
                "theme_title": "Executive Decisions",
                "theme_summary": "The presidency moved on cabinet changes.",
                "article_count": 2,
                "articles": [
                    {
                        "id": "lead-1",
                        "title": "Tinubu sacks Edun, Dangiwa",
                        "url": "https://example.com/lead",
                        "source": "Daily Trust",
                        "published_at": "2026-04-22T01:42:08+00:00",
                    },
                    {
                        "id": "a2",
                        "title": "Dangiwa accepts cabinet axe",
                        "url": "https://example.com/a2",
                        "source": "Vanguard",
                        "published_at": "2026-04-21T19:25:15+00:00",
                    },
                ],
            }
        ],
        "metadata": {
            "clustering_method": "ai",
            "lead_selection_method": "ai",
        },
    }


def write_processed(tmp_path, payload):
    processed_dir = tmp_path / "data" / "processed"
    processed_dir.mkdir(parents=True)
    processed_path = processed_dir / "2026-04-22.json"
    processed_path.write_text(json.dumps(payload), encoding="utf-8")
    return processed_path


def mock_subprocess_run(monkeypatch, captured=None):
    def fake_run(command, check, capture_output, text):
        if captured is not None:
            captured["command"] = command
            captured["check"] = check
            captured["capture_output"] = capture_output
            captured["text"] = text
        output_path = command[command.index("-o") + 1]
        with open(output_path, "w", encoding="utf-8") as f:
            f.write("<html><body>Rendered</body></html>")

    monkeypatch.setattr(formatter_module.subprocess, "run", fake_run)


def test_run_writes_mjml_and_html(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    processed_path = write_processed(tmp_path, valid_payload())
    mock_subprocess_run(monkeypatch)

    output_path = Formatter(str(processed_path)).run()

    assert output_path == "data/formatted/2026-04-22.html"
    assert (tmp_path / "data" / "formatted" / "2026-04-22.mjml").exists()
    assert (tmp_path / "data" / "formatted" / "2026-04-22.html").exists()


def test_formatter_escapes_news_text(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    payload = valid_payload()
    payload["lead_story"]["title"] = 'Tinubu <script>alert("x")</script> & cabinet'
    payload["lead_story"]["summary"] = 'Summary with <b>markup</b> & "quotes".'
    payload["lead_story"]["source"] = "Daily & Trust"
    payload["themes"][0]["theme_title"] = "Executive <Moves>"
    payload["themes"][0]["articles"][0]["title"] = "Article <unsafe> & title"
    processed_path = write_processed(tmp_path, payload)
    mock_subprocess_run(monkeypatch)

    Formatter(str(processed_path)).run()
    mjml = (tmp_path / "data" / "formatted" / "2026-04-22.mjml").read_text(encoding="utf-8")

    assert "&lt;script&gt;alert(\"x\")&lt;/script&gt; &amp; cabinet" in mjml
    assert "Summary with &lt;b&gt;markup&lt;/b&gt; &amp; \"quotes\"." in mjml
    assert "Daily &amp; Trust" in mjml
    assert "Executive &lt;Moves&gt;" in mjml
    assert "Article &lt;unsafe&gt; &amp; title" in mjml
    assert "<script>" not in mjml
    assert "<b>markup</b>" not in mjml


def test_missing_input_raises_file_not_found(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    with pytest.raises(FileNotFoundError):
        Formatter("data/processed/missing.json").run()


def test_invalid_payload_missing_lead_title_raises_value_error(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    payload = valid_payload()
    del payload["lead_story"]["title"]
    processed_path = write_processed(tmp_path, payload)

    with pytest.raises(ValueError, match="lead_story.title"):
        Formatter(str(processed_path)).run()


def test_invalid_theme_article_raises_value_error(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    payload = valid_payload()
    del payload["themes"][0]["articles"][0]["url"]
    processed_path = write_processed(tmp_path, payload)

    with pytest.raises(ValueError, match=r"themes\[0\]\.articles\[0\]\.url"):
        Formatter(str(processed_path)).run()


def test_mjml_failure_preserves_clear_error(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    processed_path = write_processed(tmp_path, valid_payload())

    def fake_run(command, check, capture_output, text):
        raise subprocess.CalledProcessError(1, command, stderr="bad mjml")

    monkeypatch.setattr(formatter_module.subprocess, "run", fake_run)

    with pytest.raises(RuntimeError, match="MJML rendering failed: bad mjml"):
        Formatter(str(processed_path)).run()


def test_fallback_to_path_mjml_when_local_cli_missing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    processed_path = write_processed(tmp_path, valid_payload())
    captured = {}
    mock_subprocess_run(monkeypatch, captured)
    monkeypatch.setattr(formatter_module.os.path, "exists", lambda path: False if "node_modules" in path else True)

    Formatter(str(processed_path)).run()

    assert captured["command"][0] == "mjml"
