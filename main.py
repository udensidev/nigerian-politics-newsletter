import argparse
from typing import Optional

from agents.collector import Collector
from agents.editor import Editor
from agents.formatter import Formatter
from agents.sender import NewsletterTestSender


def run_pipeline() -> Optional[str]:
    """
    Run the full Nigerian Politics Newsletter pipeline.
    """
    print("Starting the Nigerian Politics Newsletter pipeline...")
    
    # 1. Collect
    collector = Collector()
    articles = collector.run()
    print(f"Collector finished. Collected {len(articles)} articles.")
    if not articles:
        print("No articles collected. Stopping before editor and formatter.")
        return None
    
    # 2. Edit
    editor = Editor()
    processed_path = editor.run()
    if not processed_path:
        print("Editor produced no output. Stopping before formatter.")
        return None
    print(f"Editor finished. Processed output: {processed_path}")
    
    # 3. Format
    formatter = Formatter(processed_path)
    html_path = formatter.run()
    print(f"Formatter finished. HTML output: {html_path}")
    
    print("Pipeline finished successfully.")
    return html_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Nigerian Politics Newsletter pipeline.")
    parser.add_argument(
        "--send-test",
        action="store_true",
        help="Send the generated newsletter to NEWSLETTER_TEST_RECIPIENT after a successful pipeline run.",
    )
    parser.add_argument(
        "--send-production",
        action="store_true",
        help="Send the generated newsletter to NEWSLETTER_RECIPIENTS after a successful pipeline run.",
    )
    parser.add_argument(
        "--confirm-production",
        action="store_true",
        help="Required with --send-production to confirm a real subscriber send.",
    )
    args = parser.parse_args()

    if args.send_test and args.send_production:
        parser.error("--send-test and --send-production cannot be used together.")

    if args.confirm_production and not args.send_production:
        parser.error("--confirm-production can only be used with --send-production.")

    if args.send_production and not args.confirm_production:
        parser.error("--send-production requires --confirm-production.")

    html_path = run_pipeline()
    if not html_path:
        if args.send_test or args.send_production:
            print("No formatted newsletter output produced. Skipping send.")
        return

    if args.send_test or args.send_production:
        recipients = NewsletterTestSender(
            html_path,
            production=args.send_production,
            confirm_production=args.confirm_production,
        ).run()
        if args.send_production:
            print(f"Production newsletter sent to {len(recipients)} recipients.")
        else:
            print(f"Test newsletter sent to: {recipients[0]}")

if __name__ == "__main__":
    main()
