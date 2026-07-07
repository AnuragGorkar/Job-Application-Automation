import html

from bs4 import BeautifulSoup


def clean_html(raw_text: str) -> str:
    """Centralized HTML unescaping and stripping."""
    if not raw_text:
        return ""

    unescaped = html.unescape(raw_text)
    return BeautifulSoup(unescaped, "html.parser").get_text(separator="\n").strip()
