import os
import re
import xml.etree.ElementTree as ET

import requests
from bs4 import BeautifulSoup, NavigableString

from .config import DOC_VIEWER_BASE, LEGISINFO_BASE
from .parser import (
    get_latest_event_date_from_xml,
    get_stage_date_from_xml,
    get_stage_info,
    make_summary_markdown,
    xml_to_markdown,
)
from .schemas import MetadataPendingBill, ScrapeResult, StagePendingBill
from .utils import clean_sponsor_name, generate_sponsor_email, log_message


def fetch_url_with_cache(url, cache_path=None):
    """Fetch URL contents, using a local cache file if cache_path is specified."""
    if cache_path and os.path.exists(cache_path):
        with open(cache_path, encoding="utf-8") as f:
            return f.read()

    try:
        res = requests.get(url, timeout=30)
        if res.status_code == 200:
            if cache_path:
                os.makedirs(os.path.dirname(cache_path), exist_ok=True)
                with open(cache_path, "w", encoding="utf-8") as f:
                    f.write(res.text)
            return res.text
    except Exception as e:
        log_message(f"    Error fetching URL {url}: {e}")
    return None


def clean_html_to_markdown(soup_node):
    """Clean DocumentViewer HTML block and format it into clean Markdown recursively."""

    # Decompose navigation, headers, footers, accessible notice
    def is_noise_class(c):
        return c and any(x in c.lower() for x in ("navigation", "header", "footer", "toc", "option"))

    for elem in soup_node.find_all(class_=is_noise_class):
        elem.decompose()

    # Also find and decompose links to next/prev page
    for link in soup_node.find_all("a"):
        text = link.get_text().lower()
        if any(x in text for x in ("next page", "previous page", "table of contents", "accessible@parl.gc.ca")):
            link.decompose()

    # Recursive DOM renderer
    def render_node(node):
        if isinstance(node, NavigableString):
            return node.string or ""

        if not node.name:
            return ""

        if node.name in ("style", "script", "head", "meta", "link"):
            return ""

        # Render child nodes recursively
        children_text = "".join(render_node(child) for child in node.children)

        if node.name in ("h1", "h2", "h3", "h4"):
            text = " ".join(children_text.split()).strip()
            if text:
                level = int(node.name[1])
                return f"\n\n{'#' * level} {text}\n\n"
            return ""

        if node.name == "p":
            text = " ".join(children_text.split()).strip()
            if text:
                return f"\n\n{text}\n\n"
            return ""

        if node.name == "br":
            return "\n"

        if node.name in ("b", "strong"):
            text = children_text.strip()
            if text:
                return f"**{text}**"
            return ""

        if node.name in ("i", "em"):
            text = children_text.strip()
            if text:
                return f"*{text}*"
            return ""

        if node.name == "li":
            text = " ".join(children_text.split()).strip()
            if text:
                return f"\n* {text}"
            return ""

        if node.name in ("ul", "ol"):
            return f"\n{children_text}\n"

        if node.name == "blockquote":
            lines = [f"> {line}" for line in children_text.splitlines() if line.strip()]
            return "\n\n" + "\n".join(lines) + "\n\n"

        if node.name == "table":
            rows = []
            cols_count = 0
            for tr in node.find_all("tr", recursive=False):
                cols = [" ".join(td.get_text().split()).strip() for td in tr.find_all(["td", "th"], recursive=False)]
                if any(cols):
                    rows.append("| " + " | ".join(cols) + " |")
                    cols_count = max(cols_count, len(cols))
            if rows:
                sep = "| " + " | ".join("---" for _ in range(cols_count)) + " |"
                rows.insert(1, sep)
                return "\n\n" + "\n".join(rows) + "\n\n"
            return ""

        if node.name in ("div", "span", "td", "tr", "th", "tbody"):
            return children_text

        return children_text

    text = render_node(soup_node)

    # Clean up empty lines/duplicates
    cleaned_lines = []
    for line in text.split("\n"):
        line_str = line.strip()
        if line_str:
            cleaned_lines.append(line_str)
        elif cleaned_lines and cleaned_lines[-1] != "":
            cleaned_lines.append("")

    return "\n".join(cleaned_lines).strip()


def scrape_html_bill_text(session, bill_number, slug, cache_dir=None):
    """Scrape and assemble all pages of the bill text from DocumentViewer HTML, returning markdown."""
    stage_url = f"{DOC_VIEWER_BASE}/en/{session}/bill/{bill_number}/{slug}"
    cache_path = None
    if cache_dir:
        cache_path = os.path.join(cache_dir, "docviewer", session, f"{bill_number}_{slug}.html")

    try:
        html = fetch_url_with_cache(stage_url, cache_path)
        if not html:
            return ""

        # Find all page links
        page_pattern = rf'/DocumentViewer/en/{session}/bill/{bill_number}/{slug}/page-[^"\'\s>]+'
        page_links = re.findall(page_pattern, html, re.IGNORECASE)

        # Deduplicate preserving order
        seen = set()
        unique_pages = []
        for pl in page_links:
            clean_pl = pl.split("#")[0]
            if clean_pl not in seen:
                seen.add(clean_pl)
                unique_pages.append(clean_pl)

        # If there are subpages, fetch them
        text_blocks = []
        if unique_pages:
            log_message(f"      Found {len(unique_pages)} HTML pages to fetch...")
            for idx, pl in enumerate(unique_pages):
                page_url = f"https://www.parl.ca{pl}"
                p_cache_path = None
                if cache_dir:
                    p_cache_path = os.path.join(
                        cache_dir, "stages", session, bill_number, f"{slug}_page-{idx + 1}.html"
                    )
                p_html = fetch_url_with_cache(page_url, p_cache_path)
                if p_html:
                    soup = BeautifulSoup(p_html, "html.parser")
                    content_div = soup.find(id="publicationContent") or soup.find(
                        class_="publication-container-content"
                    )
                    if content_div:
                        text_blocks.append(clean_html_to_markdown(content_div))
        else:
            # Single page
            soup = BeautifulSoup(html, "html.parser")
            content_div = soup.find(id="publicationContent") or soup.find(class_="publication-container-content")
            if content_div:
                text_blocks.append(clean_html_to_markdown(content_div))

        return "\n\n".join(text_blocks)
    except Exception as e:
        log_message(f"      Error scraping HTML bill text: {e}")
        return ""


def extract_xml_links_from_docviewer(session, bill_number, cache_dir=None):
    """Scrape first-reading page to find all available stages and their XML/HTML document links."""
    first_reading_url = f"{DOC_VIEWER_BASE}/en/{session}/bill/{bill_number}/first-reading"
    fr_cache_path = None
    if cache_dir:
        fr_cache_path = os.path.join(cache_dir, "docviewer", session, f"{bill_number}_first-reading.html")

    try:
        fr_text = fetch_url_with_cache(first_reading_url, fr_cache_path)
        if not fr_text:
            return {}, {}

        soup = BeautifulSoup(fr_text, "html.parser")

        # Find all available publication tabs
        tabs = soup.select(".publication-tabs .nav-tab a")
        stage_slugs = []
        if tabs:
            for tab in tabs:
                href = tab.get("href", "")
                match = re.search(rf"/bill/{bill_number}/([^/?#\s]+)", href)
                if match:
                    stage_slugs.append(match.group(1))
        else:
            stage_slugs = ["first-reading"]

        stage_slugs = list(dict.fromkeys(stage_slugs))

        xml_links = {}
        html_links = {}
        for slug in stage_slugs:
            stage_url = f"{DOC_VIEWER_BASE}/en/{session}/bill/{bill_number}/{slug}"
            html_links[slug] = stage_url

            s_cache_path = None
            if cache_dir:
                s_cache_path = os.path.join(cache_dir, "docviewer", session, f"{bill_number}_{slug}.html")

            s_text = fetch_url_with_cache(stage_url, s_cache_path)
            if s_text:
                xml_match = re.search(r'href=["\'](/Content/Bills/[^"\']+_E\.xml)["\']', s_text)
                if xml_match:
                    xml_links[slug] = f"https://www.parl.ca{xml_match.group(1)}"
                else:
                    generic_xml_match = re.search(r'href=["\'](/Content/Bills/[^"\']+\.xml)["\']', s_text)
                    if generic_xml_match:
                        xml_links[slug] = f"https://www.parl.ca{generic_xml_match.group(1)}"

        return xml_links, html_links
    except Exception as e:
        log_message(f"    Error scraping DocumentViewer for {bill_number}: {e}")
        return {}, {}


def scrape_bill(
    session, bill_number, cache_bill_dir, repo_path, already_downloaded_stages, dry_run=False, cache_dir=None
) -> ScrapeResult:
    """Scrape detailed bill metadata and draft texts sequentially into cache, returning pending commits."""
    os.makedirs(cache_bill_dir, exist_ok=True)
    metadata_path = os.path.join(cache_bill_dir, "metadata.xml")
    summary_path = os.path.join(cache_bill_dir, "summary.md")

    # 1. Fetch detailed metadata XML
    detail_url = f"{LEGISINFO_BASE}/en/bill/{session}/{bill_number}/xml"
    meta_cache_path = None
    if cache_dir:
        meta_cache_path = os.path.join(cache_dir, "metadata", session, f"{bill_number}.xml")

    try:
        response_text = fetch_url_with_cache(detail_url, meta_cache_path)
        if response_text:
            if not dry_run:
                with open(metadata_path, "w", encoding="utf-8") as f:
                    f.write(response_text)
                summary_md = make_summary_markdown(metadata_path)
                with open(summary_path, "w", encoding="utf-8") as f:
                    f.write(summary_md)
        else:
            log_message(f"    Failed to fetch detailed XML for {bill_number}")
            return ScrapeResult(
                success=False,
                updated_stages=set(already_downloaded_stages),
                author_name="Parliament of Canada",
                author_email="sponsor@parl.gc.ca",
                pending_commits=[],
            )
    except Exception as e:
        log_message(f"    Error fetching metadata for {bill_number}: {e}")
        return ScrapeResult(
            success=False,
            updated_stages=set(already_downloaded_stages),
            author_name="Parliament of Canada",
            author_email="sponsor@parl.gc.ca",
            pending_commits=[],
        )

    # Parse sponsor details from the newly downloaded metadata.xml
    sponsor_name = "Parliament of Canada"
    try:
        tree = ET.parse(metadata_path)
        root = tree.getroot()
        sp_name = root.findtext(".//SponsorPersonName") or ""
        sp_title = root.findtext(".//SponsorAffiliationTitleEn") or ""
        if sp_name:
            sponsor_name = f"{sp_title} {sp_name}" if sp_title else sp_name
    except Exception:
        pass

    author_name = clean_sponsor_name(sponsor_name)
    author_email = generate_sponsor_email(sponsor_name)

    # 2. Find available stage text documents from DocumentViewer
    xml_links, html_links = extract_xml_links_from_docviewer(session, bill_number, cache_dir=cache_dir)
    available_stages = set(xml_links.keys()) | set(html_links.keys())

    # Filter to stages not yet downloaded in this session
    stages_to_download = []
    for slug in available_stages:
        if slug not in already_downloaded_stages:
            stages_to_download.append(slug)

    # Sort stages chronologically
    stages_to_download.sort(key=lambda s: get_stage_info(s)[1])

    current_stages = set(already_downloaded_stages)
    pending_commits: list[StagePendingBill | MetadataPendingBill] = []

    # Create subfolder in cache for stage-specific drafts
    stages_cache_dir = os.path.join(cache_bill_dir, "stages")
    os.makedirs(stages_cache_dir, exist_ok=True)

    # 3. Sequentially download and cache each new stage
    for slug in stages_to_download:
        stage_name, _ = get_stage_info(slug)
        is_xml = slug in xml_links
        url = xml_links[slug] if is_xml else html_links[slug]

        source_type = "XML" if is_xml else "HTML Fallback"
        log_message(f"    Downloading sequential stage {bill_number} {stage_name} ({source_type}): {url}")

        try:
            if is_xml:
                st_cache_path = None
                if cache_dir:
                    st_cache_path = os.path.join(cache_dir, "stages", session, bill_number, f"{slug}.xml")

                res_text = fetch_url_with_cache(url, st_cache_path)
                if res_text:
                    current_stages.add(slug)

                    stage_xml_path = os.path.join(stages_cache_dir, f"{slug}.xml")
                    stage_md_path = os.path.join(stages_cache_dir, f"{slug}.md")

                    if not dry_run:
                        with open(stage_xml_path, "w", encoding="utf-8") as f:
                            f.write(res_text)
                        try:
                            root = ET.fromstring(res_text.encode("utf-8"))
                            md_content = xml_to_markdown(root)
                            with open(stage_md_path, "w", encoding="utf-8") as md_f:
                                md_f.write(md_content)
                        except Exception as parse_err:
                            log_message(f"      Failed to parse XML to Markdown: {parse_err}")
                else:
                    log_message(f"      Failed to download XML: {url}")
                    continue
            else:
                # HTML Fallback
                md_content = scrape_html_bill_text(session, bill_number, slug, cache_dir=cache_dir)
                if md_content:
                    current_stages.add(slug)

                    stage_xml_path = os.path.join(stages_cache_dir, f"{slug}.xml")
                    stage_md_path = os.path.join(stages_cache_dir, f"{slug}.md")

                    if not dry_run:
                        stub_xml = (
                            f"<Bill><Source>HTML Fallback</Source><Session>{session}</Session>"
                            f"<Number>{bill_number}</Number><Stage>{stage_name}</Stage></Bill>"
                        )
                        with open(stage_xml_path, "w", encoding="utf-8") as f:
                            f.write(stub_xml)
                        with open(stage_md_path, "w", encoding="utf-8") as f:
                            f.write(md_content)
                else:
                    log_message("      Failed to scrape HTML content")
                    continue

            # If download/scrape was successful, append the pending commit
            stage_date = get_stage_date_from_xml(metadata_path, slug)
            if not stage_date:
                stage_date = get_latest_event_date_from_xml(metadata_path)

            pending_bill = StagePendingBill(
                session=session,
                bill_number=bill_number,
                slug=slug,
                stage_name=stage_name,
                stage_date=stage_date,
                author_name=author_name,
                author_email=author_email,
                stage_xml_path=stage_xml_path,
                stage_md_path=stage_md_path,
                metadata_xml_path=metadata_path,
                summary_md_path=summary_path,
            )
            pending_commits.append(pending_bill)
        except Exception as e:
            log_message(f"      Error: {e}")

    # 4. Force populate bill_text.xml/md if missing on disk in target repo
    target_bill_xml_path = os.path.join(repo_path, session, "bills", bill_number, "bill_text.xml")
    if not stages_to_download and not os.path.exists(target_bill_xml_path) and available_stages:
        sorted_available = sorted(available_stages, key=lambda s: get_stage_info(s)[1])
        if sorted_available:
            latest_slug = sorted_available[-1]
            is_xml = latest_slug in xml_links
            url = xml_links[latest_slug] if is_xml else html_links[latest_slug]
            source_type = "XML" if is_xml else "HTML Fallback"
            log_message(f"    Restoring sequential text files from latest stage ({latest_slug}) via {source_type}...")
            try:
                if is_xml:
                    st_cache_path = None
                    if cache_dir:
                        st_cache_path = os.path.join(cache_dir, "stages", session, bill_number, f"{latest_slug}.xml")
                    res_text = fetch_url_with_cache(url, st_cache_path)
                    if res_text and not dry_run:
                        with open(os.path.join(cache_bill_dir, "bill_text.xml"), "w", encoding="utf-8") as f:
                            f.write(res_text)
                        root = ET.fromstring(res_text.encode("utf-8"))
                        md_content = xml_to_markdown(root)
                        with open(os.path.join(cache_bill_dir, "bill_text.md"), "w", encoding="utf-8") as md_f:
                            md_f.write(md_content)
                else:
                    md_content = scrape_html_bill_text(session, bill_number, latest_slug, cache_dir=cache_dir)
                    if md_content and not dry_run:
                        stub_xml = (
                            f"<Bill><Source>HTML Fallback</Source><Session>{session}</Session>"
                            f"<Number>{bill_number}</Number><Stage>{latest_slug}</Stage></Bill>"
                        )
                        with open(os.path.join(cache_bill_dir, "bill_text.xml"), "w", encoding="utf-8") as f:
                            f.write(stub_xml)
                        with open(os.path.join(cache_bill_dir, "bill_text.md"), "w", encoding="utf-8") as f:
                            f.write(md_content)
            except Exception as e:
                log_message(f"      Error restoring file: {e}")

    # 5. Always queue a metadata update commit at the end (will be skipped by git if no actual changes are made)
    event_date = get_latest_event_date_from_xml(metadata_path)
    restore_xml = os.path.join(cache_bill_dir, "bill_text.xml")
    restore_md = os.path.join(cache_bill_dir, "bill_text.md")

    pending_bill = MetadataPendingBill(
        session=session,
        bill_number=bill_number,
        event_date=event_date,
        author_name=author_name,
        author_email=author_email,
        metadata_xml_path=metadata_path,
        summary_md_path=summary_path,
        restore_xml_path=restore_xml if os.path.exists(restore_xml) else None,
        restore_md_path=restore_md if os.path.exists(restore_md) else None,
    )

    pending_commits.append(pending_bill)

    return ScrapeResult(
        success=True,
        updated_stages=current_stages,
        author_name=author_name,
        author_email=author_email,
        pending_commits=pending_commits,
    )
