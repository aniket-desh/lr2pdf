# lr2pdf

Turns a LessWrong or Alignment Forum post into a print-ready PDF in a margin-notes layout: EB Garamond throughout, a 4.65" text column, and a 1.95" outer column holding footnotes and link URLs (with room to write).

```bash
uv run lr2pdf https://www.lesswrong.com/posts/zj8Pk3kJujk5LoqhK/anthropic-are-the-good-guys
```

The PDF is written to `<slug>.pdf` unless you pass `-o`. Other options:

- `--paper a4` switches from US Letter to A4.
- `--no-link-notes` leaves link URLs out of the margin.
- `--sidenote-max N` sets the length (in characters) above which a footnote goes to the foot of the page instead of the margin. The default is 500.
- `--html FILE` writes the intermediate HTML, which helps when debugging layout.

## Setup

Rendering uses WeasyPrint, which needs Pango from Homebrew (`brew install pango`). Math needs Node and MathJax, installed once with `npm install`. Without them, equations print as their TeX source.

## How it works

`fetch.py` pulls the post from the site's GraphQL API, which returns clean body HTML along with title, authors, date, karma and tags. `transform.py` rewrites the HTML for print, and `print.css` lays it out:

- Footnotes move out of the endnote list. Short ones become numbered margin notes, and long ones (over `--sidenote-max`) become bottom-of-page footnotes under the text column.
- External links keep their text underlined and get their shortened URL printed in the margin, once per URL.
- MathJax markup is re-rendered from its TeX source to SVG (`tex2svg.mjs`), so the math doesn't depend on web fonts.
- Tables with four or more columns, and code blocks with lines over 70 characters, extend into the margin column instead of being squeezed.

Margin notes start level with the top of the paragraph that cites them, not the exact line. WeasyPrint mis-stacks floats that begin inside a line of text (notes overlap, and a word can be dropped), while floats placed between paragraphs stack reliably.

Fonts are EB Garamond (SIL Open Font License, `lr2pdf/fonts/OFL.txt`), instanced to static weights from the Google Fonts variable font.
