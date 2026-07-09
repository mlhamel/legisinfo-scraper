import os
import sys
import argparse
import shutil
import xml.etree.ElementTree as ET
import requests
from datetime import datetime

from .config import LEGISINFO_BASE
from .utils import log_message, print_progress
from .git_utils import run_command, run_git_commit
from .parser import get_latest_event_date_from_xml
from .index_manager import (
    parse_readme_index,
    save_readme_index,
    update_root_readme,
    migrate_existing_index
)
from .crawler import scrape_bill

def parse_event_date(date_str):
    if not date_str or date_str.startswith("0001-01-01"):
        return datetime.min
    try:
        return datetime.fromisoformat(date_str)
    except ValueError:
        try:
            return datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            return datetime.min

def get_commit_sort_key(commit):
    date_val = commit.get("stage_date") or commit.get("event_date")
    return parse_event_date(date_val)

def main():
    parser = argparse.ArgumentParser(description="LEGISinfo Git Scraper")
    parser.add_argument("--repo", required=True, help="Path to the legisinfo data repository")
    parser.add_argument("--session", default=None, help="Parliament and Session code (default: None for active session, or 'all' for all historical data)")
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
        
    # 1. Fetch bills listing XML
    if args.session and args.session.lower() == "all":
        list_url = f"{LEGISINFO_BASE}/en/bills/xml?parlsession=all"
    elif args.session:
        list_url = f"{LEGISINFO_BASE}/en/bills/xml?parlsession={args.session}"
    else:
        list_url = f"{LEGISINFO_BASE}/en/bills/xml"
        
    print(f"Fetching bills list: {list_url}")
    try:
        res = requests.get(list_url)
        if res.status_code != 200:
            print(f"Error: Failed to fetch bills list (status {res.status_code})")
            sys.exit(1)
            
        root = ET.fromstring(res.content)
    except Exception as e:
        print(f"Error fetching/parsing bill list XML: {e}")
        sys.exit(1)
        
    bills = root.findall(".//Bill")
    total_bills = len(bills)
    print(f"Total bills in list: {total_bills}")
    
    # Group bills by session code
    bills_by_session = {}
    for bill_node in bills:
        bill_session = bill_node.findtext("ParlSessionCode")
        if not bill_session:
            continue
        if bill_session not in bills_by_session:
            bills_by_session[bill_session] = []
        bills_by_session[bill_session].append(bill_node)
        
    # If a specific session was requested (and not 'all'), filter to that session
    if args.session and args.session.lower() != "all":
        if args.session in bills_by_session:
            bills_by_session = {args.session: bills_by_session[args.session]}
        else:
            print(f"Warning: Session '{args.session}' not found in the XML response. Attempting to process as empty.")
            bills_by_session = {args.session: []}
    elif not args.session:
        # Default to the session of the first bill in the list (the active session)
        if bills:
            active_session = bills[0].findtext("ParlSessionCode") or "45-1"
            print(f"Defaulting to active session: {active_session}")
            if active_session in bills_by_session:
                bills_by_session = {active_session: bills_by_session[active_session]}
            else:
                bills_by_session = {active_session: []}
        else:
            bills_by_session = {"45-1": []}
            
    all_pending_commits = []
    session_indices = {}
    
    interrupted = False
    
    # We will create a single temporary directory for all caching
    import tempfile
    with tempfile.TemporaryDirectory() as temp_dir:
        log_message(f"Created temporary caching directory: {temp_dir}")
        
        try:
            for session_code, session_bills in sorted(bills_by_session.items()):
                if not session_bills:
                    continue
                    
                session_name = session_bills[0].findtext("ParlSessionEn") or ""
                print(f"\n=== Processing Session: {session_code} ({session_name.split('~')[0]}) ===")
                
                session_dir = os.path.join(args.repo, session_code)
                os.makedirs(session_dir, exist_ok=True)
                session_readme_path = os.path.join(session_dir, "README.md")
                bills_dir = os.path.join(session_dir, "bills")
                os.makedirs(bills_dir, exist_ok=True)
                
                # Automatically migrate index from root to session folder if needed
                migrate_existing_index(args.repo, session_code, session_name)
                
                # Parse session README.md to recover status/progress maps
                print(f"Loading session progress index for {session_code}...")
                index_data = parse_readme_index(session_readme_path)
                print(f"Loaded progress for {len(index_data)} bills.")
                
                # Filter bills list
                bills_to_process = []
                for bill in session_bills:
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
                print(f"Filtering complete. Process {total_to_process} bills in session {session_code}.")
                
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
                    
                session_indices[session_code] = {
                    "readme_path": session_readme_path,
                    "all_bills_data": all_bills_data,
                    "session_name": session_name
                }
                
                processed = 0
                for bill_number, bill_node in bills_to_process:
                    status = bill_node.findtext("CurrentStatusEn") or ""
                    activity = bill_node.findtext("LatestActivityEn") or ""
                    title = bill_node.findtext("LongTitleEn") or ""
                    
                    # Check for skip/resume optimization
                    existing = index_data.get(bill_number)
                    already_downloaded_stages = set()
                    is_skipped = False
                    
                    # Paths to the target sequential files
                    target_bill_dir = os.path.join(bills_dir, bill_number)
                    bill_xml_path = os.path.join(target_bill_dir, "bill_text.xml")
                    
                    # Clean up old text_drafts subfolder if it exists (migrate layout)
                    old_drafts_dir = os.path.join(target_bill_dir, "text_drafts")
                    if os.path.exists(old_drafts_dir):
                        shutil.rmtree(old_drafts_dir, ignore_errors=True)
                        if not args.dry_run:
                            run_command(["git", "rm", "-r", "--cached", f"{session_code}/bills/{bill_number}/text_drafts"], cwd=args.repo)
                    
                    if existing:
                        already_downloaded_stages = existing["stages"]
                        # Skip optimization: only skip if metadata is identical AND the sequential file is present on disk!
                        if (existing["status"] == status and 
                            existing["activity"] == activity and 
                            already_downloaded_stages and 
                            os.path.exists(bill_xml_path)):
                            
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
                            continue
                    
                    if not is_skipped:
                        # Run scrape into cache
                        print_progress(processed, total_to_process, bill_number, "Scraping detailed data")
                        
                        cache_bill_dir = os.path.join(temp_dir, session_code, bill_number)
                        success, updated_stages, author_name, author_email, bill_commits = scrape_bill(
                            session_code, 
                            bill_number, 
                            cache_bill_dir, 
                            args.repo,
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
                            all_pending_commits.extend(bill_commits)
                        
                        processed += 1
                        print_progress(processed, total_to_process, bill_number, "Completed scraping")
                        
        except KeyboardInterrupt:
            log_message("\nExecution interrupted by user. Processing scraped data so far...")
            interrupted = True
            
        # 2. Sort all pending commits chronologically by their event/stage date
        all_pending_commits.sort(key=get_commit_sort_key)
        
        # 3. Apply commits sequentially
        committed_count = 0
        if all_pending_commits:
            print(f"\n=== Executing {len(all_pending_commits)} pending commits in chronological order ===")
            
        for commit in all_pending_commits:
            session_code = commit["session"]
            bill_number = commit["bill_number"]
            author_name = commit["author_name"]
            author_email = commit["author_email"]
            
            bill_dir = os.path.join(args.repo, session_code, "bills", bill_number)
            os.makedirs(bill_dir, exist_ok=True)
            
            if commit["type"] == "stage":
                stage_name = commit["stage_name"]
                stage_date = commit["stage_date"]
                if stage_date and stage_date.startswith("0001-01-01"):
                    stage_date = None
                
                # Copy cached files to target repo
                shutil.copy2(commit["stage_xml_path"], os.path.join(bill_dir, "bill_text.xml"))
                if os.path.exists(commit["stage_md_path"]):
                    shutil.copy2(commit["stage_md_path"], os.path.join(bill_dir, "bill_text.md"))
                shutil.copy2(commit["metadata_xml_path"], os.path.join(bill_dir, "metadata.xml"))
                shutil.copy2(commit["summary_md_path"], os.path.join(bill_dir, "summary.md"))
                
                if not args.dry_run:
                    # Stage files in git
                    run_command(["git", "add", 
                                 f"{session_code}/bills/{bill_number}/bill_text.xml", 
                                 f"{session_code}/bills/{bill_number}/bill_text.md",
                                 f"{session_code}/bills/{bill_number}/metadata.xml",
                                 f"{session_code}/bills/{bill_number}/summary.md"], cwd=args.repo)
                    
                    diff_staged = run_command(["git", "diff", "--cached", "--quiet"], cwd=args.repo)
                    if diff_staged.returncode != 0:
                        commit_msg = f"Bill {bill_number}: {stage_name} text update"
                        log_message(f"  Committing sequential stage {bill_number} ({stage_name}) at {stage_date or 'now'} by {author_name}...")
                        run_git_commit(commit_msg, stage_date, args.repo, author_name, author_email)
                        committed_count += 1
                        
            elif commit["type"] == "metadata":
                event_date = commit["event_date"]
                if event_date and event_date.startswith("0001-01-01"):
                    event_date = None
                
                shutil.copy2(commit["metadata_xml_path"], os.path.join(bill_dir, "metadata.xml"))
                shutil.copy2(commit["summary_md_path"], os.path.join(bill_dir, "summary.md"))
                
                # If there are restored files, copy them as well
                if commit.get("restore_xml_path"):
                    shutil.copy2(commit["restore_xml_path"], os.path.join(bill_dir, "bill_text.xml"))
                if commit.get("restore_md_path"):
                    shutil.copy2(commit["restore_md_path"], os.path.join(bill_dir, "bill_text.md"))
                    
                if not args.dry_run:
                    git_add_args = ["git", "add", 
                                    f"{session_code}/bills/{bill_number}/metadata.xml", 
                                    f"{session_code}/bills/{bill_number}/summary.md"]
                    if commit.get("restore_xml_path"):
                        git_add_args.append(f"{session_code}/bills/{bill_number}/bill_text.xml")
                    if commit.get("restore_md_path"):
                        git_add_args.append(f"{session_code}/bills/{bill_number}/bill_text.md")
                        
                    run_command(git_add_args, cwd=args.repo)
                    
                    diff_staged = run_command(["git", "diff", "--cached", "--quiet"], cwd=args.repo)
                    if diff_staged.returncode != 0:
                        commit_msg = f"Bill {bill_number}: Metadata update"
                        log_message(f"  Committing metadata updates for {bill_number} at {event_date or 'now'} by {author_name}...")
                        run_git_commit(commit_msg, event_date, args.repo, author_name, author_email)
                        committed_count += 1
                        
        # 4. Save and commit README indices
        if not args.dry_run:
            print("\nUpdating indices...")
            for session_code, info in session_indices.items():
                save_readme_index(info["readme_path"], info["all_bills_data"], session_code)
                update_root_readme(args.repo, session_code, info["session_name"])
                run_command(["git", "add", f"{session_code}/README.md", "README.md"], cwd=args.repo)
                
            diff_readme = run_command(["git", "diff", "--cached", "--quiet"], cwd=args.repo)
            if diff_readme.returncode != 0:
                if interrupted:
                    run_git_commit("Scraper: Save index status on user interrupt", None, args.repo)
                else:
                    run_git_commit("Scraper: Update index checked timestamps", None, args.repo)
                    
    if interrupted:
        log_message("Progress saved on interrupt. Exiting gracefully.")
        sys.exit(0)
        
    print(f"\nCompleted. Created {committed_count} commits in data repository.")

if __name__ == "__main__":
    main()
