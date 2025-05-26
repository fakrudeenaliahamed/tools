"""
YouTube Transcript Downloader and Gemini Summarizer

This script downloads English transcripts from YouTube videos and uses Google's Gemini model
to generate detailed summaries.

Note: YouTube blocks requests from cloud environments. To work around this limitation,
you need to use a proxy service like Webshare (https://www.webshare.io/).

You will also need a Google API key for Gemini. Get one at: https://ai.google.dev/
"""

import re
import os
import textwrap
import langdetect
import telegram
import asyncio
from youtube_transcript_api import (
    YouTubeTranscriptApi,
    TranscriptsDisabled,
    NoTranscriptFound,
)
from youtube_transcript_api.proxies import WebshareProxyConfig, GenericProxyConfig
import google.generativeai as genai


def extract_video_id(youtube_url):
    """
    Extract the video ID from a YouTube URL.

    Args:
        youtube_url (str): The YouTube video URL

    Returns:
        str: The YouTube video ID or None if not found
    """
    # Regular expressions to match different YouTube URL formats
    patterns = [
        r"(?:v=|\/)([0-9A-Za-z_-]{11}).*",  # Standard YouTube URLs
        r"(?:embed\/)([0-9A-Za-z_-]{11})",  # Embedded URLs
        r"(?:youtu\.be\/)([0-9A-Za-z_-]{11})",  # Shortened youtu.be URLs
    ]

    for pattern in patterns:
        match = re.search(pattern, youtube_url)
        if match:
            return match.group(1)

    return None


def verify_english_text(text):
    """
    Verify if the text is in English.

    Args:
        text (str): The text to verify

    Returns:
        bool: True if the text is in English, False otherwise
    """
    try:
        # Use a sample of the text for language detection
        sample_text = text[:1000] if len(text) > 1000 else text
        detected_lang = langdetect.detect(sample_text)
        return detected_lang == "en"
    except:
        # If language detection fails, assume it's not English
        return False


def clean_transcript(transcript_text):
    """
    Clean the transcript text by removing unnecessary characters and formatting.

    Args:
        transcript_text (str): The raw transcript text

    Returns:
        str: The cleaned transcript text
    """
    # Remove HTML tags if any
    transcript_text = re.sub(r"<[^>]+>", "", transcript_text)

    # Remove multiple spaces
    transcript_text = re.sub(r"\s+", " ", transcript_text)

    # Remove special characters that might interfere with summarization
    transcript_text = re.sub(r"[\r\n\t]", " ", transcript_text)

    # Trim leading and trailing whitespace
    transcript_text = transcript_text.strip()

    return transcript_text


def get_transcript(
    video_id,
    language="en",
    proxy_username=None,
    proxy_password=None,
    proxy_host=None,
    proxy_port=None,
):
    """
    Get the transcript for a YouTube video in the specified language.

    Args:
        video_id (str): The YouTube video ID
        language (str): The language code (default: 'en' for English)
        proxy_username (str, optional): Username for proxy authentication
        proxy_password (str, optional): Password for proxy authentication
        proxy_host (str, optional): Proxy host address
        proxy_port (int, optional): Proxy port number

    Returns:
        str: The transcript text or None if not available
    """
    try:
        # Configure proxy if credentials are provided
        if proxy_username and proxy_password:
            if proxy_host and proxy_port:
                # Use generic proxy configuration
                proxy_config = GenericProxyConfig(
                    proxy_username=proxy_username,
                    proxy_password=proxy_password,
                    proxy_host=proxy_host,
                    proxy_port=proxy_port,
                )
            else:
                # Use Webshare proxy configuration (recommended)
                proxy_config = WebshareProxyConfig(
                    proxy_username=proxy_username, proxy_password=proxy_password
                )

            # Initialize API with proxy
            transcript_api = YouTubeTranscriptApi(proxy_config=proxy_config)
        else:
            # Initialize API without proxy (may fail in cloud environments)
            transcript_api = YouTubeTranscriptApi()

        # List available transcripts
        transcript_list = transcript_api.list(video_id)

        # Try to get the transcript in the specified language
        try:
            transcript = transcript_list.find_transcript([language])
        except NoTranscriptFound:
            # If no transcript in specified language, try to get any transcript and translate it
            try:
                transcript = transcript_list.find_transcript(
                    []
                )  # Get any available transcript
                transcript = transcript.translate(
                    language
                )  # Translate to specified language
            except Exception as e:
                print(f"Error translating transcript: {e}")
                return None

        # Fetch the transcript data
        fetched_transcript = transcript.fetch()

        # Combine all text parts into a single string
        transcript_text = " ".join([snippet.text for snippet in fetched_transcript])

        # Clean the transcript
        transcript_text = clean_transcript(transcript_text)

        # Verify if the transcript is in English
        if language == "en" and not verify_english_text(transcript_text):
            print(
                "Warning: The transcript does not appear to be in English. Attempting translation..."
            )
            try:
                # Try to get any transcript and translate it to English
                any_transcript = transcript_list.find_transcript([])
                translated_transcript = any_transcript.translate("en")
                fetched_translated = translated_transcript.fetch()
                transcript_text = " ".join(
                    [snippet.text for snippet in fetched_translated]
                )
                transcript_text = clean_transcript(transcript_text)

                # Verify again
                if not verify_english_text(transcript_text):
                    print(
                        "Warning: Translation may not be accurate. Proceeding with best effort."
                    )
            except Exception as e:
                print(f"Error during translation attempt: {e}")

        return transcript_text

    except TranscriptsDisabled:
        print(f"Transcripts are disabled for video ID: {video_id}")
        return None
    except NoTranscriptFound:
        print(f"No transcript found for video ID: {video_id}")
        return None
    except Exception as e:
        print(f"Error retrieving transcript: {e}")
        return None


def download_transcript(
    youtube_url,
    language="en",
    proxy_username=None,
    proxy_password=None,
    proxy_host=None,
    proxy_port=None,
):
    """
    Download the transcript for a YouTube video URL.

    Args:
        youtube_url (str): The YouTube video URL
        language (str): The language code (default: 'en' for English)
        proxy_username (str, optional): Username for proxy authentication
        proxy_password (str, optional): Password for proxy authentication
        proxy_host (str, optional): Proxy host address (for generic proxy)
        proxy_port (int, optional): Proxy port number (for generic proxy)

    Returns:
        str: The transcript text or None if not available
    """
    video_id = extract_video_id(youtube_url)

    if not video_id:
        print(f"Invalid YouTube URL: {youtube_url}")
        return None

    return get_transcript(
        video_id, language, proxy_username, proxy_password, proxy_host, proxy_port
    )


def chunk_text(text, max_chunk_size=8000):
    """
    Split text into chunks of approximately equal size, trying to preserve sentence boundaries.

    Args:
        text (str): The text to split
        max_chunk_size (int): Maximum size of each chunk in characters

    Returns:
        list: List of text chunks
    """
    # If text is shorter than max_chunk_size, return it as is
    if len(text) <= max_chunk_size:
        return [text]

    # Split text into sentences
    sentences = re.split(r"(?<=[.!?])\s+", text)

    chunks = []
    current_chunk = ""

    for sentence in sentences:
        # If adding this sentence would exceed max_chunk_size
        if len(current_chunk) + len(sentence) > max_chunk_size:
            # If current_chunk is not empty, add it to chunks
            if current_chunk:
                chunks.append(current_chunk)
                current_chunk = ""

            # If the sentence itself is longer than max_chunk_size, split it
            if len(sentence) > max_chunk_size:
                # Split the sentence into words
                words = sentence.split()
                temp_chunk = ""

                for word in words:
                    if len(temp_chunk) + len(word) + 1 > max_chunk_size:
                        chunks.append(temp_chunk)
                        temp_chunk = word
                    else:
                        if temp_chunk:
                            temp_chunk += " " + word
                        else:
                            temp_chunk = word

                if temp_chunk:
                    current_chunk = temp_chunk
            else:
                current_chunk = sentence
        else:
            # Add the sentence to the current chunk
            if current_chunk:
                current_chunk += " " + sentence
            else:
                current_chunk = sentence

    # Add the last chunk if it's not empty
    if current_chunk:
        chunks.append(current_chunk)

    return chunks


def configure_gemini(api_key):
    """
    Configure the Gemini API with the provided API key.

    Args:
        api_key (str): The Gemini API key

    Returns:
        bool: True if configuration was successful, False otherwise
    """
    try:
        genai.configure(api_key=api_key)
        return True
    except Exception as e:
        print(f"Error configuring Gemini API: {e}")
        return False


def generate_summary(transcript_text, api_key, model_name="gemini-1.5-pro"):
    """
    Generate a detailed summary of the transcript using Gemini.

    Args:
        transcript_text (str): The transcript text to summarize
        api_key (str): The Gemini API key
        model_name (str): The Gemini model to use

    Returns:
        str: The generated summary or None if an error occurred
    """
    if not transcript_text:
        print("No transcript text provided for summarization.")
        return None

    # Configure Gemini API
    if not configure_gemini(api_key):
        return None

    try:
        # Initialize the model
        model = genai.GenerativeModel(model_name)

        # Split transcript into chunks if it's too large
        chunks = chunk_text(transcript_text)

        if len(chunks) == 1:
            # If there's only one chunk, generate summary directly
            prompt = f"""
            Please provide a detailed summary of the following transcript from a YouTube video:
            
            {transcript_text}
            
            Your summary should:
            1. Capture all key points and main ideas
            2. Include important details, examples, and explanations
            3. Maintain the logical flow and structure of the original content
            4. Be comprehensive and thorough
            5. Be well-organized with clear sections if appropriate
            
            Please provide a detailed summary that would help someone understand the full content without watching the video.
            """

            response = model.generate_content(prompt)
            return response.text
        else:
            # For multiple chunks, process each chunk and then combine
            print(f"Transcript is large, processing in {len(chunks)} chunks...")

            chunk_summaries = []
            for i, chunk in enumerate(chunks):
                print(f"Processing chunk {i+1}/{len(chunks)}...")

                chunk_prompt = f"""
                This is part {i+1} of {len(chunks)} of a transcript from a YouTube video.
                Please provide a detailed summary of this part:
                
                {chunk}
                
                Your summary should:
                1. Capture all key points and main ideas in this section
                2. Include important details, examples, and explanations
                3. Maintain the logical flow and structure of this section
                4. Be comprehensive and thorough
                """

                try:
                    chunk_response = model.generate_content(chunk_prompt)
                    chunk_summaries.append(chunk_response.text)
                except Exception as e:
                    print(f"Error generating summary for chunk {i+1}: {e}")
                    chunk_summaries.append(f"[Error summarizing part {i+1}]")

            # Combine chunk summaries
            combined_prompt = f"""
            Below are summaries of different parts of a YouTube video transcript.
            Please integrate these summaries into a single coherent and detailed summary:
            
            {' '.join([f'Part {i+1}: {summary}' for i, summary in enumerate(chunk_summaries)])}
            
            Your final summary should:
            1. Combine all the information from the different parts
            2. Eliminate redundancies while preserving all unique information
            3. Create a cohesive narrative that flows logically
            4. Be comprehensive, detailed, and well-structured
            5. Include sections or headings if appropriate
            """

            final_response = model.generate_content(combined_prompt)
            return final_response.text

    except Exception as e:
        print(f"Error generating summary: {e}")
        return None


def send_to_telegram(message, bot_token, chat_id):
    async def _send():
        bot = telegram.Bot(token=bot_token)
        # Telegram message limit is 4096 chars, so split if needed
        for i in range(0, len(message), 3900):
            await bot.send_message(
                chat_id=chat_id,
                text=escape_markdown(message[i : i + 3900]),
                parse_mode="MarkdownV2",
            )

    asyncio.run(_send())


def summarize_youtube_video(
    youtube_url,
    api_key,
    language="en",
    proxy_username=None,
    proxy_password=None,
    proxy_host=None,
    proxy_port=None,
):
    """
    Download transcript from a YouTube video and generate a detailed summary.

    Args:
        youtube_url (str): The YouTube video URL
        api_key (str): The Gemini API key
        language (str): The language code (default: 'en' for English)
        proxy_username (str, optional): Username for proxy authentication
        proxy_password (str, optional): Password for proxy authentication
        proxy_host (str, optional): Proxy host address (for generic proxy)
        proxy_port (int, optional): Proxy port number (for generic proxy)

    Returns:
        tuple: (transcript, summary) or (None, None) if an error occurred
    """
    # Download transcript
    transcript = download_transcript(
        youtube_url, language, proxy_username, proxy_password, proxy_host, proxy_port
    )

    if not transcript:
        return None, None

    # Generate summary
    summary = generate_summary(transcript, api_key)

    return transcript, summary


def escape_markdown(text):
    """
    Escape all Telegram MarkdownV2 special characters.
    """
    if not text:
        return ""
    escape_chars = r"_*[]()~`>#+-=|{}.!"
    import re

    return re.sub(r"([%s])" % re.escape(escape_chars), r"\\\1", text)


# Example usage
if __name__ == "__main__":
    # Test with a sample YouTube URL
    test_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"  # Replace with an actual video URL

    # Replace with your actual API key
    api_key = os.environ.get("GEMINI_API_KEY", "your_gemini_api_key")

    # Replace with your actual proxy credentials
    proxy_username = os.environ.get("PROXY_USERNAME", "your_proxy_username")
    proxy_password = os.environ.get("PROXY_PASSWORD", "your_proxy_password")

    # For Webshare proxy (recommended)
    transcript, summary = summarize_youtube_video(
        test_url, api_key, proxy_username=proxy_username, proxy_password=proxy_password
    )

    if transcript and summary:
        print("\n=== TRANSCRIPT ===")
        print(textwrap.shorten(transcript, width=100, placeholder="..."))
        print("\n=== SUMMARY ===")
        print(summary)

        telegram_token = os.environ.get("TELEGRAM_BOT_TOKEN")
        telegram_chat_id = os.environ.get("TELEGRAM_CHAT_ID")
        if telegram_token and telegram_chat_id:
            send_to_telegram(
                "=== TRANSCRIPT ===\n" + transcript, telegram_token, telegram_chat_id
            )
            send_to_telegram(
                "=== SUMMARY ===\n" + summary, telegram_token, telegram_chat_id
            )
            print("Sent transcript and summary to Telegram.")
        else:
            print(
                "TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set in environment variables."
            )
    else:
        print("Failed to generate summary.")
