#!/usr/bin/env python3
import os
import sys
import re
import argparse
import subprocess
import xml.etree.ElementTree as ET
import requests
from bs4 import BeautifulSoup
from datetime import datetime

# Base URL for LEGISinfo
LEGISINFO_BASE = "https://www.parl.ca/legisinfo"
DOC_VIEWER_BASE = "https://www.parl.ca/DocumentViewer"

def run_command(args, cwd=None):
    """Run a system command and return output."""
    result = subprocess.run(args, capture_output=True, text=True, cwd=cwd)
    return result

def clean_inline_text(elem):
    """Recursively reconstructs inline text, formatting tags like Ins, DefinedTermEn, Emphasis."""
    text = elem.text or ""
    for child in elem:
        child_text = clean_inline_text(child)
        tag = child.tag
        if tag in ("DefinedTermEn", "DefinedTermFr", "Ins", "ins"):
            text += f"**{child_text}**"
        elif tag == "Emphasis":
            text += f"*{child_text}*"
        elif tag in ("XRefExternal", "XRefInternal"):
            text += f"`{child_text}`"
        else:
            text += child_text
        if child.tail:
            text += child.tail
    return text.strip()

def xml_to_markdown(elem, indent=""):
    """Convert a bill text XML node recursively to Markdown."""
    lines = []
    tag = elem.tag
    
    if tag == "Identification":
        bill_num = elem.findtext("BillNumber") or ""
        long_title = elem.findtext("LongTitle") or ""
        sponsor = elem.findtext("BillSponsor") or ""
        lines.append(f"# Bill {bill_num}: {long_title}\n\n")
        if sponsor:
            lines.append(f"**Sponsor**: {sponsor}\n\n")
    elif tag == "Summary":
        lines.append("## Summary\n\n")
        for child in elem:
            if child.tag == "Provision":
                for text_node in child.findall(".//Text"):
                    lines.append(clean_inline_text(text_node) + "\n\n")
    elif tag == "Heading":
        level = elem.attrib.get("level", "1")
        title_node = elem.find("TitleText")
        if title_node is not None:
            title_text = clean_inline_text(title_node)
            hashes = "#" * (int(level) + 1)
            lines.append(f"\n{hashes} {title_text}\n\n")
    elif tag == "Section":
        label = elem.find("Label")
        label_text = clean_inline_text(label) if label is not None else ""
        lines.append(f"### Section {label_text}\n\n")
        for child in elem:
            if child.tag not in ("Label", "Subsection", "ExplanatoryNote"):
                lines.append(xml_to_markdown(child, indent))
            elif child.tag == "Subsection":
                lines.append(xml_to_markdown(child, indent + "  "))
            elif child.tag == "ExplanatoryNote":
                lines.append(xml_to_markdown(child, indent))
    elif tag == "Subsection":
        label = elem.find("Label")
        label_text = clean_inline_text(label) if label is not None else ""
        text_node = elem.find("Text")
        text_content = clean_inline_text(text_node) if text_node is not None else ""
        lines.append(f"{indent}**{label_text}** {text_content}\n\n")
        for child in elem:
            if child.tag not in ("Label", "Text", "ExplanatoryNote"):
                lines.append(xml_to_markdown(child, indent + "  "))
    elif tag == "Text":
        lines.append(f"{indent}{clean_inline_text(elem)}\n\n")
    elif tag == "ExplanatoryNote":
        lines.append(f"\n{indent}> **Explanatory Note**:\n")
        exp_text = elem.find("ExplanatoryText")
        if exp_text is not None:
            lines.append(f"{indent}> {clean_inline_text(exp_text)}\n")
        exist_text = elem.find("ExistingText")
        if exist_text is not None:
            lines.append(f"{indent}> *Existing Text*:\n")
            for text_node in exist_text.findall(".//Text"):
                lines.append(f"{indent}> > {clean_inline_text(text_node)}\n")
        lines.append("\n")
    else:
        # For general tags, just recurse
        for child in elem:
            lines.append(xml_to_markdown(child, indent))
            
    return "".join(lines)

def make_summary_markdown(bill_xml_path):
    """Generate summary.md content from metadata XML."""
    try:
        tree = ET.parse(bill_xml_path)
        root = tree.getroot()
        bill_node = root.find(".//Bill")
        if bill_node is None:
            bill_node = root
            
        bill_num = bill_node.findtext("NumberCode") or ""
        title_en = bill_node.findtext("LongTitleEn") or ""
        status_en = bill_node.findtext("StatusNameEn") or ""
        sponsor = bill_node.findtext("SponsorPersonName") or ""
        activity_en = bill_node.findtext("LatestBillEventTypeName") or ""
        activity_dt = bill_node.findtext("LatestBillEventDateTime") or ""
        
        md = []
        md.append(f"# Bill {bill_num}: {title_en}\n\n")
        md.append(f"- **Current Status**: {status_en}\n")
        md.append(f"- **Sponsor**: {sponsor}\n")
        md.append(f"- **Latest Activity**: {activity_en} (at {activity_dt})\n\n")
        
        md.append("## Legislative Stage History\n\n")
        md.append("| Chamber | Stage | Status | Completed Date |\n")
        md.append("| --- | --- | --- | --- |\n")
        
        # House stages
        house_stages = bill_node.findall(".//HouseBillStages/*")
        for stage in house_stages:
            name = stage.findtext("BillStageNameEn") or ""
            state = stage.findtext("StateNameEn") or ""
            dt = stage.findtext("LastStageEventStartDateTime") or ""
            md.append(f"| House of Commons | {name} | {state} | {dt} |\n")
            
        # Senate stages
        senate_stages = bill_node.findall(".//SenateBillStages/*")
        for stage in senate_stages:
            name = stage.findtext("BillStageNameEn") or ""
            state = stage.findtext("StateNameEn") or ""
            dt = stage.findtext("LastStageEventStartDateTime") or ""
            md.append(f"| Senate | {name} | {state} | {dt} |\n")
            
        return "".join(md)
    except Exception as e:
        return f"# Summary Generation Failed\n\nError parsing metadata: {e}"

def extract_xml_links_from_docviewer(session, bill_number):
    """Scrape first-reading page to find all available stages and their XML document links."""
    first_reading_url = f"{DOC_VIEWER_BASE}/en/{session}/bill/{bill_number}/first-reading"
    
    try:
        response = requests.get(first_reading_url)
        if response.status_code != 200:
            return {}
            
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
        
        # For each slug, fetch and locate XML link
        xml_links = {}
        for slug in stage_slugs:
            stage_url = f"{DOC_VIEWER_BASE}/en/{session}/bill/{bill_number}/{slug}"
            res = requests.get(stage_url)
            if res.status_code == 200:
                xml_match = re.search(r'href=["\'](/Content/Bills/[^"\']+_E\.xml)["\']', res.text)
                if xml_match:
                    xml_links[slug] = f"https://www.parl.ca{xml_match.group(1)}"
                else:
                    generic_xml_match = re.search(r'href=["\'](/Content/Bills/[^"\']+\.xml)["\']', res.text)
                    if generic_xml_match:
                        xml_links[slug] = f"https://www.parl.ca{generic_xml_match.group(1)}"
        
        return xml_links
    except Exception as e:
        log_message(f"    Error scraping DocumentViewer for {bill_number}: {e}")
        return {}

def log_message(msg):
    """Print a message, clearing the progress bar line first to avoid garbled output."""
    sys.stdout.write("\r\033[K")
    print(msg)
    sys.stdout.flush()

def print_progress(current, total, bill_num="", status=""):
    """Draw a zero-dependency console progress bar."""
    bar_length = 30
    filled_length = int(bar_length * current // total)
    bar = "█" * filled_length + "-" * (bar_length - filled_length)
    percent = (100 * current) // total
    sys.stdout.write(f"\rProgress: |{bar}| {percent}% [{current}/{total}] {bill_num:5} - {status[:35]:<35}")
    sys.stdout.flush()
    if current == total:
        print()

def parse_readme_index(readme_path):
    """Parse existing README.md index to recover title, status, activity, and downloaded stages."""
    index_data = {}
    if not os.path.exists(readme_path):
        return index_data
        
    try:
        with open(readme_path, "r", encoding="utf-8") as f:
            content = f.read()
            
        for line in content.splitlines():
            # Matches: | [S-2](...) | Title | Status | Activity | Stages | Checked |
            match = re.search(r'\|\s*\[([^\]]+)\]\([^)]+\)\s*\|([^|]+)\|([^|]+)\|([^|]+)\|([^|]*)\|\s*([^|]*)\s*\|', line)
            if match:
                bill_num = match.group(1).strip()
                title = match.group(2).strip()
                status = match.group(3).strip()
                activity = match.group(4).strip()
                stages_str = match.group(5).strip()
                checked = match.group(6).strip()
                
                slugs = [s.strip().replace('`', '') for s in stages_str.split(',') if s.strip() and s.strip() != "None"]
                index_data[bill_num] = {
                    "title": title,
                    "status": status,
                    "activity": activity,
                    "stages": set(slugs),
                    "last_checked": checked
                }
    except Exception as e:
        log_message(f"Warning: Failed to parse existing README.md index: {e}")
        
    return index_data

def save_readme_index(readme_path, all_bills_data, session):
    """Write the updated index table and stats to README.md."""
    total_bills = len(all_bills_data)
    in_committee = sum(1 for b in all_bills_data.values() if "committee" in b.get("status", "").lower())
    
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    md = []
    md.append(f"# Parliament Session {session} Bills Index\n\n")
    md.append("This directory contains tracked legislation for this parliament session.\n\n")
    
    md.append("## Overview\n")
    md.append(f"- **Total Tracked Bills**: {total_bills}\n")
    md.append(f"- **Bills in Committee**: {in_committee}\n")
    md.append(f"- **Last Updated**: {now_str}\n\n")
    
    md.append("## Bills List\n\n")
    md.append("| Bill | Title | Current Status | Latest Activity | Downloaded Stages | Last Checked |\n")
    md.append("| --- | --- | --- | --- | --- | --- |\n")
    
    def sort_key(bill_num):
        match = re.match(r'([A-Z]+)-(\d+)', bill_num)
        if match:
            prefix = match.group(1)
            num = int(match.group(2))
            prefix_val = 0 if prefix == "C" else 1
            return (prefix_val, num)
        return (2, bill_num)
        
    for bill_num in sorted(all_bills_data.keys(), key=sort_key):
        b = all_bills_data[bill_num]
        title = b.get("title", "").replace("|", "\\|")
        status = b.get("status", "").replace("|", "\\|")
        activity = b.get("activity", "").replace("|", "\\|")
        stages_str = ", ".join(f"`{s}`" for s in sorted(b.get("stages", []))) if b.get("stages") else "None"
        checked = b.get("last_checked", now_str)
        
        md.append(f"| [{bill_num}](bills/{bill_num}) | {title} | {status} | {activity} | {stages_str} | {checked} |\n")
        
    try:
        with open(readme_path, "w", encoding="utf-8") as f:
            f.write("".join(md))
    except Exception as e:
        log_message(f"Error saving README.md: {e}")

def update_root_readme(repo_path, session, session_name):
    """Update the main root README.md with the link and status of the parsed session."""
    root_readme_path = os.path.join(repo_path, "README.md")
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    sessions = {}
    if os.path.exists(root_readme_path):
        try:
            with open(root_readme_path, "r", encoding="utf-8") as f:
                content = f.read()
            for line in content.splitlines():
                # Matches: | Session | [Slug](path) | Status | Last Updated |
                match = re.search(r'\|\s*([^|]+)\s*\|\s*\[([^\]]+)\]\([^)]+\)\s*\|\s*([^|]+)\s*\|\s*([^|]+)\s*\|', line)
                if match:
                    s_name = match.group(1).strip()
                    s_code = match.group(2).strip()
                    s_status = match.group(3).strip()
                    s_updated = match.group(4).strip()
                    if s_code != "Link": # skip header
                        sessions[s_code] = {
                            "name": s_name,
                            "status": s_status,
                            "updated": s_updated
                        }
        except Exception as e:
            log_message(f"Warning: Failed to parse root README.md: {e}")
            
    clean_name = session_name.split("~")[0].strip() if "~" in session_name else session_name
    status = "Active" if "present" in session_name.lower() or "active" in session_name.lower() or not session_name else "Prerogative/Dissolved"
    
    sessions[session] = {
        "name": clean_name or f"Session {session}",
        "status": status,
        "updated": now_str
    }
    
    md = []
    md.append("# Canadian Parliamentary Bills Database\n\n")
    md.append("This repository contains a versioned history of Canadian legislative bills and text revisions.\n\n")
    md.append("## Supported Sessions\n\n")
    md.append("| Session | Link | Status | Last Updated |\n")
    md.append("| --- | --- | --- | --- |\n")
    
    for s_code in sorted(sessions.keys()):
        s_info = sessions[s_code]
        md.append(f"| {s_info['name']} | [{s_code}]({s_code}/README.md) | {s_info['status']} | {s_info['updated']} |\n")
        
    try:
        with open(root_readme_path, "w", encoding="utf-8") as f:
            f.write("".join(md))
    except Exception as e:
        log_message(f"Error saving root README.md: {e}")

def migrate_existing_index(repo_path, session, session_name):
    """Automatically migrates the old centralized README.md to session/README.md."""
    root_readme_path = os.path.join(repo_path, "README.md")
    session_dir = os.path.join(repo_path, session)
    session_readme_path = os.path.join(session_dir, "README.md")
    
    if os.path.exists(root_readme_path) and not os.path.exists(session_readme_path):
        try:
            with open(root_readme_path, "r", encoding="utf-8") as f:
                content = f.read()
            # If this is the old centralized index (contains bill listings)
            if "## Bills List" in content or "Downloaded Stages" in content:
                log_message(f"Migrating old centralized README.md to {session}/README.md...")
                os.makedirs(session_dir, exist_ok=True)
                with open(session_readme_path, "w", encoding="utf-8") as f:
                    f.write(content)
                os.remove(root_readme_path)
        except Exception as e:
            log_message(f"Warning: Failed to migrate old centralized index: {e}")

def scrape_bill(session, bill_number, target_bill_dir, already_downloaded_stages, dry_run=False):
    """Scrape detailed bill metadata and draft texts, returning progress details and commit message."""
    os.makedirs(target_bill_dir, exist_ok=True)
    metadata_path = os.path.join(target_bill_dir, "metadata.xml")
    summary_path = os.path.join(target_bill_dir, "summary.md")
    drafts_dir = os.path.join(target_bill_dir, "text_drafts")
    os.makedirs(drafts_dir, exist_ok=True)
    
    old_status = ""
    old_activity = ""
    if os.path.exists(metadata_path):
        try:
            tree = ET.parse(metadata_path)
            old_status = tree.findtext(".//StatusNameEn") or ""
            old_activity = tree.findtext(".//LatestBillEventTypeName") or ""
        except Exception:
            pass
            
    # 1. Fetch detailed metadata XML
    detail_url = f"{LEGISINFO_BASE}/en/bill/{session}/{bill_number}/xml"
    try:
        response = requests.get(detail_url)
        if response.status_code == 200:
            if not dry_run:
                with open(metadata_path, "w", encoding="utf-8") as f:
                    f.write(response.text)
        else:
            log_message(f"    Failed to fetch detailed XML for {bill_number} (status {response.status_code})")
            return False, already_downloaded_stages, ""
    except Exception as e:
        log_message(f"    Error fetching metadata for {bill_number}: {e}")
        return False, already_downloaded_stages, ""
        
    # 2. Generate summary markdown
    if not dry_run:
        summary_md = make_summary_markdown(metadata_path)
        with open(summary_path, "w", encoding="utf-8") as f:
            f.write(summary_md)
            
    # 3. Find and download text drafts
    xml_links = extract_xml_links_from_docviewer(session, bill_number)
    current_stages = set(already_downloaded_stages)
    added_drafts = []
    
    for slug, url in xml_links.items():
        xml_file_path = os.path.join(drafts_dir, f"{slug}.xml")
        md_file_path = os.path.join(drafts_dir, f"{slug}.md")
        
        # Check if already downloaded
        if slug not in current_stages or not os.path.exists(xml_file_path):
            log_message(f"    Downloading draft {bill_number} {slug}: {url}")
            try:
                res = requests.get(url)
                if res.status_code == 200:
                    current_stages.add(slug)
                    added_drafts.append(slug)
                    if not dry_run:
                        with open(xml_file_path, "w", encoding="utf-8") as f:
                            f.write(res.text)
                        try:
                            root = ET.fromstring(res.content)
                            md_content = xml_to_markdown(root)
                            with open(md_file_path, "w", encoding="utf-8") as md_f:
                                md_f.write(md_content)
                        except Exception as parse_err:
                            log_message(f"      Failed to parse XML draft to Markdown: {parse_err}")
                else:
                    log_message(f"      Failed (status {res.status_code})")
            except Exception as e:
                log_message(f"      Error downloading draft: {e}")
                
    new_status = ""
    new_activity = ""
    try:
        tree = ET.parse(metadata_path)
        new_status = tree.findtext(".//StatusNameEn") or ""
        new_activity = tree.findtext(".//LatestBillEventTypeName") or ""
    except Exception:
        pass
        
    # Build commit message
    if not old_status:
        commit_msg = f"Bill {bill_number}: Initialize tracking"
    elif new_status != old_status:
        commit_msg = f"Bill {bill_number}: Status updated to '{new_status}'"
    elif new_activity != old_activity:
        commit_msg = f"Bill {bill_number}: Activity: '{new_activity}'"
    elif added_drafts:
        commit_msg = f"Bill {bill_number}: Added text drafts ({', '.join(added_drafts)})"
    else:
        commit_msg = f"Bill {bill_number}: Daily update"
        
    return True, current_stages, commit_msg

def main():
    parser = argparse.ArgumentParser(description="LEGISinfo Git Scraper")
    parser.add_argument("--repo", required=True, help="Path to the legisinfo data repository")
    parser.add_argument("--session", default=None, help="Parliament and Session code (default: None for active session)")
    parser.add_argument("--limit", type=int, default=0, help="Limit number of bills to process (default: 0 for all)")
    parser.add_argument("--dry-run", action="store_true", help="Download data but do not modify git history")
    parser.add_argument("--committee-only", action="store_true", help="Only track bills currently in committee")
    
    args = parser.parse_args()
    
    if not os.path.exists(args.repo):
        print(f"Error: Repository path '{args.repo}' does not exist.")
        sys.exit(1)
        
    if not os.path.exists(os.path.join(args.repo, ".git")):
        print(f"Error: Target path '{args.repo}' is not initialized as a Git repository.")
        sys.exit(1)
        
    # 1. Fetch main bills listing XML (omitting session gets the current active session)
    if args.session:
        list_url = f"{LEGISINFO_BASE}/en/bills/xml?parlsession={args.session}"
        session = args.session
    else:
        list_url = f"{LEGISINFO_BASE}/en/bills/xml"
        session = None
        
    print(f"Fetching session bill list: {list_url}")
    try:
        res = requests.get(list_url)
        if res.status_code != 200:
            print(f"Error: Failed to fetch session bills list (status {res.status_code})")
            sys.exit(1)
            
        root = ET.fromstring(res.content)
    except Exception as e:
        print(f"Error fetching/parsing bill list XML: {e}")
        sys.exit(1)
        
    bills = root.findall(".//Bill")
    total_bills = len(bills)
    print(f"Total bills in session list: {total_bills}")
    
    # Extract session dynamically if none specified
    session_name = ""
    if bills:
        session_name = bills[0].findtext("ParlSessionEn") or ""
        if not session:
            session = bills[0].findtext("ParlSessionCode") or "45-1"
    else:
        if not session:
            session = "45-1"
            
    print(f"Detected active session: {session} ({session_name.split('~')[0]})")
    
    session_dir = os.path.join(args.repo, session)
    os.makedirs(session_dir, exist_ok=True)
    session_readme_path = os.path.join(session_dir, "README.md")
    bills_dir = os.path.join(session_dir, "bills")
    os.makedirs(bills_dir, exist_ok=True)
    
    # 2. Automatically migrate index from root to session folder if needed
    migrate_existing_index(args.repo, session, session_name)
    
    # 3. Parse session README.md to recover status/progress maps
    print("Loading session progress index...")
    index_data = parse_readme_index(session_readme_path)
    print(f"Loaded progress for {len(index_data)} bills.")
    
    # Filter bills list if committee-only is specified
    bills_to_process = []
    for bill in bills:
        bill_number = bill.findtext("BillNumberFormatted") or ""
        if not bill_number:
            continue
        status = bill.findtext("CurrentStatusEn") or ""
        if args.committee_only and "committee" not in status.lower():
            continue
        bills_to_process.append((bill_number, bill))
        
    if args.limit > 0:
        bills_to_process = bills_to_process[:args.limit]
        
    total_to_process = len(bills_to_process)
    print(f"Filtering complete. Process {total_to_process} bills.")
    
    processed = 0
    committed_count = 0
    
    # Track metadata of all processed bills to build final README.md
    all_bills_data = {}
    for k, v in index_data.items():
        all_bills_data[k] = {
            "title": v.get("title", ""),
            "status": v["status"],
            "activity": v["activity"],
            "stages": v["stages"],
            "last_checked": v["last_checked"]
        }
        
    try:
        for bill_number, bill_node in bills_to_process:
            status = bill_node.findtext("CurrentStatusEn") or ""
            activity = bill_node.findtext("LatestActivityEn") or ""
            title = bill_node.findtext("LongTitleEn") or ""
            
            # Check for skip/resume optimization
            existing = index_data.get(bill_number)
            already_downloaded_stages = set()
            is_skipped = False
            
            if existing:
                already_downloaded_stages = existing["stages"]
                if (existing["status"] == status and 
                    existing["activity"] == activity and 
                    already_downloaded_stages):
                    
                    # Update cache/checks
                    all_bills_data[bill_number] = {
                        "title": title,
                        "status": status,
                        "activity": activity,
                        "stages": already_downloaded_stages,
                        "last_checked": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    }
                    processed += 1
                    is_skipped = True
                    print_progress(processed, total_to_process, bill_number, "Skipped (Up to date)")
                    
                    # Save session index incrementally even on skip to record check time
                    if not args.dry_run:
                        save_readme_index(session_readme_path, all_bills_data, session)
                    continue
            
            if not is_skipped:
                # Run detailed scrape
                print_progress(processed, total_to_process, bill_number, "Scraping detailed data")
                target_bill_dir = os.path.join(bills_dir, bill_number)
                
                success, updated_stages, commit_msg = scrape_bill(
                    session, 
                    bill_number, 
                    target_bill_dir, 
                    already_downloaded_stages, 
                    args.dry_run
                )
                
                if success:
                    all_bills_data[bill_number] = {
                        "title": title,
                        "status": status,
                        "activity": activity,
                        "stages": updated_stages,
                        "last_checked": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    }
                    
                    if not args.dry_run:
                        # 1. Update session index file immediately
                        save_readme_index(session_readme_path, all_bills_data, session)
                        
                        # 2. Stage changes (bill folder + session README.md)
                        run_command(["git", "add", f"{session}/bills/{bill_number}", f"{session}/README.md"], cwd=args.repo)
                        
                        # 3. Check if there are staged changes
                        diff_staged = run_command(["git", "diff", "--cached", "--quiet"], cwd=args.repo)
                        if diff_staged.returncode != 0:
                            log_message(f"  Staging and committing {bill_number}: {commit_msg}")
                            commit_res = run_command(["git", "commit", "-m", commit_msg], cwd=args.repo)
                            if commit_res.returncode == 0:
                                committed_count += 1
                            else:
                                log_message(f"    Failed to commit: {commit_res.stderr}")
                
                processed += 1
                print_progress(processed, total_to_process, bill_number, "Completed")
            
    except KeyboardInterrupt:
        log_message("\nExecution interrupted by user. Saving final states...")
        if not args.dry_run:
            save_readme_index(session_readme_path, all_bills_data, session)
            update_root_readme(args.repo, session, session_name)
            run_command(["git", "add", f"{session}/README.md", "README.md"], cwd=args.repo)
            diff_readme = run_command(["git", "diff", "--cached", "--quiet"], cwd=args.repo)
            if diff_readme.returncode != 0:
                run_command(["git", "commit", "-m", "Scraper: Save index status on user interrupt"], cwd=args.repo)
        log_message("Progress saved. Exiting gracefully.")
        sys.exit(0)
        
    # At the end, commit session index and root index
    if not args.dry_run:
        save_readme_index(session_readme_path, all_bills_data, session)
        update_root_readme(args.repo, session, session_name)
        run_command(["git", "add", f"{session}/README.md", "README.md"], cwd=args.repo)
        diff_readme = run_command(["git", "diff", "--cached", "--quiet"], cwd=args.repo)
        if diff_readme.returncode != 0:
            log_message("\nCommitting remaining checked timestamps and root index...")
            run_command(["git", "commit", "-m", "Scraper: Update index checked timestamps"], cwd=args.repo)
            
    print(f"Completed. Processed {processed} bills. Created {committed_count} commits in data repository.")

if __name__ == "__main__":
    main()
