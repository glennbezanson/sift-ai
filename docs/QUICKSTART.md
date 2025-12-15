# Quick Start Guide

Get Sift up and running in 5 minutes.

## 1. Install

```bash
# Clone
git clone https://github.com/yourusername/sift-ai.git
cd sift-ai

# Install dependencies
pip install -r requirements.txt
```

## 2. Configure

```bash
# Copy example config
cp config/config.example.json config/config.json
```

Edit `config/config.json`:

```json
{
  "source_paths": [
    "C:/Users/YOU/Documents/OldFiles"
  ],
  "archive_destination": "C:/Users/YOU/Archive"
}
```

## 3. Set API Key

```bash
# Windows PowerShell
$env:ANTHROPIC_API_KEY="sk-ant-your-key-here"

# Windows CMD
set ANTHROPIC_API_KEY=sk-ant-your-key-here

# Linux/Mac
export ANTHROPIC_API_KEY=sk-ant-your-key-here
```

## 4. Run

```bash
# Step 1: Analyze your files
python main.py --phase structure

# Step 2: Review output/structure-proposal.md

# Step 3: Process files (dry run first!)
python main.py --phase process --dry-run

# Step 4: Process for real
python main.py --phase process

# Step 5: Review output/unknowns-wave1.md
# Make decisions on ambiguous files

# Step 6: Continue until done
python main.py --phase process

# Step 7: Deduplicate
python main.py --phase dedup

# Step 8: Clean up empty folders
python main.py --phase cleanup
```

## 5. Key Commands

| Command | What it does |
|---------|--------------|
| `--phase structure` | Analyze and propose folder structure |
| `--phase process` | Categorize and move files |
| `--phase process --dry-run` | Preview without moving |
| `--phase dedup` | Find and remove duplicates |
| `--phase cleanup` | Remove empty folders |
| `--resume` | Continue after interruption |
| `--test-mode` | Test on 50 files only |

## Tips

1. **Always backup first** — Sift will ask you to confirm
2. **Start with dry-run** — See what would happen
3. **Test on subset** — Use `--limit 100` first
4. **Review unknowns** — The AI flags files it's unsure about
5. **Iterate** — Each wave gets smarter as patterns emerge

## Next Steps

- Read the full [README](../README.md) for detailed configuration
- Check [ARCHITECTURE.md](ARCHITECTURE.md) for technical details
- See [TROUBLESHOOTING.md](TROUBLESHOOTING.md) if you hit issues
