"""Parser helpers for Lobby Canada registration and communication data."""

import re
from typing import Any

from civican.schemas import LobbyCommunication, LobbyRegistration

from civican.scraper.utils import fix_mojibake

# Pattern to extract legislative bill references (e.g. "Bill C-11", "Bill S-2", "C-25", "S-201")
BILL_REFERENCE_REGEX = re.compile(r"\b(?:Bill\s+)?([CS]-\d+)\b", re.IGNORECASE)


def extract_bill_references(text: str) -> list[str]:
    """Extract bill numbers (e.g., C-11, S-2) from subject matter text."""
    if not text:
        return []
    matches = BILL_REFERENCE_REGEX.findall(text)
    # Deduplicate while preserving order
    seen = set()
    res = []
    for m in matches:
        formatted = m.upper()
        if formatted not in seen:
            seen.add(formatted)
            res.append(formatted)
    return res


def parse_registration_entry(data: dict[str, Any]) -> LobbyRegistration:
    """Parse raw registration dictionary or CSV row into a LobbyRegistration Pydantic model.

    Supports both Flat CSV schemas (REGID, REGISTRANT_NAME, etc.) and Relational ZIP schemas
    (REG_ID_ENR, EN_CLIENT_ORG_CORP_NM_AN, RGSTRNT_1ST_NM_PRENOM_DCLRNT, etc.).
    """
    reg_id = str(data.get("REG_ID_ENR") or data.get("REGID") or data.get("registration_id") or data.get("id") or "")

    first_nm = str(data.get("RGSTRNT_1ST_NM_PRENOM_DCLRNT") or "").strip()
    last_nm = str(data.get("RGSTRNT_LAST_NM_DCLRNT") or "").strip()
    full_nm = f"{first_nm} {last_nm}".strip() if (first_nm or last_nm) else ""
    registrant = fix_mojibake(full_nm or str(data.get("REGISTRANT_NAME") or data.get("registrant_name") or ""))

    client_org = fix_mojibake(
        str(
            data.get("EN_CLIENT_ORG_CORP_NM_AN")
            or data.get("CLIENT_ORG_NAME")
            or data.get("FR_CLIENT_ORG_CORP_NM")
            or data.get("client_org_name")
            or ""
        )
    )

    reg_type = str(data.get("REG_TYPE_ENR") or data.get("REG_TYPE") or data.get("type") or "Corporation")
    status = str(data.get("REG_STATUS") or data.get("status") or "Active")
    effective_date = str(
        data.get("EFFECTIVE_DATE_VIGUEUR") or data.get("EFFECTIVE_DATE") or data.get("effective_date") or ""
    )
    posted_date = str(data.get("POSTED_DATE_PUBLICATION") or data.get("POSTED_DATE") or data.get("posted_date") or "")

    raw_subjects = data.get("SUBJECT_MATTER") or data.get("subject_matters") or []
    if isinstance(raw_subjects, str):
        subjects = [fix_mojibake(s.strip()) for s in raw_subjects.split(";") if s.strip()]
    else:
        subjects = [fix_mojibake(str(s)) for s in raw_subjects]

    raw_institutions = data.get("GOVT_INST_NAME") or data.get("government_institutions") or []
    if isinstance(raw_institutions, str):
        institutions = [fix_mojibake(i.strip()) for i in raw_institutions.split(";") if i.strip()]
    else:
        institutions = [fix_mojibake(str(i)) for i in raw_institutions]

    # Extract legislative proposals / bills from subject matters
    bills = []
    for s in subjects:
        bills.extend(extract_bill_references(s))

    return LobbyRegistration(
        registration_id=reg_id,
        registrant_name=registrant,
        client_org_name=client_org,
        type=reg_type,
        status=status,
        effective_date=effective_date,
        posted_date=posted_date,
        subject_matters=subjects,
        legislative_proposals=sorted(set(bills)),
        government_institutions=institutions,
    )


def parse_communication_entry(data: dict[str, Any]) -> LobbyCommunication:
    """Parse raw communication report dictionary or CSV row into a LobbyCommunication Pydantic model.

    Supports both Flat CSV schemas (COMCID, LOBBYIST_NAME, etc.) and Relational ZIP schemas
    (COMLOG_ID, RGSTRNT_1ST_NM_PRENOM_DCLRNT, DPOH_FIRST_NM_PRENOM_TCPD, etc.).
    """
    comm_id = str(data.get("COMLOG_ID") or data.get("COMCID") or data.get("communication_id") or data.get("id") or "")
    reg_id = str(data.get("REGISTRANT_NUM_DECLARANT") or data.get("REGID") or data.get("registration_id") or "")

    client_org = fix_mojibake(
        str(
            data.get("EN_CLIENT_ORG_CORP_NM_AN")
            or data.get("CLIENT_ORG_NAME")
            or data.get("FR_CLIENT_ORG_CORP_NM")
            or data.get("client_org_name")
            or ""
        )
    )
    comm_date = str(data.get("COMM_DATE") or data.get("communication_date") or "")
    posted_date = str(data.get("POSTED_DATE_PUBLICATION") or data.get("POSTED_DATE") or data.get("posted_date") or "")

    first_nm = str(data.get("RGSTRNT_1ST_NM_PRENOM_DCLRNT") or "").strip()
    last_nm = str(data.get("RGSTRNT_LAST_NM_DCLRNT") or "").strip()
    full_nm = f"{first_nm} {last_nm}".strip() if (first_nm or last_nm) else ""
    lobbyist_name = fix_mojibake(full_nm or str(data.get("LOBBYIST_NAME") or data.get("lobbyist_name") or ""))

    dpoh_first = str(data.get("DPOH_FIRST_NM_PRENOM_TCPD") or "").strip()
    dpoh_last = str(data.get("DPOH_LAST_NM_TCPD") or "").strip()
    dpoh_full = f"{dpoh_first} {dpoh_last}".strip() if (dpoh_first or dpoh_last) else ""
    dpoh_name = fix_mojibake(dpoh_full or str(data.get("DPOH_NAME") or data.get("dpoh_name") or ""))

    dpoh_title = fix_mojibake(
        str(data.get("DPOH_TITLE_TITRE_TCPD") or data.get("DPOH_TITLE") or data.get("dpoh_title") or "")
    )
    institution = fix_mojibake(
        str(
            data.get("GOVT_INST_NAME")
            or data.get("INSTITUTION")
            or data.get("government_institution")
            or data.get("institution")
            or ""
        )
    )

    raw_subjects = data.get("SUBJECT_MATTER") or data.get("subject_matters") or []
    if isinstance(raw_subjects, str):
        subjects = [fix_mojibake(s.strip()) for s in raw_subjects.split(";") if s.strip()]
    else:
        subjects = [fix_mojibake(str(s)) for s in raw_subjects]

    bills = []
    for s in subjects:
        bills.extend(extract_bill_references(s))

    return LobbyCommunication(
        communication_id=comm_id,
        registration_id=reg_id,
        client_org_name=client_org,
        communication_date=comm_date,
        posted_date=posted_date,
        lobbyist_name=lobbyist_name,
        dpoh_name=dpoh_name,
        dpoh_title=dpoh_title,
        government_institution=institution,
        subject_matters=subjects,
        legislative_proposals=sorted(set(bills)),
    )
