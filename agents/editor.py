import os
import json
import logging
import datetime
import time
import requests  # type: ignore
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv  # type: ignore
from google import genai  # type: ignore
from google.genai import types  # type: ignore

logger = logging.getLogger(__name__)

GEMINI_MODEL = "gemini-3.1-flash-lite-preview"
GEMINI_TIMEOUT_MS = 45_000
GEMINI_MAX_RETRIES = 3
GEMINI_RETRY_BACKOFF_SECONDS = 2

FALLBACK_TOPICS = {
    "National Assembly": ["senate", "house of reps", "nass", "national assembly", "bill", "legislature"],
    "Executive & Presidency": ["tinubu", "presidency", "minister", "aso rock", "shettima"],
    "Elections & INEC": ["inec", "election", "tribunal", "bye-election", "by-election", "primary", "governorship"],
    "Economy & Policy": ["cbn", "budget", "policy", "fiscal", "reform"],
    "Anti-Corruption": ["efcc", "corruption", "impeachment", "censure"],
}

class Editor:
    def __init__(self, raw_data_path: Optional[str] = None):
        load_dotenv()

        if raw_data_path:
            self.raw_data_path = raw_data_path
        else:
            today_str = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
            self.raw_data_path = f"data/raw/{today_str}.json"
            
        self.api_key = os.environ.get("GEMINI_API_KEY")
        if not self.api_key:
            logger.warning("GEMINI_API_KEY environment variable is missing. AI features will be disabled, using fallbacks.")
            
        self.clustering_method = "fallback"
        self.lead_selection_method = "fallback"

    def run(self) -> str:
        logger.info("Starting Editor pipeline.")
        articles = self._load_raw()
        if not articles:
            logger.warning("No valid articles loaded. Aborting pipeline.")
            return ""
            
        logger.info("Clustering articles...")
        themes = self._cluster_articles(articles)
        
        logger.info("Summarizing themes...")
        themes = self._summarize_themes(themes)
        
        logger.info("Selecting lead story...")
        lead = self._select_lead(articles, themes)
        
        logger.info("Building output payload...")
        payload = self._build_output(articles, themes, lead)
        
        logger.info("Saving output...")
        out_path = self._save_output(payload)
        
        logger.info(f"Editor pipeline complete. Saved to {out_path}. Themes: {len(themes)}, Articles: {len(articles)}")
        return out_path

    def _load_raw(self) -> List[Dict]:
        if not os.path.exists(self.raw_data_path):
            raise FileNotFoundError(f"Input file not found: {self.raw_data_path}")
            
        with open(self.raw_data_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            
        valid_articles = []
        total_loaded = len(data)
        total_skipped = 0
        
        for article in data:
            if not isinstance(article, dict):
                total_skipped += 1
                logger.warning(f"Skipping malformed article (not a dict): {article}")
                continue
                
            is_valid = True
            for field in ["id", "title", "url", "source", "published_at"]:
                val = article.get(field)
                if not isinstance(val, str) or not val.strip():
                    is_valid = False
                    logger.warning(f"Skipping malformed article (missing/empty {field}): {article.get('id', 'unknown')}")
                    break
                    
            if is_valid:
                valid_articles.append(article)
            else:
                total_skipped += 1
                
        logger.info(f"Loaded {len(valid_articles)} articles, skipped {total_skipped}")
        return valid_articles

    def _cluster_articles(self, articles: List[Dict]) -> List[Dict]:
        if not self.api_key:
            return self._fallback_cluster(articles)
            
        logger.info("Attempting AI clustering.")
        prompt_articles = [
            {
                "id": a["id"],
                "title": a["title"],
                "summary_snippet": a.get("summary_snippet", "")
            }
            for a in articles
        ]
        
        prompt = f"""You are the editor of a Nigerian politics newsletter.
Below is a JSON list of articles from today's news cycle.

Group them into between 3 and 6 thematic clusters that would make logical newsletter sections.
Each cluster should have a short, specific title (e.g. "National Assembly", "Economy & CBN Policy", "State Elections", "Security & Insurgency", "Anti-Corruption & EFCC").
Every article must appear in exactly one cluster. Do not drop any articles.

Return ONLY this JSON structure:
{{
  "clusters": [
    {{
      "theme_title": "...",
      "article_ids": ["a3f9c1b2e4d5", "..."]
    }}
  ]
}}
No explanation, no preamble.

Articles:
{json.dumps(prompt_articles, indent=2)}"""

        try:
            response_text = self._call_gemini(prompt)
            data = json.loads(response_text)
            
            if "clusters" not in data or not isinstance(data["clusters"], list) or not data["clusters"]:
                raise ValueError("Invalid clusters format in response")
                
            input_ids = {a["id"]: a for a in articles}
            returned_ids = set()
            
            clusters = []
            for c in data["clusters"]:
                title = c.get("theme_title")
                a_ids = c.get("article_ids", [])
                
                if not title or not isinstance(title, str) or not isinstance(a_ids, list):
                    raise ValueError("Invalid cluster object format")
                    
                cluster_articles = []
                for a_id in a_ids:
                    if a_id in input_ids:
                        if a_id not in returned_ids:
                            cluster_articles.append(input_ids[a_id])
                            returned_ids.add(a_id)
                    else:
                        logger.warning(f"AI returned unknown article ID: {a_id}")
                
                if cluster_articles:
                    clusters.append({
                        "theme_title": title,
                        "articles": cluster_articles
                    })
                    
            missing_ids = set(input_ids.keys()) - returned_ids
            if missing_ids:
                logger.warning(f"{len(missing_ids)} articles missing from AI clusters, placing in 'Other'")
                missing_articles = [input_ids[m_id] for m_id in missing_ids]
                
                other_cluster = next((c for c in clusters if c["theme_title"] == "Other"), None)
                if other_cluster:
                    other_cluster["articles"].extend(missing_articles)
                else:
                    clusters.append({
                        "theme_title": "Other",
                        "articles": missing_articles
                    })
            
            self.clustering_method = "ai"
            return clusters
            
        except Exception as e:
            logger.error(f"AI clustering failed: {e}. Falling back.")
            return self._fallback_cluster(articles)

    def _summarize_themes(self, themes: List[Dict]) -> List[Dict]:
        def apply_fallback_summaries(themes_list):
            for t in themes_list:
                if "theme_summary" not in t:
                    t["theme_summary"] = f"Today's coverage includes {len(t['articles'])} articles on {t['theme_title']}."
            return themes_list

        if not self.api_key:
            return apply_fallback_summaries(themes)
            
        logger.info("Attempting AI theme summarization.")
        
        cluster_input = []
        for t in themes:
            cluster_input.append({
                "theme_title": t["theme_title"],
                "articles": [{"title": a["title"], "summary_snippet": a.get("summary_snippet", "")} for a in t["articles"]]
            })
            
        prompt = f"""You are writing a Nigerian politics newsletter in the style of Bloomberg's Balance of Power.
Below are {len(themes)} thematic clusters of today's political news. For each cluster, write a tight 3–4 sentence summary paragraph in clear, direct newsletter prose. Write for an informed reader. Avoid repetition across themes.

Return ONLY this JSON structure:
{{
  "theme_summaries": [
    {{
      "theme_title": "...",
      "theme_summary": "..."
    }}
  ]
}}
The theme_title values must exactly match the input. No explanation, no preamble.

Clusters:
{json.dumps(cluster_input, indent=2)}"""

        try:
            response_text = self._call_gemini(prompt)
            data = json.loads(response_text)
            
            if "theme_summaries" not in data or not isinstance(data["theme_summaries"], list):
                raise ValueError("Invalid theme_summaries format in response")
                
            summaries_map = {s["theme_title"]: s["theme_summary"] for s in data["theme_summaries"] if "theme_title" in s and "theme_summary" in s}
            
            for t in themes:
                title = t["theme_title"]
                if title in summaries_map:
                    t["theme_summary"] = summaries_map[title]
                else:
                    logger.warning(f"No summary returned for theme: {title}")
                    
        except Exception as e:
            logger.error(f"AI theme summarization failed: {e}. Falling back to default summaries.")
            
        return apply_fallback_summaries(themes)

    def _select_lead(self, articles: List[Dict], themes: List[Dict]) -> Dict:
        if not articles:
            raise ValueError("No articles available to select lead from")
            
        if not self.api_key:
            return self._fallback_lead(articles)
            
        logger.info("Attempting AI lead selection.")
        
        candidate_articles = []
        for t in themes:
            sorted_theme_articles = sorted(
                t["articles"], 
                key=lambda x: x.get("published_at", ""), 
                reverse=True
            )
            for a in sorted_theme_articles[:2]:
                candidate_articles.append({
                    "id": a["id"],
                    "title": a["title"],
                    "theme": t["theme_title"],
                    "summary_snippet": a.get("summary_snippet", ""),
                    "published_at": a.get("published_at", "")
                })
                
        prompt = f"""You are the editor of a Nigerian politics newsletter.
From the articles below, select the single most newsworthy story to lead today's newsletter.
Prioritize: national significance, high political stakes, breaking developments.
Also write a 2–3 sentence editorial summary of the lead story for the newsletter opening.

Return ONLY this JSON structure:
{{
  "lead_id": "a3f9c1b2e4d5",
  "lead_summary": "..."
}}
No explanation, no preamble.

Articles:
{json.dumps(candidate_articles, indent=2)}"""

        try:
            response_text = self._call_gemini(prompt)
            data = json.loads(response_text)
            
            if "lead_id" not in data or "lead_summary" not in data:
                raise ValueError("Response missing lead_id or lead_summary")
                
            lead_id = data["lead_id"]
            lead_summary = data["lead_summary"]
            
            lead_article = next((a for a in articles if a["id"] == lead_id), None)
            if not lead_article:
                raise ValueError(f"AI selected unknown lead_id: {lead_id}")
                
            lead = lead_article.copy()
            lead["summary"] = lead_summary
            self.lead_selection_method = "ai"
            return lead
            
        except Exception as e:
            logger.error(f"AI lead selection failed: {e}. Falling back.")
            return self._fallback_lead(articles)

    def _fallback_cluster(self, articles: List[Dict]) -> List[Dict]:
        logger.info("Using fallback keyword-based clustering.")
        self.clustering_method = "fallback"
        
        clusters_map: Dict[str, List[Dict]] = {title: [] for title in FALLBACK_TOPICS.keys()}
        clusters_map["Other News"] = []
        
        for article in articles:
            assigned = False
            keywords = set(article.get("metadata", {}).get("keywords_matched", []))
            for topic, topic_keywords in FALLBACK_TOPICS.items():
                if any(kw.lower() in [k.lower() for k in keywords] for kw in topic_keywords):
                    clusters_map[topic].append(article)
                    assigned = True
                    break
            
            if not assigned:
                clusters_map["Other News"].append(article)
                
        result = []
        for title, cluster_articles in clusters_map.items():
            if cluster_articles:
                result.append({
                    "theme_title": title,
                    "articles": cluster_articles
                })
                
        return result

    def _fallback_lead(self, articles: List[Dict]) -> Dict:
        logger.info("Using fallback recency-based lead selection.")
        self.lead_selection_method = "fallback"
        
        sorted_articles = sorted(
            articles, 
            key=lambda x: x.get("published_at", ""), 
            reverse=True
        )
        lead = sorted_articles[0].copy()
        lead["summary"] = lead.get("summary_snippet", "")
        return lead

    def _call_gemini(self, prompt: str) -> str:
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY not set")
            
        client = genai.Client(api_key=self.api_key)
        last_error = None
        for attempt in range(1, GEMINI_MAX_RETRIES + 1):
            try:
                response = client.models.generate_content(
                    model=GEMINI_MODEL,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        http_options=types.HttpOptions(timeout=GEMINI_TIMEOUT_MS),
                    ),
                )
                return response.text
            except Exception as e:
                last_error = e
                if not self._is_retryable_gemini_error(e) or attempt == GEMINI_MAX_RETRIES:
                    logger.error(f"Gemini API call failed: {e}")
                    raise

                sleep_seconds = GEMINI_RETRY_BACKOFF_SECONDS * attempt
                logger.warning(
                    f"Gemini API call failed with retryable error on attempt {attempt}/{GEMINI_MAX_RETRIES}: {e}. "
                    f"Retrying in {sleep_seconds}s."
                )
                time.sleep(sleep_seconds)

        raise RuntimeError(f"Gemini API call failed after retries: {last_error}")

    def _is_retryable_gemini_error(self, error: Exception) -> bool:
        error_text = str(error).lower()
        return any(
            token in error_text
            for token in ["503", "unavailable", "resource_exhausted", "rate limit", "deadline exceeded", "timeout"]
        )

    def _build_output(self, articles: List[Dict], themes: List[Dict], lead: Dict) -> Dict:
        today_str = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
        processed_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
        
        lead_out = {
            "id": lead["id"],
            "title": lead["title"],
            "summary": lead.get("summary", ""),
            "url": lead["url"],
            "source": lead["source"],
            "published_at": lead["published_at"]
        }
        
        themes_out = []
        for t in themes:
            theme_articles_out = []
            for a in t["articles"]:
                theme_articles_out.append({
                    "id": a["id"],
                    "title": a["title"],
                    "url": a["url"],
                    "source": a["source"],
                    "published_at": a["published_at"]
                })
                
            themes_out.append({
                "theme_title": t["theme_title"],
                "theme_summary": t.get("theme_summary", ""),
                "article_count": len(t["articles"]),
                "articles": theme_articles_out
            })
            
        return {
            "date": today_str,
            "processed_at": processed_at,
            "total_articles_processed": len(articles),
            "lead_story": lead_out,
            "themes": themes_out,
            "metadata": {
                "ai_model": GEMINI_MODEL,
                "ai_timeout_seconds": GEMINI_TIMEOUT_MS // 1000,
                "clustering_method": self.clustering_method,
                "lead_selection_method": self.lead_selection_method
            }
        }

    def _save_output(self, payload: Dict) -> str:
        today_str = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
        processed_dir = "data/processed"
        os.makedirs(processed_dir, exist_ok=True)
        
        final_path = os.path.join(processed_dir, f"{today_str}.json")
        tmp_path = os.path.join(processed_dir, f"{today_str}.tmp.json")
        
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, ensure_ascii=False)
            os.replace(tmp_path, final_path)
            return final_path
        except Exception as e:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            raise RuntimeError(f"Failed to save output to {final_path}") from e

if __name__ == "__main__":
    # Standalone test
    print("Running Editor standalone test...")
    editor = Editor()
    output_path = editor.run()
    if output_path:
        print(f"Editor output saved to: {output_path}")
    else:
        print("Editor produced no output.")
