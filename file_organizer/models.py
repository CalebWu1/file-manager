from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

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
    content_peek: str | None = None
    is_active_download: bool = False


class ScannedItem(FileItem):
    modified_time: float = 0.0
    modified_at: datetime | None = None


class ClassificationResult(BaseModel):
    category: str
    subfolder: str | None = None
    confidence: float = 1.0
    source: ClassificationSource
    reason: str


class MoveOperation(BaseModel):
    source_path: Path
    target_category: str = "General"
    target_subfolder: str | None = None
    target_path: Path | None = None
    intended_path: Path | None = None
    source: ClassificationSource = ClassificationSource.HEURISTIC
    reason: str = ""
    match_reason: str = ""
    collision_detected: bool = False
    collision_action: CollisionAction = CollisionAction.AUTO_RENAME
    is_selected: bool = True
    action: ActionType = ActionType.MOVE

    def model_post_init(self, __context: Any) -> None:
        if self.match_reason and not self.reason:
            self.reason = self.match_reason
        elif self.reason and not self.match_reason:
            self.match_reason = self.reason


class SessionJournal(BaseModel):
    session_id: str
    timestamp: str
    target_dir: str
    operations: list[dict[str, str]] = Field(default_factory=list)


class QueryPredicates(BaseModel):
    extensions: list[str] = Field(default_factory=list)
    name_patterns: list[str] = Field(default_factory=list)
    min_size_bytes: int | None = None
    max_size_bytes: int | None = None
    modified_after: datetime | None = None
    modified_before: datetime | None = None
    needs_semantic_check: bool = False
    semantic_prompt: str | None = None


class QueryIntent(BaseModel):
    raw_query: str
    action: ActionType
    destination_folder: str | None = None
    predicates: QueryPredicates = Field(default_factory=QueryPredicates)
    reasoning: str = ""


class ActionOperation(BaseModel):
    source_path: Path
    action: ActionType
    target_path: Path | None = None
    intended_path: Path | None = None
    collision_action: CollisionAction = CollisionAction.AUTO_RENAME
    collision_detected: bool = False
    selected: bool = True
    match_reason: str = ""


class JournalEntry(BaseModel):
    action: ActionType = ActionType.MOVE
    source: Path
    destination: Path | None = None
    timestamp: datetime = Field(default_factory=datetime.now)


class HistorySession(BaseModel):
    session_id: str
    timestamp: datetime
    target_dir: Path
    query_prompt: str | None = None
    operations: list[JournalEntry]
