import json
import logging
import os
import datetime
import hashlib
from typing import List, Dict, Any, Optional
import feedparser # type: ignore
import requests # type: ignore
from dotenv import load_dotenv # type: ignore
from google import genai # type: ignore
from google.genai import types # type: ignore
from pydantic import BaseModel, Field # type: ignore

from utils.deduplicator import deduplicate

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(os.path.dirname(__file__), '../logs/collector.log')),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

STRONG_POLITICAL_SIGNALS = {
    "tinubu", "inec", "apc", "pdp", "lp", "efcc", "national assembly",
    "senate", "presidency", "election", "tribunal", "impeachment",
    "defection", "budget"
}

WEAK_POLITICAL_SIGNALS = {
    "governor", "minister", "policy", "bill", "protest", "obi"
}

SOFT_NEWS_TERMS = [
    "award", "patron", "hats off", "renewed hope movement", "youth mobilisation",
    "youth mobilization", "entertainment", "music star", "davido"
]

SOFT_NEWS_OVERRIDE_SIGNALS = {
    "apc", "pdp", "lp", "nnpp", "inec", "election", "campaign", "re-election",
    "reelection", "candidate", "primary", "governorship", "presidential"
}

class Collector:
    """
    Agent responsible for collecting, filtering, and deduplicating news articles
    from Nigerian political RSS feeds.
    """
    
    def __init__(self, feeds_path: Optional[str] = None):
        """
        Initialize the Collector agent.
        
        Args:
            feeds_path: Path to the JSON file containing RSS feeds.
        """
        if feeds_path is None:
            feeds_path = os.path.join(os.path.dirname(__file__), '../data/feeds.json')
        self.feeds_path = feeds_path
        self.feeds = self._load_feeds()
        
        self.keywords = [
            # Political figures
            "tinubu", "shettima", "obi", "atiku", "fubara", "kwankwaso", "wike",
            # Institutions
            "inec", "national assembly", "senate", "house of reps", 
            "efcc", "cbn", "supreme court", "presidency", "governorship",
            "apc", "pdp", "lp", "nnpp", "nass", "dss", "aso rock",
            # Topics
            "election", "politics", "policy", "minister", "governor", 
            "legislature", "corruption", "protest", "coup", "treaty", "bill", "budget",
            "tribunal", "defection", "impeachment", "censure", "dissolution", "bye-election", "by-election", "primary"
        ]
        # remove duplicates while preserving order
        self.keywords = list(dict.fromkeys(self.keywords))

    def _load_feeds(self) -> List[Dict[str, str]]:
        """Load feeds from the feeds.json file."""
        try:
            with open(self.feeds_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load feeds from {self.feeds_path}: {e}")
            return []

    def fetch_articles(self) -> List[Dict[str, Any]]:
        """
        Fetch articles published in the last 24 hours from all feeds.
        
        Returns:
            A list of article dictionaries.
        """
        articles = []
        now = datetime.datetime.now(datetime.timezone.utc)
        # 26h window (not 24h) to absorb GitHub Actions cron scheduling drift
        twenty_four_hours_ago = now - datetime.timedelta(hours=26)
        
        for feed in self.feeds:
            name = feed.get("name") or "Unknown Feed"
            url = feed.get("url")
            if not url:
                logger.warning(f"Skipping feed with missing url: {name}")
                continue

            logger.info(f"Fetching feed: {name} ({url})")
            
            try:
                # Use requests to fetch with timeout
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                }
                response = requests.get(url, timeout=10, headers=headers)
                response.raise_for_status()
                parsed = feedparser.parse(response.content)
                
                if parsed.bozo:
                    logger.warning(f"Feed {name} may be malformed: {parsed.bozo_exception}")
                
                for entry in parsed.entries:
                    # Try to parse published date
                    published_dt = None
                    if hasattr(entry, 'published_parsed') and entry.published_parsed:
                        p = entry.published_parsed
                        published_dt = datetime.datetime(p[0], p[1], p[2], p[3], p[4], p[5], tzinfo=datetime.timezone.utc)
                    elif hasattr(entry, 'updated_parsed') and entry.updated_parsed:
                        p = entry.updated_parsed
                        published_dt = datetime.datetime(p[0], p[1], p[2], p[3], p[4], p[5], tzinfo=datetime.timezone.utc)
                    else:
                        continue # Skip articles without date
                        
                    if published_dt >= twenty_four_hours_ago:
                        article_url = entry.get("link", "")
                        article_id = hashlib.sha256(article_url.encode()).hexdigest()[:12]
                        articles.append({
                            "id": article_id,
                            "title": entry.get("title", ""),
                            "url": article_url,
                            "source": name,
                            "published_at": published_dt.isoformat(),
                            "summary_snippet": entry.get("summary", entry.get("description", ""))[:500]
                        })
                        
            except requests.exceptions.Timeout:
                logger.error(f"Timeout fetching feed {name}: {url}")
            except requests.exceptions.RequestException as e:
                logger.error(f"Error fetching feed {name}: {e}")
            except Exception as e:
                logger.error(f"Unexpected error processing feed {name}: {e}")
                
        return articles

    def is_false_positive(self, title: str, summary: str = "") -> bool:
        """
        Secondary check to discard articles that matched a keyword but are likely false positives.
        """
        lower_title = title.lower()
        lower_text = f"{title} {summary}".lower()
        blocklist = [
            "super eagles", "afcon", "premier league", "champions league", 
            "naija stars", "nff", "transfer", "football", "cricket", "athletics"
        ]
        if any(term in lower_title for term in blocklist):
            return True

        has_soft_news_term = any(term in lower_text for term in SOFT_NEWS_TERMS)
        has_override_signal = any(term in lower_text for term in SOFT_NEWS_OVERRIDE_SIGNALS)
        return has_soft_news_term and not has_override_signal

    def _calculate_political_score(self, matched_keywords: List[str]) -> int:
        strong_matches = {kw for kw in matched_keywords if kw in STRONG_POLITICAL_SIGNALS}
        weak_matches = {kw for kw in matched_keywords if kw in WEAK_POLITICAL_SIGNALS}
        return (len(strong_matches) * 3) + len(weak_matches)

    def _get_filter_reason(self, matched_keywords: List[str]) -> Optional[str]:
        strong_matches = [kw for kw in matched_keywords if kw in STRONG_POLITICAL_SIGNALS]
        weak_matches = [kw for kw in matched_keywords if kw in WEAK_POLITICAL_SIGNALS]

        if strong_matches:
            return "strong_keyword"
        if len(set(weak_matches)) >= 2:
            return "multiple_contextual_keywords"
        return None

    def filter_politics(self, articles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Filter articles based on political keywords in title or summary.
        
        Args:
            articles: List of article dictionaries.
            
        Returns:
            Filtered list of articles.
        """
        filtered = []
        for article in articles:
            text_to_search = f"{article.get('title', '')} {article.get('summary_snippet', '')}".lower()
            matched_keywords = [kw for kw in self.keywords if kw in text_to_search]
            
            if matched_keywords:
                filter_reason = self._get_filter_reason(matched_keywords)
                if filter_reason and not self.is_false_positive(article.get('title', ''), article.get('summary_snippet', '')):
                    article["metadata"] = {
                        "keywords_matched": matched_keywords,
                        "political_score": self._calculate_political_score(matched_keywords),
                        "filter_reason": filter_reason,
                        "ai_quality_filtered": False
                    }
                    filtered.append(article)
        return filtered

    def optional_ai_filter(self, articles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Use Gemini API to filter out non-political articles if USE_AI_FILTER is true.
        
        Args:
            articles: List of article dictionaries.
            
        Returns:
            AI-filtered list of articles.
        """
        use_ai = os.getenv("USE_AI_FILTER", "false").lower() == "true"
        if not use_ai or not articles:
            return articles
            
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            logger.warning("USE_AI_FILTER is true but GEMINI_API_KEY is not set. Skipping AI filter.")
            return articles
            
        logger.info("Running optional AI filter via Gemini API...")
        try:
            class ArticleFilterResult(BaseModel):
                political_article_ids: List[int] = Field(description="List of integer IDs for articles strictly about Nigerian national or state politics")

            prompt_articles = [
                {
                    "id": i,
                    "title": a.get("title", ""),
                    "summary_snippet": a.get("summary_snippet", "")
                }
                for i, a in enumerate(articles)
            ]
            
            prompt = (
                "Below is a JSON list of articles. Return ONLY a JSON object containing a list of integer IDs for the articles "
                "that are strictly about Nigerian national or state politics. "
                "Remove any articles about sports, entertainment, foreign news, general non-political topics, promotional profiles, "
                "personality or celebrity politics with no institutional consequence, generic governance items with no political stakes, "
                "and duplicate soft rewrites of the same story.\n\n"
                f"{json.dumps(prompt_articles, indent=2)}"
            )
            
            client = genai.Client(api_key=api_key)
            response = client.models.generate_content(
                model='gemini-3.1-flash-lite-preview',
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=ArticleFilterResult,
                    system_instruction=(
                        "You are an expert editor for a Nigerian politics newsletter. Keep high-stakes elections, parties, presidency, "
                        "courts, legislature, cabinet, corruption, security, and major state power stories. Remove sports, entertainment, "
                        "foreign news, promotional profiles, personality or celebrity politics with no institutional consequence, generic "
                        "governance items with no political stakes, and duplicate soft rewrites."
                    ),
                    temperature=0.0
                ),
            )
            
            try:
                if not response.text:
                    logger.warning("AI returned empty response. Falling back to original.")
                    return articles
                    
                parsed_data = json.loads(response.text)
                if "political_article_ids" not in parsed_data:
                    logger.warning("political_article_ids key missing from AI response. Falling back to original.")
                    return articles
                
                returned_ids = parsed_data["political_article_ids"]
                if not isinstance(returned_ids, list):
                    logger.warning("political_article_ids is not a list. Falling back to original.")
                    return articles
                
                filtered_articles = []
                for aid in returned_ids:
                    if not isinstance(aid, int) or aid < 0 or aid >= len(articles):
                        logger.warning(f"AI returned out-of-range or invalid ID: {aid}. Skipping.")
                        continue
                    filtered_articles.append(articles[aid])
                
                for article in filtered_articles:
                    if "metadata" in article:
                        article["metadata"]["ai_quality_filtered"] = True
                        
                return filtered_articles
                
            except json.JSONDecodeError as e:
                logger.warning(f"AI returned invalid JSON: {e}. Falling back to original.")
                return articles
                
        except Exception as e:
            logger.error(f"AI filter failed: {e}. Falling back to original articles.")
            return articles

    def save_output(self, articles: List[Dict[str, Any]]) -> str:
        """
        Save the final list of articles to a timestamped JSON file.
        
        Args:
            articles: List of article dictionaries to save.
            
        Returns:
            The path to the saved file.
        """
        date_str = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
        out_dir = os.path.join(os.path.dirname(__file__), '../data/raw')
        os.makedirs(out_dir, exist_ok=True)
        file_path = os.path.join(out_dir, f"{date_str}.json")
        tmp_path = os.path.join(out_dir, f"{date_str}.tmp.json")
        
        try:
            with open(tmp_path, 'w', encoding='utf-8') as f:
                json.dump(articles, f, indent=2)
            os.replace(tmp_path, file_path)
            logger.info(f"Saved {len(articles)} articles to {file_path}")
            return file_path
        except Exception as e:
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
            logger.error(f"Failed to save output to {file_path}: {e}")
            raise

    def run(self) -> List[Dict[str, Any]]:
        """
        Run the complete collection pipeline.
        
        Returns:
            The final list of processed articles.
        """
        logger.info("Starting collection pipeline...")
        
        fetched = self.fetch_articles()
        logger.info(f"Fetched {len(fetched)} articles in the last 24 hours.")
        
        filtered = self.filter_politics(fetched)
        logger.info(f"Filtered down to {len(filtered)} articles based on keywords.")
        
        deduped = deduplicate(filtered)
        logger.info(f"Deduplicated down to {len(deduped)} unique articles.")
        
        final_articles = self.optional_ai_filter(deduped)
        if final_articles != deduped:
            logger.info(f"AI filter returned {len(final_articles)} articles.")
            
        self.save_output(final_articles)
        
        logger.info(f"Pipeline complete. Final count: {len(final_articles)} articles.")
        return final_articles

if __name__ == "__main__":
    # Standalone test
    print("Running Collector standalone test...")
    collector = Collector()
    results = collector.run()
    print(f"Total articles collected: {len(results)}")
    print("First 3 articles:")
    print(json.dumps(results[:3], indent=2))
