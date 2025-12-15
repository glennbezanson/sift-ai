# Troubleshooting Guide

Common issues and their solutions.

## Installation Issues

### "No module named 'anthropic'"

**Problem:** Dependencies not installed.

**Solution:**
```bash
pip install -r requirements.txt
```

### "No module named 'rapidfuzz'"

**Problem:** Fuzzy matching library not installed.

**Solution:**
```bash
pip install rapidfuzz
```

Note: Sift works without rapidfuzz, but entity detection will only use exact substring matching.

### Python version errors

**Problem:** Using Python < 3.9

**Solution:** Sift requires Python 3.9+ for type hints. Check your version:
```bash
python --version
```

---

## Configuration Issues

### "Config file not found"

**Problem:** `config/config.json` doesn't exist.

**Solution:**
```bash
cp config/config.example.json config/config.json
```
Then edit the file with your paths.

### "API key not found"

**Problem:** Environment variable not set.

**Solution:**
```bash
# Windows PowerShell
$env:ANTHROPIC_API_KEY="sk-ant-your-key"

# Windows CMD
set ANTHROPIC_API_KEY=sk-ant-your-key

# Linux/Mac
export ANTHROPIC_API_KEY=sk-ant-your-key
```

Verify it's set:
```bash
echo $env:ANTHROPIC_API_KEY  # PowerShell
echo %ANTHROPIC_API_KEY%     # CMD
echo $ANTHROPIC_API_KEY      # Linux/Mac
```

### "Source path does not exist"

**Problem:** Path in config doesn't exist.

**Solution:** Check the paths in `config.json`:
- Use forward slashes or escaped backslashes: `C:/Users/...` or `C:\\Users\\...`
- Ensure the directories exist
- Check for typos

---

## Runtime Issues

### "No files found to process"

**Causes & Solutions:**

1. **Wrong source path:** Verify paths exist and contain files
2. **Extension filter:** Check `process_extensions` includes your file types
3. **Skip filter:** Check `skip_folders` isn't excluding your folders
4. **All processed:** If resuming, files may already be done

Debug:
```bash
python main.py --phase structure --test-mode --limit 10
```

### API Rate Limits

**Problem:** `RateLimitError` from Anthropic API

**Solution:**
- Sift automatically retries 3 times with backoff
- If persistent, wait a few minutes and resume
- Check your Anthropic usage limits

### Slow Processing

**Causes & Solutions:**

1. **Large files:** Increase `max_file_size_mb_for_content` to skip large files
2. **PDF extraction:** PDFs are slow; consider adding `.pdf` to `skip_extensions` for first pass
3. **Self-critique:** Disable with `"self_critique_enabled": false` for 2x speed
4. **API latency:** Normal; each file requires 1-2 API calls

### Memory Issues

**Problem:** High memory usage on large file sets.

**Solution:**
- Use `--limit N` to process in batches
- Sift uses generators, so memory should be stable
- Check if other processes are consuming memory

### "Permission denied" errors

**Problem:** Can't read/move certain files.

**Solution:**
- Sift logs and skips inaccessible files
- Check file permissions
- Close files that may be open in other applications
- On Windows, some system files are protected

---

## Checkpoint Issues

### "Corrupted checkpoint"

**Problem:** `checkpoint.json` is invalid.

**Solution:**
```bash
# View the checkpoint
cat logs/checkpoint.json

# If corrupted, delete to start fresh
rm logs/checkpoint.json
```

### Resume not working

**Problem:** `--resume` starts from beginning.

**Causes:**
- Checkpoint file was deleted
- Checkpoint shows phase as "complete"
- No pending files remain

**Debug:**
```bash
cat logs/checkpoint.json | head -20
```

### Want to restart completely

**Solution:**
```bash
rm logs/checkpoint.json
rm -rf output/*
python main.py --phase structure
```

---

## Content Extraction Issues

### "[python-docx not installed]"

**Problem:** Missing optional dependency.

**Solution:**
```bash
pip install python-docx
```

### "[PDF extraction failed]"

**Causes:**
- Corrupted PDF
- Encrypted PDF
- Scanned image PDF (no text layer)

**Solution:**
- Sift logs the error and continues
- File will be categorized by filename only (lower confidence)
- For scanned PDFs, OCR support is planned for future

### "[Content extraction failed]"

**Problem:** Unknown error during extraction.

**Solution:**
- Check the log file for details
- File will be categorized by filename only
- Report persistent issues on GitHub

---

## Output Issues

### Reports not generated

**Problem:** No files in `output/` directory.

**Causes:**
- Phase didn't complete
- Error during report generation

**Solution:**
- Check for errors in console output
- Check `logs/run-*.log` for errors
- Try running the phase again

### Markdown formatting broken

**Problem:** Reports look wrong when viewed.

**Solution:**
- Use a markdown viewer (VS Code, GitHub, etc.)
- Raw text view will show markdown syntax

---

## Archive Issues

### Files not moving

**Problem:** Dry-run mode is enabled.

**Solution:**
Remove `--dry-run` flag:
```bash
python main.py --phase process  # Without --dry-run
```

### Duplicate filenames

**Problem:** Multiple files with same name going to same folder.

**Solution:**
Sift automatically adds numeric suffixes:
- `document.docx`
- `document_1.docx`
- `document_2.docx`

### Wrong categorization

**Problem:** AI put files in wrong categories.

**Solutions:**
1. Add the entity to `config/entity-mappings.json`
2. Increase `confidence_threshold` to be more conservative
3. Review and correct in unknowns batch
4. Move files manually and they'll be skipped on next run

---

## Getting Help

If your issue isn't covered here:

1. Check the [GitHub Issues](https://github.com/yourusername/sift-ai/issues)
2. Check the logs in `logs/run-*.log`
3. Open a new issue with:
   - Error message
   - Python version
   - OS
   - Relevant config (redact sensitive paths)
   - Steps to reproduce
