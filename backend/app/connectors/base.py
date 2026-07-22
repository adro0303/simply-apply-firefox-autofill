"""The connector contract.

Adding a job source means writing one file: subclass `JobConnector`, implement `fetch`,
drop it in this package. `registry.py` discovers it automatically — no registration list
to update, which is the "one connector file" success metric from the PRD.

Two rules every connector must honor:
  1. Return `JobRecord`s, never raw upstream shapes. Normalization is the connector's job.
  2. Raise on failure rather than returning []. The search layer catches per-connector and
     degrades gracefully; swallowing errors here would make a broken source look like a
     source with no results, which is much harder to debug.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from html import unescape
from html.parser import HTMLParser
from io import StringIO

import httpx

from app.schemas import JobRecord, SearchQuery

USER_AGENT = "SimplyApply/0.1 (+https://github.com/jadghazi/simplyapply)"
DEFAULT_TIMEOUT = httpx.Timeout(20.0, connect=10.0)


class JobConnector(ABC):
    #: Stable identifier used in settings, dedupe preference, and the UI.
    source: str = ""
    #: Human-readable name for the settings screen.
    label: str = ""
    #: True if the connector needs a user-supplied API key (Tier 2 sources).
    requires_key: bool = False
    #: Lower number wins when deduping. ATS boards beat aggregators because their
    #: apply_url is the employer's real application form, not a redirect.
    priority: int = 50

    @abstractmethod
    async def fetch(self, client: httpx.AsyncClient, q: SearchQuery) -> list[JobRecord]:
        """Return normalized postings. Raise on transport/parse failure."""

    # -- helpers available to every connector ------------------------------

    @staticmethod
    def matches(q: SearchQuery, title: str, description: str = "", location: str = "") -> bool:
        """Client-side filter for sources with no server-side search.

        Several Tier-1 boards return a full dump with no query parameter, so filtering
        has to happen here. Terms are ANDed: every whitespace-separated term must appear
        somewhere in the title or description.
        """
        if q.query:
            haystack = f"{title} {description}".lower()
            if not all(term in haystack for term in q.query.lower().split()):
                return False
        if q.location:
            if q.location.lower().strip() not in location.lower():
                return False
        return True


class _TextExtractor(HTMLParser):
    """Minimal HTML -> readable text.

    Job descriptions arrive as HTML from every source. We only need clean text for the
    LLM and for display, so a full markdown converter would be a dependency we don't
    need. Block-level tags become newlines; list items get a bullet.
    """

    BLOCK = {
        "p", "div", "br", "h1", "h2", "h3", "h4", "h5", "h6",
        "ul", "ol", "tr", "section", "article",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._out = StringIO()
        self._skip = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in ("script", "style"):
            self._skip += 1
        elif tag == "li":
            self._out.write("\n- ")
        elif tag in self.BLOCK:
            self._out.write("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style") and self._skip:
            self._skip -= 1
        elif tag in self.BLOCK:
            self._out.write("\n")

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self._out.write(data)

    def text(self) -> str:
        raw = self._out.getvalue().replace("\xa0", " ")
        lines = [line.strip() for line in raw.splitlines()]
        cleaned: list[str] = []
        for line in lines:
            if line or (cleaned and cleaned[-1]):
                cleaned.append(line)
        return "\n".join(cleaned).strip()


#: Matches an *escaped* opening tag — `&lt;p&gt;`, `&lt;/div&gt;`, `&lt;h4 class=…`.
#: The `(?:amp;)*` handles doubly-escaped payloads (`&amp;lt;p&amp;gt;`), where the
#: literal `&lt;` never appears until the first unescape pass has run.
#: Requiring a letter or slash after the `<` keeps prose like "latency &lt; 200ms"
#: from being mistaken for markup.
_ESCAPED_MARKUP = re.compile(r"&(?:amp;)*lt;/?[a-zA-Z]")


def html_to_text(markup: str) -> str:
    """HTML -> readable text, tolerating sources that HTML-escape their markup.

    Greenhouse returns `content` with the tags themselves escaped (`&lt;div&gt;…`).
    Feeding that straight to HTMLParser is a silent trap: `convert_charrefs` turns the
    entities into literal `<div>` *text*, so the parser sees no tags at all and the
    "cleaned" description is the raw markup verbatim. That noise then goes into the
    tailoring prompt, wasting tokens and burying the actual requirements.

    So: unescape first when the payload looks like escaped markup, and loop, because a
    doubly-escaped source (`&amp;lt;p&amp;gt;`) needs more than one pass. Bounded to
    keep a pathological input from spinning.
    """
    if not markup:
        return ""

    for _ in range(3):
        if not _ESCAPED_MARKUP.search(markup):
            break
        unescaped = unescape(markup)
        if unescaped == markup:
            break
        markup = unescaped

    parser = _TextExtractor()
    try:
        parser.feed(markup)
        parser.close()
    except Exception:
        return markup
    return parser.text()
