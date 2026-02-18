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
        token = f"UPI_BTN_{len(token_map) + 1}"
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

    text = re.sub(BTN_TOKEN_PATTERN, repl, text, flags=re.I | re.S)

    for token, html in token_map.items():
        text = re.sub(
            rf'<p[^>]*data-upi="{re.escape(token)}"[^>]*>\s*</p>',
            html,
            text,
            flags=re.I | re.S
        )

    return text


# ---------- Section Parsing ----------
def extract_sections(html_content):
    sections = []

    matches = re.finditer(
        rf'({BTN_TOKEN_PATTERN})|(<h[1-2][^>]*>.*?</h[1-2]>)|(<h6[^>]*>.*?</h6>)|(<p[^>]*>.*?</p>)|(<ul[^>]*>.*?</ul>)|(<ol[^>]*>.*?</ol>)',
        html_content,
        re.IGNORECASE | re.DOTALL,
    )

    current_section = {"heading": None, "paragraphs": [], "h6_list": []}

    for match in matches:
        tag = match.group(0)

        token_match = re.match(BTN_TOKEN_PATTERN, tag, flags=re.I | re.S)
        if token_match:
            if current_section["heading"] and (current_section["paragraphs"] or current_section["h6_list"]):
                sections.append(current_section)
            current_section = {"heading": None, "paragraphs": [], "h6_list": []}
            sections.append({"button_block": token_match.group(1)})
            continue

        if re.match(r"<h[1-2][^>]*>", tag, flags=re.I | re.S):
            if current_section["heading"] and (current_section["paragraphs"] or current_section["h6_list"]):
                sections.append(current_section)
            current_section = {"heading": tag, "paragraphs": [], "h6_list": []}

        elif re.match(r"<h6[^>]*>", tag, flags=re.I | re.S):
            current_section["h6_list"].append(tag)

        else:
            current_section["paragraphs"].append(tag)

    if current_section["heading"] and (current_section["paragraphs"] or current_section["h6_list"]):
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
def render_blocks(blocks, global_h1_plain=None, token_map=None):
    output = ""

    for filename, chunk in blocks:
        if filename == "__faq_custom_block__":
            output += apply_button_tokens(chunk[0], token_map) + "\n\n"
            continue

        if filename == "__button_block__":
            token = chunk[0].get("button_block")
            output += token_map.get(token, "") + "\n\n"
            continue

        path = resource_path(os.path.join("templates", filename))
        if not os.path.exists(path):
            return None, f"Missing template: {filename}"

        with open(path, "r", encoding="utf-8") as f:
            template = f.read()

        if global_h1_plain:
            template = template.replace("Your alt text here", global_h1_plain)

        for i, section in enumerate(chunk, start=1):
            heading = clean_heading(section["heading"])
            body = "\n".join(section["paragraphs"])
            body = apply_button_tokens(body, token_map)

            template = template.replace(f"{{{{HEADING_{i}}}}}", heading)
            template = template.replace(f"{{{{BODY_{i}}}}}", body)

            h6_joined = "\n".join(section.get("h6_list") or [])
            h6_joined = apply_button_tokens(h6_joined, token_map)
            template = template.replace("{{BOTTOM_H6}}", h6_joined)

        template = apply_button_tokens(template, token_map)
        output += template + "\n\n"

    return output, None


# ---------- Helpers ----------
def add_dynamic_blocks_for_sections(blocks, sections_stream, middle_templates):
    tmpl_i = 0
    for section in sections_stream:
        if "button_block" in section:
            blocks.append(("__button_block__", [section]))
        else:
            blocks.append((middle_templates[tmpl_i % len(middle_templates)], [section]))
            tmpl_i += 1
    return blocks


def find_first_heading_section(sections):
    for s in sections:
        if "heading" in s:
            return s
    return None


# ---------- Dynamic Template Builders ----------
def build_dynamic_template(sections, intro_template, middle_templates, use_map_outro=False, global_h1_plain=None, token_map=None):
    if len(sections) < 2:
        return None, "Not enough sections"

    # Find first real heading as intro
    first_heading_idx = None
    for idx, s in enumerate(sections):
        if "heading" in s:
            first_heading_idx = idx
            break

    if first_heading_idx is None:
        return None, "No heading section found"

    # Everything before intro can include button blocks (only used by Dealer Near)
    pre_intro = sections[:first_heading_idx]
    working = sections[first_heading_idx:]

    if len(working) < 2:
        return None, "Not enough sections after intro"

    intro, outro = working[0], working[-1]
    potential_faq = working[-2] if len(working) >= 3 else None

    content_sections = working[1:-2] if len(working) >= 3 else []

    faq_section = None
    if potential_faq and ("heading" in potential_faq) and is_faq_heading(potential_faq["heading"]):
        faq_section = potential_faq
    elif potential_faq:
        content_sections.append(potential_faq)

    blocks = []

    # If caller wants pre-intro included (Dealer Near does), they will pass it separately.
    blocks.append((intro_template, [intro]))

    add_dynamic_blocks_for_sections(blocks, content_sections, middle_templates)

    if faq_section:
        faq_html, err = render_faq_block(faq_section)
        if err:
            return None, err
        blocks.append(("__faq_custom_block__", [faq_html]))

    outro_file = get_outro_filename(blocks[-1][0], use_map_outro)
    blocks.append((outro_file, [outro]))

    rendered, err = render_blocks(blocks, global_h1_plain=global_h1_plain, token_map=token_map)
    if rendered is None:
        return None, err

    return rendered, None


def build_geo_template(sections, use_map_outro=False, global_h1_plain=None, token_map=None):
    return build_dynamic_template(
        sections,
        "Intro.txt",
        ["Content w Image right.txt", "Standout Content.txt"],
        use_map_outro,
        global_h1_plain,
        token_map,
    )


def build_srp_template(sections, use_map_outro=False, global_h1_plain=None, token_map=None):
    return build_dynamic_template(
        sections,
        "Intro.txt",
        ["No Image Section (White).txt", "No Image Section (Primary).txt"],
        use_map_outro,
        global_h1_plain,
        token_map,
    )


def build_single_image_banner_template(sections, use_map_outro=False, global_h1_plain=None, token_map=None):
    return build_dynamic_template(
        sections,
        "Banner Image Intro.txt",
        ["No Image Section (White).txt", "No Image Section (Primary).txt"],
        use_map_outro,
        global_h1_plain,
        token_map,
    )


def build_dealer_near_template(sections, use_map_outro=False, global_h1_plain=None, token_map=None):
    """
    Dealer Near must be identical to Single Image Banner, except it starts with Top Buttons.
    We assume the first item may be a button_block section.
    """
    pre_intro_blocks = []
    if sections and "button_block" in sections[0]:
        pre_intro_blocks.append(("__button_block__", [sections[0]]))
        sections = sections[1:]

    # Now build exactly like single image banner
    output, err = build_single_image_banner_template(sections, use_map_outro, global_h1_plain, token_map)
    if output is None:
        return None, err

    if pre_intro_blocks:
        pre_html, pre_err = render_blocks(pre_intro_blocks, global_h1_plain=global_h1_plain, token_map=token_map)
        if pre_html is None:
            return None, pre_err
        output = pre_html + output

    return output, None


def build_mslp_template(sections, use_map_outro=False, global_h1_plain=None, token_map=None):
    if len(sections) < 4:
        return None, "Not enough sections for MSLP template."

    intro = find_first_heading_section(sections)
    if not intro:
        return None, "No heading section found"

    # Build stream after first heading
    first_heading_idx = next(i for i, s in enumerate(sections) if "heading" in s)
    working = sections[first_heading_idx:]

    intro, outro = working[0], working[-1]
    potential_faq = working[-2]
    content_sections = working[1:-2]

    faq_section = potential_faq if (("heading" in potential_faq) and is_faq_heading(potential_faq["heading"])) else None
    if not faq_section:
        content_sections.append(potential_faq)

    blocks = [("MSLP Intro.txt", [intro])]

    buffer_three = []

    def flush_buffer():
        nonlocal buffer_three
        if len(buffer_three) == 3:
            blocks.append(("MSLP 3 Hoverbox Section.txt", buffer_three))
        elif len(buffer_three) > 0:
            blocks.append(("Penultimate.txt", buffer_three))
        buffer_three = []

    for item in content_sections:
        if "button_block" in item:
            flush_buffer()
            blocks.append(("__button_block__", [item]))
            continue

        buffer_three.append(item)
        if len(buffer_three) == 3:
            flush_buffer()

    flush_buffer()

    if faq_section:
        faq_html, err = render_faq_block(faq_section)
        if err:
            return None, err
        blocks.append(("__faq_custom_block__", [faq_html]))

    outro_file = get_outro_filename(blocks[-1][0], use_map_outro)
    blocks.append((outro_file, [outro]))

    return render_blocks(blocks, global_h1_plain=global_h1_plain, token_map=token_map)


def build_hubpage_template(sections, use_map_outro=False, global_h1_plain=None, token_map=None):
    if len(sections) < 3:
        return None, "Not enough sections"

    first_heading_idx = None
    for idx, s in enumerate(sections):
        if "heading" in s:
            first_heading_idx = idx
            break
    if first_heading_idx is None:
        return None, "No heading section found"

    working = sections[first_heading_idx:]

    intro = working[0]
    outro = working[-1]
    potential_faq = working[-2]

    content_sections = working[1:-2]
    faq_section = potential_faq if (("heading" in potential_faq) and is_faq_heading(potential_faq["heading"])) else None
    if not faq_section:
        content_sections.append(potential_faq)

    blocks = [("Hubpage Intro.txt", [intro])]

    i = 0
    toggle = True
    while i < len(content_sections):
        item = content_sections[i]

        if "button_block" in item:
            blocks.append(("__button_block__", [item]))
            i += 1
            continue

        if toggle:
            if i + 1 < len(content_sections) and ("button_block" not in content_sections[i + 1]):
                blocks.append(("Hubpage Side-By-Side.txt", content_sections[i:i + 2]))
                i += 2
            else:
                blocks.append(("No Image Section (Primary).txt", [content_sections[i]]))
                i += 1
        else:
            blocks.append(("No Image Section (Primary).txt", [content_sections[i]]))
            i += 1

        toggle = not toggle

    if faq_section:
        faq_html, err = render_faq_block(faq_section)
        if err:
            return None, err
        blocks.append(("__faq_custom_block__", [faq_html]))

    outro_file = get_outro_filename(blocks[-1][0], use_map_outro)
    blocks.append((outro_file, [outro]))

    return render_blocks(blocks, global_h1_plain=global_h1_plain, token_map=token_map)


# ---------- Routes ----------
@app.route("/", methods=["GET", "POST"])
def index():
    download_url = None

    if request.method == "POST":
        html = request.form.get("html_content", "").strip()

        geo = request.form.get("geo_toggle") == "on"
        srp = request.form.get("srp_toggle") == "on"
        mslp = request.form.get("mslp_toggle") == "on"
        banner = request.form.get("single_image_banner_toggle") == "on"
        hubpage = request.form.get("hubpage_toggle") == "on"
        dealer = request.form.get("dealer_near_toggle") == "on"
        map_toggle = request.form.get("map_outro_toggle") == "on"
        single_legacy = request.form.get("single_image_toggle") == "on"

        if not html:
            return redirect(url_for("error_game"))

        html, token_map = replace_button_blocks(html)
        sections = extract_sections(html)

        if not sections:
            return redirect(url_for("error_game"))

        first_heading_section = find_first_heading_section(sections)
        if not first_heading_section:
            return redirect(url_for("error_game"))

        global_h1_plain = strip_all_html(clean_heading(first_heading_section["heading"]))

        if dealer:
            output, error = build_dealer_near_template(sections, map_toggle, global_h1_plain, token_map)
        elif hubpage:
            output, error = build_hubpage_template(sections, map_toggle, global_h1_plain, token_map)
        elif geo:
            output, error = build_geo_template(sections, map_toggle, global_h1_plain, token_map)
        elif mslp:
            output, error = build_mslp_template(sections, map_toggle, global_h1_plain, token_map)
        elif srp or single_legacy:
            output, error = build_srp_template(sections, map_toggle, global_h1_plain, token_map)
        elif banner:
            output, error = build_single_image_banner_template(sections, map_toggle, global_h1_plain, token_map)
        else:
            return redirect(url_for("error_game"))

        if output is None or error:
            app.logger.error(error)
            return redirect(url_for("error_game"))

        filename = re.sub(r"[^a-zA-Z0-9]+", "_", global_h1_plain).lower()[:50] + ".txt"
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
