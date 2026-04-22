# Nigerian Politics Newsletter Pipeline

An automated pipeline to collect, filter, and format news related to Nigerian politics into a daily newsletter.

## Setup Instructions

1. **Python Version**: Ensure you are using Python 3.10 or higher.
2. **Virtual Environment**: 
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```
3. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   npm install
   ```
4. **Configuration**:
   Copy `.env.example` to `.env` and configure your API keys.
   ```bash
   cp .env.example .env
   ```
   To enable the optional Gemini AI filter step, set `USE_AI_FILTER=true` and provide a valid `GEMINI_API_KEY`.

## Running the Pipeline

**Run the full pipeline:**
```bash
venv/bin/python main.py
```

**Run the full pipeline and send to your test inbox:**
```bash
venv/bin/python main.py --send-test
```

**Run the full pipeline and send to production recipients:**
```bash
venv/bin/python main.py --send-production --confirm-production
```

**Run the collector standalone:**
```bash
venv/bin/python -m agents.collector
```

**Run the editor standalone:**
```bash
venv/bin/python -m agents.editor
```

**Run the formatter standalone:**
```bash
venv/bin/python -m agents.formatter
```

**Send a rendered issue to your test inbox:**

Add SMTP settings to `.env`:

```bash
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_FROM=mmesomaudensi@gmail.com
SMTP_USERNAME=mmesomaudensi@gmail.com
SMTP_PASSWORD=<google-app-password>
NEWSLETTER_TEST_RECIPIENT=mmesomaudensi@gmail.com
NEWSLETTER_RECIPIENTS=recipient1@example.com,recipient2@example.com
```

Then send the rendered HTML to your test inbox:

```bash
venv/bin/python -m agents.sender data/formatted/YYYY-MM-DD.html
```

After previewing the test send, send to production recipients:

```bash
venv/bin/python -m agents.sender data/formatted/YYYY-MM-DD.html --production --confirm-production
```

For Gmail, `SMTP_PASSWORD` must be a Google App Password, not your normal Google account password. `SMTP_USERNAME` and `SMTP_PASSWORD` are optional only when your SMTP server does not require authentication. `SMTP_USE_TLS` defaults to `true`; set it to `false` for a local SMTP capture tool.

## Local Cron Production Schedule

The daily production runner appends stdout and stderr to dated files under `logs/` and exits non-zero if collection, editing, formatting, or sending fails.

Run it manually once after configuring `.env`:

```bash
scripts/run_daily_newsletter.sh
```

Example cron entry for a daily 7:00 AM local run:

```cron
0 7 * * * /path/to/nigerian-politics-newsletter/scripts/run_daily_newsletter.sh
```

After the scheduled run, inspect the dated log:

```bash
tail -100 logs/newsletter-YYYY-MM-DD.log
```

A `SUCCESS` line confirms the production send completed. A `FAILED` line includes the exit code and means no later script steps completed.

## Outputs

- Raw articles: `data/raw/YYYY-MM-DD.json`
- Processed newsletter content: `data/processed/YYYY-MM-DD.json`
- Formatted MJML email: `data/formatted/YYYY-MM-DD.mjml`
- Formatted HTML email: `data/formatted/YYYY-MM-DD.html`
