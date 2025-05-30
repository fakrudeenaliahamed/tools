import os
import re
from flask import (
    Blueprint,
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    session,
)
import openai
from airtable import Airtable
from dotenv import load_dotenv

notes_bp = Blueprint("notes", __name__, template_folder="templates")

# Load environment variables from .env file
load_dotenv()

# --- Configuration ---
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
AIRTABLE_BASE_ID = os.getenv("AIRTABLE_BASE_ID")
AIRTABLE_TABLE_NAME = os.getenv("AIRTABLE_TABLE_NAME")
AIRTABLE_API_KEY = os.getenv("AIRTABLE_API_KEY")

# --- Initialize Services ---
try:
    openai.api_key = OPENAI_API_KEY
except Exception as e:
    print(f"Error configuring OpenAI API: {e}")

try:
    airtable = Airtable(AIRTABLE_BASE_ID, AIRTABLE_TABLE_NAME, api_key=AIRTABLE_API_KEY)
except Exception as e:
    print(f"Error configuring Airtable: {e}")
    airtable = None


# --- Helper Functions ---
def openai_chat(prompt, max_tokens=4000, temperature=0.5):
    try:
        client = openai.OpenAI(api_key=OPENAI_API_KEY)
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
            temperature=temperature,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"Error communicating with OpenAI: {e}")
        flash(f"Error communicating with OpenAI: {e}", "error")
        return None


def process_with_openai(text_content):
    """
    Sends content to OpenAI to get HTML formatting.
    Returns html_output or None on error.
    """
    prompt = f"""
Convert the following notes into clean, readable, semantically correct HTML for web display.

Instructions:
- Use <p>, <h1>-<h3>, <ul>, <ol>, <li>, <strong>, <em> as appropriate.
- For code, use <pre><code> (add language class if possible), preserve formatting, and escape HTML chars.
- For lists, use <ul> or <ol>.
- Wrap URLs in <a> tags.
- Use <hr> for clear section breaks.
- Do not include <html>, <head>, or <body> tags.
- Do not omit any content.

Notes:
{text_content}
"""
    html_output = openai_chat(prompt)
    if not html_output:
        return None, None
    return html_output, None


def summarize_with_openai(html_content_to_summarize):
    """
    Sends HTML content to OpenAI to get a summary as bullet points.
    Returns summary text or None on error.
    """
    text_for_summary = re.sub("<[^<]+?>", "", html_content_to_summarize)
    text_for_summary = text_for_summary[:10000]

    prompt = f"""
Summarize the following text as concise bullet points (one point per line, no numbering, no extra text):

---
{text_for_summary}
---
"""
    return openai_chat(prompt, max_tokens=200)


def generate_note_from_title_with_openai(title_for_note):
    """
    Generates initial note content based on a title using OpenAI.
    Returns generated text content or None on error.
    """
    prompt = f"""
You are a helpful assistant. Please generate a short draft for a note based on the following title.
The content should be a few paragraphs, suitable for a starting point.
Do not include any HTML formatting in this initial draft.
Just provide the raw text content.

TITLE: "{title_for_note}"

DRAFT CONTENT:
"""
    return openai_chat(prompt, max_tokens=10000)


def generate_title_with_openai(note_content):
    """
    Generates a concise, relevant title for a note using OpenAI, max 100 chars.
    """
    prompt = f"""
Given the following note content, generate a concise and relevant title (max 100 characters, no quotes):

Content:
{note_content}
"""
    title = openai_chat(prompt, max_tokens=30)
    if title:
        return title.strip()[:100]
    return title


def get_all_categories():
    """Return the list of categories for the dropdown."""
    return ["aws", "kubernetes", "networking"]


# --- Flask Routes ---
@notes_bp.route("/", methods=["GET", "POST"])
def index():
    if not airtable:
        flash("Airtable not configured. Cannot fetch or save notes.", "error")
        return render_template("notes_index.html", notes=[])

    if request.method == "POST":
        title = request.form.get("title")
        content = request.form.get("content")
        category = request.form.get("category") or "Default"

        if not content:
            flash("Content is required for manual note.", "error")
            return redirect(url_for("notes.index"))

        if not title:
            # Auto-generate title if not provided
            title = generate_title_with_openai(content)
            if not title:
                flash("Failed to generate title.", "error")
                return redirect(url_for("notes.index"))
            title = title[:100]

        html_content, _ = process_with_openai(content)
        if html_content is None:
            return redirect(url_for("notes.index"))

        try:
            note_data = {
                "Title": title,
                "HTMLContent": html_content,
                "Category": category,
            }
            airtable.insert(note_data)
            flash("Note saved successfully!", "success")
        except Exception as e:
            print(f"Error saving to Airtable: {e}")
            flash(f"Error saving note to Airtable: {e}", "error")
        return redirect(url_for("notes.index"))

    # Search/filter logic
    category_query = request.args.get("category", "")
    notes_to_display = []
    try:
        formula = ""
        if category_query:
            escaped_category = category_query.replace("'", "\\'")
            formula = f"{{Category}} = '{escaped_category}'"
        all_notes_raw = airtable.get_all(formula=formula, sort=[("CreatedAt", "desc")])
        for record in all_notes_raw:
            notes_to_display.append({"id": record["id"], **record.get("fields", {})})
        if category_query and not notes_to_display:
            flash(f"No notes found in category '{category_query}'.", "info")
    except Exception as e:
        print(f"Error fetching notes from Airtable: {e}")
        flash(f"Error fetching notes: {e}", "error")
        notes_to_display = []

    all_categories = get_all_categories()
    return render_template(
        "notes_index.html",
        notes=notes_to_display,
        category_query=category_query,
        all_categories=all_categories,
    )


@notes_bp.route("/generate_note", methods=["POST"])
def generate_note_route():
    if not airtable or not OPENAI_API_KEY:
        flash("Airtable or OpenAI API not configured.", "error")
        return redirect(url_for("notes.index"))

    title = request.form.get("generate_title")
    category = request.form.get("category") or "Default"
    if not title:
        flash("Title is required to generate a note.", "error")
        return redirect(url_for("notes.index"))

    draft_content = generate_note_from_title_with_openai(title)
    if not draft_content:
        return redirect(url_for("notes.index"))

    html_content, _ = process_with_openai(draft_content)
    if html_content is None:
        flash("Failed to process the generated content from OpenAI.", "error")
        return redirect(url_for("notes.index"))

    try:
        note_data = {
            "Title": title,
            "HTMLContent": html_content,
            "Category": category,
        }
        airtable.insert(note_data)
        flash(f"Note '{title}' generated and saved successfully! ✨", "success")
    except Exception as e:
        print(f"Error saving generated note to Airtable: {e}")
        flash(f"Error saving generated note to Airtable: {e}", "error")

    return redirect(url_for("notes.index"))


@notes_bp.route("/note/<note_id>", methods=["GET", "POST"])
def view_note(note_id):
    if not airtable:
        flash("Airtable not configured. Cannot fetch note.", "error")
        return redirect(url_for("notes.index"))

    summary = session.pop(f"summary_{note_id}", None)

    if request.method == "POST":
        if not OPENAI_API_KEY:
            flash("OpenAI API not configured for summarization.", "error")
        else:
            try:
                record = airtable.get(note_id)
                if record and "fields" in record and "HTMLContent" in record["fields"]:
                    html_to_summarize = record["fields"]["HTMLContent"]
                    summary_text = summarize_with_openai(html_to_summarize)
                    if summary_text:
                        session[f"summary_{note_id}"] = summary_text
                        flash("Summary generated! ✨", "success")
                else:
                    flash("Note content not found for summarization.", "error")
            except Exception as e:
                print(f"Error during summarization route: {e}")
                flash(f"Error generating summary: {e}", "error")
        return redirect(url_for("notes.view_note", note_id=note_id))

    try:
        record = airtable.get(note_id)
        if record and "fields" in record:
            note = {"id": record["id"], **record["fields"]}

            # Fetch latest notes for sidebar
            latest_notes = []
            try:
                all_notes_raw = airtable.get_all(
                    sort=[("CreatedAt", "desc")], maxRecords=5
                )
                for record in all_notes_raw:
                    if record["id"] != note_id:
                        latest_notes.append(
                            {"id": record["id"], **record.get("fields", {})}
                        )
            except Exception as e:
                latest_notes = []

            return render_template(
                "view_note.html", note=note, summary=summary, latest_notes=latest_notes
            )
        else:
            flash("Note not found.", "error")
            return redirect(url_for("notes.index"))
    except Exception as e:
        print(f"Error fetching note {note_id} from Airtable: {e}")
        flash(f"Error fetching note: {e}", "error")
        return redirect(url_for("notes.index"))
