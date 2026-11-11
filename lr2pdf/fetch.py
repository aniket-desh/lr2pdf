"""Fetch a post from the LessWrong (or Alignment Forum) GraphQL API."""

import json
import re
import urllib.request
from dataclasses import dataclass
from urllib.parse import urlparse

QUERY = """
query ($id: String) {
  post(input: {selector: {_id: $id}}) {
    result {
      _id title slug pageUrl url postedAt wordCount readTimeMinutes baseScore
      user { displayName }
      coauthors { displayName }
      tags { name }
      contents { html }
    }
  }
}
"""

HOSTS = {"www.lesswrong.com", "lesswrong.com", "www.alignmentforum.org", "alignmentforum.org"}


@dataclass
class Post:
    id: str
    title: str
    slug: str
    page_url: str
    linkpost_url: str | None
    posted_at: str
    word_count: int
    read_minutes: int
    karma: int
    authors: list[str]
    tags: list[str]
    html: str
    site: str


def parse_post_ref(ref: str) -> tuple[str, str]:
    """Return (api host, post id) from a post URL or a bare 17-character id."""
    if re.fullmatch(r"[A-Za-z0-9]{17}", ref):
        return "www.lesswrong.com", ref
    u = urlparse(ref if "://" in ref else "https://" + ref)
    if u.hostname not in HOSTS:
        raise ValueError(f"not a LessWrong or Alignment Forum URL: {ref}")
    m = re.search(r"/posts/([A-Za-z0-9]{17})", u.path)
    if not m:
        raise ValueError(f"could not find a post id in {ref}")
    host = "www.alignmentforum.org" if "alignmentforum" in u.hostname else "www.lesswrong.com"
    return host, m.group(1)


def fetch_post(ref: str) -> Post:
    host, post_id = parse_post_ref(ref)
    body = json.dumps({"query": QUERY, "variables": {"id": post_id}}).encode()
    req = urllib.request.Request(
        f"https://{host}/graphql",
        data=body,
        headers={"Content-Type": "application/json", "User-Agent": "lr2pdf/0.1"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.load(resp)
    if data.get("errors"):
        raise RuntimeError(f"GraphQL error: {data['errors'][0].get('message')}")
    r = (data.get("data") or {}).get("post", {}).get("result")
    if not r:
        raise RuntimeError(f"post {post_id} not found")
    authors = [r["user"]["displayName"]] if r.get("user") else []
    authors += [c["displayName"] for c in r.get("coauthors") or []]
    page_url = r.get("pageUrl") or f"https://{host}/posts/{post_id}/{r['slug']}"
    return Post(
        id=r["_id"],
        title=r["title"],
        slug=r["slug"],
        page_url=page_url,
        linkpost_url=r.get("url"),
        posted_at=r["postedAt"],
        word_count=r.get("wordCount") or 0,
        read_minutes=r.get("readTimeMinutes") or 0,
        karma=r.get("baseScore") or 0,
        authors=authors,
        tags=[t["name"] for t in r.get("tags") or []],
        html=(r.get("contents") or {}).get("html") or "",
        site="Alignment Forum" if "alignmentforum" in host else "LessWrong",
    )
