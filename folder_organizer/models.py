from enum import Enum
from pathlib import Path
from typing import List, Optional, Dict
from pydantic import BaseModel, Field


class ClassificationSource(str, Enum):
    HEURISTIC = "heuristic"
    LLM = "llama3.2"
    MANUAL = "manual"


class CollisionAction(str, Enum):
    AUTO_RENAME = "auto_rename"
    SKIP = "skip"
    OVERWRITE = "overwrite"


class FileItem(BaseModel):
    path: Path
    filename: str
    extension: str
    size_bytes: int
    modified_time: float
    content_peek: Optional[str] = None
    is_active_download: bool = False


class ClassificationResult(BaseModel):
    category: str
    subfolder: Optional[str] = None
    confidence: float = 1.0
    source: ClassificationSource
    reason: str


class MoveOperation(BaseModel):
    source_path: Path
    target_category: str
    target_subfolder: Optional[str] = None
    target_path: Path
    intended_path: Optional[Path] = None
    source: ClassificationSource
    reason: str
    collision_detected: bool = False
    collision_action: CollisionAction = CollisionAction.AUTO_RENAME
    is_selected: bool = True


class SessionJournal(BaseModel):
    session_id: str
    timestamp: str
    target_dir: str
    operations: List[Dict[str, str]] = Field(default_factory=list)
