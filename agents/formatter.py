import datetime
import html
import json
import os
import subprocess
from typing import Any, Dict, Optional


class Formatter:
    """Format processed newsletter content into MJML and HTML email artifacts."""

    def __init__(self, processed_data_path: Optional[str] = None, output_dir: str = "data/formatted"):
        today_str = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
        self.processed_data_path = processed_data_path or f"data/processed/{today_str}.json"
        self.output_dir = output_dir
        self.repo_root = os.getcwd()

    def run(self) -> str:
        payload = self._load_processed()
        self._validate_payload(payload)

        issue_date = payload["date"]
        mjml = self._build_mjml(payload)

        os.makedirs(self.output_dir, exist_ok=True)
        mjml_path = os.path.join(self.output_dir, f"{issue_date}.mjml")
        html_path = os.path.join(self.output_dir, f"{issue_date}.html")
        tmp_mjml_path = os.path.join(self.output_dir, f"{issue_date}.tmp.mjml")
        tmp_html_path = os.path.join(self.output_dir, f"{issue_date}.tmp.html")

        try:
            self._write_atomic(tmp_mjml_path, mjml_path, mjml)
            self._render_html(mjml_path, tmp_html_path)
            os.replace(tmp_html_path, html_path)
        except Exception:
            for tmp_path in [tmp_mjml_path, tmp_html_path]:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            raise

        return html_path

    def _load_processed(self) -> Dict[str, Any]:
        if not os.path.exists(self.processed_data_path):
            raise FileNotFoundError(f"Input file not found: {self.processed_data_path}")

        with open(self.processed_data_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        if not isinstance(data, dict):
            raise ValueError("processed payload must be a JSON object")
        return data

    def _validate_payload(self, payload: Dict[str, Any]) -> None:
        self._require_non_empty_string(payload, "date")
        self._require_optional_string(payload, "processed_at")
        self._require_optional_int(payload, "total_articles_processed")
        self._require_optional_dict(payload, "metadata")

        lead = payload.get("lead_story")
        if not isinstance(lead, dict):
            raise ValueError("lead_story must be an object")

        for field in ["id", "title", "summary", "url", "source", "published_at"]:
            self._require_string(lead, f"lead_story.{field}", allow_empty=(field == "summary"))

        themes = payload.get("themes")
        if not isinstance(themes, list) or not themes:
            raise ValueError("themes must be a non-empty list")

        for theme_index, theme in enumerate(themes):
            theme_path = f"themes[{theme_index}]"
            if not isinstance(theme, dict):
                raise ValueError(f"{theme_path} must be an object")

            self._require_non_empty_string(theme, f"{theme_path}.theme_title")
            self._require_string(theme, f"{theme_path}.theme_summary", allow_empty=True)
            self._require_optional_int(theme, f"{theme_path}.article_count")

            articles = theme.get("articles")
            if not isinstance(articles, list):
                raise ValueError(f"{theme_path}.articles must be a list")

            for article_index, article in enumerate(articles):
                article_path = f"{theme_path}.articles[{article_index}]"
                if not isinstance(article, dict):
                    raise ValueError(f"{article_path} must be an object")
                for field in ["id", "title", "url", "source", "published_at"]:
                    self._require_string(article, f"{article_path}.{field}")

    def _build_mjml(self, payload: Dict[str, Any]) -> str:
        issue_date = self._e(payload["date"])
        lead = payload["lead_story"]
        metadata = payload.get("metadata", {})

        preview = lead.get("summary") or lead["title"]
        total_articles = payload.get("total_articles_processed")
        meta_parts = []
        if isinstance(total_articles, int):
            meta_parts.append(f"{total_articles} articles")
        if isinstance(metadata, dict):
            clustering_method = metadata.get("clustering_method")
            lead_method = metadata.get("lead_selection_method")
            if isinstance(clustering_method, str) and clustering_method:
                meta_parts.append(f"clusters: {clustering_method}")
            if isinstance(lead_method, str) and lead_method:
                meta_parts.append(f"lead: {lead_method}")
        meta_line = " | ".join(meta_parts)

        theme_sections = "\n".join(self._build_theme_section(theme) for theme in payload["themes"])
        footer_generated = ""
        processed_at = payload.get("processed_at")
        if isinstance(processed_at, str) and processed_at:
            footer_generated = f"Generated {self._e(self._format_timestamp(processed_at))}<br />"

        return f"""<mjml>
  <mj-head>
    <mj-title>Nigerian Politics Brief - {issue_date}</mj-title>
    <mj-preview>{self._e(preview)}</mj-preview>
    <mj-attributes>
      <mj-all font-family="Arial, Helvetica, sans-serif" />
      <mj-body background-color="#f4f5f7" />
      <mj-section background-color="#ffffff" />
      <mj-text color="#111827" font-size="15px" line-height="1.55" />
      <mj-class name="muted" color="#6b7280" font-size="12px" line-height="1.4" />
      <mj-class name="eyebrow" color="#8f1d1d" font-size="11px" font-weight="700" text-transform="uppercase" letter-spacing="1px" />
    </mj-attributes>
  </mj-head>
  <mj-body width="680px" background-color="#f4f5f7">
    <mj-section padding="28px 28px 12px 28px">
      <mj-column>
        <mj-text font-size="26px" font-weight="700" padding-bottom="4px">Nigerian Politics Brief</mj-text>
        <mj-text mj-class="muted" padding-top="0">{issue_date}{self._meta_suffix(meta_line)}</mj-text>
      </mj-column>
    </mj-section>

    <mj-section padding="12px 28px 20px 28px">
      <mj-column>
        <mj-text mj-class="eyebrow" padding-bottom="6px">Lead Story</mj-text>
        <mj-text font-size="22px" font-weight="700" line-height="1.25" padding-top="0" padding-bottom="8px">
          <a href="{self._e_attr(lead["url"])}" style="color:#111827;text-decoration:none;">{self._e(lead["title"])}</a>
        </mj-text>
        <mj-text padding-top="0" padding-bottom="8px">{self._e(lead["summary"])}</mj-text>
        <mj-text mj-class="muted" padding-top="0">{self._e(lead["source"])} | {self._e(self._format_timestamp(lead["published_at"]))}</mj-text>
      </mj-column>
    </mj-section>

    {theme_sections}

    <mj-section padding="18px 28px 30px 28px">
      <mj-column>
        <mj-divider border-color="#e5e7eb" border-width="1px" padding="0 0 14px 0" />
        <mj-text mj-class="muted">
          {footer_generated}Stories link to original publishers.
        </mj-text>
      </mj-column>
    </mj-section>
  </mj-body>
</mjml>
"""

    def _build_theme_section(self, theme: Dict[str, Any]) -> str:
        articles_html = "\n".join(self._build_article_row(article) for article in theme["articles"])
        article_count = theme.get("article_count")
        if not isinstance(article_count, int):
            article_count = len(theme["articles"])

        return f"""    <mj-section padding="10px 28px 18px 28px">
      <mj-column>
        <mj-divider border-color="#e5e7eb" border-width="1px" padding="0 0 18px 0" />
        <mj-text font-size="18px" font-weight="700" padding-bottom="4px">{self._e(theme["theme_title"])}</mj-text>
        <mj-text mj-class="muted" padding-top="0" padding-bottom="8px">{article_count} articles</mj-text>
        <mj-text padding-top="0" padding-bottom="10px">{self._e(theme["theme_summary"])}</mj-text>
        {articles_html}
      </mj-column>
    </mj-section>"""

    def _build_article_row(self, article: Dict[str, Any]) -> str:
        return f"""        <mj-text font-size="14px" line-height="1.45" padding="5px 0">
          <a href="{self._e_attr(article["url"])}" style="color:#111827;text-decoration:underline;">{self._e(article["title"])}</a><br />
          <span style="color:#6b7280;font-size:12px;">{self._e(article["source"])} | {self._e(self._format_timestamp(article["published_at"]))}</span>
        </mj-text>"""

    def _render_html(self, mjml_path: str, tmp_html_path: str) -> None:
        command = [self._mjml_command(), mjml_path, "-o", tmp_html_path]
        try:
            subprocess.run(command, check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as e:
            error_text = e.stderr.strip() or e.stdout.strip() or str(e)
            raise RuntimeError(f"MJML rendering failed: {error_text}") from e

    def _mjml_command(self) -> str:
        local_cli = os.path.join(self.repo_root, "node_modules", ".bin", "mjml")
        if os.path.exists(local_cli):
            return local_cli
        return "mjml"

    def _write_atomic(self, tmp_path: str, final_path: str, content: str) -> None:
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp_path, final_path)

    def _format_timestamp(self, value: str) -> str:
        try:
            normalized = value.replace("Z", "+00:00")
            parsed = datetime.datetime.fromisoformat(normalized)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=datetime.timezone.utc)
            parsed = parsed.astimezone(datetime.timezone.utc)
            return parsed.strftime("%b %d, %H:%M UTC")
        except ValueError:
            return value

    def _meta_suffix(self, meta_line: str) -> str:
        if not meta_line:
            return ""
        return f" | {self._e(meta_line)}"

    def _e(self, value: Any) -> str:
        return html.escape(str(value), quote=False)

    def _e_attr(self, value: Any) -> str:
        return html.escape(str(value), quote=True)

    def _require_non_empty_string(self, data: Dict[str, Any], path: str) -> None:
        self._require_string(data, path, allow_empty=False)

    def _require_string(self, data: Dict[str, Any], path: str, allow_empty: bool = False) -> None:
        field = path.split(".")[-1]
        value = data.get(field)
        if not isinstance(value, str):
            raise ValueError(f"{path} must be a string")
        if not allow_empty and not value.strip():
            raise ValueError(f"{path} must be a non-empty string")

    def _require_optional_string(self, data: Dict[str, Any], path: str) -> None:
        field = path.split(".")[-1]
        if field in data and not isinstance(data[field], str):
            raise ValueError(f"{path} must be a string if present")

    def _require_optional_int(self, data: Dict[str, Any], path: str) -> None:
        field = path.split(".")[-1]
        if field in data and not isinstance(data[field], int):
            raise ValueError(f"{path} must be an integer if present")

    def _require_optional_dict(self, data: Dict[str, Any], path: str) -> None:
        field = path.split(".")[-1]
        if field in data and not isinstance(data[field], dict):
            raise ValueError(f"{path} must be an object if present")


if __name__ == "__main__":
    print("Running Formatter standalone test...")
    formatter = Formatter()
    output_path = formatter.run()
    print(f"Formatter HTML output saved to: {output_path}")
