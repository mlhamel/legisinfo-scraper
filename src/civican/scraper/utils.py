import contextlib
import re
import sys

import ftfy


def fix_mojibake(text: str) -> str:
    """Repair any Mojibake or encoding corruption across all Unicode special characters."""
    if not text:
        return text

    with contextlib.suppress(Exception):
        text = ftfy.fix_text(text)

    mojibake_markers = ("Ã", "â€", "Å“", "ï¿½", "Â")
    if any(marker in text for marker in mojibake_markers):
        for enc in ("cp1252", "iso-8859-1"):
            try:
                fixed = text.encode(enc).decode("utf-8")
                text = fixed
                break
            except (UnicodeEncodeError, UnicodeDecodeError):
                continue

    replacements = {
        "â€œ": "\u201c",
        "â€\x9d": "\u201d",
        "â€™": "\u2019",
        "â\x80\x98": "\u2018",
        "â€“": "\u2013",
        "â€”": "\u2014",
        "â€¦": "\u2026",
        "â€¢": "\u2022",
        "â\x80\x9c": "\u201c",
        "â\x80\x9d": "\u201d",
        "â\x80\x99": "\u2019",
        "â\x80\x93": "\u2013",
        "â\x80\x94": "\u2014",
    }
    for bad, good in replacements.items():
        if bad in text:
            text = text.replace(bad, good)

    return text


def clean_sponsor_name(name):
    """Clean the sponsor name to Title Case."""
    if not name:
        return "Parliament of Canada"
    name = fix_mojibake(name)
    if name.isupper():
        return name.title()
    return name


def generate_sponsor_email(name):
    """Generate a clean mock parliament email address from sponsor name."""
    if not name:
        return "sponsor@parl.gc.ca"
    cleaned = name.lower()
    # Remove common titles
    cleaned = re.sub(r"\b(the honourable|senator|p\.c\.|m\.p\.)\b", "", cleaned)
    cleaned = re.sub(r"[^a-z\s]", "", cleaned).strip()
    email_prefix = ".".join(cleaned.split())
    if not email_prefix:
        email_prefix = "sponsor"
    return f"{email_prefix}@parl.gc.ca"


def log_message(msg):
    """Print a message, clearing the progress bar line first to avoid garbled output."""
    sys.stdout.write("\r\033[K")
    print(msg)  # noqa: T201
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
        pass
