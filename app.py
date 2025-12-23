from flask import Flask, request, send_file, render_template, url_for, redirect
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


# ---------- Outro Configuration ----------
STANDARD_OUTRO = "Outro.txt"
LIGHT_GRAY_OUTRO = "Light-gray outro.txt"
MAP_OUTRO = "Outro w map.txt"
LIGHT_GRAY_MAP_OUTRO = "Light-gray outro w map.txt"


def get_outro_filename(prev_template, use_map=False):
    if prev_template in ("Standout Content.txt", "No Image Section (Primary).txt"):
        return LIGHT_GRAY_MAP_OUTRO if use_map else LIGHT_GRAY_OUTRO
    return MAP_OUTRO if use_map else STANDARD_OUTRO


# ---------- Section Parsing ----------
def extract_sections(html_content):
    sections = []
    matches = re.finditer(
        r'(<h[1-2][^>]*>.*?</h[1-2]>)|(<h6[^>]*>.*?</h6>)|(<p[^>]*>.*?</p>)|(<ul[^>]*>.*?</ul>)|(<ol[^>]*>.*?</ol>)',
        html_content,
        re.IGNORECASE | re.DOTALL,
    )

    current_section = {"heading": None, "paragraphs": [], "h6_list": []}

    for match in matches:
        tag = match.group(0)

        if re.match(r"<h[1-2][^>]*>", tag):
            if current_section["heading"] and current_section["paragraphs"]:
                sections.append(current_section)
            current_section = {"heading": tag, "paragraphs": [], "h6_list": []}

        elif re.match(r"<h6[^>]*>", tag):
            current_section["h6_list"].append(tag)

        else:
            current_section["paragraphs"].append(tag)

    if current_section["heading"] and current_section["paragraphs"]:
        sections.append(current_section)

    return sections


def clean_heading(heading):
    return re.sub(r"</?h[1-6][^>]*>", "", heading)


def strip_all_html(text):
    return re.sub(r"<[^>]+>", "", text or "").strip()


def is_faq_heading(heading):
    return bool(re.search(r"<h2[^>]*>.*?faq.*?</h2>", heading, re.IGNORECASE | re.DOTALL))


# ---------- FAQ Rendering ----------
def render_faq_block(faq_section):
    path = resource_path(os.path.join("templates", "FAQ section.txt"))
    if not os.path.exists(path):
        return None, "Missing FAQ section template"

    with open(path, "r", encoding="utf-8") as f:
        faq_template = f.read()

    panels = []
    current_title = None
    current_body = []

    for tag in faq_section["paragraphs"]:
        question_match = re.match(r"<p><strong>(.*?)</strong></p>", tag)
        if question_match:
            if current_title:
                panels.append((current_title, current_body))
            current_title = question_match.group(1)
            current_body = []
        else:
            current_body.append(tag)

    if current_title:
        panels.append((current_title, current_body))

    faq_items = []
    for title, body in panels:
        faq_items.append(f"""
<div class="autorepo_accordion">
  <details>
    <summary>{title}</summary>
    <div class="autorepo_content-card" data-include-img="no">
      <div class="autorepo_content-box">
        <div class="autorepo_content-text">
          {''.join(body)}
        </div>
      </div>
    </div>
  </details>
</div>
""")

    return faq_template.replace("{{FAQ_ITEMS}}", "\n".join(faq_items)), None


# ---------- Block Rendering ----------
def render_blocks(blocks, global_h1_plain=None):
    output = ""

    for filename, chunk in blocks:
        if filename == "__faq_custom_block__":
            output += chunk[0] + "\n\n"
            continue

        path = resource_path(os.path.join("templates", filename))
        if not os.path.exists(path):
            return None, f"Missing template: {filename}"

        with open(path, "r", encoding="utf-8") as f:
            template = f.read()

        # Alt text replacement (only if template contains your placeholder)
        if global_h1_plain:
            template = template.replace("Your alt text here", global_h1_plain)

        for i, section in enumerate(chunk, start=1):
            template = template.replace(f"{{{{HEADING_{i}}}}}", clean_heading(section["heading"]))
            template = template.replace(f"{{{{BODY_{i}}}}}", "\n".join(section["paragraphs"]))

            # H6 handling (insert ALL h6 tags)
            h6_joined = "\n".join(section.get("h6_list") or [])
            template = template.replace("{{BOTTOM_H6}}", h6_joined)

        output += template + "\n\n"

    return output, None


# ---------- Dynamic Template Builders ----------
def build_dynamic_template(sections, intro_template, middle_templates, use_map_outro=False, global_h1_plain=None):
    if len(sections) < 3:
        return None, "Not enough sections"

    intro, outro = sections[0], sections[-1]
    potential_faq = sections[-2]
    content_sections = sections[1:-2]

    faq_section = potential_faq if is_faq_heading(potential_faq["heading"]) else None
    if not faq_section:
        content_sections.append(potential_faq)

    blocks = [(intro_template, [intro])]

    for i, section in enumerate(content_sections):
        blocks.append((middle_templates[i % len(middle_templates)], [section]))

    if faq_section:
        faq_html, err = render_faq_block(faq_section)
        if err:
            return None, err
        blocks.append(("__faq_custom_block__", [faq_html]))

    outro_file = get_outro_filename(blocks[-1][0], use_map_outro)
    blocks.append((outro_file, [outro]))

    return render_blocks(blocks, global_h1_plain=global_h1_plain)


def build_geo_template(sections, use_map_outro=False, global_h1_plain=None):
    return build_dynamic_template(
        sections,
        "Intro.txt",
        ["Content w Image right.txt", "Standout Content.txt"],
        use_map_outro,
        global_h1_plain,
    )


def build_single_image_template(sections, use_map_outro=False, global_h1_plain=None):
    return build_dynamic_template(
        sections,
        "Intro.txt",
        ["No Image Section (White).txt", "No Image Section (Primary).txt"],
        use_map_outro,
        global_h1_plain,
    )


def build_single_image_banner_template(sections, use_map_outro=False, global_h1_plain=None):
    return build_dynamic_template(
        sections,
        "Banner Image Intro.txt",
        ["No Image Section (White).txt", "No Image Section (Primary).txt"],
        use_map_outro,
        global_h1_plain,
    )


# ---------- MSLP Template ----------
def build_mslp_template(sections, use_map_outro=False, global_h1_plain=None):
    if len(sections) < 4:
        return None, "Not enough sections for MSLP template."

    intro, outro = sections[0], sections[-1]
    potential_faq = sections[-2]
    content_sections = sections[1:-2]
    faq_section = potential_faq if is_faq_heading(potential_faq["heading"]) else None
    if not faq_section:
        content_sections.append(potential_faq)

    blocks = [("MSLP Intro.txt", [intro])]

    if len(content_sections) == 6:
        blocks.append(("MSLP 3 Hoverbox Section.txt", content_sections[:3]))
        blocks.append(("MSLP 3 Hoverbox Section.txt", content_sections[3:]))
    else:
        i = 0
        while i + 3 <= len(content_sections):
            blocks.append(("MSLP 3 Hoverbox Section.txt", content_sections[i:i+3]))
            i += 3
        if i < len(content_sections):
            blocks.append(("Penultimate.txt", content_sections[i:]))

    if faq_section:
        faq_html, err = render_faq_block(faq_section)
        if err:
            return None, err
        blocks.append(("__faq_custom_block__", [faq_html]))

    outro_file = get_outro_filename(blocks[-1][0], use_map_outro)
    blocks.append((outro_file, [outro]))

    return render_blocks(blocks, global_h1_plain=global_h1_plain)


# ---------- Hubpage Template ----------
def build_hubpage_template(sections, use_map_outro=False, global_h1_plain=None):
    if len(sections) < 3:
        return None, "Not enough sections"

    intro = sections[0]
    outro = sections[-1]
    potential_faq = sections[-2]

    content_sections = sections[1:-2]
    faq_section = potential_faq if is_faq_heading(potential_faq["heading"]) else None
    if not faq_section:
        content_sections.append(potential_faq)

    blocks = [("Hubpage Intro.txt", [intro])]

    i = 0
    use_side_by_side = True

    while i < len(content_sections):
        if use_side_by_side and i + 1 < len(content_sections):
            blocks.append(("Hubpage Side-By-Side.txt", content_sections[i:i+2]))
            i += 2
        else:
            blocks.append(("No Image Section (Primary).txt", [content_sections[i]]))
            i += 1
        use_side_by_side = not use_side_by_side

    if faq_section:
        faq_html, err = render_faq_block(faq_section)
        if err:
            return None, err
        blocks.append(("__faq_custom_block__", [faq_html]))

    outro_file = get_outro_filename(blocks[-1][0], use_map_outro)
    blocks.append((outro_file, [outro]))

    return render_blocks(blocks, global_h1_plain=global_h1_plain)


# ---------- Routes ----------
@app.route("/", methods=["GET", "POST"])
def index():
    download_url = None

    if request.method == "POST":
        html = request.form.get("html_content", "").strip()

        geo = request.form.get("geo_toggle") == "on"
        mslp = request.form.get("mslp_toggle") == "on"
        single = request.form.get("single_image_toggle") == "on"
        banner = request.form.get("single_image_banner_toggle") == "on"
        hubpage = request.form.get("hubpage_toggle") == "on"
        map_toggle = request.form.get("map_outro_toggle") == "on"

        if not html:
            return redirect(url_for("error_game"))

        sections = extract_sections(html)

        # Plain-text H1 for image alt replacement
        h1_match = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.IGNORECASE | re.DOTALL)
        global_h1_plain = strip_all_html(h1_match.group(1)) if h1_match else None

        if hubpage:
            output, error = build_hubpage_template(sections, map_toggle, global_h1_plain)
        elif geo:
            output, error = build_geo_template(sections, map_toggle, global_h1_plain)
        elif mslp:
            output, error = build_mslp_template(sections, map_toggle, global_h1_plain)
        elif single:
            output, error = build_single_image_template(sections, map_toggle, global_h1_plain)
        elif banner:
            output, error = build_single_image_banner_template(sections, map_toggle, global_h1_plain)
        else:
            return redirect(url_for("error_game"))

        if output is None or error:
            app.logger.error(error)
            return redirect(url_for("error_game"))

        filename = (
            re.sub(r"[^a-zA-Z0-9]+", "_", global_h1_plain).lower()[:50] + ".txt"
            if global_h1_plain
            else "output.txt"
        )

        path = os.path.join(TEMP_OUTPUT_DIR, filename)
        with open(path, "w", encoding="utf-8") as f:
            f.write(output)

        download_url = url_for("download_file", filename=filename)

    return render_template("index.html", download_url=download_url)


@app.route("/download/<filename>")
def download_file(filename):
    path = os.path.join(TEMP_OUTPUT_DIR, filename)
    if not os.path.exists(path):
        return redirect(url_for("error_game"))
    return send_file(path, as_attachment=True)


@app.route("/error-game")
def error_game():
    return render_template("error_game.html")


if __name__ == "__main__":
    app.run(debug=False)
