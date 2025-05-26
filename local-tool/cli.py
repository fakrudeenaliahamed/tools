#!/usr/bin/env python3
"""
YouTube Transcript to Gemini Summary - Command Line Interface

This script provides a command-line interface for downloading YouTube transcripts
and generating summaries using the Gemini AI model.
"""

import os
import argparse
import textwrap
import re

from youtube_transcript_summarizer import (
    summarize_youtube_video,
    send_to_telegram,
)
from dotenv import load_dotenv

load_dotenv()


def main():
    parser = argparse.ArgumentParser(
        description="Download YouTube transcript and generate summary using Gemini AI",
        formatter_class=argparse.RawTextHelpFormatter,
    )

    parser.add_argument("youtube_url", help="YouTube video URL")

    parser.add_argument(
        "--api-key",
        "-k",
        help="Gemini API key (can also be set via GEMINI_API_KEY environment variable)",
    )

    parser.add_argument(
        "--proxy-username",
        "-u",
        help="Proxy username (can also be set via PROXY_USERNAME environment variable)",
    )

    parser.add_argument(
        "--proxy-password",
        "-p",
        help="Proxy password (can also be set via PROXY_PASSWORD environment variable)",
    )

    parser.add_argument("--proxy-host", help="Proxy host (for generic proxy)")

    parser.add_argument("--proxy-port", type=int, help="Proxy port (for generic proxy)")

    parser.add_argument(
        "--language",
        "-l",
        default="en",
        help="Language code for transcript (default: en)",
    )

    parser.add_argument(
        "--output",
        "-o",
        help="Output file to save summary (if not specified, prints to console)",
    )

    parser.add_argument(
        "--save-transcript", "-t", help="File to save transcript (optional)"
    )

    args = parser.parse_args()

    # Get API key from args or environment variable
    api_key = args.api_key or os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print(
            "Error: Gemini API key is required. Provide it with --api-key or set GEMINI_API_KEY environment variable."
        )
        return 1

    # Get proxy credentials from args or environment variables
    proxy_username = args.proxy_username or os.environ.get("PROXY_USERNAME")
    proxy_password = args.proxy_password or os.environ.get("PROXY_PASSWORD")

    # Get transcript and summary
    transcript, summary = summarize_youtube_video(
        args.youtube_url,
        api_key,
        language=args.language,
        proxy_username=proxy_username,
        proxy_password=proxy_password,
        proxy_host=args.proxy_host,
        proxy_port=args.proxy_port,
    )

    if not transcript or not summary:
        print("Failed to generate summary.")
        return 1

    # Save transcript if requested
    if args.save_transcript:
        try:
            with open(args.save_transcript, "w", encoding="utf-8") as f:
                f.write(transcript)
            print(f"Transcript saved to: {args.save_transcript}")
        except Exception as e:
            print(f"Error saving transcript: {e}")

    # Save or print summary
    if args.output:
        try:
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(summary)
            print(f"Summary saved to: {args.output}")
        except Exception as e:
            print(f"Error saving summary: {e}")
    else:
        print("\n=== SUMMARY ===\n")
        print(summary)

    # Send to Telegram if credentials are available
    telegram_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    telegram_chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if telegram_token and telegram_chat_id:
        # send_to_telegram(
        #     escape_markdown("=== TRANSCRIPT ===\n" + transcript),
        #     telegram_token,
        #     telegram_chat_id,
        # )
        send_to_telegram(
            "=== SUMMARY ===\n" + summary,
            telegram_token,
            telegram_chat_id,
        )
        print("Sent transcript and summary to Telegram.")
    else:
        print(
            "TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set in environment variables."
        )

    return 0


if __name__ == "__main__":
    exit(main())
