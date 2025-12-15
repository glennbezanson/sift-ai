# Changelog

All notable changes to Sift will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2024-12-09

### Added

- **Core Features**
  - AI-powered file categorization using Claude Opus 4.5
  - Self-critique system for borderline confidence decisions
  - Sibling context injection for improved consistency
  - Entity detection with fuzzy matching (customer/project names)
  - Three-tier deduplication (hash, pattern, AI similarity)

- **Processing Workflow**
  - Phase 0: Structure analysis and proposal
  - Waves 1-N: Iterative file processing
  - Deduplication pass
  - Cleanup pass for empty folders

- **Safety & Reliability**
  - Backup confirmation requirement
  - Dry-run mode for previewing actions
  - Full checkpoint/resume system
  - Comprehensive action logging

- **Content Extraction**
  - Word documents (.docx, .doc)
  - Excel spreadsheets (.xlsx, .xls)
  - PowerPoint presentations (.pptx, .ppt)
  - PDF files
  - Plain text and CSV files
  - RTF files (basic support)

- **Reports**
  - Structure proposal (markdown)
  - Unknowns batch reports per wave
  - Deduplication report
  - Final summary statistics

- **CLI Interface**
  - `--phase` for running specific phases
  - `--resume` for continuing from checkpoint
  - `--dry-run` for preview mode
  - `--test-mode` and `--limit` for testing
  - Colored output with progress bars

### Technical Details

- Python 3.9+ required
- Uses Claude Opus 4.5 (`claude-opus-4-5-20250514`) for all AI operations
- Configurable confidence threshold (default: 7)
- Supports Windows and Unix paths
- Graceful handling of file access errors

---

## [Unreleased]

### Planned

- Web UI for reviewing unknowns
- OCR support for image files
- Email file extraction (.eml, .msg)
- Cloud storage integration
- Batch cost estimation
- Automated tests
