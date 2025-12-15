#!/usr/bin/env python3
"""
Sift - AI-Powered Intelligent File Archiving

Main CLI entry point for running Sift operations.
"""

import argparse
import asyncio
import sys
import time
from datetime import datetime
from pathlib import Path

try:
    from colorama import init, Fore, Style
    init()
    HAS_COLOR = True
except ImportError:
    HAS_COLOR = False

try:
    from tqdm import tqdm
    HAS_TQDM = True
except ImportError:
    HAS_TQDM = False

from sift.config import SiftConfig
from sift.scanner import FileScanner, ScanResult
from sift.extractor import ContentExtractor
from sift.entities import EntityManager
from sift.categorizer import Categorizer, StructureAnalyzer, AsyncCategorizer
from sift.deduplicator import Deduplicator
from sift.checkpoint import Checkpoint, CheckpointManager, Logger
from sift.mover import FileMover, ArchiveStructureManager
from sift.reports import ReportGenerator


def color(text: str, color_code: str) -> str:
    """Apply color if available."""
    if HAS_COLOR:
        return f"{color_code}{text}{Style.RESET_ALL}"
    return text


def print_header(text: str):
    """Print a styled header."""
    print()
    print(color(f"{'=' * 60}", Fore.CYAN if HAS_COLOR else ""))
    print(color(f"  {text}", Fore.CYAN if HAS_COLOR else ""))
    print(color(f"{'=' * 60}", Fore.CYAN if HAS_COLOR else ""))
    print()


def print_success(text: str):
    """Print success message."""
    print(color(f"[OK] {text}", Fore.GREEN if HAS_COLOR else ""))


def print_warning(text: str):
    """Print warning message."""
    print(color(f"[!] {text}", Fore.YELLOW if HAS_COLOR else ""))


def print_error(text: str):
    """Print error message."""
    print(color(f"[X] {text}", Fore.RED if HAS_COLOR else ""))


def confirm_backup() -> bool:
    """Prompt user to confirm backup exists."""
    print()
    print_warning("BACKUP CONFIRMATION REQUIRED")
    print()
    print("Sift will move and delete files. This is not easily reversible.")
    print()
    response = input("Have you created a backup of your source directories? (yes/no): ")
    return response.strip().lower() == "yes"


def run_structure_phase(
    config: SiftConfig,
    checkpoint: Checkpoint,
    checkpoint_manager: CheckpointManager,
    logger: Logger,
    limit: int | None = None,
) -> bool:
    """Run Phase 0: Structure Analysis."""
    print_header("Phase 0: Structure Analysis")

    # Scan files
    print("Scanning source directories...")
    scanner = FileScanner(config)
    scan_result = scanner.scan_all(limit=limit)

    if scan_result.total_count == 0:
        print_error("No files found to process.")
        return False

    print_success(f"Found {scan_result.total_count:,} files ({scanner.format_size(scan_result.total_size_bytes)})")
    print()

    # Show scan summary
    print(scanner.get_scan_summary(scan_result))
    print()

    # Get sample filenames for AI
    sample_filenames = [f.filename for f in scan_result.files[:100]]

    # Initialize entity manager
    entity_manager = EntityManager(config.get_entity_mappings_path())

    # Analyze and propose structure
    print("Analyzing with AI to propose archive structure...")
    analyzer = StructureAnalyzer(config, entity_manager)
    proposal = analyzer.analyze_and_propose(
        scanner.get_scan_summary(scan_result),
        sample_filenames,
    )

    # Save proposal
    report_gen = ReportGenerator(config)
    report_path = report_gen.save_report("structure-proposal.md", proposal)
    print_success(f"Structure proposal saved to: {report_path}")

    # Extract structure for checkpoint
    structure = analyzer.parse_structure_from_proposal(proposal)
    checkpoint.archive_structure = structure
    checkpoint.files_total = scan_result.total_count
    checkpoint.phase = "structure"
    checkpoint_manager.save(checkpoint)

    print()
    print("Please review output/structure-proposal.md")
    print("When ready, run: python main.py --phase process")

    return True


def run_process_phase(
    config: SiftConfig,
    checkpoint: Checkpoint,
    checkpoint_manager: CheckpointManager,
    logger: Logger,
    dry_run: bool = False,
    limit: int | None = None,
    use_parallel: bool = True,
) -> bool:
    """Run Wave Processing phase."""
    print_header(f"Wave {checkpoint.current_wave}: Processing Files")

    if not checkpoint.archive_structure:
        print_error("No archive structure defined. Run --phase structure first.")
        return False

    if not checkpoint.structure_approved:
        print()
        response = input("Have you reviewed and approved the structure proposal? (yes/no): ")
        if response.strip().lower() != "yes":
            print("Please review output/structure-proposal.md first.")
            return False
        checkpoint.structure_approved = True
        checkpoint_manager.save(checkpoint)

    # Scan files
    print("Scanning source directories...")
    scanner = FileScanner(config)
    scan_result = scanner.scan_all(limit=limit)

    # Get files not yet processed
    pending_files = checkpoint_manager.get_files_pending(checkpoint, scan_result.files)
    print(f"Files pending: {len(pending_files):,}")

    if not pending_files:
        print_success("All files have been processed!")
        checkpoint.phase = "wave_complete"
        checkpoint_manager.save(checkpoint)
        return True

    # Initialize components
    entity_manager = EntityManager(config.get_entity_mappings_path())
    extractor = ContentExtractor(config)
    deduplicator = Deduplicator(config, extractor)
    mover = FileMover(config, checkpoint_manager, logger)
    report_gen = ReportGenerator(config)

    # Run pattern-based dedup FIRST to catch v1/v2 variants before AI categorization
    print("Checking for version variants (v1/v2 patterns)...")
    pattern_dupes = deduplicator.find_pattern_duplicates(pending_files)

    # Mark duplicate versions for deletion
    version_dupes_to_skip = set()
    for group in pattern_dupes:
        for dup in group.duplicates:
            version_dupes_to_skip.add(str(dup.path))
            if not dry_run:
                checkpoint_manager.mark_file_processed(
                    checkpoint, dup, "DELETE (older version)", 10, "delete"
                )
            print_warning(f"Version duplicate: {dup.filename} -> keep {group.canonical_file.filename}")

    if version_dupes_to_skip:
        print(f"Found {len(version_dupes_to_skip)} version duplicates to skip")

    # Filter out version duplicates from pending files
    pending_files = [f for f in pending_files if str(f.path) not in version_dupes_to_skip]
    print(f"Files to categorize: {len(pending_files):,}")

    # Process files
    unknowns = []
    moved_count = 0
    skip_count = 0
    delete_count = len(version_dupes_to_skip)

    start_time = time.time()

    if use_parallel and config.parallel_batch_size > 1:
        # Use async parallel processing
        print(f"Using parallel processing (batch size: {config.parallel_batch_size})")
        results = asyncio.run(_process_files_async(
            config, entity_manager, extractor, checkpoint, pending_files
        ))

        # Process results
        for result in results:
            try:
                if result.action == "move":
                    if not dry_run:
                        mover.move_file(result.file_info, result.category, checkpoint, dry_run=False)
                    checkpoint_manager.mark_file_processed(
                        checkpoint, result.file_info, result.category, result.confidence, "move"
                    )
                    moved_count += 1

                elif result.action == "skip":
                    checkpoint_manager.mark_file_processed(
                        checkpoint, result.file_info, result.category, result.confidence, "skip"
                    )
                    skip_count += 1

                else:  # unknown
                    unknowns.append(result)
                    checkpoint_manager.add_unknown(checkpoint, checkpoint.current_wave, str(result.file_info.path))
                    checkpoint_manager.mark_file_processed(
                        checkpoint, result.file_info, result.category, result.confidence, "unknown"
                    )

            except Exception as e:
                logger.error(f"Error processing result for {result.file_info.path}: {e}")
                continue
    else:
        # Sequential processing (fallback)
        categorizer = Categorizer(config, entity_manager, extractor, checkpoint.archive_structure)

        file_iterator = pending_files
        if HAS_TQDM:
            file_iterator = tqdm(pending_files, desc="Processing", unit="file")

        for file_info in file_iterator:
            try:
                result = categorizer.categorize(file_info)

                if result.action == "move":
                    if not dry_run:
                        mover.move_file(file_info, result.category, checkpoint, dry_run=False)
                    checkpoint_manager.mark_file_processed(
                        checkpoint, file_info, result.category, result.confidence, "move"
                    )
                    moved_count += 1

                elif result.action == "skip":
                    checkpoint_manager.mark_file_processed(
                        checkpoint, file_info, result.category, result.confidence, "skip"
                    )
                    skip_count += 1

                else:  # unknown
                    unknowns.append(result)
                    checkpoint_manager.add_unknown(checkpoint, checkpoint.current_wave, str(file_info.path))
                    checkpoint_manager.mark_file_processed(
                        checkpoint, file_info, result.category, result.confidence, "unknown"
                    )

            except Exception as e:
                logger.error(f"Error processing {file_info.path}: {e}")
                continue

    elapsed = time.time() - start_time
    files_per_sec = len(pending_files) / elapsed if elapsed > 0 else 0

    print()
    print_success(f"Moved: {moved_count:,} files")
    if delete_count > 0:
        print_warning(f"Version duplicates to delete: {delete_count:,} files")
    print(f"Skipped: {skip_count:,} files")
    print_warning(f"Needs review: {len(unknowns):,} files")
    print(f"Performance: {files_per_sec:.2f} files/sec ({elapsed:.1f}s total)")

    # Generate unknowns report if any
    if unknowns:
        report_gen.generate_unknowns_report(
            checkpoint.current_wave,
            unknowns,
            checkpoint.archive_structure,
        )
        print()
        print(f"Review unknowns in: output/unknowns-wave{checkpoint.current_wave}.md")

    checkpoint.current_wave += 1
    checkpoint.phase = "wave_complete"
    checkpoint_manager.save(checkpoint)

    return True


async def _process_files_async(
    config: SiftConfig,
    entity_manager: EntityManager,
    extractor: ContentExtractor,
    checkpoint: Checkpoint,
    files: list,
):
    """Process files using async parallel categorization."""
    categorizer = AsyncCategorizer(config, entity_manager, extractor, checkpoint.archive_structure)

    # Progress tracking
    processed = [0]
    total = len(files)

    def progress_callback(current, total_files):
        processed[0] = current
        if HAS_TQDM:
            # Update would require more complex tqdm integration
            pass
        else:
            print(f"\rProcessing: {current}/{total_files} files", end="", flush=True)

    if not HAS_TQDM:
        print(f"Processing {total} files in parallel...")

    results = await categorizer.categorize_batch_async(files, progress_callback)

    if not HAS_TQDM:
        print()  # Newline after progress

    return results


def run_dedup_phase(
    config: SiftConfig,
    checkpoint: Checkpoint,
    checkpoint_manager: CheckpointManager,
    logger: Logger,
    dry_run: bool = False,
) -> bool:
    """Run Deduplication phase."""
    print_header("Deduplication Pass")

    # Scan archive destination for duplicates
    archive_path = Path(config.archive_destination)
    if not archive_path.exists():
        print_error(f"Archive destination does not exist: {archive_path}")
        return False

    print("Scanning archive for duplicates...")

    # Create temp config for scanning archive
    archive_config = SiftConfig(
        source_paths=[str(archive_path)],
        archive_destination=config.archive_destination,
        skip_folders=config.skip_folders,
        process_extensions=config.process_extensions,
        max_file_size_mb_for_content=config.max_file_size_mb_for_content,
        api_key_env_var=config.api_key_env_var,
        base_dir=config.base_dir,
    )

    scanner = FileScanner(archive_config)
    scan_result = scanner.scan_all()

    print(f"Files in archive: {scan_result.total_count:,}")

    # Run deduplication
    extractor = ContentExtractor(config)
    deduplicator = Deduplicator(config, extractor)

    print("Finding duplicates (this may take a while)...")
    dedup_result = deduplicator.deduplicate(scan_result.files)

    # Generate report
    report = deduplicator.format_dedup_report(dedup_result)
    report_gen = ReportGenerator(config)
    report_path = report_gen.save_report("dedup-report.md", report)

    print()
    print_success(f"Deduplication report saved to: {report_path}")
    print()
    print(f"Hash duplicates: {len(dedup_result.hash_duplicates):,} groups")
    print(f"Pattern duplicates: {len(dedup_result.pattern_duplicates):,} groups")
    print(f"AI duplicates: {len(dedup_result.ai_duplicates):,} groups")
    print(f"Total files to delete: {len(dedup_result.files_to_delete):,}")
    print(f"Space to save: {dedup_result.space_saved_bytes / 1024 / 1024:.1f} MB")

    if not dry_run and dedup_result.files_to_delete:
        print()
        response = input("Delete duplicate files? (yes/no): ")
        if response.strip().lower() == "yes":
            mover = FileMover(config, checkpoint_manager, logger)
            for file_info in dedup_result.files_to_delete:
                mover.delete_file(file_info, checkpoint, dry_run=False)
            print_success(f"Deleted {len(dedup_result.files_to_delete)} duplicate files")

    checkpoint.phase = "dedup_complete"
    checkpoint_manager.save(checkpoint)

    return True


def run_cleanup_phase(
    config: SiftConfig,
    checkpoint: Checkpoint,
    checkpoint_manager: CheckpointManager,
    logger: Logger,
    dry_run: bool = False,
) -> bool:
    """Run Cleanup phase - remove empty folders."""
    print_header("Cleanup Pass")

    mover = FileMover(config, checkpoint_manager, logger)

    print("Scanning for empty folders...")
    removed = mover.cleanup_empty_folders(config.source_paths, checkpoint, dry_run=dry_run)

    if dry_run:
        print(f"Would remove: {removed} empty folders")
    else:
        print_success(f"Removed: {removed} empty folders")

    checkpoint.phase = "complete"
    checkpoint_manager.save(checkpoint)

    return True


def run_resume(
    config: SiftConfig,
    checkpoint: Checkpoint,
    checkpoint_manager: CheckpointManager,
    logger: Logger,
    dry_run: bool = False,
) -> bool:
    """Resume from last checkpoint."""
    print_header("Resuming from Checkpoint")

    print(f"Last run: {checkpoint.last_run}")
    print(f"Phase: {checkpoint.phase}")
    print(f"Wave: {checkpoint.current_wave}")
    print(f"Files processed: {checkpoint.files_processed}/{checkpoint.files_total}")
    print()

    if checkpoint.phase in ("init", "structure"):
        return run_structure_phase(config, checkpoint, checkpoint_manager, logger)
    elif checkpoint.phase in ("wave_processing", "wave_complete"):
        return run_process_phase(config, checkpoint, checkpoint_manager, logger, dry_run=dry_run)
    elif checkpoint.phase == "dedup_complete":
        return run_cleanup_phase(config, checkpoint, checkpoint_manager, logger, dry_run=dry_run)
    else:
        print_success("All phases complete!")
        return True


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Sift - AI-Powered Intelligent File Archiving",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py --phase structure          # Analyze and propose structure
  python main.py --phase process --dry-run  # Preview file moves
  python main.py --phase process            # Run processing wave
  python main.py --phase dedup              # Find and remove duplicates
  python main.py --phase cleanup            # Remove empty folders
  python main.py --resume                   # Continue from checkpoint
        """,
    )

    parser.add_argument(
        "--phase",
        choices=["structure", "process", "dedup", "cleanup"],
        help="Phase to run",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume from last checkpoint",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview actions without making changes",
    )
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="Path to config file (default: config/config.json)",
    )
    parser.add_argument(
        "--test-mode",
        action="store_true",
        help="Run in test mode with limited files",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of files to process",
    )

    args = parser.parse_args()

    # Validate arguments
    if not args.phase and not args.resume:
        parser.print_help()
        sys.exit(1)

    # Load configuration
    try:
        config = SiftConfig.load(args.config)
    except FileNotFoundError as e:
        print_error(str(e))
        sys.exit(1)

    # Set up logging and checkpoints
    logger = Logger(config.get_logs_dir())
    checkpoint_manager = CheckpointManager(config.get_logs_dir())

    # Load or create checkpoint
    checkpoint = checkpoint_manager.load()

    # Check for backup confirmation on first run
    if not checkpoint.backup_confirmed and not args.dry_run:
        if not confirm_backup():
            print()
            print("Please create a backup before running Sift.")
            print("Or use --dry-run to preview actions.")
            sys.exit(1)
        checkpoint.backup_confirmed = True
        checkpoint_manager.save(checkpoint)

    # Determine limit
    limit = args.limit
    if args.test_mode and not limit:
        limit = 50

    # Track start time
    start_time = datetime.now()

    # Run appropriate phase
    success = False

    try:
        if args.resume:
            success = run_resume(config, checkpoint, checkpoint_manager, logger, dry_run=args.dry_run)
        elif args.phase == "structure":
            success = run_structure_phase(config, checkpoint, checkpoint_manager, logger, limit=limit)
        elif args.phase == "process":
            success = run_process_phase(config, checkpoint, checkpoint_manager, logger, dry_run=args.dry_run, limit=limit)
        elif args.phase == "dedup":
            success = run_dedup_phase(config, checkpoint, checkpoint_manager, logger, dry_run=args.dry_run)
        elif args.phase == "cleanup":
            success = run_cleanup_phase(config, checkpoint, checkpoint_manager, logger, dry_run=args.dry_run)

    except KeyboardInterrupt:
        print()
        print_warning("Interrupted. Progress has been saved.")
        print("Run with --resume to continue.")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        print_error(f"Error: {e}")
        raise

    # Generate final summary if complete
    if checkpoint.phase == "complete":
        report_gen = ReportGenerator(config)
        scanner = FileScanner(config)
        scan_result = scanner.scan_all()
        report_gen.generate_final_summary(checkpoint, scan_result, None, start_time)
        print()
        print_success("Final summary saved to: output/final-summary.md")

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
