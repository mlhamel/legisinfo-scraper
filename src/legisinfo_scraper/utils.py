import sys
import re

def clean_sponsor_name(name):
    """Clean the sponsor name to Title Case."""
    if not name:
        return "Parliament of Canada"
    if name.isupper():
        return name.title()
    return name

def generate_sponsor_email(name):
    """Generate a clean mock parliament email address from sponsor name."""
    if not name:
        return "sponsor@parl.gc.ca"
    cleaned = name.lower()
    # Remove common titles
    cleaned = re.sub(r'\b(the honourable|senator|p\.c\.|m\.p\.)\b', '', cleaned)
    cleaned = re.sub(r'[^a-z\s]', '', cleaned).strip()
    email_prefix = ".".join(cleaned.split())
    if not email_prefix:
        email_prefix = "sponsor"
    return f"{email_prefix}@parl.gc.ca"

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
