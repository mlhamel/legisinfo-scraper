import os
import re
from datetime import datetime

from .utils import fix_mojibake, log_message


def parse_readme_index(readme_path):
    """Parse existing README.md index to recover status, activity, and downloaded stages."""
    index_data = {}
    if not os.path.exists(readme_path):
        return index_data

    try:
        with open(readme_path, encoding="utf-8") as f:
            content = f.read()

        # Reconstruct split lines for robust parsing
        raw_lines = content.splitlines()
        lines = []
        for line in raw_lines:
            if line.strip().startswith("|") and not line.startswith("|") and lines:
                lines[-1] = lines[-1].rstrip() + " " + line.strip()
            else:
                lines.append(line)

        for line in lines:
            # Matches: | [S-2](...) | Title | Status | Activity | Stages | Checked |
            match = re.search(
                r"\|\s*\[([^\]]+)\]\([^)]+\)\s*\|([^|]+)\|([^|]+)\|([^|]+)\|([^|]*)\|\s*([^|]*)\s*\|", line
            )
            if match:
                bill_num = match.group(1).strip()
                title = fix_mojibake(" ".join(match.group(2).split()))
                status = fix_mojibake(" ".join(match.group(3).split()))
                activity = fix_mojibake(" ".join(match.group(4).split()))
                stages_str = match.group(5).strip()
                checked = match.group(6).strip()

                slugs = [s.strip().replace("`", "") for s in stages_str.split(",") if s.strip() and s.strip() != "None"]
                index_data[bill_num] = {
                    "title": title,
                    "status": status,
                    "activity": activity,
                    "stages": set(slugs),
                    "last_checked": checked,
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
        match = re.match(r"([A-Z]+)-(\d+)", bill_num)
        if match:
            prefix = match.group(1)
            num = int(match.group(2))
            prefix_val = 0 if prefix == "C" else 1
            return (prefix_val, num)
        return (2, bill_num)

    for bill_num in sorted(all_bills_data.keys(), key=sort_key):
        b = all_bills_data[bill_num]
        title = fix_mojibake(b.get("title", "")).replace("|", "\\|")
        status = fix_mojibake(b.get("status", "")).replace("|", "\\|")
        activity = fix_mojibake(b.get("activity", "")).replace("|", "\\|")
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
            with open(root_readme_path, encoding="utf-8") as f:
                content = f.read()
            for line in content.splitlines():
                # Matches: | Session | [Slug](path) | Status | Last Updated |
                match = re.search(r"\|\s*([^|]+)\s*\|\s*\[([^\]]+)\]\([^)]+\)\s*\|\s*([^|]+)\s*\|\s*([^|]+)\s*\|", line)
                if match:
                    s_name = match.group(1).strip()
                    s_code = match.group(2).strip()
                    s_status = match.group(3).strip()
                    s_updated = match.group(4).strip()
                    if s_code != "Link":  # skip header
                        sessions[s_code] = {"name": s_name, "status": s_status, "updated": s_updated}
        except Exception as e:
            log_message(f"Warning: Failed to parse root README.md: {e}")

    clean_name = session_name.split("~")[0].strip() if "~" in session_name else session_name
    status = (
        "Active"
        if "present" in session_name.lower() or "active" in session_name.lower() or not session_name
        else "Prerogative/Dissolved"
    )

    sessions[session] = {"name": clean_name or f"Session {session}", "status": status, "updated": now_str}

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


def migrate_existing_index(repo_path, session):
    """Automatically migrates the old centralized README.md to session/README.md."""
    root_readme_path = os.path.join(repo_path, "README.md")
    session_dir = os.path.join(repo_path, session)
    session_readme_path = os.path.join(session_dir, "README.md")

    if os.path.exists(root_readme_path) and not os.path.exists(session_readme_path):
        try:
            with open(root_readme_path, encoding="utf-8") as f:
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
