"""
Deduplication engine for Sift.
Implements three-tier duplicate detection: hash, pattern, and AI similarity.
"""

import hashlib
import json
import re
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import anthropic

from .config import SiftConfig
from .extractor import ContentExtractor
from .scanner import FileInfo


# Model is now configured via config.model


@dataclass
class DuplicateGroup:
    """A group of duplicate/similar files."""

    canonical_file: FileInfo  # The file to keep
    duplicates: list[FileInfo] = field(default_factory=list)
    detection_method: str = ""  # "hash", "pattern", "ai"
    similarity_score: Optional[float] = None
    ai_reasoning: Optional[str] = None


@dataclass
class DeduplicationResult:
    """Results from deduplication pass."""

    hash_duplicates: list[DuplicateGroup] = field(default_factory=list)
    pattern_duplicates: list[DuplicateGroup] = field(default_factory=list)
    ai_duplicates: list[DuplicateGroup] = field(default_factory=list)
    files_to_delete: list[FileInfo] = field(default_factory=list)
    space_saved_bytes: int = 0


class Deduplicator:
    """Three-tier deduplication engine."""

    # Patterns for version detection
    VERSION_PATTERNS = [
        r"[_\-\s]v(\d+)",  # _v1, -v2, v3
        r"[_\-\s]V(\d+)",  # _V1, -V2
        r"[_\-\s]version[_\-\s]?(\d+)",  # _version1, -version_2
        r"\s?\((\d+)\)",  # (1), (2)
        r"[_\-\s]r(\d+)",  # _r1, -r2 (revision)
        r"[_\-\s]rev[_\-\s]?(\d+)",  # _rev1, -rev_2
    ]

    FINAL_PATTERNS = [
        r"[_\-\s]FINAL",
        r"[_\-\s]final",
        r"[_\-\s]Final",
        r"[_\-\s]APPROVED",
        r"[_\-\s]approved",
    ]

    DRAFT_PATTERNS = [
        r"[_\-\s]DRAFT",
        r"[_\-\s]draft",
        r"[_\-\s]Draft",
        r"[_\-\s]WIP",
        r"[_\-\s]wip",
    ]

    def __init__(self, config: SiftConfig, extractor: ContentExtractor):
        self.config = config
        self.extractor = extractor
        self.client = config.get_anthropic_client()

    def compute_file_hash(self, file_path: Path) -> Optional[str]:
        """Compute MD5 hash of file."""
        try:
            hasher = hashlib.md5()
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(65536), b""):
                    hasher.update(chunk)
            return hasher.hexdigest()
        except (OSError, PermissionError):
            return None

    def find_hash_duplicates(self, files: list[FileInfo]) -> list[DuplicateGroup]:
        """Find exact duplicates using file hashes."""
        hash_map: dict[str, list[FileInfo]] = defaultdict(list)

        for file_info in files:
            file_hash = self.compute_file_hash(file_info.path)
            if file_hash:
                hash_map[file_hash].append(file_info)

        groups = []
        for file_hash, file_list in hash_map.items():
            if len(file_list) > 1:
                # Keep the newest file
                sorted_files = sorted(file_list, key=lambda f: f.modified_time, reverse=True)
                group = DuplicateGroup(
                    canonical_file=sorted_files[0],
                    duplicates=sorted_files[1:],
                    detection_method="hash",
                )
                groups.append(group)

        return groups

    def extract_base_name(self, filename: str) -> str:
        """Extract base name by removing version patterns."""
        name = Path(filename).stem

        # Remove version patterns
        for pattern in self.VERSION_PATTERNS:
            name = re.sub(pattern, "", name)

        # Remove final/draft patterns
        for pattern in self.FINAL_PATTERNS + self.DRAFT_PATTERNS:
            name = re.sub(pattern, "", name)

        # Remove trailing underscores, hyphens, spaces
        name = re.sub(r"[_\-\s]+$", "", name)

        return name.lower()

    def extract_version_info(self, filename: str) -> dict:
        """Extract version information from filename."""
        info = {
            "version_number": None,
            "is_final": False,
            "is_draft": False,
        }

        # Check for version numbers
        for pattern in self.VERSION_PATTERNS:
            match = re.search(pattern, filename, re.IGNORECASE)
            if match:
                info["version_number"] = int(match.group(1))
                break

        # Check for final marker
        for pattern in self.FINAL_PATTERNS:
            if re.search(pattern, filename):
                info["is_final"] = True
                break

        # Check for draft marker
        for pattern in self.DRAFT_PATTERNS:
            if re.search(pattern, filename):
                info["is_draft"] = True
                break

        return info

    def find_pattern_duplicates(self, files: list[FileInfo]) -> list[DuplicateGroup]:
        """Find version variants using filename patterns."""
        # Group by base name and extension
        base_groups: dict[tuple[str, str], list[FileInfo]] = defaultdict(list)

        for file_info in files:
            base_name = self.extract_base_name(file_info.filename)
            ext = file_info.extension.lower()
            key = (base_name, ext)
            base_groups[key].append(file_info)

        groups = []
        for (base_name, ext), file_list in base_groups.items():
            if len(file_list) > 1:
                # Determine which file to keep
                # Priority: FINAL > highest version > newest modified
                sorted_files = self._sort_by_version_priority(file_list)
                group = DuplicateGroup(
                    canonical_file=sorted_files[0],
                    duplicates=sorted_files[1:],
                    detection_method="pattern",
                )
                groups.append(group)

        return groups

    def _sort_by_version_priority(self, files: list[FileInfo]) -> list[FileInfo]:
        """Sort files by version priority (canonical file first)."""

        def priority_key(f: FileInfo) -> tuple:
            info = self.extract_version_info(f.filename)
            # Lower tuple = higher priority
            # Priority order: is_final (True=0), not draft (True=0), version desc, modified desc
            return (
                0 if info["is_final"] else 1,
                0 if not info["is_draft"] else 1,
                -(info["version_number"] or 0),
                -f.modified_time.timestamp(),
            )

        return sorted(files, key=priority_key)

    def find_ai_duplicates(
        self, files: list[FileInfo], existing_groups: list[DuplicateGroup]
    ) -> list[DuplicateGroup]:
        """Find near-duplicates using AI content comparison."""
        # Get files not already in duplicate groups
        already_processed = set()
        for group in existing_groups:
            already_processed.add(str(group.canonical_file.path))
            for dup in group.duplicates:
                already_processed.add(str(dup.path))

        remaining_files = [f for f in files if str(f.path) not in already_processed]

        # Group by folder and extension for comparison candidates
        folder_ext_groups: dict[tuple[str, str], list[FileInfo]] = defaultdict(list)
        for file_info in remaining_files:
            folder = file_info.path.parent.name
            ext = file_info.extension.lower()
            folder_ext_groups[(folder, ext)].append(file_info)

        groups = []

        for (folder, ext), file_list in folder_ext_groups.items():
            if len(file_list) < 2:
                continue

            # Compare pairs within same folder/extension
            compared_pairs = set()

            for i, file1 in enumerate(file_list):
                for file2 in file_list[i + 1 :]:
                    pair_key = tuple(sorted([str(file1.path), str(file2.path)]))
                    if pair_key in compared_pairs:
                        continue
                    compared_pairs.add(pair_key)

                    similarity = self._compare_files_ai(file1, file2)

                    if similarity and similarity["is_duplicate"]:
                        # Determine which to keep
                        if similarity["keep_file"] == 1:
                            canonical, duplicate = file1, file2
                        else:
                            canonical, duplicate = file2, file1

                        # Check if canonical is already in a group
                        added_to_existing = False
                        for existing_group in groups:
                            if str(existing_group.canonical_file.path) == str(canonical.path):
                                existing_group.duplicates.append(duplicate)
                                added_to_existing = True
                                break

                        if not added_to_existing:
                            group = DuplicateGroup(
                                canonical_file=canonical,
                                duplicates=[duplicate],
                                detection_method="ai",
                                similarity_score=similarity["similarity"],
                                ai_reasoning=similarity["reasoning"],
                            )
                            groups.append(group)

        return groups

    def _compare_files_ai(
        self, file1: FileInfo, file2: FileInfo
    ) -> Optional[dict]:
        """Compare two files using AI to detect near-duplicates."""
        content1 = self.extractor.extract(file1.path, max_chars=2000)
        content2 = self.extractor.extract(file2.path, max_chars=2000)

        if not content1 or not content2:
            return None

        if content1.startswith("[") or content2.startswith("["):
            # Extraction failed
            return None

        prompt = f"""Compare these two files and determine if they are duplicates or near-duplicates.

File 1: {file1.filename}
Modified: {file1.modified_time.strftime('%Y-%m-%d')}
Content preview:
---
{content1}
---

File 2: {file2.filename}
Modified: {file2.modified_time.strftime('%Y-%m-%d')}
Content preview:
---
{content2}
---

Return ONLY valid JSON:
{{
  "is_duplicate": true or false,
  "similarity": 0.0 to 1.0,
  "reasoning": "Brief explanation",
  "keep_file": 1 or 2,
  "keep_reason": "Why this file should be kept"
}}

Consider files duplicates if they contain substantially the same content,
even with minor differences like formatting, typos, or small additions.
When choosing which to keep, prefer: more complete, more recent, better formatted.
"""

        try:
            response = self.client.messages.create(
                model=self.config.model,
                max_tokens=512,
                messages=[{"role": "user", "content": prompt}],
            )

            result_text = response.content[0].text

            # Parse JSON
            try:
                return json.loads(result_text)
            except json.JSONDecodeError:
                match = re.search(r"\{[\s\S]*\}", result_text)
                if match:
                    return json.loads(match.group())
                return None

        except Exception:
            return None

    def deduplicate(self, files: list[FileInfo]) -> DeduplicationResult:
        """Run full three-tier deduplication."""
        result = DeduplicationResult()

        # Tier 1: Hash-based exact duplicates
        result.hash_duplicates = self.find_hash_duplicates(files)

        # Tier 2: Pattern-based version variants
        result.pattern_duplicates = self.find_pattern_duplicates(files)

        # Tier 3: AI-based similarity detection
        all_existing = result.hash_duplicates + result.pattern_duplicates
        result.ai_duplicates = self.find_ai_duplicates(files, all_existing)

        # Compile files to delete
        for group in result.hash_duplicates + result.pattern_duplicates + result.ai_duplicates:
            for dup in group.duplicates:
                result.files_to_delete.append(dup)
                result.space_saved_bytes += dup.size_bytes

        return result

    def format_dedup_report(self, result: DeduplicationResult) -> str:
        """Format deduplication results as markdown report."""
        lines = [
            "# Deduplication Report",
            "",
            f"**Total duplicates found:** {len(result.files_to_delete)}",
            f"**Space to be saved:** {result.space_saved_bytes / 1024 / 1024:.1f} MB",
            "",
        ]

        if result.hash_duplicates:
            lines.extend([
                "## Exact Duplicates (Hash Match)",
                "",
            ])
            for group in result.hash_duplicates:
                lines.append(f"**Keep:** {group.canonical_file.filename}")
                lines.append(f"  - Path: {group.canonical_file.path}")
                lines.append("  - **Delete:**")
                for dup in group.duplicates:
                    lines.append(f"    - {dup.path}")
                lines.append("")

        if result.pattern_duplicates:
            lines.extend([
                "## Version Variants (Pattern Match)",
                "",
            ])
            for group in result.pattern_duplicates:
                lines.append(f"**Keep:** {group.canonical_file.filename}")
                lines.append(f"  - Path: {group.canonical_file.path}")
                lines.append("  - **Delete:**")
                for dup in group.duplicates:
                    lines.append(f"    - {dup.path}")
                lines.append("")

        if result.ai_duplicates:
            lines.extend([
                "## Near-Duplicates (AI Detection)",
                "",
            ])
            for group in result.ai_duplicates:
                lines.append(f"**Keep:** {group.canonical_file.filename}")
                lines.append(f"  - Path: {group.canonical_file.path}")
                if group.ai_reasoning:
                    lines.append(f"  - Reason: {group.ai_reasoning}")
                lines.append("  - **Delete:**")
                for dup in group.duplicates:
                    lines.append(f"    - {dup.path} (similarity: {group.similarity_score:.0%})")
                lines.append("")

        return "\n".join(lines)
