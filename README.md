# Nigerian Politics Newsletter Pipeline

An automated pipeline to collect, filter, and format news related to Nigerian politics into a daily newsletter.

## Setup Instructions

1. **Prerequisites**:
   - Python 3.10 or higher
   - Node.js and npm
   - A Google App Password if sending through Gmail SMTP
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
   To install test dependencies too:
   ```bash
   pip install -r requirements-dev.txt
   ```
4. **Configuration**:
   Copy `.env.example` to `.env` and configure your API keys.
   ```bash
   cp .env.example .env
   ```
   To enable the optional Gemini AI filter step, set `USE_AI_FILTER=true` and provide a valid `GEMINI_API_KEY`.

## Running the Pipeline

The examples below use macOS/Linux paths. On Windows, use `venv\Scripts\python` instead of `venv/bin/python`.

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
SMTP_FROM=you@example.com
SMTP_USERNAME=you@example.com
SMTP_PASSWORD=<google-app-password>
NEWSLETTER_TEST_RECIPIENT=you@example.com
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

## GitHub Actions Production Schedule

GitHub Actions is the recommended production scheduler. It runs on GitHub's infrastructure, so the newsletter does not depend on this computer being awake at 7:00 AM.

The workflow in `.github/workflows/daily-newsletter.yml` runs daily at 7:00 AM Central time and can also be started manually from the GitHub Actions tab with **Run workflow**. GitHub schedules are UTC-only, so the workflow has two UTC cron entries and skips whichever one is not 7:00 AM in `America/Chicago`.

Add these repository secrets before enabling production sends:

```text
GEMINI_API_KEY
USE_AI_FILTER
SMTP_HOST
SMTP_PORT
SMTP_FROM
SMTP_USERNAME
SMTP_PASSWORD
SMTP_USE_TLS
NEWSLETTER_RECIPIENTS
```

For Gmail, `SMTP_PASSWORD` must be a Google App Password. `SMTP_USERNAME` and `SMTP_PASSWORD` are optional only when your SMTP server does not require authentication. `SMTP_USE_TLS` defaults to `true` in the sender code when unset, but setting it explicitly in GitHub secrets keeps production behavior clear.

Each workflow run installs Python and Node dependencies, runs the test suite, sends the production newsletter with:

```bash
python main.py --send-production --confirm-production
```

The workflow uses Node 24-compatible GitHub action versions. The `node-version` setting in the workflow controls the project's Node runtime for `npm ci` and MJML, so it can remain pinned separately from the GitHub action runtime.

The workflow uploads generated logs and newsletter files as run artifacts. These files are not committed to the repository.

## Local Cron Fallback

The cron runner is available for macOS/Linux systems with local cron, but it is best treated as a fallback. Local cron will not run missed jobs if the computer is asleep at the scheduled time.

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

Only `data/feeds.json` is tracked in git. The pipeline creates output directories locally as needed, and generated data/log directories are ignored.

- Raw articles: `data/raw/YYYY-MM-DD.json`
- Processed newsletter content: `data/processed/YYYY-MM-DD.json`
- Formatted MJML email: `data/formatted/YYYY-MM-DD.mjml`
- Formatted HTML email: `data/formatted/YYYY-MM-DD.html`

Pipeline dates use UTC for input and output filenames.
