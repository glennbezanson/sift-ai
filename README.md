# Sift
## AI-Powered Intelligent File Archiving

<p align="center">
  <img src="https://img.shields.io/badge/python-3.9+-blue.svg" alt="Python 3.9+">
  <img src="https://img.shields.io/badge/license-MIT-green.svg" alt="MIT License">
  <img src="https://img.shields.io/badge/AI-Claude%20Opus%204.5-purple.svg" alt="Claude Opus 4.5">
</p>

**Sift** is an AI-powered file organization tool that intelligently analyzes, categorizes, deduplicates, and archives years of accumulated documents. Unlike traditional file organizers that rely on folder names or simple rules, Sift uses Claude's advanced language understanding to read document content, detect customer/project relationships, and make smart decisions about where files truly belong.

---

## Why Sift?

After years of work, most of us have accumulated thousands of documents scattered across folders with names like "New Folder (3)", "Final FINAL v2", and "misc_2019_backup". Traditional cleanup approaches fail because:

- **Filenames lie** — `Budget.xlsx` tells you nothing about which project or client it belongs to
- **Folder structure is inconsistent** — The same client might appear as "Acme", "ACME Corp", "Acme Inc" across different folders
- **Manual review doesn't scale** — Nobody has time to open and read 10,000 documents
- **Simple rules miss context** — A file mentioning "Acme" might be *about* Acme or just *reference* them

Sift solves this by using AI to understand document content, not just metadata.

---

## Key Features

### AI-Driven Categorization
Sift reads document content (Word, Excel, PowerPoint, PDF, text files) and uses Claude Opus 4.5 to understand what each file is actually about — not just what it's named.

### 10x Parallel Processing
Process files **10x faster** with async parallel API calls:
- Batch size of 10 concurrent requests
- ~0.89 files/sec vs ~0.10 files/sec sequential
- 50 files in ~54 seconds instead of ~8 minutes

### Conditional Self-Critique
Smart self-critique that only runs when needed:
- **High confidence (9-10):** Trust initial result, skip second API call
- **Borderline (6-8):** Run self-critique to verify
- **Low confidence (1-5):** Mark as unknown, skip unnecessary API call

This reduces API costs by 40-60% while maintaining accuracy.

### Sibling Context Injection
When categorizing a file, Sift tells the AI about other files in the same folder that have already been categorized. Files that live together usually belong together — this dramatically improves consistency.

### Smart Entity Detection
Sift learns customer/project names as it works:
- Fuzzy matches variations ("Acme Corp" = "ACME" = "Acme Inc.")
- Builds a knowledge base that improves over time
- Flags uncertain matches for human confirmation

### Three-Tier Deduplication
1. **Hash matching** — Identical files detected instantly via MD5
2. **Pattern matching** — Catches `v1`, `v2`, `FINAL`, `(1)`, `(2)` variants
3. **AI similarity** — Finds near-duplicates with completely different names

### Human-in-the-Loop
Low-confidence decisions are batched into readable markdown reports for human review. You make the calls on genuinely ambiguous files — the AI handles the obvious 80%.

### Resume-Capable
Full checkpoint system saves progress after every file. Interrupt anytime, resume later. Process 50,000 files over multiple sessions without losing work.

---

## How It Works

### Phase 0: Structure Analysis
```
python main.py --phase structure
```
Sift scans your document tree and proposes an archive structure based on:
- Detected customers/projects
- Date ranges of files
- Content themes and patterns

You review and approve before any files move.

### Waves 1-N: Processing
```
python main.py --phase process
```
Files are processed in waves:
1. AI categorizes each file with confidence score (1-10)
2. High-confidence files (≥7) move automatically
3. Low-confidence files batch into `unknowns-wave1.md` for your review
4. You refine, AI learns, next wave runs smarter

### Deduplication Pass
```
python main.py --phase dedup
```
Three-tier duplicate detection cleans up the archive.

### Cleanup Pass
```
python main.py --phase cleanup
```
Removes empty folders after all moves complete.

---

## Installation

### Prerequisites
- Python 3.9 or higher
- Anthropic API key ([get one here](https://console.anthropic.com/))

### Setup

```bash
# Clone the repository
git clone https://github.com/yourusername/sift-ai.git
cd sift-ai

# Install dependencies
pip install -r requirements.txt

# Copy and configure
cp config/config.example.json config/config.json
cp config/entity-mappings.example.json config/entity-mappings.json

# Set your API key
export ANTHROPIC_API_KEY=sk-ant-xxxxx   # Linux/Mac
set ANTHROPIC_API_KEY=sk-ant-xxxxx      # Windows CMD
$env:ANTHROPIC_API_KEY="sk-ant-xxxxx"   # Windows PowerShell
```

### Dependencies

| Package | Purpose |
|---------|---------|
| `anthropic` | Claude API client (sync + async) |
| `python-docx` | Word document extraction (.docx) |
| `pywin32` | Legacy Word extraction (.doc) on Windows |
| `PyPDF2` | PDF text extraction |
| `pdf2image` | PDF to image for Vision fallback |
| `Pillow` | Image processing for PDF Vision |
| `openpyxl` | Excel file extraction |
| `python-pptx` | PowerPoint extraction |
| `rapidfuzz` | Fuzzy string matching |
| `tqdm` | Progress bars |
| `colorama` | Colored terminal output |

### Document Support

| Format | Method |
|--------|--------|
| `.docx` | python-docx |
| `.doc` | pywin32 COM / antiword / textract |
| `.xlsx` | openpyxl |
| `.pdf` | PyPDF2, falls back to Claude Vision for image PDFs |
| `.pptx` | python-pptx |
| `.txt/.csv` | Direct read |

---

## Configuration

### config/config.json

```json
{
  "source_paths": [
    "C:/Users/YourName/Documents",
    "C:/Users/YourName/Desktop/Old Files"
  ],
  "archive_destination": "C:/Users/YourName/Archive",
  "confidence_threshold": 7,
  "skip_folders": ["node_modules", ".git", "__pycache__"],
  "skip_extensions": [".md", ".log", ".tmp"],
  "process_extensions": [".docx", ".xlsx", ".pdf", ".txt", ".csv"],
  "max_file_size_mb_for_content": 50,
  "api_key_env_var": "ANTHROPIC_API_KEY",
  "entity_type": "customer",
  "entity_mappings_file": "config/entity-mappings.json",
  "self_critique_enabled": true,
  "sibling_context_enabled": true
}
```

### Configuration Options

| Option | Description | Default |
|--------|-------------|---------|
| `source_paths` | Directories to scan for files | Required |
| `archive_destination` | Where to move organized files | Required |
| `confidence_threshold` | Minimum AI confidence to auto-move (1-10) | `7` |
| `skip_folders` | Folder names to ignore | Common dev folders |
| `skip_extensions` | File extensions to skip | `.md`, `.log`, etc. |
| `process_extensions` | File extensions to process | Office docs, PDFs |
| `max_file_size_mb_for_content` | Skip content extraction above this size | `50` |
| `entity_type` | What entities to detect ("customer", "project", "client") | `"customer"` |
| `self_critique_enabled` | Enable AI self-review pass | `true` |
| `sibling_context_enabled` | Include sibling file context in prompts | `true` |
| `sibling_context_limit` | Max sibling files to include | `10` |

### Performance Options

| Option | Description | Default |
|--------|-------------|---------|
| `parallel_batch_size` | Number of concurrent API calls | `10` |
| `self_critique_threshold_min` | Min confidence to trigger self-critique | `6` |
| `self_critique_threshold_max` | Max confidence to trigger self-critique | `8` |
| `skip_content_for_clear_signals` | Skip extraction for obvious filenames | `true` |

### Entity Configuration

| Option | Description |
|--------|-------------|
| `self_company_names` | Your company names (excluded from entity detection) |
| `internal_employees` | Known employees (for context, not folders) |
| `known_vendors` | Companies that sell TO you |
| `known_customers_active` | Companies you sell TO (active) |
| `known_customers_terminated` | Former customers (still route to Customers/) |
| `auto_category_patterns` | Regex patterns for auto-categorization |
| `generic_filename_patterns` | Patterns for files needing manual review |

### config/entity-mappings.json

Pre-seed known customers/projects and their variations:

```json
{
  "entity_type": "customer",
  "entity_mappings": {
    "Acme Corporation": ["Acme Corp", "Acme", "ACME Inc"],
    "Beta Technologies": ["Beta Tech", "BetaTech", "Beta"]
  },
  "learned_entities": [],
  "fuzzy_matches_pending_confirmation": []
}
```

Sift adds newly detected entities to `learned_entities` as it processes files.

---

## Usage

### Quick Start

```bash
# 1. Analyze and propose structure
python main.py --phase structure

# 2. Review output/structure-proposal.md, then process
python main.py --phase process

# 3. Review output/unknowns-wave1.md, make decisions

# 4. Continue processing (runs next wave)
python main.py --phase process

# 5. When all waves done, deduplicate
python main.py --phase dedup

# 6. Clean up empty folders
python main.py --phase cleanup
```

### Command Reference

```bash
# Analyze source directories and propose archive structure
python main.py --phase structure

# Process files (moves high-confidence, batches unknowns)
python main.py --phase process

# Preview what would happen without moving anything
python main.py --phase process --dry-run

# Find and remove duplicate files
python main.py --phase dedup

# Remove empty folders from source paths
python main.py --phase cleanup

# Resume from last checkpoint after interruption
python main.py --resume

# Test on a small subset first
python main.py --phase structure --test-mode --limit 50

# Use a custom config file
python main.py --phase structure --config /path/to/config.json
```

### CLI Options

| Option | Description |
|--------|-------------|
| `--phase` | Phase to run: `structure`, `process`, `dedup`, `cleanup` |
| `--resume` | Continue from last checkpoint |
| `--dry-run` | Preview actions without making changes |
| `--config` | Path to config file (default: `config/config.json`) |
| `--test-mode` | Run with `--limit 50` for testing |
| `--limit N` | Process only N files |

---

## Output Files

All output goes to the `output/` directory:

| File | Description |
|------|-------------|
| `structure-proposal.md` | Proposed archive structure from Phase 0 |
| `unknowns-wave1.md` | Files needing human review (Wave 1) |
| `unknowns-wave2.md` | Files needing human review (Wave 2) |
| `dedup-report.md` | Duplicate files found and recommendations |
| `dry-run-report.md` | Preview of what would happen |
| `final-summary.md` | End-of-run statistics |

### Example: unknowns-wave1.md

```markdown
# Wave 1 Unknowns - Needs Human Review

## File 1

- **Path:** `/Documents/Work/ambiguous_file.docx`
- **Filename:** ambiguous_file.docx
- **Modified:** 2023-04-15

### AI Analysis
- **Proposed Category:** Customers/Acme Corp
- **Confidence:** 4/10
- **Reasoning:** File mentions both "Acme" and "Beta Corp". Unable to determine primary association.

### Self-Critique
Content references Acme in the header but discusses Beta Corp project details throughout. This may be a cross-client collaboration document.

### Decision Required
- **A)** Customers/Acme Corp (AI suggestion)
- **B)** Customers/Beta Corp
- **C)** Projects/Multi-Client
- **D)** Skip this file
- **E)** Other (specify category)
```

---

## Architecture

### Directory Structure

```
sift-ai/
├── config/
│   ├── config.example.json       # Template (committed)
│   ├── config.json               # Your config (gitignored)
│   ├── entity-mappings.json      # Learned entity names (gitignored)
│   └── prompt-refinements.json   # Learned improvements (gitignored)
├── logs/
│   ├── run-YYYYMMDD-HHMMSS.log   # Action log
│   └── checkpoint.json           # Resume state
├── output/
│   ├── structure-proposal.md
│   ├── unknowns-wave1.md
│   └── final-summary.md
├── sift/
│   ├── __init__.py
│   ├── config.py                 # Configuration management
│   ├── scanner.py                # File tree walking
│   ├── extractor.py              # Content extraction
│   ├── entities.py               # Entity detection
│   ├── categorizer.py            # AI categorization
│   ├── deduplicator.py           # Duplicate detection
│   ├── checkpoint.py             # State persistence
│   ├── mover.py                  # File operations
│   └── reports.py                # Report generation
├── main.py                       # CLI entry point
├── requirements.txt
├── README.md
└── LICENSE
```

### Module Overview

| Module | Responsibility |
|--------|----------------|
| `config.py` | Load/validate configuration, manage paths |
| `scanner.py` | Walk directory trees, collect file metadata |
| `extractor.py` | Extract text from Office docs, PDFs |
| `entities.py` | Detect and fuzzy-match entity names |
| `categorizer.py` | AI categorization with self-critique |
| `deduplicator.py` | Three-tier duplicate detection |
| `checkpoint.py` | Save/restore processing state |
| `mover.py` | File move/delete operations |
| `reports.py` | Generate markdown reports |

---

## AI Prompts

### Categorization Prompt

```
You are categorizing a file for archive organization.

File metadata:
- Path: {path}
- Filename: {filename}
- Modified: {date}

Content preview:
{content_preview}

Known customers: Acme Corp, Beta Technologies, ...

Approved archive structure:
- Customers/{Customer Name}/
- Projects/
- Admin/
- Archive-Pre-2023/

Other files in this folder already categorized:
- Invoice_Acme_2023.pdf → Customers/Acme Corp (confidence 9)
- Meeting_Notes.docx → Customers/Acme Corp (confidence 8)

Return JSON:
{
  "category": "Customers/Acme Corp",
  "entity_detected": "Acme Corp",
  "confidence": 8,
  "reasoning": "Content discusses Acme project timeline",
  "action": "move"
}
```

### Self-Critique Prompt

```
You categorized this file as: Customers/Acme Corp
Confidence: 7
Reasoning: Filename contains 'Acme'

Now critique your decision:
1. What could be wrong with this categorization?
2. What alternative interpretations exist?
3. After self-review, what is your final category and confidence?

Return JSON:
{
  "original_category": "Customers/Acme Corp",
  "original_confidence": 7,
  "critique": "File mentions Acme but is actually a template",
  "alternative_interpretations": ["Admin/Templates", "Projects/General"],
  "final_category": "Admin/Templates",
  "final_confidence": 8,
  "changed": true
}
```

---

## Safety Features

### Backup Confirmation
On first run, Sift requires explicit confirmation that you've backed up your files:

```
⚠  BACKUP CONFIRMATION REQUIRED

Sift will move and delete files. This is not easily reversible.

Have you created a backup of your source directories? (yes/no):
```

### Dry Run Mode
Preview all actions without moving anything:

```bash
python main.py --phase process --dry-run
```

### Checkpoint System
Progress is saved after every file. If interrupted:
- `Ctrl+C` saves current state
- `python main.py --resume` continues exactly where you left off

### Action Logging
Every move and delete is logged to `logs/run-YYYYMMDD-HHMMSS.log`:

```
[2024-12-09 14:30:15] [ACTION] MOVED: /Documents/invoice.pdf -> /Archive/Customers/Acme/invoice.pdf
[2024-12-09 14:30:16] [ACTION] DELETED: /Documents/invoice_copy.pdf
```

---

## Best Practices

### Start Small
Test on a subset before running on your full document collection:

```bash
python main.py --phase structure --test-mode --limit 50
```

### Review the Structure Proposal
The AI-proposed structure in `output/structure-proposal.md` is just a suggestion. Edit it to match your preferences before processing.

### Seed Known Entities
Pre-populate `config/entity-mappings.json` with your known customers/projects. This dramatically improves accuracy from the start.

### Process in Waves
Don't try to finish in one session. The wave system lets you:
1. Process a batch
2. Review unknowns
3. Refine understanding
4. Process next wave with improved accuracy

### Check Unknowns Carefully
The files in `unknowns-waveN.md` are there because the AI wasn't confident. These often reveal:
- Edge cases in your categorization scheme
- Entities that should be added to mappings
- Files that genuinely need human judgment

---

## Troubleshooting

### "Config file not found"
Copy the example config:
```bash
cp config/config.example.json config/config.json
```

### "API key not found"
Set the environment variable:
```bash
export ANTHROPIC_API_KEY=sk-ant-xxxxx
```

### "No files found to process"
Check that:
1. `source_paths` in config point to existing directories
2. Files have extensions listed in `process_extensions`
3. Directories aren't in `skip_folders`

### High API costs
- Use `--limit` to process in smaller batches
- Increase `confidence_threshold` to reduce self-critique passes
- Disable `self_critique_enabled` for first pass

### Slow processing
- Enable parallel processing with `parallel_batch_size: 10` (default)
- Content extraction is the bottleneck for sequential mode
- Increase `max_file_size_mb_for_content` to skip large files
- PDFs are slowest; consider skipping with `skip_extensions`

---

## Contributing

Contributions welcome! Please:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

### Development Setup

```bash
git clone https://github.com/yourusername/sift-ai.git
cd sift-ai
python -m venv venv
source venv/bin/activate  # or `venv\Scripts\activate` on Windows
pip install -r requirements.txt
```

---

## License

MIT License - see [LICENSE](LICENSE) file.

---

## Acknowledgments

- Built with [Claude API](https://anthropic.com) by Anthropic
- Inspired by years of accumulated document chaos

---

## Roadmap

- [x] Parallel processing (10x speed improvement)
- [x] Legacy .doc file support
- [x] PDF Vision fallback for image-based PDFs
- [x] Vendor vs Customer distinction
- [x] Generic filename detection
- [ ] Web UI for reviewing unknowns
- [ ] Support for image files (OCR)
- [ ] Email file (.eml, .msg) extraction
- [ ] Integration with cloud storage (OneDrive, Google Drive)
- [ ] Batch cost estimation before processing
- [ ] Export to different archive formats
