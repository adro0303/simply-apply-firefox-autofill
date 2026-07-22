"""HTML -> text tests.

Regression coverage for a bug found only by looking at the running UI: Greenhouse
HTML-escapes its markup, and because HTMLParser's `convert_charrefs` turns `&lt;p&gt;`
into literal `<p>` *text*, the parser saw zero tags and passed the raw markup straight
through. Length checks in a smoke test looked fine — the string was long, just wrong.
Every one of those descriptions then went into the tailoring prompt as noise.
"""

from __future__ import annotations

from app.connectors.base import html_to_text


def test_plain_html_is_stripped() -> None:
    out = html_to_text("<div><p>Hello</p><p>World</p></div>")
    assert "<" not in out
    assert "Hello" in out and "World" in out


def test_escaped_markup_is_unescaped_then_stripped() -> None:
    """The actual Greenhouse shape."""
    raw = "&lt;div class=&quot;content-intro&quot;&gt;&lt;p&gt;GitLab is a platform.&lt;/p&gt;&lt;/div&gt;"
    out = html_to_text(raw)
    assert out == "GitLab is a platform."
    assert "&lt;" not in out and "<" not in out and "class=" not in out


def test_double_escaped_markup_is_handled() -> None:
    assert html_to_text("&amp;lt;p&amp;gt;Nested&amp;lt;/p&amp;gt;") == "Nested"


def test_literal_less_than_in_prose_is_not_treated_as_markup() -> None:
    """`if x &lt; y` must survive — the guard requires a letter/slash after `&lt;`."""
    out = html_to_text("<p>Latency &lt; 200ms required</p>")
    assert "< 200ms" in out


def test_list_items_become_bullets() -> None:
    out = html_to_text("<ul><li>First</li><li>Second</li></ul>")
    assert "- First" in out and "- Second" in out


def test_script_and_style_content_is_dropped() -> None:
    out = html_to_text("<div>Keep<script>var evil=1;</script><style>.x{}</style></div>")
    assert "Keep" in out
    assert "evil" not in out and ".x{}" not in out


def test_entities_in_text_are_decoded() -> None:
    assert "R&D" in html_to_text("<p>R&amp;D team</p>")


def test_empty_and_none_safe() -> None:
    assert html_to_text("") == ""


def test_plain_text_passes_through() -> None:
    assert html_to_text("Just a plain description.") == "Just a plain description."
