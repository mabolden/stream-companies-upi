from flask import Flask, request, send_file, render_template, url_for, redirect, jsonify
import re
import os
import sys
import logging
import tempfile


# ---------- App Setup ----------
def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except AttributeError:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


app = Flask(
    __name__,
    template_folder=resource_path("templates"),
    static_folder=resource_path("static"),
)

logging.basicConfig(
    filename="app.log",
    level=logging.DEBUG,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

TEMP_OUTPUT_DIR = tempfile.mkdtemp(prefix="upi_output_")


# ---------- BUTTON SYSTEM ----------
BTN_TOKEN_FMT = "__UPI_BUTTON_BLOCK_{token}__"
BTN_TOKEN_PATTERN = r"__UPI_BUTTON_BLOCK_(UPI_BTN_\d+)__"


def replace_button_blocks(html):
    token_map = {}

    p_wrapped_pattern = r'(<p[^>]*>\s*((?:<a\s+href="[^"]+">.*?</a>\s*){2,3})\s*</p>)'
    bare_pattern = r'((?:<a\s+href="[^"]+">.*?</a>\s*){2,3})'

    def build_button_html(links):
        if len(links) == 2:
            template_name = "Top Buttons.txt"
        elif len(links) == 3:
            template_name = "Button Row.txt"
        else:
            return None

        path = os.path.join(app.template_folder, template_name)
        if not os.path.exists(path):
            return None

        with open(path, "r", encoding="utf-8") as f:
            template = f.read()

        for i, (url, text) in enumerate(links, start=1):
            template = template.replace(f"BUTTON_{i}_URL", url.strip())
            template = template.replace(f"BUTTON {i} TEXT", text.strip())

        return template

    def make_token(html_snippet):
        token = f"UPI_BTN_{len(token_map)+1}"
        token_map[token] = html_snippet
        return "\n" + BTN_TOKEN_FMT.format(token=token) + "\n"

    def repl_p(match):
        anchors = match.group(2)
        links = re.findall(r'<a\s+href="([^"]+)">(.*?)</a>', anchors, re.I | re.S)
        btn_html = build_button_html(links)
        return make_token(btn_html) if btn_html else match.group(1)

    html = re.sub(p_wrapped_pattern, repl_p, html, flags=re.I | re.S)

    def repl_bare(match):
        block = match.group(1)
        links = re.findall(r'<a\s+href="([^"]+)">(.*?)</a>', block, re.I | re.S)
        btn_html = build_button_html(links)
        return make_token(btn_html) if btn_html else block

    html = re.sub(bare_pattern, repl_bare, html, flags=re.I | re.S)

    return html, token_map


def apply_button_tokens(text, token_map):
    if not token_map or not text:
        return text

    def repl(m):
        token = m.group(1)
        return token_map.get(token, "")

    return re.sub(BTN_TOKEN_PATTERN, repl, text, flags=re.I | re.S)


# ---------- SECTION PARSER ----------
def extract_sections(html_content):
    sections = []

    matches = re.finditer(
        rf'({BTN_TOKEN_PATTERN})|(<h[1-2][^>]*>.*?</h[1-2]>)|(<h6[^>]*>.*?</h6>)|(<p[^>]*>.*?</p>)|(<ul[^>]*>.*?</ul>)|(<ol[^>]*>.*?</ol>)',
        html_content,
        re.IGNORECASE | re.DOTALL,
    )

    current = {"heading": None, "content": []}

    for match in matches:
        tag = match.group(0)

        token_match = re.match(BTN_TOKEN_PATTERN, tag)
        if token_match:
            sections.append({"button_block": token_match.group(1)})
            continue

        if re.match(r"<h[1-2]", tag, re.I):
            if current["heading"]:
                sections.append(current)
            current = {"heading": tag, "content": []}
        else:
            current["content"].append(tag)

    if current["heading"]:
        sections.append(current)

    return sections


# ---------- FAQ SCHEMA ----------
def extract_faq_schema_pairs(html):

    matches = re.findall(
        r"<p>\s*<strong>(.*?)</strong>\s*</p>\s*<p>(.*?)</p>",
        html,
        re.S | re.I
    )

    def clean(text):
        return re.sub("<.*?>", "", text or "").strip()

    return [(clean(q), clean(a)) for q, a in matches if clean(q) and clean(a)]


def build_schema(html):
    pairs = extract_faq_schema_pairs(html)

    if not pairs:
        return None

    return {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {
                "@type": "Question",
                "name": q,
                "acceptedAnswer": {
                    "@type": "Answer",
                    "text": a
                }
            }
            for q, a in pairs
        ]
    }


# ---------- API ROUTE ----------
@app.route("/generate-schema", methods=["POST"])
def generate_schema():
    html = (request.form.get("html_content") or request.form.get("html") or "").strip()

    if not html:
        return jsonify({"error": "No input provided"}), 400

    schema = build_schema(html)

    if not schema:
        return jsonify({"error": "No FAQ found"}), 400

    return jsonify(schema)


# ---------- MAIN ROUTE ----------
@app.route("/", methods=["GET", "POST"])
def index():
    download_url = None
    schema = None

    if request.method == "POST":
        html = request.form.get("html_content", "").strip()

        if not html:
            return redirect(url_for("error_game"))

        # build schema automatically
        schema = build_schema(html)

        # process buttons
        html, token_map = replace_button_blocks(html)

        # replace tokens with real HTML
        html = apply_button_tokens(html, token_map)

        # extract sections (validation only)
        sections = extract_sections(html)
        if not sections:
            return redirect(url_for("error_game"))

        # safe heading detection
        first_real = next((s for s in sections if "heading" in s), None)
        if not first_real:
            return redirect(url_for("error_game"))

        global_h1_plain = re.sub("<.*?>", "", first_real["heading"])

        # final output
        output = html

        filename = re.sub(r"[^a-zA-Z0-9]+", "_", global_h1_plain).lower()[:50] + ".txt"
        path = os.path.join(TEMP_OUTPUT_DIR, filename)

        with open(path, "w", encoding="utf-8") as f:
            f.write(output)

        download_url = url_for("download_file", filename=filename)

    return render_template("index.html", download_url=download_url, schema=schema)


# ---------- DOWNLOAD ----------
@app.route("/download/<filename>")
def download_file(filename):
    path = os.path.join(TEMP_OUTPUT_DIR, filename)
    if not os.path.exists(path):
        return redirect(url_for("error_game"))
    return send_file(path, as_attachment=True)


# ---------- ERROR PAGE ----------
@app.route("/error-game")
def error_game():
    return render_template("error_game.html")


# ---------- RUN ----------
if __name__ == "__main__":
    app.run(debug=False)
