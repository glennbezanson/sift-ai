"""
Report generation module for Sift.
Creates markdown reports for structure proposals, unknowns batches, and final summaries.
"""

from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Optional

from .categorizer import CategorizationResult
from .checkpoint import Checkpoint
from .config import SiftConfig
from .deduplicator import DeduplicationResult
from .scanner import ScanResult


class ReportGenerator:
    """Generates various reports for Sift operations."""

    def __init__(self, config: SiftConfig):
        self.config = config
        self.output_dir = config.get_output_dir()

    def save_report(self, filename: str, content: str) -> Path:
        """Save a report to the output directory."""
        report_path = self.output_dir / filename
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(content)
        return report_path

    def generate_structure_proposal(
        self, proposal_content: str, scan_result: ScanResult
    ) -> str:
        """Format and save structure proposal report."""
        header = f"""# Structure Analysis Report

**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
**Files Scanned:** {scan_result.total_count:,}
**Total Size:** {self._format_size(scan_result.total_size_bytes)}

---

"""
        content = header + proposal_content

        self.save_report("structure-proposal.md", content)
        return content

    def _categorize_folder(self, path_str: str) -> str:
        """Determine folder category from file path for grouping."""
        path_normalized = path_str.replace(chr(92), '/')
        path_lower = path_normalized.lower()

        if 'zohoattachments' in path_lower:
            return 'Downloads/ZohoAttachments'
        elif '/downloads/' in path_lower:
            return 'Downloads'
        elif '/desktop/' in path_lower:
            return 'Desktop'
        elif '/archive/' in path_lower:
            return 'Archive'
        elif 'work documents' in path_lower:
            parts = path_normalized.split('Work Documents/')
            if len(parts) > 1:
                sub = parts[1].split('/')[0] if '/' in parts[1] else 'root'
                return 'Work Documents/' + sub
            return 'Work Documents'
        elif '/attachments/' in path_lower:
            return 'OneDrive Root'
        else:
            return 'OneDrive Root'


    def generate_unknowns_report(
        self,
        wave: int,
        unknowns: list[CategorizationResult],
        archive_structure: list[str],
    ) -> str:
        """Generate a report of files that need human review.
        
        Uses folder-grouped format if config.generate_folder_grouped_reports is True.
        Wave size is controlled by config.unknowns_wave_size (default 100).
        """
        # Check if folder-grouped reports are enabled
        if getattr(self.config, 'generate_folder_grouped_reports', False):
            return self._generate_folder_grouped_unknowns_report(wave, unknowns)
        
        # Original flat report format
        lines = [
            f"# Wave {wave} Unknowns - Needs Human Review",
            "",
            f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"**Files Requiring Review:** {len(unknowns)}",
            "",
            "---",
            "",
        ]

        for i, result in enumerate(unknowns, 1):
            lines.extend([
                f"## File {i}",
                "",
                f"- **Path:** `{result.file_info.path}`",
                f"- **Filename:** {result.file_info.filename}",
                f"- **Modified:** {result.file_info.modified_time.strftime('%Y-%m-%d')}",
                f"- **Size:** {self._format_size(result.file_info.size_bytes)}",
                "",
                f"### AI Analysis",
                f"- **Proposed Category:** {result.category}",
                f"- **Confidence:** {result.confidence}/10",
                f"- **Reasoning:** {result.reasoning}",
                "",
            ])

            if result.critique:
                lines.extend([
                    f"### Self-Critique",
                    f"{result.critique}",
                    "",
                ])

            if result.alternatives:
                lines.extend([
                    "### Alternative Interpretations",
                    "",
                ])
                for alt in result.alternatives:
                    lines.append(f"- {alt}")
                lines.append("")

            # Generate options
            lines.extend([
                "### Decision Required",
                "",
            ])

            # Add the AI's suggestion as option A
            lines.append(f"- **A)** {result.category} (AI suggestion)")

            # Add alternatives as options
            option_letter = ord('B')
            if result.alternatives:
                for alt in result.alternatives[:3]:
                    lines.append(f"- **{chr(option_letter)})** {alt}")
                    option_letter += 1

            # Add standard options
            lines.extend([
                f"- **{chr(option_letter)})** Skip this file",
                f"- **{chr(option_letter + 1)})** Other (specify category)",
            ])

            lines.extend(["", "---", ""])

        content = "\n".join(lines)
        self.save_report(f"unknowns-wave{wave}.md", content)
        return content


    def _generate_folder_grouped_unknowns_report(
        self,
        wave: int,
        unknowns: list[CategorizationResult],
    ) -> str:
        """Generate folder-grouped unknowns report (improved format from lessons learned)."""
        # Group unknowns by folder
        by_folder: dict[str, list[CategorizationResult]] = defaultdict(list)
        for result in unknowns:
            folder = self._categorize_folder(str(result.file_info.path))
            by_folder[folder].append(result)

        lines = [
            f"# Wave {wave} Unknowns - Needs Human Review",
            "",
            f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"**Files Requiring Review:** {len(unknowns)}",
            "",
            "## Summary by Folder",
            "",
            "| Folder | Count | Size |",
            "|--------|-------|------|",
        ]

        # Summary table
        for folder in sorted(by_folder.keys(), key=lambda x: -len(by_folder[x])):
            files = by_folder[folder]
            total_size = sum(f.file_info.size_bytes for f in files)
            lines.append(f"| {folder} | {len(files)} | {self._format_size(total_size)} |")

        lines.extend(["", "---"])

        # Detailed sections by folder
        for folder in sorted(by_folder.keys(), key=lambda x: -len(by_folder[x])):
            files = by_folder[folder]
            files.sort(key=lambda x: x.file_info.filename.lower())
            total_size = sum(f.file_info.size_bytes for f in files)

            lines.extend([
                "",
                f"## {folder} ({len(files)} files, {self._format_size(total_size)})",
                "",
                "| # | Filename | Full Path | Modified | Size | Action |",
                "|---|----------|-----------|----------|------|--------|",
            ])

            for i, result in enumerate(files, 1):
                path_str = str(result.file_info.path).replace(chr(92), '/')
                modified = result.file_info.modified_time.strftime('%Y-%m-%d')
                size = self._format_size(result.file_info.size_bytes)
                lines.append(f"| {i} | {result.file_info.filename} | {path_str} | {modified} | {size} | |")

            lines.extend(["", "---"])

        # Decision format instructions
        lines.extend([
            "",
            "## Decision Format",
            "",
            "Fill in the Action column or provide bulk decisions:",
            "- `DELETE` - Delete the file",
            "- `SKIP` - Leave in place",
            "- `MOVE: [destination]` - Move to archive subfolder",
            "",
            "Examples:",
            "- `Archive: DELETE ALL`",
            "- `Desktop: DELETE 5-8, SKIP rest`",
            "- `OneDrive Root #1,2,9: Customers/Northside/`",
        ])

        content = "\n".join(lines)
        self.save_report(f"unknowns-wave{wave}.md", content)
        return content

    def generate_final_summary(
        self,
        checkpoint: Checkpoint,
        scan_result: Optional[ScanResult],
        dedup_result: Optional[DeduplicationResult],
        start_time: datetime,
    ) -> str:
        """Generate the final summary report."""
        duration = datetime.now() - start_time
        hours = duration.total_seconds() / 3600

        lines = [
            "# Sift Summary",
            "",
            f"**Run Date:** {datetime.now().strftime('%Y-%m-%d')}",
            f"**Duration:** {hours:.1f} hours",
            "",
            "---",
            "",
            "## Statistics",
            "",
        ]

        if scan_result:
            lines.append(f"- **Total files scanned:** {scan_result.total_count:,}")

        lines.extend([
            f"- **Files processed:** {checkpoint.files_processed:,}",
            f"- **Files moved:** {len(checkpoint.files_moved):,}",
        ])

        if dedup_result:
            lines.append(f"- **Files deleted (duplicates):** {len(checkpoint.files_deleted):,}")

        # Count unknowns
        total_unknowns = sum(len(v) for v in checkpoint.unknowns_wave.values())
        if total_unknowns > 0:
            lines.append(f"- **Files pending review:** {total_unknowns:,}")

        lines.extend(["", "## By Category", ""])

        # Group moved files by category
        category_counts: dict[str, int] = {}
        for move in checkpoint.files_moved:
            to_path = Path(move["to"])
            # Extract category from path (relative to archive root)
            try:
                rel_path = to_path.relative_to(self.config.archive_destination)
                category = str(rel_path.parent)
                if category == ".":
                    category = "Root"
            except ValueError:
                category = "Unknown"

            category_counts[category] = category_counts.get(category, 0) + 1

        for category, count in sorted(category_counts.items(), key=lambda x: -x[1]):
            lines.append(f"- **{category}:** {count:,} files")

        if dedup_result:
            lines.extend([
                "",
                "## Deduplication Results",
                "",
                f"- **Exact duplicates removed:** {len(dedup_result.hash_duplicates):,}",
                f"- **Version variants removed:** {len(dedup_result.pattern_duplicates):,}",
                f"- **AI-detected duplicates:** {len(dedup_result.ai_duplicates):,}",
                f"- **Space saved:** {self._format_size(dedup_result.space_saved_bytes)}",
            ])

        # Waves summary
        if checkpoint.unknowns_wave:
            lines.extend(["", "## Waves Summary", ""])
            for wave, unknowns in sorted(checkpoint.unknowns_wave.items()):
                lines.append(f"- **Wave {wave}:** {len(unknowns)} files needed review")

        lines.extend(["", "---", "", "*Report generated by Sift*"])

        content = "\n".join(lines)
        self.save_report("final-summary.md", content)
        return content

    def generate_dry_run_report(
        self,
        categorizations: list[CategorizationResult],
        scan_result: ScanResult,
    ) -> str:
        """Generate a dry-run preview report."""
        lines = [
            "# Dry Run Report - Preview of Proposed Actions",
            "",
            f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"**Total Files Analyzed:** {len(categorizations)}",
            "",
            "---",
            "",
        ]

        # Group by action
        moves = [c for c in categorizations if c.action == "move"]
        unknowns = [c for c in categorizations if c.action == "unknown"]
        skips = [c for c in categorizations if c.action == "skip"]

        lines.extend([
            "## Summary",
            "",
            f"- **Would Move:** {len(moves)} files",
            f"- **Needs Review:** {len(unknowns)} files",
            f"- **Would Skip:** {len(skips)} files",
            "",
        ])

        # Group moves by category
        if moves:
            lines.extend(["## Proposed Moves by Category", ""])

            category_files: dict[str, list[CategorizationResult]] = {}
            for result in moves:
                if result.category not in category_files:
                    category_files[result.category] = []
                category_files[result.category].append(result)

            for category in sorted(category_files.keys()):
                files = category_files[category]
                lines.extend([
                    f"### {category} ({len(files)} files)",
                    "",
                ])
                for result in files[:10]:  # Show first 10
                    lines.append(f"- {result.file_info.filename} (confidence: {result.confidence})")
                if len(files) > 10:
                    lines.append(f"- ... and {len(files) - 10} more")
                lines.append("")

        if unknowns:
            lines.extend([
                "## Files Needing Review",
                "",
            ])
            for result in unknowns[:20]:  # Show first 20
                lines.append(
                    f"- {result.file_info.filename} → {result.category} "
                    f"(confidence: {result.confidence})"
                )
            if len(unknowns) > 20:
                lines.append(f"- ... and {len(unknowns) - 20} more")

        content = "\n".join(lines)
        self.save_report("dry-run-report.md", content)
        return content

    def _format_size(self, size_bytes: int) -> str:
        """Format byte size as human-readable string."""
        for unit in ["B", "KB", "MB", "GB", "TB"]:
            if size_bytes < 1024:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024
        return f"{size_bytes:.1f} PB"
