import json
import logging
import re
from typing import Any

import ollama

from file_organizer.models import ActionType, QueryIntent, QueryPredicates

logger = logging.getLogger(__name__)


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
        destination_folder: str | None = None

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
        min_size: int | None = None
        max_size: int | None = None

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


class QueryCompiler:
    """Compiles natural language queries using local Ollama (Llama 3.2) with heuristic fallback."""

    SYSTEM_PROMPT = """You are a file query interpreter for a desktop folder organizer.
Analyze the user's natural language request and extract:
1. "action": "FIND" (just searching/listing), "MOVE" (moving files), or "TRASH" (deleting/recycling files).
2. "destination_folder": string or null (e.g. "Installers", "Receipts", if action is MOVE).
3. "predicates":
   - "extensions": array of lowercase extensions starting with a dot (e.g. [".exe", ".msi"]). Expand terms like "installers" to [".exe", ".msi", ".dmg", ".pkg", ".appinstaller", ".deb", ".rpm"].
   - "name_patterns": array of filename substrings (e.g. ["setup", "install"]).
   - "min_size_bytes": integer or null.
   - "max_size_bytes": integer or null.
   - "needs_semantic_check": boolean (true if query requires verifying content peek text, e.g. "Amazon receipts" or "tax documents").
   - "semantic_prompt": string or null (the verification question if needs_semantic_check is true).
4. "reasoning": brief explanation.

Respond ONLY with valid JSON conforming to this schema. No markdown formatting."""

    def __init__(
        self,
        model: str = "llama3.2",
        host: str = "http://localhost:11434",
        client: Any | None = None,
    ):
        self.model = model
        self.host = host
        self._client = client or ollama.Client(host=host)
        self._fallback = KeywordFallbackCompiler()

    def compile(self, prompt: str) -> QueryIntent:
        try:
            response = self._client.chat(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                format="json",
                options={"temperature": 0.0},
            )
            content = response.get("message", {}).get("content", "{}")
            data = json.loads(content)

            action = ActionType(data.get("action", "FIND").upper())
            dest = data.get("destination_folder")
            pred_data = data.get("predicates") or {}

            predicates = QueryPredicates(
                extensions=[
                    e if e.startswith(".") else f".{e}" for e in pred_data.get("extensions", [])
                ],
                name_patterns=pred_data.get("name_patterns", []),
                min_size_bytes=pred_data.get("min_size_bytes"),
                max_size_bytes=pred_data.get("max_size_bytes"),
                needs_semantic_check=bool(pred_data.get("needs_semantic_check", False)),
                semantic_prompt=pred_data.get("semantic_prompt"),
            )

            return QueryIntent(
                raw_query=prompt,
                action=action,
                destination_folder=dest,
                predicates=predicates,
                reasoning=data.get("reasoning", "Parsed by Llama 3.2"),
            )
        except Exception as exc:
            logger.warning(
                f"Ollama query compilation failed ({exc}); falling back to keyword heuristics"
            )
            return self._fallback.compile(prompt)
