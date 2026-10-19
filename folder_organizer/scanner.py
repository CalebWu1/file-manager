from pathlib import Path
from typing import List, Set
from folder_organizer.models import FileItem, COMPOUND_EXTENSIONS
from folder_organizer.utils.file_peek import extract_content_peek

class Scanner:
    """Scans target directory for unorganized files while filtering incomplete/system files."""

    IGNORED_EXTENSIONS: Set[str] = {
        ".crdownload", ".part", ".download", ".tmp"
    }

    IGNORED_NAMES: Set[str] = {
        "desktop.ini", "thumbs.db", ".ds_store"
    }

    def scan_directory(self, target_dir: Path) -> List[FileItem]:
        if not target_dir.exists() or not target_dir.is_dir():
            raise ValueError(f"Target directory does not exist or is not a directory: {target_dir}")

        items: List[FileItem] = []
        for entry in target_dir.iterdir():
            # Skip subdirectories
            if not entry.is_file():
                continue

            name = entry.name
            lower_name = name.lower()

            # Skip hidden files
            if name.startswith("."):
                continue

            # Skip system files
            if lower_name in self.IGNORED_NAMES:
                continue

            # Detect compound extension like .tar.gz if present
            comp_ext = next((c for c in COMPOUND_EXTENSIONS if lower_name.endswith(c)), None)
            ext = comp_ext if comp_ext else entry.suffix.lower()

            # Skip active downloads
            if ext in self.IGNORED_EXTENSIONS or any(lower_name.endswith(e) for e in self.IGNORED_EXTENSIONS):
                continue

            try:
                stat = entry.stat()
                size_bytes = stat.st_size
                mtime = stat.st_mtime
            except OSError:
                continue

            content_peek = extract_content_peek(entry)

            items.append(FileItem(
                path=entry,
                filename=name,
                extension=ext,
                size_bytes=size_bytes,
                modified_time=mtime,
                content_peek=content_peek
            ))

        return items
