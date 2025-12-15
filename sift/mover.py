"""
File operations module for Sift.
Handles moving, deleting, and organizing files.
"""

import os
import shutil
from pathlib import Path
from typing import Optional

from .checkpoint import Checkpoint, CheckpointManager, Logger
from .config import SiftConfig
from .scanner import FileInfo


class FileMover:
    """Handles file move and delete operations."""

    def __init__(
        self,
        config: SiftConfig,
        checkpoint_manager: CheckpointManager,
        logger: Logger,
    ):
        self.config = config
        self.checkpoint_manager = checkpoint_manager
        self.logger = logger
        self.archive_root = Path(config.archive_destination)

    def ensure_category_folder(self, category: str) -> Path:
        """Ensure the category folder exists and return its path."""
        # Handle nested categories like "Customers/Acme Corp"
        category_path = self.archive_root / category
        category_path.mkdir(parents=True, exist_ok=True)
        return category_path

    def move_file(
        self,
        file_info: FileInfo,
        category: str,
        checkpoint: Checkpoint,
        dry_run: bool = False,
    ) -> Optional[Path]:
        """
        Move a file to its category folder in the archive.
        Returns the new path, or None if move failed.
        """
        try:
            dest_folder = self.ensure_category_folder(category)
            dest_path = dest_folder / file_info.filename

            # Handle filename conflicts
            if dest_path.exists():
                dest_path = self._get_unique_path(dest_path)

            if dry_run:
                self.logger.action("WOULD MOVE", str(file_info.path), str(dest_path))
                return dest_path

            # Perform the move
            shutil.move(str(file_info.path), str(dest_path))

            self.logger.action("MOVED", str(file_info.path), str(dest_path))
            self.checkpoint_manager.mark_file_moved(
                checkpoint, str(file_info.path), str(dest_path)
            )

            return dest_path

        except (OSError, shutil.Error) as e:
            self.logger.error(f"Failed to move {file_info.path}: {e}")
            return None

    def delete_file(
        self,
        file_info: FileInfo,
        checkpoint: Checkpoint,
        dry_run: bool = False,
    ) -> bool:
        """
        Delete a file (duplicate).
        Returns True if successful.
        """
        try:
            if dry_run:
                self.logger.action("WOULD DELETE", str(file_info.path))
                return True

            file_info.path.unlink()

            self.logger.action("DELETED", str(file_info.path))
            self.checkpoint_manager.mark_file_deleted(checkpoint, str(file_info.path))

            return True

        except (OSError, PermissionError) as e:
            self.logger.error(f"Failed to delete {file_info.path}: {e}")
            return False

    def _get_unique_path(self, path: Path) -> Path:
        """Generate a unique path by adding a number suffix."""
        stem = path.stem
        suffix = path.suffix
        parent = path.parent

        counter = 1
        while True:
            new_name = f"{stem}_{counter}{suffix}"
            new_path = parent / new_name
            if not new_path.exists():
                return new_path
            counter += 1

    def cleanup_empty_folders(
        self,
        source_paths: list[str],
        checkpoint: Checkpoint,
        dry_run: bool = False,
    ) -> int:
        """
        Remove empty folders from source paths.
        Returns count of folders removed.
        """
        removed_count = 0

        for source_path_str in source_paths:
            source_path = Path(source_path_str)
            if not source_path.exists():
                continue

            # Walk bottom-up to remove empty folders
            for root, dirs, files in os.walk(source_path, topdown=False):
                for dir_name in dirs:
                    dir_path = Path(root) / dir_name

                    # Check if directory is empty
                    try:
                        if not any(dir_path.iterdir()):
                            if dry_run:
                                self.logger.action("WOULD REMOVE FOLDER", str(dir_path))
                            else:
                                dir_path.rmdir()
                                self.logger.action("REMOVED FOLDER", str(dir_path))
                            removed_count += 1
                    except (OSError, PermissionError) as e:
                        self.logger.warning(f"Could not remove folder {dir_path}: {e}")

        return removed_count


class ArchiveStructureManager:
    """Manages the archive folder structure."""

    def __init__(self, config: SiftConfig):
        self.config = config
        self.archive_root = Path(config.archive_destination)

    def create_structure(self, categories: list[str], dry_run: bool = False) -> list[Path]:
        """Create all category folders in the archive."""
        created = []

        for category in categories:
            category_path = self.archive_root / category

            if dry_run:
                print(f"Would create: {category_path}")
                created.append(category_path)
            else:
                category_path.mkdir(parents=True, exist_ok=True)
                created.append(category_path)

        return created

    def get_existing_structure(self) -> list[str]:
        """Get list of existing category folders in archive."""
        if not self.archive_root.exists():
            return []

        categories = []

        for item in self.archive_root.rglob("*"):
            if item.is_dir():
                rel_path = item.relative_to(self.archive_root)
                categories.append(str(rel_path))

        return sorted(categories)

    def validate_category(self, category: str, allowed_categories: list[str]) -> bool:
        """Check if a category is in the allowed list."""
        # Exact match
        if category in allowed_categories:
            return True

        # Check if it's a subcategory of an allowed category
        for allowed in allowed_categories:
            if category.startswith(allowed + "/"):
                return True

        return False
