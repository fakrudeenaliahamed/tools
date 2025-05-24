from flask import Flask, render_template
from funds_app import funds_bp
from notes_app import notes_bp

app = Flask(__name__)
app.secret_key = "your_secret_key"


# Register blueprints with prefixes
app.register_blueprint(funds_bp, url_prefix="/funds")
app.register_blueprint(notes_bp, url_prefix="/notes")


@app.route("/")
def landing():
    return render_template("index.html")  # Landing page with links


if __name__ == "__main__":
    app.run(debug=True, port=10000)
