"""Turn LessWrong post HTML into print-ready HTML with margin notes.

LessWrong's editor output has three things a printout handles differently from the web:
footnotes live in an endnote list (we move them next to the text that cites them),
links are clickable (we print their URLs in the margin), and math is MathJax CHTML that
needs web fonts (we re-render the TeX source as SVG).
"""

import base64
import json
import re
import shutil
import subprocess
from pathlib import Path
from urllib.parse import urlparse

from bs4 import BeautifulSoup, NavigableString, Tag

BLOCK_TAGS = {"p", "div", "li", "ul", "ol", "blockquote", "h1", "h2", "h3", "h4", "h5", "h6",
              "pre", "figure", "figcaption", "table", "tr", "td", "th", "tbody", "thead"}
# Footnotes longer than this (in characters of text) go to the bottom of the page
# instead of the margin: a margin column is ~2in wide, so a 500-character note is
# already about 25 lines tall, and floats taller than the space left on a page get
# pushed off it.
DEFAULT_SIDENOTE_MAX = 500


def _text_len(tag: Tag) -> int:
    return len(tag.get_text(" ", strip=True))


def _flatten_blocks(soup: BeautifulSoup, tag: Tag) -> None:
    """Rename block elements inside a note to spans so the note can sit inline in a <p>.

    HTML parsers close a <p> when they meet another <p> or <ul>, so a note with
    paragraphs would break the paragraph that cites it. Spans with a b-<tag> class
    keep the structure, and the stylesheet gives them display: block.
    """
    for el in tag.find_all(list(BLOCK_TAGS)):
        el["class"] = [f"b-{el.name}"]
        el.name = "span"


def _top_level(el: Tag, root: Tag) -> Tag:
    while el.parent is not None and el.parent is not root:
        el = el.parent
    return el


def _place_note(note: Tag, ref: Tag, root: Tag) -> None:
    """Anchor a margin note at the top of the top-level block that cites it.

    Ideally a note would float from the exact line of its reference, but WeasyPrint
    mis-stacks floats that start inside a line box: notes from neighbouring lines
    overlap, and a float inside an unbreakable run can drop the preceding word.
    Block-level floats between paragraphs stack reliably, so each note starts level
    with the first line of its paragraph (or lower, if earlier notes are in the way).
    """
    # Notes are placed in document order, so inserting each one directly before its
    # paragraph keeps several notes for one paragraph in reference order.
    note.name = "div"
    _top_level(ref, root).insert_before(note)


def _short_url(href: str, max_len: int = 46) -> str:
    u = urlparse(href)
    host = (u.hostname or "").removeprefix("www.")
    path = u.path.rstrip("/")
    if host in ("lesswrong.com", "alignmentforum.org"):
        m = re.match(r"/posts/[A-Za-z0-9]{17}/(.+)", path)
        if m:
            path = "/posts/…/" + m.group(1)
    s = host + path
    if u.query and len(s) < max_len - 8:
        s += "?" + u.query
    return s if len(s) <= max_len else s[: max_len - 1] + "…"


def _render_math(soup: BeautifulSoup) -> None:
    """Replace MathJax CHTML with SVG rendered from the TeX kept in aria-label."""
    nodes = []
    for el in soup.select("span.math-tex, div.math-tex, span.mjpage"):
        if el.find_parent(class_=["math-tex", "mjpage"]):
            continue
        m = el.select_one(".mjx-math[aria-label]")
        if m is None:
            continue
        display = el.select_one(".MJXc-display") is not None
        nodes.append((el, m["aria-label"], display))
    if not nodes:
        return

    svgs = [None] * len(nodes)
    node_bin = shutil.which("node")
    script = Path(__file__).with_name("tex2svg.mjs")
    if node_bin:
        try:
            out = subprocess.run(
                [node_bin, str(script)],
                input=json.dumps([{"tex": t, "display": d} for _, t, d in nodes]),
                capture_output=True, text=True, timeout=120, check=True,
            )
            svgs = json.loads(out.stdout)
        except (subprocess.SubprocessError, json.JSONDecodeError) as e:
            print(f"warning: math rendering failed ({e}); printing TeX source instead")

    for (el, tex, display), svg in zip(nodes, svgs):
        if svg:
            # MathJax sizes the SVG in ex units and sets a vertical-align that puts the
            # math baseline on the text baseline; carry those over to the <img>.
            w = re.search(r'width="([\d.]+)ex"', svg)
            h = re.search(r'height="([\d.]+)ex"', svg)
            va = re.search(r'vertical-align:\s*(-?[\d.]+)ex', svg)
            src = "data:image/svg+xml;base64," + base64.b64encode(svg.encode()).decode()
            img = soup.new_tag("img", src=src, alt=tex)
            img["class"] = ["math"]
            style = []
            if w and h:
                style += [f"width:{w.group(1)}ex", f"height:{h.group(1)}ex"]
            if va and not display:
                style.append(f"vertical-align:{va.group(1)}ex")
            img["style"] = ";".join(style)
            new = img
        else:
            new = soup.new_tag("code")
            new.string = tex
        if display:
            wrap = soup.new_tag("span")
            wrap["class"] = ["math-display"]
            wrap.append(new)
            new = wrap
        el.replace_with(new)


def transform(html: str, *, link_notes: bool = True,
              sidenote_max: int = DEFAULT_SIDENOTE_MAX) -> str:
    soup = BeautifulSoup(f"<div id='root'>{html}</div>", "lxml")
    root = soup.find(id="root")

    _render_math(soup)

    # Inline styles from the editor (pre-wrap spans, table borders, fixed widths) fight
    # the print stylesheet. Keep only figure widths, which authors use to size images.
    for el in root.find_all(style=True):
        if el.name == "img" and "math" in el.get("class", []):
            continue
        keep = re.search(r"width:\s*[\d.]+%", el["style"]) if el.name == "figure" else None
        if keep:
            el["style"] = keep.group(0)
        else:
            del el["style"]
    for span in root.find_all("span", attrs={"class": False, "id": False}):
        span.unwrap()

    # Spoilers and collapsed sections are meant to be revealed; on paper, just show them.
    for el in root.select(".spoilers, .spoiler"):
        el["class"] = ["spoiler"]
    for el in root.find_all("details"):
        el.name = "div"
        el["class"] = ["details"]
    for el in root.find_all("summary"):
        el.name = "p"
        el["class"] = ["summary"]

    # The post title is the page's h1, so body headings move down one level.
    for level in (5, 4, 3, 2, 1):
        for h in root.find_all(f"h{level}"):
            h.name = f"h{level + 1}"

    # --- Footnotes -----------------------------------------------------------------
    notes = {}
    for li in root.select("li.footnote-item"):
        for back in li.select(".footnote-backref, .footnote-back-link, a[href^='#fnref']"):
            back.decompose()
        notes[li.get("id", "")] = li
    # extract(), not decompose(): decompose destroys the <li> children we still need.
    for section in root.select("ol.footnotes, ol.footnote-section, .footnote-section"):
        section.extract()

    def footnote(ref: Tag) -> None:
        a = ref.find("a", href=True)
        fid = a["href"].lstrip("#") if a else ""
        n = ref.get("data-footnote-index") or re.sub(r"\D", "", a.get_text() if a else "")
        li = notes.get(fid)
        if li is None:
            ref.decompose()
            return

        for wrapper in li.select(".footnote-content, [data-footnote-content]"):
            wrapper.unwrap()
        body = soup.new_tag("span")
        for child in list(li.children):
            body.append(child.extract())
        _flatten_blocks(soup, body)
        # The number goes inside the first paragraph so it shares a line with the text.
        first_p = body.find(class_="b-p")
        lead = first_p if first_p is not None and not first_p.find_previous_sibling(class_=True) else body
        # Drop links' margin notes inside notes; print the URL inline instead.
        for lk in body.find_all("a", href=True):
            if lk["href"].startswith("http") and lk.get_text(strip=True) not in lk["href"]:
                url = soup.new_tag("span")
                url["class"] = ["inline-url"]
                url.string = f" ({_short_url(lk['href'])})"
                lk.insert_after(url)

        if _text_len(body) <= sidenote_max:
            call = soup.new_tag("sup")
            call["class"] = ["note-call"]
            call.string = n
            note = soup.new_tag("span")
            note["class"] = ["sidenote"]
            num = soup.new_tag("span")
            num["class"] = ["note-num"]
            num.string = n
            if lead.contents and isinstance(lead.contents[0], NavigableString):
                lead.contents[0].replace_with(lead.contents[0].lstrip())
            lead.insert(0, num)
            num.insert_after(" ")
            note.append(body)
            ref.replace_with(call)
            _place_note(note, call, root)
        else:
            # WeasyPrint's float: footnote generates the call mark where this element
            # sits, so the element itself replaces the reference.
            note = soup.new_tag("span")
            note["class"] = ["footnote"]
            note["data-n"] = n
            note.append(body)
            ref.replace_with(note)

    seen = set()

    def link(a: Tag) -> None:
        href = a["href"]
        if not href.startswith(("http://", "https://")):
            return
        a["class"] = a.get("class", []) + ["ext"]
        if not link_notes or a.find_parent(class_=["sidenote", "footnote"]):
            return
        text = a.get_text(strip=True)
        if not text or text in href or href in seen:
            return
        seen.add(href)
        note = soup.new_tag("span")
        note["class"] = ["sidenote", "linknote"]
        note.string = _short_url(href)
        _place_note(note, a, root)

    # One pass in document order, so the notes beside a paragraph read in the order
    # their references appear in it. find_all collects targets before any footnote is
    # moved, so links inside footnotes are left to the footnote handler.
    for el in root.find_all(lambda t: (t.name == "span" and "footnote-reference" in t.get("class", []))
                            or (t.name == "a" and t.has_attr("href"))):
        if el.name == "span":
            footnote(el)
        elif not el.find_parent(class_="footnote-reference"):
            link(el)

    # --- Cleanup -------------------------------------------------------------------
    # Spaced ASCII hyphens are dashes in running text.
    for t in root.find_all(string=re.compile(r" - ")):
        if not t.find_parent(["pre", "code"]):
            t.replace_with(t.replace(" - ", " – "))
    for p in root.find_all("p"):
        if not p.get_text(strip=True) and not p.find(["img", "br"]) and not p.find(class_="math-display"):
            p.decompose()
    for cap in root.find_all("figcaption"):
        while cap.contents and getattr(cap.contents[0], "name", None) == "br":
            cap.contents[0].decompose()
    for img in root.find_all("img"):
        for attr in ("srcset", "sizes", "loading"):
            img.attrs.pop(attr, None)
    # Code with long lines spills into the note column rather than wrapping: at 7.6pt
    # the text column holds ~70 characters of monospace, the full width ~105.
    for pre in root.find_all("pre"):
        if max((len(l) for l in pre.get_text().splitlines()), default=0) > 70:
            pre["class"] = pre.get("class", []) + ["wide"]
    for table in root.find_all("table"):
        cols = max((len(tr.find_all(["td", "th"], recursive=False)) for tr in table.find_all("tr")), default=0)
        if cols >= 4:
            fig = table.find_parent("figure")
            if fig is None:
                fig = table.wrap(soup.new_tag("div"))
            fig["class"] = fig.get("class", []) + ["wide"]

    # Small caps on the opening line, but only for a real body paragraph: many posts
    # open with an italic preface or epigraph that shouldn't get them.
    for p in root.find_all("p", recursive=False):
        text = p.get_text(strip=True)
        if not text:
            continue
        italic = sum(len(i.get_text(strip=True)) for i in p.find_all(["i", "em"]))
        if italic < 0.5 * len(text):
            p["class"] = p.get("class", []) + ["lede"]
            break

    return root.decode_contents()
