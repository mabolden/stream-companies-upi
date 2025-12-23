from flask import Flask, request, send_file, render_template, url_for, redirect
import re
import os
import logging

# Setup logging
logging.basicConfig(filename="app.log", level=logging.DEBUG, format="%(asctime)s - %(levelname)s - %(message)s")

app = Flask(__name__)

TEMPLATE_SETS = {
    "default": {
        4: [("Intro.txt", 1), ("Content w Image right.txt", 1), ("Standout Content.txt", 1), ("Outro.txt", 1)],
        5: [("Intro.txt", 1), ("3 Section Hover Box.txt", 3), ("Outro.txt", 1)],
        6: [("Intro.txt", 1), ("3 Section Hover Box.txt", 3), ("Penultimate.txt", 1), ("Outro.txt", 1)],
        7: [("Intro.txt", 1), ("3 Section Hover Box.txt", 3), ("2 Section Hover Box.txt", 2), ("Outro.txt", 1)],
        8: [("Intro.txt", 1), ("3 Section Hover Box.txt", 3), ("3 Section Hover Box.txt", 3), ("Outro.txt", 1)]
    },
    "geo": "dynamic",
    "mslp": "dynamic"
}

STANDARD_OUTRO = "Outro.txt"
LIGHT_GRAY_OUTRO = "Light-gray outro.txt"
MAP_OUTRO = "Outro w map.txt"
LIGHT_GRAY_MAP_OUTRO = "Light-gray outro w map.txt"

def get_outro_filename(prev_template, use_map=False):
    if prev_template == "Standout Content.txt":
        return LIGHT_GRAY_MAP_OUTRO if use_map else LIGHT_GRAY_OUTRO
    return MAP_OUTRO if use_map else STANDARD_OUTRO

def extract_sections(html_content):
    sections = []
    matches = re.finditer(r'(<h[1-2][^>]*>.*?</h[1-2]>)|(<p[^>]*>.*?</p>)|(<ul[^>]*>.*?</ul>)|(<ol[^>]*>.*?</ol>)', html_content, re.IGNORECASE | re.DOTALL)
    current_section = {"heading": None, "paragraphs": []}
    for match in matches:
        tag = match.group(0)
        if re.match(r'<h[1-2][^>]*>', tag):
            if current_section["heading"] and current_section["paragraphs"]:
                sections.append(current_section)
            current_section = {"heading": tag, "paragraphs": []}
        else:
            current_section["paragraphs"].append(tag)
    if current_section["heading"] and current_section["paragraphs"]:
        sections.append(current_section)
    return sections

def clean_heading(heading):
    return re.sub(r'</?h[1-6][^>]*>', '', heading)

def is_faq_heading(heading):
    return bool(re.search(r'<h2[^>]*>.*?faq.*?</h2>', heading, re.IGNORECASE | re.DOTALL))

def parse_faq_panels(faq_section):
    paragraphs = faq_section["paragraphs"]
    panels = []
    current_title = None
    current_body = []
    for tag in paragraphs:
        question_match = re.match(r'<p><strong>(.*?)</strong></p>', tag)
        if question_match:
            if current_title:
                panels.append((current_title, current_body))
            current_title = question_match.group(1)
            current_body = []
        else:
            current_body.append(tag)
    if current_title:
        panels.append((current_title, current_body))
    accordion_html = '<h2><strong>FAQs</strong></h2>'
    accordion_html += '<section class="autorepo_accordion-panel" data-theme-background-color="white" data-theme-font-color="black" data-accordion-count="{}" data-accordion-count-min="2" data-accordion-count-max="6" data-container-padding="yes">'.format(len(panels))
    for title, body_tags in panels:
        body_html = "\n".join(body_tags)
        accordion_html += f'''<div class="autorepo_accordion">
    <details>
        <summary>{title}</summary>
        <div class="autorepo_content-card" data-include-img="yes" data-theme-img-position="left" data-theme-background-color="white">
            <figure></figure>
            <div class="autorepo_content-box">
                <div class="autorepo_content-text">
                    {body_html}
                </div>
            </div>
        </div>
    </details>
</div>'''
    accordion_html += '</section>'
    return accordion_html

def render_blocks(blocks):
    final_content = ""
    for filename, chunk in blocks:
        if filename == "__faq_custom_block__":
            final_content += chunk[0] + "\n\n"
            continue
        file_path = os.path.join(os.getcwd(), filename)
        if not os.path.exists(file_path):
            return None, f"Missing template: {filename}"
        with open(file_path, "r", encoding="utf-8") as f:
            template = f.read()
        for i, section in enumerate(chunk, start=1):
            heading = clean_heading(section["heading"])
            body = "\n".join(section["paragraphs"])
            template = template.replace(f"{{{{HEADING_{i}}}}}", heading)
            template = template.replace(f"{{{{BODY_{i}}}}}", body)
        final_content += template + "\n\n"
    return final_content, None

def build_geo_template(sections, use_map_outro=False):
    if len(sections) < 3:
        return None, "Not enough sections for geo template."
    intro, outro = sections[0], sections[-1]
    potential_faq = sections[-2]
    content_sections = sections[1:-2]
    faq_section = potential_faq if is_faq_heading(potential_faq["heading"]) else None
    if not faq_section:
        content_sections.append(potential_faq)
    blocks = [("Intro.txt", [intro])]
    for i in range(0, len(content_sections), 2):
        if i < len(content_sections):
            blocks.append(("Content w Image right.txt", [content_sections[i]]))
        if i + 1 < len(content_sections):
            blocks.append(("Standout Content.txt", [content_sections[i + 1]]))
    if faq_section:
        faq_html = parse_faq_panels(faq_section)
        blocks.append(("__faq_custom_block__", [faq_html]))
    last_template = blocks[-1][0] if blocks else ""
    outro_filename = get_outro_filename(last_template, use_map_outro)
    blocks.append((outro_filename, [outro]))
    return render_blocks(blocks)

def build_default_template(sections, use_map_outro=False):
    count = len(sections)
    template_sequence = TEMPLATE_SETS["default"].get(count)
    if not template_sequence:
        return None, "Unsupported section count for default template."
    blocks = []
    section_idx = 0
    for template_name, num_sections in template_sequence:
        if "Outro" in template_name:
            prev_template = blocks[-1][0] if blocks else ""
            template_name = get_outro_filename(prev_template, use_map_outro)
        chunk = sections[section_idx:section_idx + num_sections]
        if len(chunk) < num_sections:
            return None, f"Not enough sections for {template_name}"
        blocks.append((template_name, chunk))
        section_idx += num_sections
    return render_blocks(blocks)

def build_mslp_template(sections, use_map_outro=False):
    if len(sections) < 3:
        return None, "Not enough sections for MSLP template."
    intro, outro = sections[0], sections[-1]
    content_sections = sections[1:-1]
    blocks = [("Intro.txt", [intro])]
    for section in content_sections:
        blocks.append(("Content w Image right.txt", [section]))
    last_template = blocks[-1][0] if blocks else ""
    outro_filename = get_outro_filename(last_template, use_map_outro)
    blocks.append((outro_filename, [outro]))
    return render_blocks(blocks)

@app.route("/", methods=["GET", "POST"])
def index():
    download_url = None
    if request.method == "POST":
        user_html = request.form.get("html_content", "").strip()
        geo_toggle = request.form.get("geo_toggle") == "on"
        mslp_toggle = request.form.get("mslp_toggle") == "on"
        map_toggle = request.form.get("map_outro_toggle") == "on"
        if not user_html:
            return redirect(url_for('error_game'))
        sections = extract_sections(user_html)
        if geo_toggle:
            final_output, error = build_geo_template(sections, map_toggle)
        elif mslp_toggle:
            final_output, error = build_mslp_template(sections, map_toggle)
        else:
            final_output, error = build_default_template(sections, map_toggle)
        if final_output is None:
            return redirect(url_for('error_game'))
        match = re.search(r'<h1[^>]*>(.*?)</h1>', user_html, re.IGNORECASE | re.DOTALL)
        filename = f"{re.sub(r'[^a-zA-Z0-9]+', '_', match.group(1)).strip('_').lower()[:50]}.txt" if match else "output.txt"
        with open(filename, "w", encoding="utf-8") as f:
            f.write(final_output)
        download_url = url_for('download_file', filename=filename)
    return render_template("index.html", download_url=download_url)

@app.route("/download/<filename>")
def download_file(filename):
    try:
        return send_file(filename, as_attachment=True)
    except Exception as e:
        logging.error(f"Download failed: {e}")
        return redirect(url_for('error_game'))

@app.errorhandler(500)
def internal_server_error(e):
    return redirect(url_for('error_game'))

@app.route("/error-game")
def error_game():
    return render_template("error_game.html")

if __name__ == "__main__":
    app.run(debug=True)
