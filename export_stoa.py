
#!/usr/bin/env python3
import os
import re
import subprocess
import requests
import logging
from datetime import datetime, timezone
from typing import List, Tuple

# Configuration
HEDGEDOC_URL = "https://doc.anagora.org"
SSH_TARGET = "hedgedoc@patera"
EXPORT_DIR = os.path.expanduser("~/agora/stoa/doc.anagora.org")
GIT_REPO_URL = "https://github.com/flancia-coop/doc.anagora.org"
LAST_SYNC_FILE = os.path.join(EXPORT_DIR, ".last_sync")

# Spam Filter Constants
SPAM_KEYWORDS = ['casino', 'cacuoc', 'nhacai', 'dangky', 'dangnhap', 'keonhacai', 'escort', 'hentai', 'chyoa']
VN_CHARS = re.compile(r'[àáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđ]', re.IGNORECASE)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger('stoa-exporter')

def get_last_sync() -> str:
    if os.path.exists(LAST_SYNC_FILE):
        with open(LAST_SYNC_FILE, 'r') as f:
            return f.read().strip()
    return ""

def update_last_sync():
    os.makedirs(EXPORT_DIR, exist_ok=True)
    with open(LAST_SYNC_FILE, 'w') as f:
        # Save current time in ISO format for PostgreSQL
        f.write(datetime.now(timezone.utc).isoformat())

def get_note_aliases() -> List[str]:
    """Fetches the list of note aliases from the remote HedgeDoc database."""
    logger.info("Fetching note aliases from patera...")
    last_sync = get_last_sync()
    
    if last_sync:
        logger.info(f"Incremental sync: fetching notes updated since {last_sync}")
        sql = f"SELECT alias FROM \\\"Notes\\\" WHERE \\\"createdAt\\\" != \\\"lastchangeAt\\\" AND length(alias) > 0 AND \\\"updatedAt\\\" >= '{last_sync}'"
    else:
        logger.info("Full sync: fetching all modified notes")
        sql = "SELECT alias FROM \\\"Notes\\\" WHERE \\\"createdAt\\\" != \\\"lastchangeAt\\\" AND length(alias) > 0"
        
    cmd = ["ssh", SSH_TARGET, f'LC_ALL=C psql -t -A -c "{sql}"']
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        aliases = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        logger.info(f"Found {len(aliases)} modified aliases.")
        return aliases
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to fetch aliases: {e.stderr}")
        return []

def is_spam(alias: str, content: str) -> Tuple[bool, str]:
    """Applies heuristics to identify spam notes."""
    # Check alias for obvious spam patterns
    if re.search(r'(casino|bet|club|88).*\.(com|vip|io|org|net|ink)', alias, re.I):
        return True, "alias_pattern"
    
    # Check content
    links = re.findall(r'https?://', content)
    has_vn = VN_CHARS.search(content) is not None
    
    score = 0
    if len(links) > 50: score += 2
    if len(links) > 200: score += 3
    if has_vn: score += 2
    if any(k in content.lower() for k in SPAM_KEYWORDS): score += 3

    if score >= 4:
        return True, f"content_score:{score}"
    
    return False, "safe"

def export_note(alias: str):
    """Downloads the note content and saves it if it's not spam."""
    # Ensure export dir exists
    os.makedirs(EXPORT_DIR, exist_ok=True)
    file_path = os.path.join(EXPORT_DIR, f"{alias}.md")
    
    # We download via HTTP download link (usually public in HedgeDoc)
    # Alternatively, we could use the hedgedoc CLI on patera, but HTTP is simpler from here.
    download_url = f"{HEDGEDOC_URL}/{alias}/download"
    
    try:
        response = requests.get(download_url, timeout=10)
        if response.status_code != 200:
            logger.warning(f"Failed to download {alias} (Status: {response.status_code})")
            return

        content = response.text
        spam_detected, reason = is_spam(alias, content)
        
        if spam_detected:
            logger.info(f"Skipping spam note: [[{alias}]] Reason: {reason}")
            if os.path.exists(file_path):
                os.remove(file_path)
            return

        # Valid note, save it
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)
        # logger.debug(f"Exported [[{alias}]]")

    except Exception as e:
        logger.error(f"Error exporting [[{alias}]]: {e}")

def git_sync():
    """Commits and pushes changes to the repository."""
    logger.info("Syncing with Git...")
    cwd = os.getcwd()
    try:
        os.chdir(EXPORT_DIR)
        # Check if it's a git repo
        if not os.path.exists(".git"):
            subprocess.run(["git", "init"], check=True)
            subprocess.run(["git", "remote", "add", "origin", GIT_REPO_URL], check=True)

        subprocess.run(["git", "add", "."], check=True)
        # Check if there are changes to commit
        status = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True)
        if status.stdout:
            subprocess.run(["git", "commit", "-m", "stoa update (automated)"], check=True)
            subprocess.run(["git", "push", "origin", "main"], check=True)
            logger.info("Git sync complete.")
        else:
            logger.info("No changes to sync.")
    except Exception as e:
        logger.error(f"Git sync failed: {e}")
    finally:
        os.chdir(cwd)

def main():
    aliases = get_note_aliases()
    if not aliases:
        return

    logger.info(f"Starting export of {len(aliases)} notes to {EXPORT_DIR}...")
    for i, alias in enumerate(aliases):
        if i % 50 == 0:
            logger.info(f"Progress: {i}/{len(aliases)}")
        export_note(alias)
    
    update_last_sync()
    git_sync()

if __name__ == "__main__":
    main()
