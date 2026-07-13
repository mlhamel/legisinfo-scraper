import os
import sys
import xml.etree.ElementTree as ET

import requests

from .config import LEGISINFO_BASE
from .index_manager import parse_readme_index


def report_status(repo_path):
    url = f"{LEGISINFO_BASE}/en/bills/xml?parlsession=all"
    print("Fetching global bills list from LEGISinfo...")  # noqa: T201
    try:
        res = requests.get(url, timeout=30)
        if res.status_code != 200:
            sys.exit(1)
        root = ET.fromstring(res.content)
    except Exception:
        sys.exit(1)

    bills = root.findall(".//Bill")

    # Group bills by session and collect API status/activity info
    api_sessions = {}
    api_bills_info = {}  # (session, bill_number) -> (status, activity)
    for b in bills:
        sess_code = b.findtext("ParlSessionCode")
        bill_num = b.findtext("BillNumberFormatted")
        if not sess_code or not bill_num:
            continue
        if sess_code not in api_sessions:
            api_sessions[sess_code] = set()
        api_sessions[sess_code].add(bill_num)

        status = " ".join((b.findtext("CurrentStatusEn") or "").split())
        activity = " ".join((b.findtext("LatestActivityEn") or "").split())
        api_bills_info[(sess_code, bill_num)] = (status, activity)

    print("\nSession Scraping Status Report:")  # noqa: T201
    print("=" * 70)  # noqa: T201
    print(f"{'Session':<10} | {'Total Bills':<12} | {'Scraped Bills':<14} | {'Status':<12}")  # noqa: T201
    print("-" * 70)  # noqa: T201

    for sess_code in sorted(api_sessions.keys()):
        total_api_bills = len(api_sessions[sess_code])

        sess_dir = os.path.join(repo_path, sess_code)
        readme_path = os.path.join(sess_dir, "README.md")

        if not os.path.exists(sess_dir) or not os.path.exists(readme_path):
            status = "Not Scraped"
            scraped_count = 0
        else:
            try:
                index_data = parse_readme_index(readme_path)
                scraped_count = len(index_data)

                # Check if all API bills exist in index
                missing_bills = api_sessions[sess_code] - set(index_data.keys())

                # Check if any bill is out of sync with API status/activity
                incomplete_bills = []
                for b_num, b_data in index_data.items():
                    api_info = api_bills_info.get((sess_code, b_num))
                    if api_info:
                        api_status, api_activity = api_info
                        index_status = b_data.get("status", "")
                        index_activity = b_data.get("activity", "")
                        if index_status != api_status or index_activity != api_activity:
                            incomplete_bills.append(b_num)

                if not missing_bills and not incomplete_bills and scraped_count >= total_api_bills:
                    status = "Complete"
                else:
                    status = "Incomplete"
            except Exception:
                status = "Incomplete"
                scraped_count = 0

        print(f"{sess_code:<10} | {total_api_bills:<12} | {scraped_count:<14} | {status:<12}")  # noqa: T201
