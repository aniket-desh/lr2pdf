"""lr2pdf: turn a LessWrong post into a print-friendly PDF."""

import argparse
import html
import os
import sys
from datetime import datetime
from pathlib import Path

from .fetch import fetch_post
from .transform import DEFAULT_SIDENOTE_MAX, transform

HERE = Path(__file__).parent
PAPER = {"letter": "letter", "a4": "A4"}


def build_html(post, body: str) -> str:
    esc = html.escape
    date = datetime.fromisoformat(post.posted_at.replace("Z", "+00:00"))
    date_str = f"{date.day} {date:%B %Y}"
    authors = ", ".join(esc(a) for a in post.authors)
    meta = [f'<span class="site">{esc(post.site)}</span>']
    stats = []
    if post.karma:
        stats.append(f"{post.karma} karma")
    if post.read_minutes:
        stats.append(f"{post.read_minutes} min read")
    if stats:
        meta.append(" · ".join(stats))
    if post.tags:
        meta.append(f'<span class="tags">{esc(", ".join(post.tags))}</span>')
    linkpost = ""
    if post.linkpost_url:
        linkpost = f'<div class="linkpost">Linkpost for {esc(post.linkpost_url)}</div>'
    printed = f"{datetime.now():%-d %B %Y}"
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>{esc(post.title)}</title></head>
<body>
<header class="masthead">
  <div class="meta">{'<br>'.join(meta)}</div>
  <h1 class="title">{esc(post.title)}</h1>
  <div class="byline">{authors} &nbsp;·&nbsp; <span class="date">{date_str}</span></div>
  {linkpost}
</header>
<main>
{body}
</main>
<div class="colophon">{esc(post.page_url)} &nbsp;·&nbsp; printed {printed}</div>
</body></html>"""


def _ensure_homebrew_libs() -> None:
    """WeasyPrint loads Pango through dlopen, and on macOS a non-Homebrew Python (uv's,
    for instance) doesn't search /opt/homebrew/lib. dyld reads its search path only at
    process start, so re-exec once with the fallback path set."""
    brew_lib = "/opt/homebrew/lib"
    if (sys.platform == "darwin" and "DYLD_FALLBACK_LIBRARY_PATH" not in os.environ
            and os.path.isdir(brew_lib)):
        env = dict(os.environ, DYLD_FALLBACK_LIBRARY_PATH=brew_lib)
        os.execve(sys.executable, [sys.executable, "-m", "lr2pdf.cli", *sys.argv[1:]], env)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="lr2pdf", description=__doc__)
    ap.add_argument("url", help="LessWrong or Alignment Forum post URL (or post id)")
    ap.add_argument("-o", "--output", help="output PDF path (default: <slug>.pdf)")
    ap.add_argument("--paper", choices=PAPER, default="letter")
    ap.add_argument("--no-link-notes", action="store_true",
                    help="don't print link URLs in the margin")
    ap.add_argument("--sidenote-max", type=int, default=DEFAULT_SIDENOTE_MAX,
                    help="footnotes longer than this many characters go to the page foot "
                         f"(default {DEFAULT_SIDENOTE_MAX})")
    ap.add_argument("--html", help="also write the intermediate HTML here (for debugging)")
    args = ap.parse_args(argv)

    _ensure_homebrew_libs()
    from weasyprint import CSS, HTML
    from weasyprint.text.fonts import FontConfiguration

    post = fetch_post(args.url)
    body = transform(post.html, link_notes=not args.no_link_notes,
                     sidenote_max=args.sidenote_max)
    doc = build_html(post, body)
    if args.html:
        Path(args.html).write_text(doc)

    out = Path(args.output or f"{post.slug}.pdf")
    fonts = FontConfiguration()  # required for the stylesheet's @font-face rules to load
    stylesheets = [CSS(filename=str(HERE / "print.css"), font_config=fonts),
                   CSS(string=f"@page {{ size: {PAPER[args.paper]}; }}")]
    HTML(string=doc, base_url=str(HERE) + "/").write_pdf(
        out, stylesheets=stylesheets, font_config=fonts)
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
