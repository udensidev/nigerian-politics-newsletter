import sys

import pytest  # type: ignore

import main


def test_pipeline_runs_collector_editor_formatter_in_order(monkeypatch):
    calls = []

    class FakeCollector:
        def run(self):
            calls.append("collector")
            return [{"id": "1"}]

    class FakeEditor:
        def run(self):
            calls.append("editor")
            return "data/processed/2026-04-22.json"

    class FakeFormatter:
        def __init__(self, processed_path):
            calls.append(("formatter_init", processed_path))

        def run(self):
            calls.append("formatter")
            return "data/formatted/2026-04-22.html"

    monkeypatch.setattr(main, "Collector", FakeCollector)
    monkeypatch.setattr(main, "Editor", FakeEditor)
    monkeypatch.setattr(main, "Formatter", FakeFormatter)

    html_path = main.run_pipeline()

    assert calls == [
        "collector",
        "editor",
        ("formatter_init", "data/processed/2026-04-22.json"),
        "formatter",
    ]
    assert html_path == "data/formatted/2026-04-22.html"


def test_pipeline_stops_when_collector_returns_no_articles(monkeypatch):
    calls = []

    class FakeCollector:
        def run(self):
            calls.append("collector")
            return []

    class FakeEditor:
        def run(self):
            calls.append("editor")
            return "data/processed/2026-04-22.json"

    class FakeFormatter:
        def __init__(self, processed_path):
            calls.append("formatter_init")

        def run(self):
            calls.append("formatter")
            return "data/formatted/2026-04-22.html"

    monkeypatch.setattr(main, "Collector", FakeCollector)
    monkeypatch.setattr(main, "Editor", FakeEditor)
    monkeypatch.setattr(main, "Formatter", FakeFormatter)

    html_path = main.run_pipeline()

    assert calls == ["collector"]
    assert html_path is None


def test_pipeline_stops_when_editor_returns_empty_path(monkeypatch):
    calls = []

    class FakeCollector:
        def run(self):
            calls.append("collector")
            return [{"id": "1"}]

    class FakeEditor:
        def run(self):
            calls.append("editor")
            return ""

    class FakeFormatter:
        def __init__(self, processed_path):
            calls.append("formatter_init")

        def run(self):
            calls.append("formatter")
            return "data/formatted/2026-04-22.html"

    monkeypatch.setattr(main, "Collector", FakeCollector)
    monkeypatch.setattr(main, "Editor", FakeEditor)
    monkeypatch.setattr(main, "Formatter", FakeFormatter)

    html_path = main.run_pipeline()

    assert calls == ["collector", "editor"]
    assert html_path is None


def patch_successful_pipeline(monkeypatch):
    calls = []

    class FakeCollector:
        def run(self):
            calls.append("collector")
            return [{"id": "1"}]

    class FakeEditor:
        def run(self):
            calls.append("editor")
            return "data/processed/2026-04-22.json"

    class FakeFormatter:
        def __init__(self, processed_path):
            calls.append(("formatter_init", processed_path))

        def run(self):
            calls.append("formatter")
            return "data/formatted/2026-04-22.html"

    monkeypatch.setattr(main, "Collector", FakeCollector)
    monkeypatch.setattr(main, "Editor", FakeEditor)
    monkeypatch.setattr(main, "Formatter", FakeFormatter)
    return calls


def test_main_default_pipeline_does_not_send(monkeypatch):
    calls = patch_successful_pipeline(monkeypatch)
    send_calls = []

    class FakeSender:
        def __init__(self, html_path, production=False, confirm_production=False):
            send_calls.append((html_path, production, confirm_production))

        def run(self):
            return ["reader@example.com"]

    monkeypatch.setattr(main, "NewsletterTestSender", FakeSender)
    monkeypatch.setattr(sys, "argv", ["main.py"])

    main.main()

    assert calls == [
        "collector",
        "editor",
        ("formatter_init", "data/processed/2026-04-22.json"),
        "formatter",
    ]
    assert send_calls == []


def test_main_send_test_sends_formatter_output(monkeypatch, capsys):
    patch_successful_pipeline(monkeypatch)
    send_calls = []

    class FakeSender:
        def __init__(self, html_path, production=False, confirm_production=False):
            send_calls.append((html_path, production, confirm_production))

        def run(self):
            return ["reader@example.com"]

    monkeypatch.setattr(main, "NewsletterTestSender", FakeSender)
    monkeypatch.setattr(sys, "argv", ["main.py", "--send-test"])

    main.main()

    assert send_calls == [("data/formatted/2026-04-22.html", False, False)]
    assert "Test newsletter sent to: reader@example.com" in capsys.readouterr().out


def test_main_production_send_requires_confirmation_before_pipeline(monkeypatch):
    calls = []

    class FakeCollector:
        def run(self):
            calls.append("collector")
            return [{"id": "1"}]

    monkeypatch.setattr(main, "Collector", FakeCollector)
    monkeypatch.setattr(sys, "argv", ["main.py", "--send-production"])

    with pytest.raises(SystemExit):
        main.main()

    assert calls == []


def test_main_send_production_sends_after_formatter(monkeypatch, capsys):
    calls = patch_successful_pipeline(monkeypatch)
    send_calls = []

    class FakeSender:
        def __init__(self, html_path, production=False, confirm_production=False):
            send_calls.append((html_path, production, confirm_production))

        def run(self):
            calls.append("sender")
            return ["first@example.com", "second@example.com"]

    monkeypatch.setattr(main, "NewsletterTestSender", FakeSender)
    monkeypatch.setattr(sys, "argv", ["main.py", "--send-production", "--confirm-production"])

    main.main()

    assert calls == [
        "collector",
        "editor",
        ("formatter_init", "data/processed/2026-04-22.json"),
        "formatter",
        "sender",
    ]
    assert send_calls == [("data/formatted/2026-04-22.html", True, True)]
    assert "Production newsletter sent to 2 recipients." in capsys.readouterr().out


def test_main_does_not_send_when_collector_returns_no_articles(monkeypatch):
    send_calls = []

    class FakeCollector:
        def run(self):
            return []

    class FakeSender:
        def __init__(self, html_path, production=False, confirm_production=False):
            send_calls.append((html_path, production, confirm_production))

        def run(self):
            return ["reader@example.com"]

    monkeypatch.setattr(main, "Collector", FakeCollector)
    monkeypatch.setattr(main, "NewsletterTestSender", FakeSender)
    monkeypatch.setattr(sys, "argv", ["main.py", "--send-test"])

    main.main()

    assert send_calls == []


def test_main_does_not_send_when_editor_returns_empty_path(monkeypatch):
    send_calls = []

    class FakeCollector:
        def run(self):
            return [{"id": "1"}]

    class FakeEditor:
        def run(self):
            return ""

    class FakeSender:
        def __init__(self, html_path, production=False, confirm_production=False):
            send_calls.append((html_path, production, confirm_production))

        def run(self):
            return ["reader@example.com"]

    monkeypatch.setattr(main, "Collector", FakeCollector)
    monkeypatch.setattr(main, "Editor", FakeEditor)
    monkeypatch.setattr(main, "NewsletterTestSender", FakeSender)
    monkeypatch.setattr(sys, "argv", ["main.py", "--send-test"])

    main.main()

    assert send_calls == []
