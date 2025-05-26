"""
YouTube Transcript Downloader and Gemini Summarizer

This script downloads English transcripts from YouTube videos and uses Google's Gemini model
to generate detailed summaries.

Note: YouTube blocks requests from cloud environments. To work around this limitation,
you need to use a proxy service like Webshare (https://www.webshare.io/).
"""

import re
import langdetect
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound
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
        r'(?:v=|\/)([0-9A-Za-z_-]{11}).*',  # Standard YouTube URLs
        r'(?:embed\/)([0-9A-Za-z_-]{11})',  # Embedded URLs
        r'(?:youtu\.be\/)([0-9A-Za-z_-]{11})'  # Shortened youtu.be URLs
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
        return detected_lang == 'en'
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
    transcript_text = re.sub(r'<[^>]+>', '', transcript_text)
    
    # Remove multiple spaces
    transcript_text = re.sub(r'\s+', ' ', transcript_text)
    
    # Remove special characters that might interfere with summarization
    transcript_text = re.sub(r'[\r\n\t]', ' ', transcript_text)
    
    # Trim leading and trailing whitespace
    transcript_text = transcript_text.strip()
    
    return transcript_text

def get_transcript(video_id, language='en', proxy_username=None, proxy_password=None, proxy_host=None, proxy_port=None):
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
                    proxy_port=proxy_port
                )
            else:
                # Use Webshare proxy configuration (recommended)
                proxy_config = WebshareProxyConfig(
                    proxy_username=proxy_username,
                    proxy_password=proxy_password
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
                transcript = transcript_list.find_transcript([])  # Get any available transcript
                transcript = transcript.translate(language)  # Translate to specified language
            except Exception as e:
                print(f"Error translating transcript: {e}")
                return None
        
        # Fetch the transcript data
        fetched_transcript = transcript.fetch()
        
        # Combine all text parts into a single string
        transcript_text = ' '.join([snippet.text for snippet in fetched_transcript])
        
        # Clean the transcript
        transcript_text = clean_transcript(transcript_text)
        
        # Verify if the transcript is in English
        if language == 'en' and not verify_english_text(transcript_text):
            print("Warning: The transcript does not appear to be in English. Attempting translation...")
            try:
                # Try to get any transcript and translate it to English
                any_transcript = transcript_list.find_transcript([])
                translated_transcript = any_transcript.translate('en')
                fetched_translated = translated_transcript.fetch()
                transcript_text = ' '.join([snippet.text for snippet in fetched_translated])
                transcript_text = clean_transcript(transcript_text)
                
                # Verify again
                if not verify_english_text(transcript_text):
                    print("Warning: Translation may not be accurate. Proceeding with best effort.")
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

def download_transcript(youtube_url, language='en', proxy_username=None, proxy_password=None, proxy_host=None, proxy_port=None):
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
    
    return get_transcript(video_id, language, proxy_username, proxy_password, proxy_host, proxy_port)

# Example usage
if __name__ == "__main__":
    # Test with a sample YouTube URL
    test_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"  # Replace with an actual video URL
    
    # To use with proxy (required in cloud environments)
    # Replace with your actual proxy credentials
    proxy_username = "your_proxy_username"
    proxy_password = "your_proxy_password"
    
    # For Webshare proxy (recommended)
    transcript = download_transcript(
        test_url, 
        proxy_username=proxy_username, 
        proxy_password=proxy_password
    )
    
    # For generic proxy
    # transcript = download_transcript(
    #     test_url, 
    #     proxy_username=proxy_username, 
    #     proxy_password=proxy_password,
    #     proxy_host="your_proxy_host",
    #     proxy_port=your_proxy_port
    # )
    
    if transcript:
        print("Transcript downloaded successfully!")
        print(f"Transcript length: {len(transcript)} characters")
        print("First 200 characters of transcript:")
        print(transcript[:200] + "...")
    else:
        print("Failed to download transcript.")
