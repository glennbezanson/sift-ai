# Sift AI - Lessons Learned

**Date:** 2025-12-10
**Session:** Production run on OneDrive with ~5,000 files

---

## Session Summary

- **Files processed:** 4,951
- **Moved:** 4,107 files
- **Deleted (version duplicates):** 375 files
- **Unknowns requiring human review:** 468 files
- **Skipped:** 1 file

---

## Key Findings

### 1. Wave Size Too Small (Critical)

**Problem:** The unknowns report generated waves of only 20 files at a time. With 446 unknowns remaining (402 in Downloads folder alone), this created excessive back-and-forth.

**Solution:**
- Increase default wave size from 20 to 100 files
- Add `unknowns_wave_size` config option
- Generate grouped reports by folder instead of flat lists

### 2. Downloads/ZohoAttachments Should Auto-Skip

**Problem:** 402 of 446 unknowns were in the Downloads folder. 193 were ZohoAttachments with cryptic hashed filenames that provide zero categorization signal. The AI marked these as "Unknown" with 0-2 confidence because the filenames are literally random hashes.

**Solution:**
- Add `auto_skip_folders` config option: `["Downloads", "ZohoAttachments"]`
- These folders should be flagged as "user cleanup needed" rather than AI-categorized
- Generate a separate "Downloads Cleanup Report" instead of mixing with unknowns

### 3. Full Paths Critical for Human Review

**Problem:** Early wave reports only showed filename without full path, making it impossible to make decisions.

**Solution:**
- Always include full path in unknowns reports
- Group by source folder for context
- Include folder summary at top of report

### 4. Bulk Actions Preferred Over Per-File Decisions

**Problem:** The wave reports expected decisions for each file individually. Users want to say "DELETE all ZohoAttachments" or "SKIP entire Archive folder".

**Solution:**
- Support bulk folder actions in reports
- Add decision format options: "FOLDER: ACTION" syntax
- Group files by folder and show counts

### 5. Empty Folder Cleanup Should Be Automatic

**Problem:** After bulk moves/deletes, many empty folders remained. Required manual cleanup pass.

**Solution:**
- Add `auto_cleanup_empty_folders` config option (default: true)
- Run cleanup after each batch of moves
- Log what was removed

### 6. Archive Folder Files Should Skip by Default

**Problem:** Files already in Archive/a. Work/ were being flagged for review. These are intentionally archived and shouldn't need AI categorization.

**Solution:**
- Add `pre_archived_folders` config option
- Skip files already in designated archive locations
- Or add to `skip_folders` in config

### 7. Version Duplicate Detection Works Well

The pattern-based deduplication correctly identified 375 version duplicates (v1/v2, (1)/(2) patterns). This saved significant manual work.

### 8. Confidence Threshold May Be Too High

**Problem:** Many files marked as "unknown" with confidence 5-6 could have been auto-moved with lower threshold.

**Observation:** Current threshold is 7. Consider:
- Threshold 6 for files with clear customer name matches
- Threshold 5 for files matching known patterns
- Only human review for confidence < 5

---

## Configuration Recommendations

```json
{
  "unknowns_wave_size": 100,
  "auto_skip_folders": ["Downloads", "ZohoAttachments"],
  "pre_archived_folders": ["Archive"],
  "auto_cleanup_empty_folders": true,
  "confidence_threshold": 6,
  "generate_folder_grouped_reports": true
}
```

---

## Report Format Improvements

### Current (Wave N - 20 files)
```markdown
## File 1
- Path: `...`
- Filename: xyz.pdf
...
```

### Proposed (Folder-Grouped)
```markdown
## Summary by Folder
| Folder | Count | Size | Suggested Action |
|--------|-------|------|------------------|
| Downloads | 209 | 401 MB | SKIP/DELETE |
| ZohoAttachments | 193 | 16 MB | DELETE ALL |
| OneDrive Root | 13 | 33 MB | REVIEW |

## OneDrive Root (13 files)
| # | Filename | Full Path | Modified | Size | Action |
```

---

## Code Changes Needed

1. **config.py**
   - Add `unknowns_wave_size: int = 100`
   - Add `auto_skip_folders: list[str] = []`
   - Add `auto_cleanup_empty_folders: bool = True`
   - Add `generate_folder_grouped_reports: bool = True`

2. **reports.py**
   - Rewrite `generate_unknowns_report()` to group by folder
   - Add folder summary table at top
   - Include full paths always
   - Support configurable wave size

3. **main.py**
   - Call cleanup after moves if `auto_cleanup_empty_folders`
   - Skip files in `auto_skip_folders` before categorization

4. **scanner.py**
   - Add option to exclude auto-skip folders from scan entirely

---

## Performance Notes

- Parallel batch processing (5 concurrent) worked well
- ~5000 files processed in single session
- Azure AI Foundry endpoint stable throughout
- Checkpoint recovery worked correctly when resuming

---

## Future Improvements

1. **Interactive CLI for bulk decisions** - Allow "Downloads: DELETE ALL" commands directly
2. **Pre-scan folder analysis** - Identify problematic folders (Downloads, random hashes) before AI processing
3. **Smart folder routing** - Route Downloads to "Review/Downloads" subfolder instead of unknown
4. **Content hash dedup** - Already implemented but not used in this run
5. **Learned entity persistence** - Save entity mappings discovered during run
