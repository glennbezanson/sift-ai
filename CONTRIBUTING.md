# Contributing to Sift

Thank you for your interest in contributing to Sift! This document provides guidelines and information for contributors.

## Getting Started

### Prerequisites

- Python 3.9 or higher
- Git
- An Anthropic API key for testing

### Development Setup

1. Fork the repository on GitHub
2. Clone your fork locally:
   ```bash
   git clone https://github.com/YOUR_USERNAME/sift-ai.git
   cd sift-ai
   ```

3. Create a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # Linux/Mac
   venv\Scripts\activate     # Windows
   ```

4. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

5. Set up configuration:
   ```bash
   cp config/config.example.json config/config.json
   cp config/entity-mappings.example.json config/entity-mappings.json
   ```

6. Set your API key:
   ```bash
   export ANTHROPIC_API_KEY=sk-ant-xxxxx
   ```

## How to Contribute

### Reporting Bugs

Before submitting a bug report:
- Check existing issues to avoid duplicates
- Collect relevant information (Python version, OS, error messages)

When submitting a bug report, include:
- A clear, descriptive title
- Steps to reproduce the issue
- Expected vs actual behavior
- Relevant log output from `logs/`
- Your configuration (with sensitive paths redacted)

### Suggesting Features

Feature suggestions are welcome! Please:
- Check existing issues/discussions first
- Describe the use case and problem being solved
- Explain how the feature would work
- Consider backward compatibility

### Submitting Changes

1. Create a feature branch:
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. Make your changes following our code style

3. Test your changes:
   ```bash
   # Run syntax checks
   python -m py_compile main.py
   python -m py_compile sift/*.py

   # Test with dry-run mode
   python main.py --phase structure --test-mode --limit 10
   python main.py --phase process --dry-run --limit 10
   ```

4. Commit with clear messages:
   ```bash
   git commit -m "Add feature: description of what it does"
   ```

5. Push and create a Pull Request:
   ```bash
   git push origin feature/your-feature-name
   ```

## Code Style

### Python Guidelines

- Follow PEP 8 style guide
- Use type hints for function signatures
- Write docstrings for classes and public methods
- Keep functions focused and under 50 lines when possible
- Use meaningful variable names

### Example

```python
def categorize_file(
    self,
    file_info: FileInfo,
    context: Optional[SiblingContext] = None,
) -> CategorizationResult:
    """
    Categorize a single file using AI analysis.

    Args:
        file_info: Metadata about the file to categorize
        context: Optional context from sibling files

    Returns:
        CategorizationResult with category, confidence, and reasoning
    """
    # Implementation here
```

### Commit Messages

- Use present tense ("Add feature" not "Added feature")
- Keep first line under 50 characters
- Reference issues when relevant ("Fix #123: description")

Good examples:
- `Add support for .msg email files`
- `Fix entity detection for hyphenated names`
- `Improve deduplication performance for large sets`

## Project Structure

```
sift-ai/
├── sift/                 # Core package
│   ├── __init__.py
│   ├── config.py         # Configuration management
│   ├── scanner.py        # File discovery
│   ├── extractor.py      # Content extraction
│   ├── entities.py       # Entity detection
│   ├── categorizer.py    # AI categorization
│   ├── deduplicator.py   # Duplicate detection
│   ├── checkpoint.py     # State management
│   ├── mover.py          # File operations
│   └── reports.py        # Report generation
├── config/               # Configuration files
├── logs/                 # Runtime logs (gitignored)
├── output/               # Generated reports (gitignored)
├── main.py               # CLI entry point
└── requirements.txt
```

### Adding New Features

**New file type support:**
1. Add extraction method to `sift/extractor.py`
2. Add extension to `get_extraction_capabilities()`
3. Update default `process_extensions` in config
4. Add dependency to `requirements.txt` if needed

**New categorization logic:**
1. Modify prompts in `sift/categorizer.py`
2. Update `CategorizationResult` dataclass if new fields needed
3. Update report generation in `sift/reports.py`

**New CLI options:**
1. Add argument to `argparse` in `main.py`
2. Implement handler logic
3. Update `--help` examples

## Testing

Currently, testing is manual. When contributing:

1. Test with `--dry-run` first
2. Test with `--test-mode --limit 50` on real files
3. Verify checkpoint/resume works by interrupting and resuming
4. Check generated reports are valid markdown

Future: We plan to add automated tests. Contributions to test infrastructure are especially welcome!

## Documentation

- Update README.md for user-facing changes
- Add docstrings for new code
- Update configuration examples if adding new options
- Add examples to relevant sections

## Questions?

- Open a GitHub Discussion for general questions
- Open an Issue for bugs or specific feature requests
- Check existing issues/discussions first

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
