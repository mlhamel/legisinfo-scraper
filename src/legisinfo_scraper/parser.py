import os
import xml.etree.ElementTree as ET

from .config import STAGE_DETAILS


def get_stage_info(slug):
    """Return friendly stage name and chronological sorting priority."""
    for key, (name, priority) in STAGE_DETAILS.items():
        if key in slug.lower():
            return name, priority
    return slug.replace("-", " ").title(), 99


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


def clean_date_str(date_str):
    if not date_str or date_str.startswith("0001-01-01"):
        return "N/A"
    return date_str


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
        activity_dt = clean_date_str(bill_node.findtext("LatestBillEventDateTime"))

        md = []
        md.append(f"# Bill {bill_num}: {title_en}\n\n")
        md.append(f"- **Current Status**: {status_en}\n")
        md.append(f"- **Sponsor**: {sponsor}\n")

        if activity_dt and activity_dt != "N/A":
            md.append(f"- **Latest Activity**: {activity_en} (at {activity_dt})\n\n")
        else:
            md.append(f"- **Latest Activity**: {activity_en}\n\n")

        md.append("## Legislative Stage History\n\n")
        md.append("| Chamber | Stage | Status | Completed Date |\n")
        md.append("| --- | --- | --- | --- |\n")

        # House stages
        house_stages = bill_node.findall(".//HouseBillStages/*")
        for stage in house_stages:
            name = stage.findtext("BillStageNameEn") or ""
            state = stage.findtext("StateNameEn") or ""
            dt = clean_date_str(stage.findtext("LastStageEventStartDateTime"))
            md.append(f"| House of Commons | {name} | {state} | {dt} |\n")

        # Senate stages
        senate_stages = bill_node.findall(".//SenateBillStages/*")
        for stage in senate_stages:
            name = stage.findtext("BillStageNameEn") or ""
            state = stage.findtext("StateNameEn") or ""
            dt = clean_date_str(stage.findtext("LastStageEventStartDateTime"))
            md.append(f"| Senate | {name} | {state} | {dt} |\n")

        return "".join(md)
    except Exception as e:
        return f"# Summary Generation Failed\n\nError parsing metadata: {e}"


DIRECT_STAGE_TAGS = {
    "first-reading": ["PassedHouseFirstReadingDateTime", "PassedSenateFirstReadingDateTime"],
    "second-reading": ["PassedHouseSecondReadingDateTime", "PassedSenateSecondReadingDateTime"],
    "third-reading": ["PassedHouseThirdReadingDateTime", "PassedSenateThirdReadingDateTime"],
    "royal-assent": ["ReceivedRoyalAssentDateTime"],
}


def get_stage_date_from_xml(metadata_path, slug):
    """Find the completion date of a specific stage in the metadata XML."""
    if not os.path.exists(metadata_path):
        return None
    try:
        tree = ET.parse(metadata_path)
        root = tree.getroot()
        stage_name, _ = get_stage_info(slug)

        # 1. Search all stages in House and Senate (modern format)
        for stage_node in root.findall(".//HouseBillStage") + root.findall(".//SenateBillStage"):
            name = stage_node.findtext("BillStageNameEn") or ""
            if stage_name.lower() in name.lower():
                dt = stage_node.findtext("LastStageEventStartDateTime")
                if dt and not dt.startswith("0001-01-01"):
                    return dt

        # 2. Fall back to direct stage date tags (historical format)
        for key, tags in DIRECT_STAGE_TAGS.items():
            if key in slug.lower():
                for tag in tags:
                    dt = root.findtext(f".//{tag}")
                    if dt and not dt.startswith("0001-01-01"):
                        return dt
    except Exception:
        pass
    return None


def get_latest_event_date_from_xml(metadata_path):
    """Get the latest bill event date from metadata XML."""
    if not os.path.exists(metadata_path):
        return None
    try:
        tree = ET.parse(metadata_path)
        root = tree.getroot()

        # 1. Try LatestBillEventDateTime
        dt = root.findtext(".//LatestBillEventDateTime")
        if dt and not dt.startswith("0001-01-01"):
            return dt

        # 2. Try LatestCompletedBillStageDateTime
        dt = root.findtext(".//LatestCompletedBillStageDateTime")
        if dt and not dt.startswith("0001-01-01"):
            return dt

        # 3. Scan all tags ending with DateTime or Date and find the max/latest date
        dates = []
        for elem in root.iter():
            if elem.text and any(suffix in elem.tag for suffix in ("DateTime", "Date")):
                val = elem.text.strip()
                if (
                    val
                    and not val.startswith("0001-01-01")
                    and len(val) >= 10
                    and val[0:4].isdigit()
                    and val[4] == "-"
                    and val[7] == "-"
                ):
                    dates.append(val)
        if dates:
            return max(dates)
    except Exception:
        pass
    return None
