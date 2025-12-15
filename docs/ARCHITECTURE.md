# Architecture

This document describes Sift's internal architecture and design decisions.

## Overview

Sift is designed as a pipeline of discrete phases, each with clear inputs and outputs. State is persisted between runs via a checkpoint system, allowing the process to be interrupted and resumed.

```
┌─────────────────┐
│  Source Files   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│    Scanner      │──────► File metadata
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   Extractor     │──────► Text content
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Categorizer    │──────► Categories + confidence
│   (Claude AI)   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│     Mover       │──────► Organized archive
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Deduplicator   │──────► Cleaned archive
└─────────────────┘
```

## Module Responsibilities

### config.py — Configuration Management

**Purpose:** Load, validate, and provide access to configuration settings.

**Key Class:** `SiftConfig`

```python
@dataclass
class SiftConfig:
    source_paths: list[str]
    archive_destination: str
    confidence_threshold: int = 7
    # ... other settings
```

**Design Decisions:**
- Uses dataclass for type safety and defaults
- Supports loading from JSON file
- Provides helper methods for derived paths (logs dir, output dir)
- API key retrieved from environment variable (not stored in config)

---

### scanner.py — File Discovery

**Purpose:** Walk directory trees and collect file metadata without reading content.

**Key Classes:**
- `FileInfo` — Metadata about a single file
- `ScanResult` — Aggregated scan statistics
- `FileScanner` — The scanner implementation

**Design Decisions:**
- Uses generators for memory efficiency on large file sets
- Filters by folder name and extension during walk (not after)
- Collects statistics during scan (extension counts, date ranges)
- Relative paths stored for consistent categorization across runs

---

### extractor.py — Content Extraction

**Purpose:** Extract readable text from various document formats.

**Key Class:** `ContentExtractor`

**Supported Formats:**
| Format | Library | Notes |
|--------|---------|-------|
| .docx | python-docx | Paragraphs extracted in order |
| .pdf | PyPDF2 | Page-by-page extraction |
| .xlsx | openpyxl | First 50 rows, first 5 sheets |
| .pptx | python-pptx | Slide-by-slide text |
| .txt/.csv | Built-in | Multiple encoding attempts |
| .rtf | Regex | Basic RTF command stripping |

**Design Decisions:**
- Libraries are optional (graceful degradation if not installed)
- Content truncated to `max_chars` to control prompt size
- Extraction errors return error message string (not exception)
- File size check before attempting extraction

---

### entities.py — Entity Detection

**Purpose:** Detect and normalize customer/project names across documents.

**Key Class:** `EntityManager`

**Features:**
- Canonical name → alias mapping
- Fuzzy matching via rapidfuzz
- Learning of new entities at runtime
- Pending confirmations for fuzzy matches

**Design Decisions:**
- Persisted to JSON for human editability
- Substring matching before fuzzy matching (faster)
- Minimum word length (3) to avoid false positives
- Threshold-based fuzzy matching (default 80%)

---

### categorizer.py — AI Categorization

**Purpose:** Use Claude to analyze files and assign categories.

**Key Classes:**
- `CategorizationResult` — Output of categorization
- `SiblingContext` — Context about already-categorized files
- `Categorizer` — Main categorization engine
- `StructureAnalyzer` — Phase 0 structure proposal

**The Two-Step Process:**

1. **Initial Categorization**
   - Send file metadata + content preview to Claude
   - Include known entities and approved structure
   - Include sibling file context for consistency
   - Receive category, confidence, reasoning

2. **Self-Critique (if enabled)**
   - For borderline confidence (4-8), ask Claude to critique its decision
   - "What could be wrong?"
   - "What alternatives exist?"
   - Model may change its answer after reflection

**Prompt Structure:**
```
You are categorizing a file for archive organization.

File metadata: [path, name, date, size]
Content preview: [extracted text]
Known entities: [from entity manager]
Approved structure: [from checkpoint]
Sibling context: [recently categorized files in same folder]

Return JSON with category, confidence, reasoning, action
```

**Design Decisions:**
- Uses Claude Opus 4.5 for best reasoning capability
- Confidence 1-10 scale (7+ = auto-move, <7 = needs review)
- Self-critique optional (can be disabled for speed/cost)
- Sibling context limited to N files to control prompt size
- Folder-level tracking for sibling context (not global)

---

### deduplicator.py — Duplicate Detection

**Purpose:** Find and remove duplicate files using three tiers.

**Key Classes:**
- `DuplicateGroup` — A set of duplicate files with canonical choice
- `DeduplicationResult` — All found duplicates
- `Deduplicator` — The detection engine

**Three Tiers:**

1. **Hash Matching**
   - MD5 hash of file content
   - Exact duplicates only
   - Keep newest by modification date

2. **Pattern Matching**
   - Extract base name (remove version suffixes)
   - Match `_v1`, `_v2`, `FINAL`, `(1)`, `(2)` patterns
   - Keep by priority: FINAL > highest version > newest

3. **AI Similarity**
   - For remaining files in same folder with same extension
   - Compare content previews
   - Claude determines if semantically duplicate
   - Returns which file to keep and why

**Design Decisions:**
- Tiers run in order (cheaper before expensive)
- Files already in groups excluded from later tiers
- AI comparison only within folder (not cross-folder)
- Human confirmation before deletion

---

### checkpoint.py — State Persistence

**Purpose:** Save and restore processing state for resume capability.

**Key Classes:**
- `Checkpoint` — Current processing state
- `CheckpointManager` — Save/load operations
- `Logger` — Action logging

**Checkpoint Contents:**
```python
@dataclass
class Checkpoint:
    phase: str                    # Current phase
    current_wave: int             # Wave number
    files_processed: int          # Progress count
    last_file_processed: str      # For resume point
    structure_approved: bool      # User confirmed structure
    backup_confirmed: bool        # User confirmed backup
    archive_structure: list[str]  # Approved categories
    processed_files: dict         # Path → categorization
    unknowns_wave: dict           # Wave → list of paths
    files_moved: list[dict]       # Move history
    files_deleted: list[str]      # Delete history
```

**Design Decisions:**
- JSON format for human readability/debugging
- Saved after every file (not batched)
- Includes full categorization for each file
- Separate unknowns lists per wave

---

### mover.py — File Operations

**Purpose:** Move and delete files safely.

**Key Classes:**
- `FileMover` — Move/delete operations
- `ArchiveStructureManager` — Create archive folders

**Design Decisions:**
- Creates destination folders on demand
- Handles filename conflicts (adds numeric suffix)
- Dry-run mode for previewing
- All operations logged
- Cleanup walks bottom-up (children before parents)

---

### reports.py — Report Generation

**Purpose:** Generate human-readable markdown reports.

**Key Class:** `ReportGenerator`

**Reports Generated:**
- `structure-proposal.md` — AI-proposed archive structure
- `unknowns-waveN.md` — Files needing human review
- `dedup-report.md` — Duplicate analysis
- `dry-run-report.md` — Preview of proposed actions
- `final-summary.md` — End-of-run statistics

**Design Decisions:**
- Markdown for universal readability
- Unknowns include full AI reasoning
- Options presented as A/B/C/D choices
- Statistics grouped by category

---

## Data Flow

### Phase 0: Structure Analysis

```
source_paths → Scanner → ScanResult
                            │
                            ▼
                    StructureAnalyzer (Claude)
                            │
                            ▼
                    structure-proposal.md
                            │
                            ▼
                    Checkpoint (archive_structure)
```

### Wave Processing

```
Checkpoint (pending files) → Scanner → FileInfo[]
                                          │
                                          ▼
                                    Extractor → content
                                          │
                                          ▼
                                    Categorizer (Claude)
                                          │
                        ┌─────────────────┼─────────────────┐
                        ▼                 ▼                 ▼
                   confidence≥7      confidence<7        skip
                        │                 │                 │
                        ▼                 ▼                 ▼
                     Mover          unknowns-wave.md     (no action)
                        │
                        ▼
                   Archive folder
```

### Deduplication

```
Archive files → Scanner → FileInfo[]
                             │
         ┌───────────────────┼───────────────────┐
         ▼                   ▼                   ▼
    Hash matching      Pattern matching     AI similarity
         │                   │                   │
         └───────────────────┼───────────────────┘
                             ▼
                    DuplicateGroups
                             │
                             ▼
                     dedup-report.md
                             │
                             ▼
                    (User confirms)
                             │
                             ▼
                        Deletions
```

---

## Error Handling

| Error Type | Handling |
|------------|----------|
| File access denied | Log, skip, continue |
| Content extraction failure | Use filename-only, lower confidence |
| API rate limit | Retry with exponential backoff (3 attempts) |
| API error | Retry once, then flag as unknown |
| Corrupt file | Log, skip, continue |
| Move failure | Log error, do not mark as moved |
| Checkpoint corruption | Start fresh |

---

## Performance Considerations

1. **Memory:** Uses generators for file scanning; doesn't load all files into memory
2. **API Calls:** One call per file (two if self-critique enabled)
3. **Batching:** Files processed one at a time with checkpoint after each
4. **Parallelization:** Not implemented (API is the bottleneck, not CPU)
5. **Content Size:** Truncated to ~5000 chars to control prompt token usage

---

## Future Architecture Considerations

- **Queue-based processing** for web UI integration
- **Parallel API calls** if rate limits allow
- **Streaming extraction** for very large files
- **Embedding-based similarity** for faster deduplication
- **Plugin system** for new file type extractors
