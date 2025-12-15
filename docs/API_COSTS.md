# API Cost Estimation

Sift uses the Claude API, which has usage-based pricing. This document helps estimate costs.

## Claude Opus 4.5 Pricing

As of December 2024 (check [Anthropic pricing](https://www.anthropic.com/pricing) for current rates):

| Type | Price |
|------|-------|
| Input tokens | $15 / 1M tokens |
| Output tokens | $75 / 1M tokens |

## Tokens Per File

Each file requires 1-2 API calls depending on configuration.

### Categorization Call

| Component | Approximate Tokens |
|-----------|-------------------|
| System prompt + structure | ~500 input |
| File metadata | ~100 input |
| Content preview (up to 5000 chars) | ~1500 input |
| Entity context | ~100 input |
| Sibling context | ~200 input |
| **Total input** | **~2400 tokens** |
| JSON response | ~150 output |
| **Total output** | **~150 tokens** |

### Self-Critique Call (if enabled)

| Component | Approximate Tokens |
|-----------|-------------------|
| Original decision | ~300 input |
| Critique prompt | ~200 input |
| **Total input** | **~500 tokens** |
| Critique response | ~200 output |
| **Total output** | **~200 tokens** |

## Cost Per File

### Without Self-Critique

```
Input:  2,400 tokens × $15/1M = $0.036
Output:   150 tokens × $75/1M = $0.011
Total:                         $0.047 per file
```

### With Self-Critique (borderline files only)

Assuming 30% of files trigger self-critique:

```
Base cost:       $0.047
Critique (30%):  $0.015 × 0.30 = $0.005
Total:           ~$0.052 per file
```

## Batch Estimates

| Files | Without Critique | With Critique |
|-------|-----------------|---------------|
| 100 | $4.70 | $5.20 |
| 500 | $23.50 | $26.00 |
| 1,000 | $47.00 | $52.00 |
| 5,000 | $235.00 | $260.00 |
| 10,000 | $470.00 | $520.00 |

## Cost Reduction Strategies

### 1. Disable Self-Critique

Set in config:
```json
{
  "self_critique_enabled": false
}
```
Saves ~10% on typical runs.

### 2. Increase Confidence Threshold

```json
{
  "confidence_threshold": 8
}
```
Higher threshold means fewer files need self-critique, but more end up in unknowns.

### 3. Skip Large Files

```json
{
  "max_file_size_mb_for_content": 10
}
```
Smaller files = shorter content = fewer tokens.

### 4. Reduce Content Preview

Edit `sift/categorizer.py` to reduce `max_chars` in content truncation:
```python
content_section = f"Content preview:\n{content_preview[:2000]}\n"
```

### 5. Skip Content-Heavy Extensions

Add to `skip_extensions` for first pass:
```json
{
  "skip_extensions": [".pdf", ".pptx"]
}
```
Process filename-only first, then do content-rich pass on unknowns.

### 6. Use Test Mode First

```bash
python main.py --phase structure --test-mode --limit 50
```
Process 50 files (~$2.50) to validate your configuration.

## Deduplication Costs

AI-based deduplication (Tier 3) makes additional API calls:

```
Per comparison: ~$0.03
Comparisons per folder: (n × (n-1)) / 2
```

For a folder with 10 similar files: 45 comparisons = ~$1.35

To reduce:
- Hash and pattern matching (Tiers 1-2) are free
- AI comparison only runs on remaining files
- Only compares within same folder + extension

## Structure Analysis Cost

Phase 0 makes one API call with scan summary:

```
~5,000 input tokens + ~1,000 output tokens
≈ $0.15 per run
```

## Total Project Estimate

For a typical 5,000 file archive project:

| Phase | Estimated Cost |
|-------|---------------|
| Structure analysis | $0.15 |
| Wave 1 processing | $235.00 |
| Wave 2 (unknowns) | $25.00 |
| Deduplication | $50.00 |
| **Total** | **~$310** |

## Monitoring Costs

Check your usage at: https://console.anthropic.com/usage

## Budget Mode (Future)

Planned features for cost control:
- [ ] Pre-run cost estimation
- [ ] Budget limits with pause
- [ ] Cheaper model option for bulk processing
- [ ] Local LLM fallback
