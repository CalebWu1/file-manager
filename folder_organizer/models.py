from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional
from pydantic import BaseModel, Field

COMPOUND_EXTENSIONS = (".tar.gz", ".tar.bz2", ".tar.xz")


class ClassificationSource(str, Enum):
    HEURISTIC = "heuristic"
    LLM = "llama3.2"
    MANUAL = "manual"


class CollisionAction(str, Enum):
    AUTO_RENAME = "auto_rename"
    SKIP = "skip"
    OVERWRITE = "overwrite"


class ActionType(str, Enum):
    FIND = "FIND"
    MOVE = "MOVE"
    TRASH = "TRASH"


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


class QueryPredicates(BaseModel):
    extensions: list[str] = Field(default_factory=list)
    name_patterns: list[str] = Field(default_factory=list)
    min_size_bytes: Optional[int] = None
    max_size_bytes: Optional[int] = None
    modified_after: Optional[datetime] = None
    modified_before: Optional[datetime] = None
    needs_semantic_check: bool = False
    semantic_prompt: Optional[str] = None


class QueryIntent(BaseModel):
    raw_query: str
    action: ActionType
    destination_folder: Optional[str] = None
    predicates: QueryPredicates = Field(default_factory=QueryPredicates)
    reasoning: str = ""


class ActionOperation(BaseModel):
    source_path: Path
    action: ActionType
    target_path: Optional[Path] = None
    intended_path: Optional[Path] = None
    collision_action: CollisionAction = CollisionAction.AUTO_RENAME
    collision_detected: bool = False
    selected: bool = True
    match_reason: str = ""


class JournalEntry(BaseModel):
    action: ActionType = ActionType.MOVE
    source: Path
    destination: Optional[Path] = None
    timestamp: datetime = Field(default_factory=datetime.now)


class HistorySession(BaseModel):
    session_id: str
    timestamp: datetime
    target_dir: Path
    query_prompt: Optional[str] = None
    operations: list[JournalEntry]

