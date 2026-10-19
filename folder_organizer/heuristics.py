from typing import Optional, Dict
from folder_organizer.models import FileItem, ClassificationResult, ClassificationSource

class HeuristicEngine:
    """Fast deterministic rule engine that maps known file extensions to base categories."""

    EXTENSION_MAP: Dict[str, str] = {
        # Installers / Packages
        ".exe": "Installers",
        ".msi": "Installers",
        ".dmg": "Installers",
        ".pkg": "Installers",
        ".deb": "Installers",
        ".rpm": "Installers",
        ".appimage": "Installers",
        # Archives
        ".zip": "Archives",
        ".tar": "Archives",
        ".gz": "Archives",
        ".tar.gz": "Archives",
        ".tgz": "Archives",
        ".7z": "Archives",
        ".rar": "Archives",
        ".bz2": "Archives",
        ".xz": "Archives",
        # Disk Images
        ".iso": "Disk Images",
        ".img": "Disk Images",
        ".vhd": "Disk Images",
        # Fonts
        ".ttf": "Fonts",
        ".otf": "Fonts",
        ".woff": "Fonts",
        ".woff2": "Fonts",
    }

    def classify(self, item: FileItem) -> Optional[ClassificationResult]:
        ext = item.extension.lower()
        if ext in self.EXTENSION_MAP:
            category = self.EXTENSION_MAP[ext]
            return ClassificationResult(
                category=category,
                subfolder=None,
                confidence=1.0,
                source=ClassificationSource.HEURISTIC,
                reason=f"Matched deterministic extension rule for '{ext}'"
            )
        return None
