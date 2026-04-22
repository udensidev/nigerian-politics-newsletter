import pytest # type: ignore
import os
import json
import datetime
from agents.collector import Collector

@pytest.fixture
def collector(tmp_path):
    # Create a temporary feeds.json file
    feeds_dir = tmp_path / "data"
    feeds_dir.mkdir()
    feeds_file = feeds_dir / "feeds.json"
    feeds_data = [
        {"name": "Test Feed", "url": "https://example.com/rss"}
    ]
    feeds_file.write_text(json.dumps(feeds_data))
    
    return Collector(feeds_path=str(feeds_file))

def test_load_feeds(collector):
    assert len(collector.feeds) == 1
    assert collector.feeds[0]["name"] == "Test Feed"

def test_is_false_positive(collector):
    # Should be false positive (sports)
    assert collector.is_false_positive("Super Eagles win AFCON") == True
    assert collector.is_false_positive("Governor wins performance award") == True
    assert collector.is_false_positive("Davido releases new single") == True
    # Should not be false positive (politics)
    assert collector.is_false_positive("President Tinubu signs bill") == False
    assert collector.is_false_positive("Davido backs Adeleke re-election campaign") == False

def test_filter_politics(collector):
    articles = [
        {
            "id": "1",
            "title": "Tinubu signs new budget",
            "summary_snippet": "The president signed the budget into law today."
        },
        {
            "id": "2",
            "title": "Super Eagles qualify for World Cup",
            "summary_snippet": "The football team won their match."
        },
        {
            "id": "3",
            "title": "New restaurant opens in Lagos",
            "summary_snippet": "A new eatery is now open for business."
        },
        {
            "id": "4",
            "title": "Governor receives new award",
            "summary_snippet": "The state governor was honoured at a ceremony."
        },
        {
            "id": "5",
            "title": "Governor signs minister-backed policy bill",
            "summary_snippet": "The state government said the policy bill will reform public services."
        }
    ]
    
    filtered = collector.filter_politics(articles)
    
    # Only article 1 should remain (it has "Tinubu", "budget", "president")
    # Article 2 has "Super Eagles" which is a false positive
    # Article 3 has no political keywords
    # Article 4 has only weak/promotional signals
    # Article 5 has multiple contextual weak signals
    assert [article["id"] for article in filtered] == ["1", "5"]
    assert "tinubu" in filtered[0]["metadata"]["keywords_matched"]
    assert filtered[0]["metadata"]["political_score"] >= 3
    assert filtered[0]["metadata"]["filter_reason"] == "strong_keyword"
    assert filtered[1]["metadata"]["political_score"] >= 2
    assert filtered[1]["metadata"]["filter_reason"] == "multiple_contextual_keywords"

def test_filter_politics_rejects_single_weak_keyword(collector):
    articles = [
        {
            "id": "1",
            "title": "Governor attends community event",
            "summary_snippet": "The governor met local residents."
        }
    ]

    assert collector.filter_politics(articles) == []

def test_filter_politics_keeps_strong_signals(collector):
    articles = [
        {
            "id": "1",
            "title": "INEC chairman faces PDP lawsuit",
            "summary_snippet": "The election tribunal filing names INEC officials."
        },
        {
            "id": "2",
            "title": "Tinubu submits budget to Senate",
            "summary_snippet": "The presidency said the budget supports reform priorities."
        }
    ]

    filtered = collector.filter_politics(articles)

    assert [article["id"] for article in filtered] == ["1", "2"]
    assert all(article["metadata"]["filter_reason"] == "strong_keyword" for article in filtered)

def test_filter_politics_handles_campaign_celebrity_boundary(collector):
    articles = [
        {
            "id": "1",
            "title": "Davido appointed youth mobilisation head, backs Adeleke re-election bid",
            "summary_snippet": "The campaign council said the music star will mobilise young voters."
        },
        {
            "id": "2",
            "title": "Davido appears at entertainment event",
            "summary_snippet": "The music star performed after meeting a governor."
        }
    ]

    filtered = collector.filter_politics(articles)

    assert [article["id"] for article in filtered] == ["1"]
    assert filtered[0]["metadata"]["filter_reason"] == "strong_keyword"

def test_filter_politics_rejects_promotional_soft_news(collector):
    articles = [
        {
            "id": "1",
            "title": "HATS OFF TO OBOREVWORI",
            "summary_snippet": "Sheriff Oborevwori wins Outstanding Governor of the Year award."
        },
        {
            "id": "2",
            "title": "Why NIPR chose Gov Sani as patron",
            "summary_snippet": "The information minister praised the governor as a friendly communication associate."
        }
    ]

    assert collector.filter_politics(articles) == []

def test_fetch_articles_mocked(mocker, collector):
    # Mock requests.get
    mock_response = mocker.Mock()
    mock_response.status_code = 200
    # Minimal RSS content
    now = datetime.datetime.now(datetime.timezone.utc)
    pub_date = now.strftime("%a, %d %b %Y %H:%M:%S GMT")
    
    rss_content = f"""<?xml version="1.0" encoding="UTF-8" ?>
    <rss version="2.0">
    <channel>
        <item>
            <title>Politics News 1</title>
            <link>https://example.com/1</link>
            <description>Summary of politics news 1</description>
            <pubDate>{pub_date}</pubDate>
        </item>
        <item>
            <title>Old News</title>
            <link>https://example.com/2</link>
            <description>This is too old</description>
            <pubDate>Mon, 01 Jan 2024 00:00:00 GMT</pubDate>
        </item>
    </channel>
    </rss>
    """
    mock_response.content = rss_content.encode('utf-8')
    mocker.patch('requests.get', return_value=mock_response)
    
    articles = collector.fetch_articles()
    
    # Should only return 1 article because the other is too old (> 26 hours)
    assert len(articles) == 1
    assert articles[0]["title"] == "Politics News 1"
