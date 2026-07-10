import os
import re
import xml.etree.ElementTree as ET
import requests
from bs4 import BeautifulSoup, NavigableString
from .config import LEGISINFO_BASE, DOC_VIEWER_BASE
from .utils import log_message, clean_sponsor_name, generate_sponsor_email
from .git_utils import run_command, run_git_commit
from .parser import (
    get_stage_info,
    xml_to_markdown,
    make_summary_markdown,
    get_stage_date_from_xml,
    get_latest_event_date_from_xml
)

def clean_html_to_markdown(soup_node):
    """Clean DocumentViewer HTML block and format it into clean Markdown."""
    # Decompose navigation, headers, footers, accessible notice
    for elem in soup_node.find_all(class_=lambda c: c and any(x in c.lower() for x in ("navigation", "header", "footer", "toc", "option"))):
        elem.decompose()
        
    # Also find and decompose links to next/prev page
    for link in soup_node.find_all("a"):
        text = link.get_text().lower()
        if any(x in text for x in ("next page", "previous page", "table of contents", "accessible@parl.gc.ca")):
            link.decompose()
            
    # Convert remaining structure
    lines = []
    for child in soup_node.descendants:
        if child.name in ("h1", "h2", "h3", "h4"):
            text = " ".join(child.get_text().split())
            if text:
                level = int(child.name[1])
                lines.append(f"\n\n{'#' * level} {text}\n\n")
        elif child.name == "p":
            text = " ".join(child.get_text().split())
            if text:
                lines.append(f"{text}\n\n")
        elif isinstance(child, NavigableString):
            text = child.strip()
            # Avoid duplicating text that is already inside children
            if text and child.parent.name not in ("p", "h1", "h2", "h3", "h4", "a", "div", "span"):
                lines.append(f"{text}\n\n")
                
    # Fallback to simple get_text if we ended up empty
    text = "".join(lines).strip()
    if not text:
        text = soup_node.get_text()
        
    # Clean up empty lines/duplicates
    cleaned_lines = []
    for line in text.split("\n"):
        line_str = line.strip()
        if line_str:
            cleaned_lines.append(line_str)
        elif cleaned_lines and cleaned_lines[-1] != "":
            cleaned_lines.append("")
            
    return "\n".join(cleaned_lines)

def scrape_html_bill_text(session, bill_number, slug):
    """Scrape and assemble all pages of the bill text from DocumentViewer HTML, returning markdown."""
    stage_url = f"{DOC_VIEWER_BASE}/en/{session}/bill/{bill_number}/{slug}"
    try:
        res = requests.get(stage_url)
        if res.status_code != 200:
            return ""
            
        html = res.text
        # Find all page links
        page_pattern = rf'/DocumentViewer/en/{session}/bill/{bill_number}/{slug}/page-[^"\'\s>]+'
        page_links = re.findall(page_pattern, html, re.IGNORECASE)
        
        # Deduplicate preserving order
        seen = set()
        unique_pages = []
        for pl in page_links:
            clean_pl = pl.split('#')[0]
            if clean_pl not in seen:
                seen.add(clean_pl)
                unique_pages.append(clean_pl)
                
        # If there are subpages, fetch them
        text_blocks = []
        if unique_pages:
            log_message(f"      Found {len(unique_pages)} HTML pages to fetch...")
            for pl in unique_pages:
                page_url = f"https://www.parl.ca{pl}"
                p_res = requests.get(page_url)
                if p_res.status_code == 200:
                    soup = BeautifulSoup(p_res.text, 'html.parser')
                    content_div = soup.find(id="publicationContent") or soup.find(class_="publication-container-content")
                    if content_div:
                        text_blocks.append(clean_html_to_markdown(content_div))
        else:
            # Single page
            soup = BeautifulSoup(html, 'html.parser')
            content_div = soup.find(id="publicationContent") or soup.find(class_="publication-container-content")
            if content_div:
                text_blocks.append(clean_html_to_markdown(content_div))
                
        return "\n\n".join(text_blocks)
    except Exception as e:
        log_message(f"      Error scraping HTML bill text: {e}")
        return ""

def extract_xml_links_from_docviewer(session, bill_number):
    """Scrape first-reading page to find all available stages and their XML/HTML document links."""
    first_reading_url = f"{DOC_VIEWER_BASE}/en/{session}/bill/{bill_number}/first-reading"
    
    try:
        response = requests.get(first_reading_url)
        if response.status_code != 200:
            return {}, {}
            
        soup = BeautifulSoup(response.text, 'html.parser')
        
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
            
            res = requests.get(stage_url)
            if res.status_code == 200:
                xml_match = re.search(r'href=["\'](/Content/Bills/[^"\']+_E\.xml)["\']', res.text)
                if xml_match:
                    xml_links[slug] = f"https://www.parl.ca{xml_match.group(1)}"
                else:
                    generic_xml_match = re.search(r'href=["\'](/Content/Bills/[^"\']+\.xml)["\']', res.text)
                    if generic_xml_match:
                        xml_links[slug] = f"https://www.parl.ca{generic_xml_match.group(1)}"
        
        return xml_links, html_links
    except Exception as e:
        log_message(f"    Error scraping DocumentViewer for {bill_number}: {e}")
        return {}, {}

def scrape_bill(session, bill_number, cache_bill_dir, repo_path, already_downloaded_stages, dry_run=False):
    """Scrape detailed bill metadata and draft texts sequentially into cache, returning pending commits."""
    os.makedirs(cache_bill_dir, exist_ok=True)
    metadata_path = os.path.join(cache_bill_dir, "metadata.xml")
    summary_path = os.path.join(cache_bill_dir, "summary.md")
    
    # 1. Fetch detailed metadata XML
    detail_url = f"{LEGISINFO_BASE}/en/bill/{session}/{bill_number}/xml"
    try:
        response = requests.get(detail_url)
        if response.status_code == 200:
            if not dry_run:
                with open(metadata_path, "w", encoding="utf-8") as f:
                    f.write(response.text)
                summary_md = make_summary_markdown(metadata_path)
                with open(summary_path, "w", encoding="utf-8") as f:
                    f.write(summary_md)
        else:
            log_message(f"    Failed to fetch detailed XML for {bill_number} (status {response.status_code})")
            return False, already_downloaded_stages, "Parliament of Canada", "sponsor@parl.gc.ca", []
    except Exception as e:
        log_message(f"    Error fetching metadata for {bill_number}: {e}")
        return False, already_downloaded_stages, "Parliament of Canada", "sponsor@parl.gc.ca", []

    # Parse sponsor details from the newly downloaded metadata.xml
    sponsor_name = "Parliament of Canada"
    try:
        tree = ET.parse(metadata_path)
        root = tree.getroot()
        sp_name = root.findtext(".//SponsorPersonName") or ""
        sp_title = root.findtext(".//SponsorAffiliationTitleEn") or ""
        if sp_name:
            if sp_title:
                sponsor_name = f"{sp_title} {sp_name}"
            else:
                sponsor_name = sp_name
    except Exception:
        pass
        
    author_name = clean_sponsor_name(sponsor_name)
    author_email = generate_sponsor_email(sponsor_name)
    
    # 2. Find available stage text documents from DocumentViewer
    xml_links, html_links = extract_xml_links_from_docviewer(session, bill_number)
    available_stages = set(xml_links.keys()) | set(html_links.keys())
    
    # Filter to stages not yet downloaded in this session
    stages_to_download = []
    for slug in available_stages:
        if slug not in already_downloaded_stages:
            stages_to_download.append(slug)
            
    # Sort stages chronologically
    stages_to_download.sort(key=lambda s: get_stage_info(s)[1])
    
    current_stages = set(already_downloaded_stages)
    pending_commits = []
    
    # Create subfolder in cache for stage-specific drafts
    stages_cache_dir = os.path.join(cache_bill_dir, "stages")
    os.makedirs(stages_cache_dir, exist_ok=True)
    
    # 3. Sequentially download and cache each new stage
    for slug in stages_to_download:
        stage_name, _ = get_stage_info(slug)
        is_xml = slug in xml_links
        url = xml_links[slug] if is_xml else html_links[slug]
        
        log_message(f"    Downloading sequential stage {bill_number} {stage_name} ({'XML' if is_xml else 'HTML Fallback'}): {url}")
        
        try:
            if is_xml:
                res = requests.get(url)
                if res.status_code == 200:
                    current_stages.add(slug)
                    
                    stage_xml_path = os.path.join(stages_cache_dir, f"{slug}.xml")
                    stage_md_path = os.path.join(stages_cache_dir, f"{slug}.md")
                    
                    if not dry_run:
                        with open(stage_xml_path, "w", encoding="utf-8") as f:
                            f.write(res.text)
                        try:
                            root = ET.fromstring(res.content)
                            md_content = xml_to_markdown(root)
                            with open(stage_md_path, "w", encoding="utf-8") as md_f:
                                md_f.write(md_content)
                        except Exception as parse_err:
                            log_message(f"      Failed to parse XML to Markdown: {parse_err}")
                else:
                    log_message(f"      Failed to download XML (status {res.status_code})")
                    continue
            else:
                # HTML Fallback
                md_content = scrape_html_bill_text(session, bill_number, slug)
                if md_content:
                    current_stages.add(slug)
                    
                    stage_xml_path = os.path.join(stages_cache_dir, f"{slug}.xml")
                    stage_md_path = os.path.join(stages_cache_dir, f"{slug}.md")
                    
                    if not dry_run:
                        stub_xml = f"<Bill><Source>HTML Fallback</Source><Session>{session}</Session><Number>{bill_number}</Number><Stage>{stage_name}</Stage></Bill>"
                        with open(stage_xml_path, "w", encoding="utf-8") as f:
                            f.write(stub_xml)
                        with open(stage_md_path, "w", encoding="utf-8") as f:
                            f.write(md_content)
                else:
                    log_message(f"      Failed to scrape HTML content")
                    continue

            # If download/scrape was successful, append the pending commit
            stage_date = get_stage_date_from_xml(metadata_path, slug)
            if not stage_date:
                stage_date = get_latest_event_date_from_xml(metadata_path)
                
            pending_commits.append({
                "type": "stage",
                "session": session,
                "bill_number": bill_number,
                "slug": slug,
                "stage_name": stage_name,
                "stage_date": stage_date,
                "author_name": author_name,
                "author_email": author_email,
                "stage_xml_path": stage_xml_path,
                "stage_md_path": stage_md_path,
                "metadata_xml_path": metadata_path,
                "summary_md_path": summary_path,
            })
        except Exception as e:
            log_message(f"      Error: {e}")
            
    # 4. Force populate bill_text.xml/md if missing on disk in target repo
    target_bill_xml_path = os.path.join(repo_path, session, "bills", bill_number, "bill_text.xml")
    if not stages_to_download and not os.path.exists(target_bill_xml_path) and available_stages:
        sorted_available = sorted(list(available_stages), key=lambda s: get_stage_info(s)[1])
        if sorted_available:
            latest_slug = sorted_available[-1]
            is_xml = latest_slug in xml_links
            url = xml_links[latest_slug] if is_xml else html_links[latest_slug]
            log_message(f"    Restoring sequential text files from latest stage ({latest_slug}) via {'XML' if is_xml else 'HTML Fallback'}...")
            try:
                if is_xml:
                    res = requests.get(url)
                    if res.status_code == 200:
                        if not dry_run:
                            with open(os.path.join(cache_bill_dir, "bill_text.xml"), "w", encoding="utf-8") as f:
                                f.write(res.text)
                            root = ET.fromstring(res.content)
                            md_content = xml_to_markdown(root)
                            with open(os.path.join(cache_bill_dir, "bill_text.md"), "w", encoding="utf-8") as md_f:
                                md_f.write(md_content)
                else:
                    md_content = scrape_html_bill_text(session, bill_number, latest_slug)
                    if md_content:
                        if not dry_run:
                            stub_xml = f"<Bill><Source>HTML Fallback</Source><Session>{session}</Session><Number>{bill_number}</Number><Stage>{latest_slug}</Stage></Bill>"
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
    
    pending_commits.append({
        "type": "metadata",
        "session": session,
        "bill_number": bill_number,
        "event_date": event_date,
        "author_name": author_name,
        "author_email": author_email,
        "metadata_xml_path": metadata_path,
        "summary_md_path": summary_path,
        "restore_xml_path": restore_xml if os.path.exists(restore_xml) else None,
        "restore_md_path": restore_md if os.path.exists(restore_md) else None,
    })
                
    return True, current_stages, author_name, author_email, pending_commits
