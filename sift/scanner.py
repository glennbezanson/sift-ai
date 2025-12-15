"""
File scanner module for Sift.
Walks directory trees and collects file metadata.
"""

import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Generator, Optional

from .config import SiftConfig


@dataclass
class FileInfo:
    """Information about a single file."""

    path: Path
    filename: str
    extension: str
    size_bytes: int
    modified_time: datetime
    created_time: datetime
    parent_folder: str
    relative_path: str  # Relative to source root

    # Processing state
    category: Optional[str] = None
    confidence: Optional[int] = None
    entity_detected: Optional[str] = None
    action: Optional[str] = None
    reasoning: Optional[str] = None
    processed: bool = False

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "path": str(self.path),
            "filename": self.filename,
            "extension": self.extension,
            "size_bytes": self.size_bytes,
            "modified_time": self.modified_time.isoformat(),
            "created_time": self.created_time.isoformat(),
            "parent_folder": self.parent_folder,
            "relative_path": self.relative_path,
            "category": self.category,
            "confidence": self.confidence,
            "entity_detected": self.entity_detected,
            "action": self.action,
            "reasoning": self.reasoning,
            "processed": self.processed,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "FileInfo":
        """Create from dictionary."""
        data["path"] = Path(data["path"])
        data["modified_time"] = datetime.fromisoformat(data["modified_time"])
        data["created_time"] = datetime.fromisoformat(data["created_time"])
        return cls(**data)


@dataclass
class ScanResult:
    """Results from scanning source directories."""

    files: list[FileInfo] = field(default_factory=list)
    total_count: int = 0
    total_size_bytes: int = 0
    extension_counts: dict[str, int] = field(default_factory=dict)
    folder_counts: dict[str, int] = field(default_factory=dict)
    date_range: tuple[Optional[datetime], Optional[datetime]] = (None, None)
    skipped_count: int = 0
    error_count: int = 0
    errors: list[str] = field(default_factory=list)


class FileScanner:
    """Scans directories and collects file information."""

    def __init__(self, config: SiftConfig):
        self.config = config
        self.skip_folders_lower = {f.lower() for f in config.skip_folders}
        self.skip_extensions_lower = {e.lower() for e in config.skip_extensions}
        self.process_extensions_lower = {e.lower() for e in config.process_extensions}

    def should_skip_folder(self, folder_name: str) -> bool:
        """Check if folder should be skipped."""
        return folder_name.lower() in self.skip_folders_lower

    def should_process_file(self, file_path: Path) -> bool:
        """Check if file should be processed based on extension."""
        ext = file_path.suffix.lower()

        # Skip if in skip list
        if ext in self.skip_extensions_lower:
            return False

        # Process if in allowed list (or if list is empty, process all)
        if self.process_extensions_lower:
            return ext in self.process_extensions_lower

        return True

    def get_file_info(self, file_path: Path, source_root: Path) -> Optional[FileInfo]:
        """Get file information, return None if file should be skipped."""
        try:
            if not self.should_process_file(file_path):
                return None

            stat = file_path.stat()

            return FileInfo(
                path=file_path,
                filename=file_path.name,
                extension=file_path.suffix.lower(),
                size_bytes=stat.st_size,
                modified_time=datetime.fromtimestamp(stat.st_mtime),
                created_time=datetime.fromtimestamp(stat.st_ctime),
                parent_folder=file_path.parent.name,
                relative_path=str(file_path.relative_to(source_root)),
            )
        except (OSError, PermissionError) as e:
            return None

    def scan_directory(
        self, source_path: Path, limit: Optional[int] = None
    ) -> Generator[FileInfo, None, None]:
        """Generator that yields FileInfo for each processable file."""
        count = 0

        for root, dirs, files in os.walk(source_path):
            # Filter out skip folders (modifying dirs in-place affects walk)
            dirs[:] = [d for d in dirs if not self.should_skip_folder(d)]

            for filename in files:
                if limit and count >= limit:
                    return

                file_path = Path(root) / filename
                file_info = self.get_file_info(file_path, source_path)

                if file_info:
                    count += 1
                    yield file_info

    def scan_all(self, limit: Optional[int] = None) -> ScanResult:
        """Scan all configured source paths and return results."""
        result = ScanResult()
        earliest_date: Optional[datetime] = None
        latest_date: Optional[datetime] = None
        files_found = 0

        for source_path_str in self.config.source_paths:
            source_path = Path(source_path_str)

            if not source_path.exists():
                result.errors.append(f"Source path does not exist: {source_path}")
                result.error_count += 1
                continue

            if not source_path.is_dir():
                result.errors.append(f"Source path is not a directory: {source_path}")
                result.error_count += 1
                continue

            remaining_limit = limit - files_found if limit else None

            for file_info in self.scan_directory(source_path, remaining_limit):
                result.files.append(file_info)
                result.total_count += 1
                result.total_size_bytes += file_info.size_bytes
                files_found += 1

                # Track extension counts
                ext = file_info.extension
                result.extension_counts[ext] = result.extension_counts.get(ext, 0) + 1

                # Track top-level folder counts
                folder = file_info.relative_path.split(os.sep)[0]
                result.folder_counts[folder] = result.folder_counts.get(folder, 0) + 1

                # Track date range
                if earliest_date is None or file_info.modified_time < earliest_date:
                    earliest_date = file_info.modified_time
                if latest_date is None or file_info.modified_time > latest_date:
                    latest_date = file_info.modified_time

                if limit and files_found >= limit:
                    break

            if limit and files_found >= limit:
                break

        result.date_range = (earliest_date, latest_date)
        return result

    def format_size(self, size_bytes: int) -> str:
        """Format byte size as human-readable string."""
        for unit in ["B", "KB", "MB", "GB", "TB"]:
            if size_bytes < 1024:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024
        return f"{size_bytes:.1f} PB"

    def get_scan_summary(self, result: ScanResult) -> str:
        """Generate a summary of scan results."""
        lines = [
            "# Scan Summary",
            "",
            f"**Total Files:** {result.total_count:,}",
            f"**Total Size:** {self.format_size(result.total_size_bytes)}",
            "",
        ]

        if result.date_range[0] and result.date_range[1]:
            lines.extend([
                f"**Date Range:** {result.date_range[0].strftime('%Y-%m-%d')} to {result.date_range[1].strftime('%Y-%m-%d')}",
                "",
            ])

        # Extension breakdown
        lines.append("## File Types")
        sorted_exts = sorted(result.extension_counts.items(), key=lambda x: -x[1])
        for ext, count in sorted_exts[:15]:
            lines.append(f"- {ext}: {count:,} files")
        if len(sorted_exts) > 15:
            lines.append(f"- ... and {len(sorted_exts) - 15} more types")

        lines.append("")

        # Folder breakdown
        lines.append("## Top Folders")
        sorted_folders = sorted(result.folder_counts.items(), key=lambda x: -x[1])
        for folder, count in sorted_folders[:15]:
            lines.append(f"- {folder}: {count:,} files")
        if len(sorted_folders) > 15:
            lines.append(f"- ... and {len(sorted_folders) - 15} more folders")

        if result.errors:
            lines.extend(["", "## Errors"])
            for error in result.errors:
                lines.append(f"- {error}")

        return "\n".join(lines)
