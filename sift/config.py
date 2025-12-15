"""
Configuration management for Sift.
"""

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class SiftConfig:
    """Configuration settings for Sift."""

    source_paths: list[str] = field(default_factory=list)
    archive_destination: str = ""
    confidence_threshold: int = 7
    skip_folders: list[str] = field(default_factory=lambda: [
        "node_modules", ".git", "__pycache__", ".obsidian", ".vscode", "venv", ".env"
    ])
    skip_extensions: list[str] = field(default_factory=lambda: [".md", ".log", ".tmp", ".bak"])
    process_extensions: list[str] = field(default_factory=lambda: [
        ".docx", ".doc", ".xlsx", ".xls", ".pptx", ".ppt", ".pdf", ".txt", ".csv"
    ])
    max_file_size_mb_for_content: int = 50
    api_key_env_var: str = "ANTHROPIC_API_KEY"
    api_base_url: Optional[str] = None  # For Azure/proxy endpoints
    model: str = "claude-opus-4-5-20250514"  # Model name (may differ on Azure)
    entity_type: str = "customer"
    entity_mappings_file: str = "config/entity-mappings.json"
    batch_size: int = 50
    max_retries: int = 3
    retry_delay_seconds: int = 2
    self_critique_enabled: bool = True
    sibling_context_enabled: bool = True
    sibling_context_limit: int = 10

    # Self-company names (exclude from entity detection)
    self_company_names: list[str] = field(default_factory=list)

    # Internal employees (for context, not entity folders)
    internal_employees: dict[str, dict] = field(default_factory=dict)

    # Known vendors (separate from customers)
    known_vendors: dict[str, list[str]] = field(default_factory=dict)

    # Known customers (active)
    known_customers_active: dict[str, list[str]] = field(default_factory=dict)

    # Known customers (terminated) - with reason
    known_customers_terminated: dict[str, dict] = field(default_factory=dict)

    # Auto-categorization patterns (filename regex -> category)
    auto_category_patterns: dict[str, str] = field(default_factory=dict)

    # Generic filename patterns that should go to Archive/Review/
    generic_filename_patterns: list[str] = field(default_factory=lambda: [
        r"^Book\d*\.xlsx?$",
        r"^Document\d*\.docx?$",
        r"^Presentation\d*\.pptx?$",
        r"^Untitled",
        r"^New Document",
        r"^Copy of ",
    ])

    # Performance settings
    parallel_batch_size: int = 10  # Number of files to process concurrently
    self_critique_threshold_min: int = 6  # Min confidence for self-critique
    self_critique_threshold_max: int = 8  # Max confidence for self-critique
    skip_content_for_clear_signals: bool = True  # Use metadata-only for obvious files
    batch_process_folders: bool = True  # Process folder siblings together

    # Unknowns report settings (from lessons learned 2025-12-10)
    unknowns_wave_size: int = 100  # Number of files per wave (was 20, too slow)
    auto_skip_folders: list[str] = field(default_factory=lambda: [
        "Downloads", "ZohoAttachments"  # Folders with uncategorizable files
    ])
    auto_cleanup_empty_folders: bool = True  # Clean up empty folders after moves
    generate_folder_grouped_reports: bool = True  # Group unknowns by folder

    # Clear filename signals that don't need content extraction
    clear_category_signals: list[str] = field(default_factory=lambda: [
        r"^Invoice[_\s-]",
        r"^Proposal[_\s-]",
        r"^Contract[_\s-]",
        r"^SOW[_\s-]",
        r"^Resume[_\s-]",
        r"^Meeting[_\s]Notes",
        r"^NDA[_\s-]",
        r"[_\s-]Invoice\.pdf$",
        r"[_\s-]Signed\.pdf$",
        r"[_\s-]Agreement\.pdf$",
    ])

    # Runtime paths
    base_dir: Path = field(default_factory=Path.cwd)

    def __post_init__(self):
        """Validate configuration after initialization."""
        if isinstance(self.base_dir, str):
            self.base_dir = Path(self.base_dir)

    @classmethod
    def load(cls, config_path: Optional[str] = None) -> "SiftConfig":
        """Load configuration from JSON file."""
        if config_path is None:
            config_path = Path.cwd() / "config" / "config.json"
        else:
            config_path = Path(config_path)

        if not config_path.exists():
            raise FileNotFoundError(
                f"Config file not found: {config_path}\n"
                f"Copy config/config.example.json to config/config.json and customize it."
            )

        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        data["base_dir"] = config_path.parent.parent
        return cls(**data)

    def get_api_key(self) -> str:
        """Get API key from environment variable."""
        key = os.environ.get(self.api_key_env_var)
        if not key:
            raise ValueError(
                f"API key not found. Set the {self.api_key_env_var} environment variable."
            )
        return key

    def get_anthropic_client(self):
        """Get configured Anthropic client (supports Azure endpoints)."""
        import anthropic

        if self.api_base_url:
            # Use AnthropicFoundry for Azure AI Services
            try:
                from anthropic import AnthropicFoundry
                return AnthropicFoundry(
                    api_key=self.get_api_key(),
                    base_url=self.api_base_url,
                )
            except ImportError:
                # Fallback to standard client with base_url
                return anthropic.Anthropic(
                    api_key=self.get_api_key(),
                    base_url=self.api_base_url,
                )
        else:
            return anthropic.Anthropic(api_key=self.get_api_key())

    def get_async_anthropic_client(self):
        """Get configured async Anthropic client for parallel processing."""
        import anthropic

        if self.api_base_url:
            # Use AsyncAnthropicFoundry for Azure AI Services
            try:
                from anthropic import AsyncAnthropicFoundry
                return AsyncAnthropicFoundry(
                    api_key=self.get_api_key(),
                    base_url=self.api_base_url,
                )
            except ImportError:
                # Fallback to standard async client with base_url
                return anthropic.AsyncAnthropic(
                    api_key=self.get_api_key(),
                    base_url=self.api_base_url,
                )
        else:
            return anthropic.AsyncAnthropic(api_key=self.get_api_key())

    def get_entity_mappings_path(self) -> Path:
        """Get full path to entity mappings file."""
        return self.base_dir / self.entity_mappings_file

    def get_logs_dir(self) -> Path:
        """Get logs directory path."""
        logs_dir = self.base_dir / "logs"
        logs_dir.mkdir(exist_ok=True)
        return logs_dir

    def get_output_dir(self) -> Path:
        """Get output directory path."""
        output_dir = self.base_dir / "output"
        output_dir.mkdir(exist_ok=True)
        return output_dir

    def max_file_size_bytes(self) -> int:
        """Get max file size in bytes."""
        return self.max_file_size_mb_for_content * 1024 * 1024
