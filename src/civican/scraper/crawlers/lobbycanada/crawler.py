"""Lobby Canada Crawler implementation inheriting from BaseCrawler."""

import csv
import io
import os
import subprocess
import tempfile
import zipfile
from typing import Any

from civican.schemas import LobbyScrapeResult

from civican.scraper.crawlers.base import BaseCrawler
from civican.scraper.exporters.base import BaseExporter
from civican.scraper.exporters.json_file import JsonFileExporter
from civican.scraper.utils import log_message

from .config import (
    COMMUNICATIONS_CSV_URL,
    COMMUNICATIONS_DATASET_URL,
    REGISTRATIONS_CSV_URL,
    REGISTRATIONS_DATASET_URL,
)
from .exporter import LobbyCanadaDuckDBExporter
from .parser import parse_communication_entry, parse_registration_entry


def download_open_canada_file(url: str, target_path: str, timeout: int = 300) -> bool:
    """Download Open Data file from Open Government Portal to target_path using curl_cffi or curl."""
    os.makedirs(os.path.dirname(os.path.abspath(target_path)), exist_ok=True)

    # 1. Try curl_cffi to bypass Cloudflare WAF challenge (impersonating Chrome browser)
    try:
        from curl_cffi import requests as cffi_requests

        resp = cffi_requests.get(url, impersonate="chrome120", timeout=timeout)
        if resp.status_code == 200 and len(resp.content) > 1000:
            with open(target_path, "wb") as f:
                f.write(resp.content)
            return True
        log_message(f"Notice: curl_cffi returned status {resp.status_code} for {url}")
    except Exception as e:
        log_message(f"Notice: curl_cffi download failed for {url}: {e}")

    # 2. Fallback to curl CLI
    try:
        proc = subprocess.run(
            [
                "curl",
                "-sL",
                "-A",
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36",
                "-o",
                target_path,
                url,
            ],
            timeout=timeout,
        )
        if proc.returncode == 0 and os.path.exists(target_path) and os.path.getsize(target_path) > 1000:
            return True
    except Exception as e:
        log_message(f"Warning: Exception in download_open_canada_file ({url}): {e}")

    return False


def fetch_open_canada_csv(dataset_url: str, csv_url: str, timeout: int = 120) -> str:
    """Fetch CSV content from Open Canada for backward compatibility with callers and tests."""
    _ = dataset_url
    with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        if download_open_canada_file(csv_url, tmp_path, timeout=timeout):
            if "registrations" in csv_url:
                rows = parse_zip_registrations(tmp_path)
            else:
                rows = parse_zip_communications(tmp_path)
            if rows:
                fieldnames = list(rows[0].keys())
                out = io.StringIO()
                writer = csv.DictWriter(out, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)
                return out.getvalue()
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
    return ""


def parse_zip_registrations(zip_path: str) -> list[dict[str, Any]]:
    """Parse registrations from a multi-CSV Open Data ZIP archive."""
    subjects_map: dict[str, list[str]] = {}
    insts_map: dict[str, list[str]] = {}
    records = []

    with zipfile.ZipFile(zip_path) as z:
        if "Registration_SubjectMatterDetailsExport.csv" in z.namelist():
            with z.open("Registration_SubjectMatterDetailsExport.csv") as f:
                reader = csv.DictReader(line.decode("utf-8", errors="replace") for line in f)
                for row in reader:
                    reg_id = row.get("REG_ID_ENR", "")
                    desc = row.get("DESCRIPTION", "").strip()
                    if reg_id and desc:
                        subjects_map.setdefault(reg_id, []).append(desc)

        if "Registration_GovernmentInstExport.csv" in z.namelist():
            with z.open("Registration_GovernmentInstExport.csv") as f:
                reader = csv.DictReader(line.decode("utf-8", errors="replace") for line in f)
                for row in reader:
                    reg_id = row.get("REG_ID_ENR", "")
                    inst = row.get("EN_INST_NM_AN", "").strip()
                    if reg_id and inst:
                        insts_map.setdefault(reg_id, []).append(inst)

        if "Registration_PrimaryExport.csv" in z.namelist():
            with z.open("Registration_PrimaryExport.csv") as f:
                reader = csv.DictReader(line.decode("utf-8", errors="replace") for line in f)
                for row in reader:
                    reg_id = row.get("REG_ID_ENR", "")
                    prenom = row.get('RGSTRNT_1ST_NM_PRENOM_DCLRNT', '').strip()
                    nom = row.get('RGSTRNT_LAST_NM_NOM_DCLRNT', '').strip()
                    registrant = f"{prenom} {nom}".strip()
                    client_org = (
                        row.get("EN_CLIENT_ORG_CORP_NM_AN", "").strip() or row.get("EN_CLIENT_ORG_NM_AN", "").strip()
                    )
                    reg_type = row.get("REG_TYPE_ENR", "").strip()
                    status = row.get("REG_STATUS_STATUT_ENR", "").strip()
                    effective_date = row.get("EFFECTIVE_DATE_VIGUEUR", "").strip()
                    posted_date = row.get("POSTED_DATE_PUBLICATION", "").strip()

                    subjects = subjects_map.get(reg_id, [])
                    insts = insts_map.get(reg_id, [])

                    subject_str = "; ".join(subjects) if subjects else ""
                    inst_str = "; ".join(insts) if insts else ""

                    entry = {
                        "REGID": reg_id,
                        "REGISTRANT_NAME": registrant,
                        "CLIENT_ORG_NAME": client_org,
                        "REG_TYPE": reg_type,
                        "REG_STATUS": status,
                        "EFFECTIVE_DATE": effective_date,
                        "POSTED_DATE": posted_date,
                        "SUBJECT_MATTER": subject_str,
                        "GOVT_INST_NAME": inst_str,
                    }
                    records.append(entry)

    return records


def parse_zip_communications(zip_path: str) -> list[dict[str, Any]]:
    """Parse communication reports from a multi-CSV Open Data ZIP archive."""
    dpoh_map: dict[str, list[tuple[str, str, str]]] = {}
    records = []

    with zipfile.ZipFile(zip_path) as z:
        if "Communication_DpohExport.csv" in z.namelist():
            with z.open("Communication_DpohExport.csv") as f:
                reader = csv.DictReader(line.decode("utf-8", errors="replace") for line in f)
                for row in reader:
                    com_id = row.get("COMLOG_ID", "")
                    name = f"{row.get('DPOH_1ST_NM_PRENOM_ACDP', '')} {row.get('DPOH_LAST_NM_NOM_ACDP', '')}".strip()
                    title = row.get("EN_TITLE_TITRE_AN", "").strip()
                    inst = row.get("EN_INST_NM_AN", "").strip()
                    if com_id:
                        dpoh_map.setdefault(com_id, []).append((name, title, inst))

        if "Communication_PrimaryExport.csv" in z.namelist():
            with z.open("Communication_PrimaryExport.csv") as f:
                reader = csv.DictReader(line.decode("utf-8", errors="replace") for line in f)
                for row in reader:
                    com_id = row.get("COMLOG_ID", "")
                    reg_id = row.get("REG_ID_ENR", "")
                    client_org = (
                        row.get("EN_CLIENT_ORG_CORP_NM_AN", "").strip() or row.get("EN_CLIENT_ORG_NM_AN", "").strip()
                    )
                    comm_date = row.get("COMMUNICATION_DATE", "").strip()
                    posted_date = row.get("POSTED_DATE_PUBLICATION", "").strip()
                    first_name = row.get("LOBBYIST_1ST_NM_PRENOM_LOBBYISTE", "").strip()
                    last_name = row.get("LOBBYIST_LAST_NM_NOM_LOBBYISTE", "").strip()
                    lobbyist = f"{first_name} {last_name}".strip()

                    dpoh_list = dpoh_map.get(com_id, [])
                    dpoh_name = dpoh_list[0][0] if dpoh_list else ""
                    dpoh_title = dpoh_list[0][1] if dpoh_list else ""
                    inst_name = dpoh_list[0][2] if dpoh_list else ""

                    entry = {
                        "COMCID": com_id,
                        "REGID": reg_id,
                        "CLIENT_ORG_NAME": client_org,
                        "COMM_DATE": comm_date,
                        "POSTED_DATE": posted_date,
                        "LOBBYIST_NAME": lobbyist,
                        "DPOH_NAME": dpoh_name,
                        "DPOH_TITLE": dpoh_title,
                        "GOVT_INST_NAME": inst_name,
                    }
                    records.append(entry)

    return records


class LobbyCanadaCrawler(BaseCrawler):
    """Crawler for Lobby Canada (registrations and monthly communication reports)."""

    @property
    def source_name(self) -> str:
        return "lobbycanada"

    def scrape_bill(
        self,
        session: str,
        bill_number: str,
        cache_bill_dir: str,
        repo_path: str,
        already_downloaded_stages: set[str],
        dry_run: bool = False,
        cache_dir: str | None = None,
    ) -> Any:
        _ = (session, bill_number, cache_bill_dir, repo_path, already_downloaded_stages, dry_run, cache_dir)
        return None

    def report_status(self, repo_path: str) -> Any:
        _ = repo_path
        return None

    def fetch_registrations(self, limit: int = 0) -> list[Any]:
        """Fetch lobbyist registrations from Open Government Portal."""
        _ = limit
        return []

    def fetch_communications(self, limit: int = 0) -> list[Any]:
        """Fetch monthly communication reports from Open Government Portal."""
        _ = limit
        return []

    def scrape_data(
        self,
        repo_path: str,
        data_type: str = "all",
        year: int | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        bulk: bool = False,
        limit: int = 0,
        output_format: str = "duckdb",
        db_path: str | None = None,
        dry_run: bool = False,
    ) -> LobbyScrapeResult:
        """Scrape real registrations and communication reports from Open Government Portal into repo_path."""
        scope_desc = f"year={year}" if year else f"range={start_date} to {end_date}" if start_date else "all"
        if bulk:
            scope_desc += " [BULK OPEN DATA]"

        log_message(
            f"Starting Lobby Canada ({data_type}, {scope_desc}, format={output_format}) scraping into {repo_path}..."
        )

        scraped_registrations = []
        scraped_communications = []

        cache_dir = os.path.join(repo_path, ".cache")
        cached_reg_zip = os.path.join(cache_dir, "registrations_enregistrements_ocl_cal.zip")
        cached_comm_zip = os.path.join(cache_dir, "communications_ocl_cal.zip")

        # 1. Fetch Registrations from Open Government Portal or local ZIP cache
        if data_type in ("all", "registrations"):
            log_message("Fetching Lobbying Registrations from Open Government Portal...")
            if not os.path.exists(cached_reg_zip):
                log_message(f"Downloading Open Data registrations archive to {cached_reg_zip}...")
                download_open_canada_file(REGISTRATIONS_CSV_URL, cached_reg_zip)

            reg_rows = []
            if os.path.exists(cached_reg_zip):
                try:
                    reg_rows = parse_zip_registrations(cached_reg_zip)
                except Exception as e:
                    log_message(f"Warning: Failed to parse registration ZIP: {e}")

            if not reg_rows:
                try:
                    text = fetch_open_canada_csv(REGISTRATIONS_DATASET_URL, REGISTRATIONS_CSV_URL).lstrip("\ufeff\r\n")
                    if "REGID" in text[:200] or "REG_ID" in text[:200]:
                        reader = csv.DictReader(text.splitlines())
                        reg_rows = list(reader)
                except Exception as e:
                    log_message(f"Warning: Failed to fetch registrations CSV: {e}")

            for row in reg_rows:
                reg = parse_registration_entry(row)
                if not reg.registration_id:
                    continue
                if year and reg.effective_date and not reg.effective_date.startswith(str(year)):
                    continue
                if start_date and reg.effective_date and reg.effective_date < start_date:
                    continue
                if end_date and reg.effective_date and reg.effective_date > end_date:
                    continue

                scraped_registrations.append(reg)
                if limit > 0 and len(scraped_registrations) >= limit:
                    break
            log_message(f"Parsed {len(scraped_registrations)} registration records.")

        # 2. Fetch Communications from Open Government Portal or local ZIP cache
        if data_type in ("all", "communications"):
            log_message("Fetching Monthly Communication Reports from Open Government Portal...")
            if not os.path.exists(cached_comm_zip):
                log_message(f"Downloading Open Data communications archive to {cached_comm_zip}...")
                download_open_canada_file(COMMUNICATIONS_CSV_URL, cached_comm_zip)

            comm_rows = []
            if os.path.exists(cached_comm_zip):
                try:
                    comm_rows = parse_zip_communications(cached_comm_zip)
                except Exception as e:
                    log_message(f"Warning: Failed to parse communication ZIP: {e}")

            if not comm_rows:
                try:
                    text = fetch_open_canada_csv(COMMUNICATIONS_DATASET_URL, COMMUNICATIONS_CSV_URL).lstrip(
                        "\ufeff\r\n"
                    )
                    if "COMCID" in text[:200] or "COMLOG" in text[:200]:
                        reader = csv.DictReader(text.splitlines())
                        comm_rows = list(reader)
                except Exception as e:
                    log_message(f"Warning: Failed to fetch communications CSV: {e}")

            for row in comm_rows:
                comm = parse_communication_entry(row)
                if not comm.communication_id:
                    continue
                if year and comm.communication_date and not comm.communication_date.startswith(str(year)):
                    continue
                if start_date and comm.communication_date and comm.communication_date < start_date:
                    continue
                if end_date and comm.communication_date and comm.communication_date > end_date:
                    continue

                scraped_communications.append(comm)
                if limit > 0 and len(scraped_communications) >= limit:
                    break
            log_message(f"Parsed {len(scraped_communications)} communication records.")

        # 3. Export parsed records using configured exporters
        exporters: list[BaseExporter] = []
        target_db = db_path or os.path.join(repo_path, "lobbycanada.duckdb")

        try:
            if not dry_run:
                if output_format in ("json", "all"):
                    exporters.append(JsonFileExporter(repo_path=repo_path))
                if output_format in ("duckdb", "all"):
                    exporters.append(LobbyCanadaDuckDBExporter(db_path=target_db))

                for exp in exporters:
                    if scraped_registrations:
                        exp.export_registrations(scraped_registrations)
                    if scraped_communications:
                        exp.export_communications(scraped_communications)

            return LobbyScrapeResult(
                success=True,
                total_scraped=len(scraped_registrations) + len(scraped_communications),
                registrations_scraped=len(scraped_registrations),
                communications_scraped=len(scraped_communications),
                repo_path=repo_path,
            )
        finally:
            for exp in exporters:
                exp.close()
