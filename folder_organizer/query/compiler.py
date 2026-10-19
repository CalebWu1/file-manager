import re
from typing import Optional

from folder_organizer.models import ActionType, QueryIntent, QueryPredicates


class KeywordFallbackCompiler:
    """Deterministic regex & keyword compiler for offline/fallback queries."""

    KEYWORD_EXTENSIONS = {
        "installer": [".exe", ".msi", ".dmg", ".pkg", ".appinstaller", ".deb", ".rpm"],
        "setup": [".exe", ".msi", ".dmg", ".pkg", ".appinstaller", ".deb", ".rpm"],
        "archive": [".zip", ".tar.gz", ".tar.bz2", ".tar.xz", ".7z", ".rar"],
        "zip": [".zip", ".tar.gz", ".tar.bz2", ".tar.xz", ".7z", ".rar"],
        "video": [".mp4", ".mkv", ".mov", ".avi", ".webm"],
        "movie": [".mp4", ".mkv", ".mov", ".avi", ".webm"],
        "audio": [".mp3", ".wav", ".flac", ".m4a", ".aac"],
        "music": [".mp3", ".wav", ".flac", ".m4a", ".aac"],
        "song": [".mp3", ".wav", ".flac", ".m4a", ".aac"],
        "image": [".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"],
        "photo": [".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"],
        "picture": [".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"],
        "document": [".pdf", ".docx", ".doc", ".txt", ".xlsx", ".csv", ".pptx"],
        "pdf": [".pdf"],
        "code": [".py", ".js", ".ts", ".html", ".css", ".json", ".rs", ".go"],
    }

    SIZE_MULTIPLIERS = {
        "b": 1,
        "kb": 1024,
        "mb": 1024 * 1024,
        "gb": 1024 * 1024 * 1024,
    }

    def compile(self, prompt: str) -> QueryIntent:
        cleaned = prompt.strip()
        lower = cleaned.lower()

        # 1. Parse Action & Destination
        action = ActionType.FIND
        destination_folder: Optional[str] = None

        if re.search(r"\b(delete|trash|remove|clean\s*up)\b", lower):
            action = ActionType.TRASH
        else:
            move_match = re.search(
                r"\b(?:move|put|store|organize)\s+(?:all\s+)?(.*?)\s+(?:in|to|into)\s+([a-zA-Z0-9_\- ]+)",
                lower,
            )
            if move_match:
                action = ActionType.MOVE
                destination_folder = move_match.group(2).strip().title()

        # 2. Parse Extensions from keywords
        extensions: list[str] = []
        name_patterns: list[str] = []
        for kw, exts in self.KEYWORD_EXTENSIONS.items():
            if re.search(rf"\b{kw}s?\b", lower):
                for e in exts:
                    if e not in extensions:
                        extensions.append(e)

        if "setup" in lower:
            name_patterns.append("setup")

        # 3. Parse Size Thresholds
        min_size: Optional[int] = None
        max_size: Optional[int] = None

        min_match = re.search(r"(?:over|larger\s+than|>)\s*(\d+(?:\.\d+)?)\s*(kb|mb|gb|b)", lower)
        if min_match:
            val, unit = float(min_match.group(1)), min_match.group(2).lower()
            min_size = int(val * self.SIZE_MULTIPLIERS[unit])

        max_match = re.search(r"(?:under|smaller\s+than|<)\s*(\d+(?:\.\d+)?)\s*(kb|mb|gb|b)", lower)
        if max_match:
            val, unit = float(max_match.group(1)), max_match.group(2).lower()
            max_size = int(val * self.SIZE_MULTIPLIERS[unit])

        predicates = QueryPredicates(
            extensions=extensions,
            name_patterns=name_patterns,
            min_size_bytes=min_size,
            max_size_bytes=max_size,
        )

        return QueryIntent(
            raw_query=cleaned,
            action=action,
            destination_folder=destination_folder,
            predicates=predicates,
            reasoning=f"Heuristic parse: action={action.value}, extensions={len(extensions)} matched",
        )
