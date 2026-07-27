from bs4 import BeautifulSoup

from legisinfo_scraper.crawler import clean_html_to_markdown


def test_clean_html_to_markdown_deep_nesting():
    # Build deeply nested HTML structure: 3000 levels of nested div tags
    html_parts = []
    for i in range(3000):
        html_parts.append(f'<div id="d{i}">')
    html_parts.append("<p>Deeply nested text content</p>")
    for _i in range(3000):
        html_parts.append("</div>")

    html = "".join(html_parts)
    soup = BeautifulSoup(html, "html.parser")
    markdown = clean_html_to_markdown(soup)
    assert "Deeply nested text content" in markdown
