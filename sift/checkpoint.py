"""
Checkpoint and resume system for Sift.
Saves progress to allow resuming after interruption.
"""

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from .scanner import FileInfo


@dataclass
class Checkpoint:
    """Current processing state."""

    last_run: datetime = field(default_factory=datetime.now)
    phase: str = "init"  # init, structure, wave_processing, dedup, cleanup, complete
    current_wave: int = 1
    files_processed: int = 0
    files_total: int = 0
    last_file_processed: Optional[str] = None
    structure_approved: bool = False
    backup_confirmed: bool = False

    # Archive structure
    archive_structure: list[str] = field(default_factory=list)

    # Processed files state
    processed_files: dict[str, dict] = field(default_factory=dict)  # path -> categorization

    # Unknown files pending review
    unknowns_wave: dict[int, list[str]] = field(default_factory=dict)  # wave -> list of paths

    # Deduplication state
    files_to_delete: list[str] = field(default_factory=list)
    files_deleted: list[str] = field(default_factory=list)

    # Moves completed
    files_moved: list[dict] = field(default_factory=list)  # [{from, to}]

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "last_run": self.last_run.isoformat(),
            "phase": self.phase,
            "current_wave": self.current_wave,
            "files_processed": self.files_processed,
            "files_total": self.files_total,
            "last_file_processed": self.last_file_processed,
            "structure_approved": self.structure_approved,
            "backup_confirmed": self.backup_confirmed,
            "archive_structure": self.archive_structure,
            "processed_files": self.processed_files,
            "unknowns_wave": {str(k): v for k, v in self.unknowns_wave.items()},
            "files_to_delete": self.files_to_delete,
            "files_deleted": self.files_deleted,
            "files_moved": self.files_moved,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Checkpoint":
        """Create from dictionary."""
        checkpoint = cls()
        checkpoint.last_run = datetime.fromisoformat(data.get("last_run", datetime.now().isoformat()))
        checkpoint.phase = data.get("phase", "init")
        checkpoint.current_wave = data.get("current_wave", 1)
        checkpoint.files_processed = data.get("files_processed", 0)
        checkpoint.files_total = data.get("files_total", 0)
        checkpoint.last_file_processed = data.get("last_file_processed")
        checkpoint.structure_approved = data.get("structure_approved", False)
        checkpoint.backup_confirmed = data.get("backup_confirmed", False)
        checkpoint.archive_structure = data.get("archive_structure", [])
        checkpoint.processed_files = data.get("processed_files", {})
        checkpoint.unknowns_wave = {int(k): v for k, v in data.get("unknowns_wave", {}).items()}
        checkpoint.files_to_delete = data.get("files_to_delete", [])
        checkpoint.files_deleted = data.get("files_deleted", [])
        checkpoint.files_moved = data.get("files_moved", [])
        return checkpoint


class CheckpointManager:
    """Manages checkpoint save/load operations."""

    def __init__(self, logs_dir: Path):
        self.checkpoint_path = logs_dir / "checkpoint.json"
        self.logs_dir = logs_dir

    def exists(self) -> bool:
        """Check if a checkpoint file exists."""
        return self.checkpoint_path.exists()

    def load(self) -> Checkpoint:
        """Load checkpoint from file, or return new checkpoint if none exists."""
        if not self.checkpoint_path.exists():
            return Checkpoint()

        try:
            with open(self.checkpoint_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return Checkpoint.from_dict(data)
        except (json.JSONDecodeError, KeyError) as e:
            # Corrupted checkpoint, start fresh
            return Checkpoint()

    def save(self, checkpoint: Checkpoint):
        """Save checkpoint to file."""
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        checkpoint.last_run = datetime.now()

        with open(self.checkpoint_path, "w", encoding="utf-8") as f:
            json.dump(checkpoint.to_dict(), f, indent=2)

    def clear(self):
        """Remove checkpoint file."""
        if self.checkpoint_path.exists():
            self.checkpoint_path.unlink()

    def mark_file_processed(
        self,
        checkpoint: Checkpoint,
        file_info: FileInfo,
        category: str,
        confidence: int,
        action: str,
    ):
        """Mark a file as processed and save checkpoint."""
        checkpoint.processed_files[str(file_info.path)] = {
            "category": category,
            "confidence": confidence,
            "action": action,
            "processed_at": datetime.now().isoformat(),
        }
        checkpoint.files_processed += 1
        checkpoint.last_file_processed = str(file_info.path)
        self.save(checkpoint)

    def add_unknown(self, checkpoint: Checkpoint, wave: int, file_path: str):
        """Add a file to unknowns for a specific wave."""
        if wave not in checkpoint.unknowns_wave:
            checkpoint.unknowns_wave[wave] = []
        checkpoint.unknowns_wave[wave].append(file_path)
        self.save(checkpoint)

    def mark_file_moved(
        self, checkpoint: Checkpoint, from_path: str, to_path: str
    ):
        """Record a file move operation."""
        checkpoint.files_moved.append({
            "from": from_path,
            "to": to_path,
            "moved_at": datetime.now().isoformat(),
        })
        self.save(checkpoint)

    def mark_file_deleted(self, checkpoint: Checkpoint, file_path: str):
        """Record a file deletion."""
        checkpoint.files_deleted.append(file_path)
        self.save(checkpoint)

    def is_file_processed(self, checkpoint: Checkpoint, file_path: str) -> bool:
        """Check if a file has already been processed."""
        return str(file_path) in checkpoint.processed_files

    def get_files_pending(
        self, checkpoint: Checkpoint, all_files: list[FileInfo]
    ) -> list[FileInfo]:
        """Get list of files not yet processed."""
        processed_paths = set(checkpoint.processed_files.keys())
        return [f for f in all_files if str(f.path) not in processed_paths]


class Logger:
    """Simple logging to file and console."""

    def __init__(self, logs_dir: Path):
        self.logs_dir = logs_dir
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        self.log_file = logs_dir / f"run-{timestamp}.log"
        self.logs_dir.mkdir(parents=True, exist_ok=True)

    def log(self, message: str, level: str = "INFO"):
        """Log a message to file and optionally print."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_line = f"[{timestamp}] [{level}] {message}"

        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(log_line + "\n")

    def info(self, message: str):
        """Log info message."""
        self.log(message, "INFO")

    def warning(self, message: str):
        """Log warning message."""
        self.log(message, "WARN")

    def error(self, message: str):
        """Log error message."""
        self.log(message, "ERROR")

    def action(self, action: str, source: str, dest: Optional[str] = None):
        """Log a file action."""
        if dest:
            self.log(f"{action}: {source} -> {dest}", "ACTION")
        else:
            self.log(f"{action}: {source}", "ACTION")
