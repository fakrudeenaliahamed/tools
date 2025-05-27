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
            model="gpt-3.5-turbo",
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
    Sends content to OpenAI to get HTML formatting and tags.
    Returns a tuple (html_output, tags_string) or (None, None) on error.
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

After the HTML, on a new line, provide 3-5 relevant tags, prefixed with "TAGS: ".
"""
    full_response_text = openai_chat(prompt)
    if not full_response_text:
        return None, None

    html_output = full_response_text
    tags_string = ""

    tags_match = re.search(
        r"TAGS:\s*(.*)", full_response_text, re.IGNORECASE | re.DOTALL
    )
    if tags_match:
        tags_string = tags_match.group(1).strip()
        html_output = re.sub(
            r"TAGS:\s*(.*)", "", html_output, flags=re.IGNORECASE | re.DOTALL
        ).strip()
    else:
        lines = full_response_text.strip().split("\n")
        if (
            len(lines) > 1
            and "TAGS:" not in lines[-2]
            and not lines[-1].startswith("<")
        ):
            tags_string = lines[-1].strip()
            html_output = "\n".join(lines[:-1]).strip()

    return html_output, tags_string


def summarize_with_openai(html_content_to_summarize):
    """
    Sends HTML content to OpenAI to get a summary.
    Returns summary text or None on error.
    """
    text_for_summary = re.sub("<[^<]+?>", "", html_content_to_summarize)
    text_for_summary = text_for_summary[:10000]

    prompt = f"""
Please provide a concise summary (2-3 sentences) of the following text:
---
{text_for_summary}
---
"""
    return openai_chat(prompt, max_tokens=150)


def generate_note_from_title_with_openai(title_for_note):
    """
    Generates initial note content based on a title using OpenAI.
    Returns generated text content or None on error.
    """
    prompt = f"""
You are a helpful assistant. Please generate a short draft for a note based on the following title.
The content should be a few paragraphs, suitable for a starting point.
Do not include any "TAGS:" section or HTML formatting in this initial draft.
Just provide the raw text content.

TITLE: "{title_for_note}"

DRAFT CONTENT:
"""
    return openai_chat(prompt, max_tokens=10000)


# --- Flask Routes ---
@notes_bp.route("/", methods=["GET", "POST"])
def index():
    if not airtable:
        flash("Airtable not configured. Cannot fetch or save notes.", "error")
        return render_template("notes_index.html", notes=[])

    if request.method == "POST":
        title = request.form.get("title")
        content = request.form.get("content")

        if not title or not content:
            flash("Title and content are required for manual note.", "error")
            return redirect(url_for("notes.index"))

        html_content, tags = process_with_openai(content)
        if html_content is None:
            return redirect(url_for("notes.index"))

        try:
            note_data = {"Title": title, "HTMLContent": html_content, "Tags": tags}
            airtable.insert(note_data)
            flash("Note saved successfully!", "success")
        except Exception as e:
            print(f"Error saving to Airtable: {e}")
            flash(f"Error saving note to Airtable: {e}", "error")
        return redirect(url_for("notes.index"))

    search_query = request.args.get("search", "")
    notes_to_display = []
    try:
        formula_parts = []
        if search_query:
            escaped_query = search_query.replace("'", "\\'")
            formula_parts.append(f"FIND(LOWER('{escaped_query}'), LOWER(Title))")
            formula_parts.append(f"FIND(LOWER('{escaped_query}'), LOWER(Tags))")

        formula = ""
        if formula_parts:
            formula = f"OR({', '.join(formula_parts)})"

        all_notes_raw = airtable.get_all(formula=formula, sort=[("CreatedAt", "desc")])

        for record in all_notes_raw:
            notes_to_display.append({"id": record["id"], **record.get("fields", {})})

        if search_query and not notes_to_display:
            flash(f"No notes found matching '{search_query}'.", "info")

    except Exception as e:
        print(f"Error fetching notes from Airtable: {e}")
        flash(f"Error fetching notes: {e}", "error")
        notes_to_display = []

    return render_template(
        "notes_index.html", notes=notes_to_display, search_query=search_query
    )


@notes_bp.route("/generate_note", methods=["POST"])
def generate_note_route():
    if not airtable or not OPENAI_API_KEY:
        flash("Airtable or OpenAI API not configured.", "error")
        return redirect(url_for("notes.index"))

    title = request.form.get("generate_title")
    if not title:
        flash("Title is required to generate a note.", "error")
        return redirect(url_for("notes.index"))

    draft_content = generate_note_from_title_with_openai(title)
    if not draft_content:
        return redirect(url_for("notes.index"))

    html_content, tags = process_with_openai(draft_content)
    if html_content is None or tags is None:
        flash("Failed to process the generated content from OpenAI.", "error")
        return redirect(url_for("notes.index"))

    try:
        note_data = {
            "Title": title,
            "HTMLContent": html_content,
            "Tags": tags,
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
            return render_template("view_note.html", note=note, summary=summary)
        else:
            flash("Note not found.", "error")
            return redirect(url_for("notes.index"))
    except Exception as e:
        print(f"Error fetching note {note_id} from Airtable: {e}")
        flash(f"Error fetching note: {e}", "error")
        return redirect(url_for("notes.index"))
