from enum import Enum
from typing import Literal

from pydantic import BaseModel


class PendingBillType(str, Enum):
    STAGE = "stage"
    METADATA = "metadata"


class PendingBill(BaseModel):
    session: str
    bill_number: str
    author_name: str
    author_email: str
    metadata_xml_path: str
    summary_md_path: str


class StagePendingBill(PendingBill):
    type: Literal["stage"] = "stage"
    slug: str
    stage_name: str
    stage_date: str | None = None
    stage_xml_path: str
    stage_md_path: str


class MetadataPendingBill(PendingBill):
    type: Literal["metadata"] = "metadata"
    event_date: str | None = None
    restore_xml_path: str | None = None
    restore_md_path: str | None = None


class ScrapeResult(BaseModel):
    success: bool
    updated_stages: set[str]
    author_name: str
    author_email: str
    pending_commits: list[StagePendingBill | MetadataPendingBill]
