"""Markdown → sanitized HTML for blog posts."""

from __future__ import annotations


def render_markdown(source: str) -> str:
    """Convert Markdown to HTML and strip scripts, handlers, and javascript: URLs.

    External links keep ``rel="noopener nofollow"``. Imported lazily so the blog
    app can load without paying the import cost on unrelated code paths.
    """
    import markdown as md
    import nh3

    html = md.markdown(
        source,
        extensions=["fenced_code", "tables", "smarty", "nl2br"],
        output_format="html",
    )
    return nh3.clean(
        html,
        link_rel="noopener nofollow",
        url_schemes={"http", "https", "mailto"},
    )
