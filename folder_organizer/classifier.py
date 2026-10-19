import json
from typing import List, Dict, Optional
import ollama
from folder_organizer.models import FileItem, ClassificationResult, ClassificationSource


class LLMClassifier:
    """Interacts with local Ollama Llama 3.2 to classify files using structured JSON outputs."""

    def __init__(self, host: str = "http://localhost:11434", model: str = "llama3.2"):
        self.host = host
        self.model = model
        self.client = ollama.Client(host=host)

    def is_available(self) -> bool:
        """Checks if local Ollama daemon is running."""
        try:
            self.client.list()
            return True
        except Exception:
            return False

    def classify_batch(self, items: List[FileItem]) -> Dict[str, ClassificationResult]:
        if not items:
            return {}

        file_summaries = []
        for item in items:
            summary = {
                "filename": item.filename,
                "extension": item.extension,
                "size_bytes": item.size_bytes,
                "peek": item.content_peek[:400] if item.content_peek else "",
            }
            file_summaries.append(summary)

        prompt = (
            "You are a file organization assistant. Categorize these files into clean folders.\n"
            "Choose a top-level category (e.g. Documents, Code, Media, Installers, Archives, Books) "
            "and an optional concise subfolder name (e.g. Invoices, Taxes, Python, Screenshots).\n"
            f"Files to classify: {json.dumps(file_summaries)}\n\n"
            "Return JSON matching this schema: "
            '{"classifications": [{"filename": "...", "category": "...", "subfolder": "...", "reason": "..."}]}'
        )

        try:
            response = self.client.chat(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                format="json",
            )
            raw_content = response.get("message", {}).get("content", "{}")
            data = json.loads(raw_content)

            results: Dict[str, ClassificationResult] = {}
            for entry in data.get("classifications", []):
                fname = entry.get("filename")
                if fname:
                    cat_raw = entry.get("category")
                    category = (cat_raw or "Documents").strip().title()
                    sub_raw = entry.get("subfolder")
                    subfolder = (sub_raw or "").strip() or None
                    reason_raw = entry.get("reason")
                    reason = (reason_raw or "Classified by Llama 3.2").strip()

                    results[fname] = ClassificationResult(
                        category=category,
                        subfolder=subfolder,
                        confidence=0.9,
                        source=ClassificationSource.LLM,
                        reason=reason,
                    )

            # Ensure all items received a result
            for item in items:
                if item.filename not in results:
                    results[item.filename] = self._fallback_classify(item)
            return results

        except Exception as e:
            # Fallback for all items if Ollama call fails
            return {item.filename: self._fallback_classify(item, error=str(e)) for item in items}

    def _fallback_classify(self, item: FileItem, error: Optional[str] = None) -> ClassificationResult:
        ext = item.extension.lower()
        if ext in {".pdf", ".docx", ".doc", ".txt", ".rtf", ".odt"}:
            category = "Documents"
        elif ext in {".py", ".js", ".ts", ".html", ".css", ".cpp", ".c", ".rs", ".go"}:
            category = "Code"
        elif ext in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".mp4", ".mp3", ".wav"}:
            category = "Media"
        else:
            category = "Other"

        reason = f"Heuristic fallback: {error}" if error else "Default extension grouping"
        return ClassificationResult(
            category=category,
            subfolder=None,
            confidence=0.5,
            source=ClassificationSource.HEURISTIC,
            reason=reason,
        )
