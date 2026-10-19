from pathlib import Path
from typing import Optional

def extract_content_peek(path: Path, max_bytes: int = 2048) -> Optional[str]:
    """Safely extracts a short plain-text snippet from text or PDF files."""
    ext = path.suffix.lower()

    # Plain text, code, markdown, csv, json
    text_extensions = {
        ".txt", ".md", ".csv", ".json", ".py", ".sh", ".html", ".css",
        ".yaml", ".yml", ".xml", ".ini", ".conf", ".sql", ".log"
    }

    if ext in text_extensions:
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                return f.read(max_bytes).strip()
        except Exception:
            return None

    # PDF shallow peek using pypdf
    if ext == ".pdf":
        try:
            import pypdf
            reader = pypdf.PdfReader(str(path))
            if reader.pages:
                text = reader.pages[0].extract_text() or ""
                return text[:max_bytes].strip()
        except Exception:
            return None

    return None
