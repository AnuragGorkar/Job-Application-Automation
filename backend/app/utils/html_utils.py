import html
from bs4 import BeautifulSoup

def clean_html(raw_text: str) -> str:
    """Centralized HTML unescaping and stripping."""
    if not raw_text:
        return ""

    unescaped = html.unescape(raw_text)
    soup = BeautifulSoup(unescaped, "html.parser")

    meaningful = [s for s in soup.find_all(string=True) if s.strip()]

    return "\n".join(meaningful).strip()