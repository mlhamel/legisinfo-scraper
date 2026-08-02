import argparse
import os
import shutil
import sys
import xml.etree.ElementTree as ET
from datetime import datetime

import requests
from civican.schemas import BillIndexData, MetadataPendingBill, StagePendingBill

from civican.scraper.git_utils import (
    find_commit_by_event_id,
    run_command,
    run_git_autosquash,
    run_git_commit,
    run_git_fixup,
)
from civican.scraper.utils import fix_mojibake, log_message, print_progress

from .config import LEGISINFO_BASE
from .crawler import scrape_bill
from .index_manager import migrate_existing_index, parse_readme_index, save_readme_index, update_root_readme


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
    if isinstance(commit, StagePendingBill):
        date_val = commit.stage_date
        priority = 0
    elif isinstance(commit, MetadataPendingBill):
        date_val = commit.event_date
        priority = 1
    else:
        date_val = None
        priority = 2
    return (parse_event_date(date_val), priority)


def main():
    parser = argparse.ArgumentParser(description="LEGISinfo Git Scraper")
    parser.add_argument("--repo", required=True, help="Path to the legisinfo data repository")
    parser.add_argument(
        "--session",
        default=None,
        help="Parliament and Session code (default: None for active session, or 'all' for all historical data)",
    )
    parser.add_argument("--limit", type=int, default=0, help="Limit number of bills to process (default: 0 for all)")
    parser.add_argument("--dry-run", action="store_true", help="Download data but do not modify git history")
    parser.add_argument("--committee-only", action="store_true", help="Only track bills currently in committee")
    parser.add_argument("--cache-dir", default=".cache", help="Path to the local persistent cache directory")
    parser.add_argument("--force", action="store_true", help="Force scraping and update formatting for existing bills")

    args = parser.parse_args()

    if args.session and args.session.lower() in ("active", "none"):
        args.session = None

    if not os.path.exists(args.repo):
        sys.exit(1)

    if not os.path.exists(os.path.join(args.repo, ".git")):
        sys.exit(1)

    # 1. Fetch bills listing XML
    if args.session and args.session.lower() == "all":
        list_url = f"{LEGISINFO_BASE}/en/bills/xml?parlsession=all"
    elif args.session:
        list_url = f"{LEGISINFO_BASE}/en/bills/xml?parlsession={args.session}"
    else:
        list_url = f"{LEGISINFO_BASE}/en/bills/xml"

    try:
        res = requests.get(list_url)
        if res.status_code != 200:
            sys.exit(1)
        res.encoding = "utf-8"
        root = ET.fromstring(fix_mojibake(res.text).encode("utf-8"))
    except Exception:
        sys.exit(1)

    bills = root.findall(".//Bill")
    len(bills)

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
            bills_by_session = {args.session: []}
    elif not args.session:
        # Default to the session of the first bill in the list (the active session)
        if bills:
            active_session = bills[0].findtext("ParlSessionCode") or "45-1"
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

                session_name = " ".join((session_bills[0].findtext("ParlSessionEn") or "").split())

                session_dir = os.path.join(args.repo, session_code)
                os.makedirs(session_dir, exist_ok=True)
                session_readme_path = os.path.join(session_dir, "README.md")
                bills_dir = os.path.join(session_dir, "bills")
                os.makedirs(bills_dir, exist_ok=True)

                # Automatically migrate index from root to session folder if needed
                migrate_existing_index(args.repo, session_code)

                # Parse session README.md to recover status/progress maps
                index_data = parse_readme_index(session_readme_path)

                # Filter bills list
                bills_to_process = []
                for bill in session_bills:
                    bill_number = bill.findtext("BillNumberFormatted") or ""
                    if not bill_number:
                        continue
                    status = " ".join((bill.findtext("CurrentStatusEn") or "").split())
                    if args.committee_only and "committee" not in status.lower():
                        continue
                    bills_to_process.append((bill_number, bill))

                if args.limit > 0:
                    bills_to_process = bills_to_process[: args.limit]

                total_to_process = len(bills_to_process)

                # Track metadata of all processed bills to build final README.md
                all_bills_data: dict[str, BillIndexData] = {}
                for k, v in index_data.items():
                    if isinstance(v, BillIndexData):
                        all_bills_data[k] = v
                    else:
                        all_bills_data[k] = BillIndexData(
                            title=v.get("title", ""),
                            status=v.get("status", ""),
                            activity=v.get("activity", ""),
                            stages=v.get("stages", set()),
                            last_checked=v.get("last_checked", ""),
                        )

                session_indices[session_code] = {
                    "readme_path": session_readme_path,
                    "all_bills_data": all_bills_data,
                    "session_name": session_name,
                }

                processed = 0
                for bill_number, bill_node in bills_to_process:
                    status = fix_mojibake(" ".join((bill_node.findtext("CurrentStatusEn") or "").split()))
                    activity = fix_mojibake(" ".join((bill_node.findtext("LatestActivityEn") or "").split()))
                    title = fix_mojibake(" ".join((bill_node.findtext("LongTitleEn") or "").split()))

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
                            run_command(
                                ["git", "rm", "-r", "--cached", f"{session_code}/bills/{bill_number}/text_drafts"],
                                cwd=args.repo,
                            )

                    if existing:
                        already_downloaded_stages = (
                            existing.stages if isinstance(existing, BillIndexData) else existing["stages"]
                        )
                        existing_status = existing.status if isinstance(existing, BillIndexData) else existing["status"]
                        existing_activity = (
                            existing.activity if isinstance(existing, BillIndexData) else existing["activity"]
                        )
                        # Skip optimization: only skip if metadata is identical AND
                        # the sequential file is present on disk!
                        if (
                            not args.force
                            and existing_status == status
                            and existing_activity == activity
                            and already_downloaded_stages
                            and os.path.exists(bill_xml_path)
                        ):
                            # Update cache/checks
                            all_bills_data[bill_number] = BillIndexData(
                                title=title,
                                status=status,
                                activity=activity,
                                stages=already_downloaded_stages,
                                last_checked=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            )
                            processed += 1
                            is_skipped = True
                            print_progress(processed, total_to_process, bill_number, "Skipped (Up to date)")
                            continue

                    if not is_skipped:
                        # Run scrape into cache
                        print_progress(processed, total_to_process, bill_number, "Scraping detailed data")

                        cache_bill_dir = os.path.join(temp_dir, session_code, bill_number)
                        stages_to_pass = set() if args.force else already_downloaded_stages
                        result = scrape_bill(
                            session_code,
                            bill_number,
                            cache_bill_dir,
                            args.repo,
                            stages_to_pass,
                            args.dry_run,
                            args.cache_dir,
                        )

                        if result.success:
                            all_bills_data[bill_number] = BillIndexData(
                                title=title,
                                status=status,
                                activity=activity,
                                stages=result.updated_stages,
                                last_checked=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            )
                            all_pending_commits.extend(result.stage_pending_commits)
                            all_pending_commits.extend(result.metadata_pending_commits)

                        processed += 1
                        print_progress(processed, total_to_process, bill_number, "Completed scraping")

        except KeyboardInterrupt:
            log_message("\nExecution interrupted by user. Processing scraped data so far...")
            interrupted = True

        # 2. Sort all pending commits chronologically by their event/stage date
        all_pending_commits.sort(key=get_commit_sort_key)

        # 3. Apply commits sequentially
        committed_count = 0
        rebase_needed = False

        if not args.dry_run:
            for commit in all_pending_commits:
                session_code = commit.session
                bill_number = commit.bill_number
                author_name = commit.author_name
                author_email = commit.author_email

                bill_dir = os.path.join(args.repo, session_code, "bills", bill_number)
                os.makedirs(bill_dir, exist_ok=True)

                if isinstance(commit, StagePendingBill):
                    stage_name = commit.stage_name
                    stage_date = commit.stage_date
                    if stage_date and stage_date.startswith("0001-01-01"):
                        stage_date = None

                    # Copy cached files to target repo
                    shutil.copy2(commit.stage_xml_path, os.path.join(bill_dir, "bill_text.xml"))
                    if os.path.exists(commit.stage_md_path):
                        shutil.copy2(commit.stage_md_path, os.path.join(bill_dir, "bill_text.md"))
                    shutil.copy2(commit.metadata_xml_path, os.path.join(bill_dir, "metadata.xml"))
                    shutil.copy2(commit.summary_md_path, os.path.join(bill_dir, "summary.md"))

                    # Stage files in git
                    run_command(["git", "add", f"{session_code}/bills/{bill_number}"], cwd=args.repo)

                    diff_staged = run_command(["git", "diff", "--cached", "--quiet"], cwd=args.repo)
                    if diff_staged.returncode != 0:
                        event_id = f"{session_code}/{bill_number}/{commit.slug}"
                        commit_msg = f"Bill {bill_number}: {stage_name} text update\n\nLegisinfo-Event: {event_id}"

                        existing_hash = find_commit_by_event_id(event_id, args.repo)
                        if existing_hash:
                            log_message(
                                f"  Creating Git fixup for stage {bill_number} ({stage_name}) "
                                f"targeting commit {existing_hash[:7]}..."
                            )
                            run_git_fixup(existing_hash, args.repo, author_name, author_email)
                            rebase_needed = True
                        else:
                            log_message(
                                f"  Committing sequential stage {bill_number} ({stage_name}) "
                                f"at {stage_date or 'now'} by {author_name}..."
                            )
                            run_git_commit(commit_msg, stage_date, args.repo, author_name, author_email)
                            committed_count += 1

                elif isinstance(commit, MetadataPendingBill):
                    event_date = commit.event_date
                    if event_date and event_date.startswith("0001-01-01"):
                        event_date = None

                    shutil.copy2(commit.metadata_xml_path, os.path.join(bill_dir, "metadata.xml"))
                    shutil.copy2(commit.summary_md_path, os.path.join(bill_dir, "summary.md"))

                    # If there are restored files, copy them as well
                    if commit.restore_xml_path:
                        shutil.copy2(commit.restore_xml_path, os.path.join(bill_dir, "bill_text.xml"))
                    if commit.restore_md_path:
                        shutil.copy2(commit.restore_md_path, os.path.join(bill_dir, "bill_text.md"))

                    run_command(["git", "add", f"{session_code}/bills/{bill_number}"], cwd=args.repo)

                    diff_staged = run_command(["git", "diff", "--cached", "--quiet"], cwd=args.repo)
                    if diff_staged.returncode != 0:
                        event_id = f"{session_code}/{bill_number}/metadata"
                        commit_msg = f"Bill {bill_number}: Metadata update\n\nLegisinfo-Event: {event_id}"

                        existing_hash = find_commit_by_event_id(event_id, args.repo)
                        if existing_hash:
                            log_message(
                                f"  Creating Git fixup for metadata updates for {bill_number} "
                                f"targeting commit {existing_hash[:7]}..."
                            )
                            run_git_fixup(existing_hash, args.repo, author_name, author_email)
                            rebase_needed = True
                        else:
                            log_message(
                                f"  Committing metadata updates for {bill_number} "
                                f"at {event_date or 'now'} by {author_name}..."
                            )
                            run_git_commit(commit_msg, event_date, args.repo, author_name, author_email)
                            committed_count += 1

        # 3.5 Run autosquash rebase if needed
        if not args.dry_run and rebase_needed:
            log_message("Performing Git autosquash rebase to integrate formatting updates...")
            rebase_res = run_git_autosquash(args.repo)
            if rebase_res.returncode != 0:
                log_message(
                    "Warning: Git autosquash rebase encountered conflicts. Aborting rebase to preserve clean tree..."
                )
                run_command(["git", "rebase", "--abort"], cwd=args.repo)

        # 4. Save and commit README indices and perform final sweep
        if not args.dry_run:
            for session_code, info in session_indices.items():
                save_readme_index(info["readme_path"], info["all_bills_data"], session_code)
                update_root_readme(args.repo, session_code, info["session_name"])

            # Final sweep: Stage and commit any remaining uncommitted or untracked bill files/indices
            status_res = run_command(["git", "status", "--porcelain"], cwd=args.repo)
            if status_res.stdout.strip():
                log_message("Finalizing and committing remaining bill files and index updates...")
                run_command(["git", "add", "-A"], cwd=args.repo)
                if interrupted:
                    run_git_commit("Scraper: Save index status on user interrupt", None, args.repo)
                else:
                    run_git_commit("Scraper: Update index checked timestamps and remaining files", None, args.repo)

    if interrupted:
        log_message("Progress saved on interrupt. Exiting gracefully.")
        sys.exit(0)


def fix_encoding_main():
    """CLI entrypoint to repair Mojibake in existing repository files."""
    parser = argparse.ArgumentParser(description="Repair Mojibake in repository files")
    parser.add_argument("--repo", default=".", help="Path to target data repository")
    args = parser.parse_args()

    fixed_count = 0
    for root_dir, _dirs, files in os.walk(args.repo):
        if any(skip in root_dir for skip in (".git", ".cache", ".venv")):
            continue
        for f in files:
            if f.endswith((".md", ".xml", ".txt")):
                path = os.path.join(root_dir, f)
                try:
                    with open(path, encoding="utf-8") as fp:
                        content = fp.read()
                    fixed = fix_mojibake(content)
                    if fixed != content:
                        fixed_count += 1
                        log_message(f"Fixed Mojibake in: {path}")
                        with open(path, "w", encoding="utf-8") as fp:
                            fp.write(fixed)
                except Exception:
                    pass
    log_message(f"Total files updated: {fixed_count}")


if __name__ == "__main__":
    main()
