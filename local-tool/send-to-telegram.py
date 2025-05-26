import os
import json
import argparse
import telegram
from telegram.ext import Updater
import asyncio
from dotenv import load_dotenv
import openai
import PyPDF2
import google.generativeai as genai
import re
import glob

load_dotenv()


OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")


async def send_to_telegram(token, chat_id, summaries_dir, downloads_dir):
    """Send summaries and files to Telegram channel"""
    try:
        bot = telegram.Bot(token=token)

        # Load concalls data
        try:
            with open("concalls_data.json", "r") as f:
                concalls = json.load(f)
        except FileNotFoundError:
            print("Concalls data file not found.")
            return False

        # Check summaries directory
        if not os.path.exists(summaries_dir):
            print(f"Summaries directory '{summaries_dir}' not found.")
            return False

        # Check downloads directory
        if not os.path.exists(downloads_dir):
            print(f"Downloads directory '{downloads_dir}' not found.")
            return False

        # Get list of summary files
        summary_files = [
            f for f in os.listdir(summaries_dir) if f.endswith("_summary.md")
        ]
        if not summary_files:
            print("No summary files found.")
            return False

        print(f"Found {len(summary_files)} summary files.")

        # Send a welcome message
        await bot.send_message(
            chat_id=chat_id,
            text=f"📊 *Daily Concall Summaries*\n\nSending {len(summary_files)} investment summaries from recent concalls.",
            parse_mode="Markdown",
        )

        # Process each summary
        for summary_file in summary_files:
            # Extract company name from filename
            company_name = summary_file.split("_")[0].replace("_", " ")

            # Read the summary
            with open(os.path.join(summaries_dir, summary_file), "r") as f:
                summary_text = f.read()

            # Extract the first 3900 characters (Telegram message limit)
            message_text = summary_text[:3900]
            if len(summary_text) > 3900:
                message_text += "...\n\n(Summary truncated due to length. See attached file for complete summary.)"

            # Send the summary text
            await bot.send_message(
                chat_id=chat_id, text=message_text, parse_mode="Markdown"
            )

            # Send the full summary file
            with open(os.path.join(summaries_dir, summary_file), "rb") as f:
                await bot.send_document(
                    chat_id=chat_id,
                    document=f,
                    filename=summary_file,
                    caption=f"{company_name} - Complete Investment Summary",
                )

            # Find and send the corresponding PDF files
            for concall in concalls:
                if company_name.lower() in concall["company_name"].lower():
                    # Find corresponding files in downloads directory
                    for filename in os.listdir(downloads_dir):
                        if concall["company_name"].replace(" ", "_") in filename:
                            # Send the PDF file
                            with open(os.path.join(downloads_dir, filename), "rb") as f:
                                await bot.send_document(
                                    chat_id=chat_id,
                                    document=f,
                                    filename=filename,
                                    caption=f"{concall['company_name']} - Original Document",
                                )

            # Add a delay to avoid hitting rate limits
            await asyncio.sleep(1)

        # Send a completion message
        await bot.send_message(
            chat_id=chat_id,
            text="✅ *All concall summaries and files have been sent.*\n\nUse these investment insights for your decision-making process.",
            parse_mode="Markdown",
        )

        return True

    except Exception as e:
        print(f"Error sending to Telegram: {e}")
        return False


async def send_hello_world(token, chat_id):
    """Send a 'Hello, world!' message to the specified Telegram chat."""
    try:
        bot = telegram.Bot(token=token)
        await bot.send_message(chat_id=chat_id, text="Hello, world! 👋")
        print("Sent 'Hello, world!' message successfully.")
        return True
    except Exception as e:
        print(f"Error sending 'Hello, world!' message: {e}")
        return False


def extract_text_from_pdf(pdf_path):
    """Extracts all text from a PDF file."""
    with open(pdf_path, "rb") as f:
        reader = PyPDF2.PdfReader(f)
        text = ""
        for page in reader.pages:
            text += page.extract_text() or ""
    return text


def summarize_text_with_openai(text, max_tokens=10000):
    """Summarizes the given text using OpenAI."""
    client = openai.OpenAI(api_key=OPENAI_API_KEY)
    prompt = (
        "summarise the concall or investor presentation useful for investors as bullet points in markup: also include industry tailwinds or headwinds., "
        + f"{text}"
    )
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=max_tokens,
        temperature=0.3,
    )
    return response.choices[0].message.content.strip()


def summarize_text_with_gemini(text, max_tokens=20000):
    """Summarizes the given text using Gemini."""
    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY not set in environment variables.")

    genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

    model = genai.GenerativeModel("models/gemini-1.5-pro-002")
    prompt = (
        "start with company introduction.creat crisp summary of the following concall or investor presentation as bullet points useful for investors. include industry tailwinds or headwinds. shrink to 6000 characters or less."
        "Use Newline for formatting."
        f"{text}"
    )
    response = model.generate_content(prompt)
    return response.text.strip()


def summarize_pdf(pdf_path):
    text = extract_text_from_pdf(pdf_path)
    # Optionally truncate if text is very long (Gemini context limit is ~32k tokens)

    summary = summarize_text_with_gemini(text)
    return summary


async def send_message_and_file(
    token, chat_id, message, file_path, file_caption=None, parse_mode="Markdown"
):
    """
    Sends a message and a file attachment to a Telegram chat.
    :param token: Telegram bot token
    :param chat_id: Telegram chat ID
    :param message: Text message to send
    :param file_path: Path to the file to send
    :param file_caption: Optional caption for the file
    :param parse_mode: Parse mode for the message (default: Markdown)
    """
    try:
        bot = telegram.Bot(token=token)
        # Send the message
        for chunk in split_message(message):
            await bot.send_message(
                chat_id=chat_id,
                text=escape_markdown(chunk),
                parse_mode="MarkdownV2",
            )
            await asyncio.sleep(0.5)  # avoid rate limits
        # Send the file
        with open(file_path, "rb") as f:
            await bot.send_document(
                chat_id=chat_id,
                document=f,
                filename=os.path.basename(file_path),
                caption=escape_markdown(file_caption) if file_caption else None,
                parse_mode="MarkdownV2",
            )
        print(f"Sent message and file '{file_path}' successfully.")
        return True
    except Exception as e:
        print(f"Error sending message and file: {e}")
        return False


def escape_markdown(text):
    """
    Escape special characters for Telegram MarkdownV2, excluding intentional Markdown syntax.
    """
    if not text:
        return ""
    return re.sub(
        r"([_*\[\]()~`>#+\-=|{}.!])", r"\\\1", text
    )  # Escape special characters for MarkdownV2


def split_message(text, chunk_size=3900):
    """Split text into chunks of at most chunk_size characters, preserving line breaks."""
    lines = text.splitlines(keepends=True)
    chunks = []
    current = ""
    for line in lines:
        if len(current) + len(line) > chunk_size:
            chunks.append(current)
            current = ""
        current += line
    if current:
        chunks.append(current)
    return chunks


if __name__ == "__main__":
    pdf_folder = "/Users/fakrudeen/Downloads/WhatsApp and Telegram for Indian Stock Research Reports/local-tool/pdf"
    pdf_files = glob.glob(os.path.join(pdf_folder, "*.pdf"))

    if not pdf_files:
        print("No PDF files found in the folder.")
    else:
        for pdf_file in pdf_files:
            print(f"Processing: {pdf_file}")
            summary = summarize_pdf(pdf_file)
            print("Summary:\n", summary)
            # Use the PDF filename (without extension) as caption
            file_caption = os.path.splitext(os.path.basename(pdf_file))[0]
            asyncio.run(
                send_message_and_file(
                    token=TELEGRAM_BOT_TOKEN,
                    chat_id=TELEGRAM_CHAT_ID,
                    message=summary,
                    file_path=pdf_file,
                    file_caption=pdf_file.split("/")[
                        -1
                    ],  # Use the full filename as caption
                )
            )
            # Optional: add a delay to avoid Telegram rate limits
            import time

            time.sleep(2)
