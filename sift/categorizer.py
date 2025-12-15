"""
AI-powered file categorization engine for Sift.
Uses Claude API to analyze and categorize files with self-critique.
Supports async parallel processing for improved performance.
"""

import asyncio
import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import anthropic

from .config import SiftConfig
from .entities import EntityManager
from .extractor import ContentExtractor
from .scanner import FileInfo


# Model is now configured via config.model


@dataclass
class CategorizationResult:
    """Result of categorizing a single file."""

    file_info: FileInfo
    category: str
    confidence: int
    entity_detected: Optional[str]
    reasoning: str
    action: str  # "move", "skip", "unknown"
    original_category: Optional[str] = None
    original_confidence: Optional[int] = None
    critique: Optional[str] = None
    alternatives: Optional[list[str]] = None
    changed_after_critique: bool = False


@dataclass
class SiblingContext:
    """Context about already-categorized sibling files."""

    categorized_files: list[tuple[str, str, int]]  # (filename, category, confidence)


# Path patterns for auto-routing based on existing folder structure
PATH_PATTERNS = [
    # Customer folders (various naming conventions)
    (r"a\. Customers[/\\]([^/\\]+)", "Customers/{match}"),
    (r"Customers[/\\]([^/\\]+)", "Customers/{match}"),
    # Vendor folders
    (r"Vendors[/\\]([^/\\]+)", "Vendors/{match}"),
    # Edge Integration Services
    (r"b\. Edge Integration Services", "Services/EIC"),
    # Functional folders
    (r"HR[/\\]", "HR"),
    (r"Finance[/\\]", "Finance"),
    (r"Governance[/\\]", "Governance"),
    (r"Templates[/\\]", "Templates"),
    (r"Contracts[/\\]", "Contracts-Legal"),
    (r"Legal[/\\]", "Contracts-Legal"),
    (r"Admin[/\\]", "Admin"),
    (r"Projects[/\\]", "Projects"),
    (r"Presentations[/\\]", "Presentations"),
]

# Known customer folder names to map
KNOWN_CUSTOMER_FOLDERS = [
    "AVS",
    "CCMR3",
    "Colonial Pipeline",
    "Aspect",
    "Alvaria",
    "Alston & Bird LLP",
    "Alston Bird",
    "CGL Security Services",
    "CGL",
    "CVS",
    "FN Global Meat Limited",
    "FN Global",
    "ACI Worldwide",
    "ACI",
    "Alliant",
    "Tellerix",
    "VMware",
]


def get_category_from_path(file_path: str) -> tuple[Optional[str], int, Optional[str]]:
    """
    Extract category from existing folder structure.
    Returns (category, confidence, entity_detected).
    """
    # Normalize path separators
    normalized_path = str(file_path).replace("\\", "/")

    # Check path patterns
    for pattern, category_template in PATH_PATTERNS:
        match = re.search(pattern, normalized_path, re.IGNORECASE)
        if match:
            if "{match}" in category_template:
                entity = match.group(1)
                category = category_template.replace("{match}", entity)
                return category, 9, entity
            return category_template, 9, None

    # Check for known customer folder names in path
    for customer in KNOWN_CUSTOMER_FOLDERS:
        # Look for customer name as a folder in the path
        pattern = rf"[/\\]{re.escape(customer)}[/\\]"
        if re.search(pattern, normalized_path, re.IGNORECASE):
            return f"Customers/{customer}", 9, customer

    return None, 0, None


class Categorizer:
    """AI-powered file categorizer with self-critique."""

    def __init__(
        self,
        config: SiftConfig,
        entity_manager: EntityManager,
        extractor: ContentExtractor,
        archive_structure: list[str],
    ):
        self.config = config
        self.entity_manager = entity_manager
        self.extractor = extractor
        self.archive_structure = archive_structure
        self.client = config.get_anthropic_client()

        # Track categorizations by folder for sibling context
        self.folder_categorizations: dict[str, list[tuple[str, str, int]]] = {}

    def _build_categorization_prompt(
        self,
        file_info: FileInfo,
        content_preview: Optional[str],
        sibling_context: Optional[SiblingContext],
    ) -> str:
        """Build the initial categorization prompt."""
        structure_text = "\n".join(f"- {cat}" for cat in self.archive_structure)
        entity_context = self.entity_manager.get_entity_context_for_prompt()

        sibling_text = ""
        if sibling_context and sibling_context.categorized_files:
            sibling_text = "\n\nOther files in this folder already categorized:\n"
            for filename, category, conf in sibling_context.categorized_files[
                : self.config.sibling_context_limit
            ]:
                sibling_text += f"- {filename} → {category} (confidence {conf})\n"

        content_section = ""
        if content_preview:
            content_section = f"""
Content preview:
---
{content_preview[:3000]}
---
"""

        # Build self-company exclusion text
        self_company_text = ""
        if self.config.self_company_names:
            names = ", ".join(f'"{n}"' for n in self.config.self_company_names)
            self_company_text = f"""
IMPORTANT - Self-Company Exclusion:
The following names are the user's OWN company - NEVER create entity folders for them:
{names}

If a document references these, it's internal documentation, not a customer record.
When you see "Proposal for {self.config.self_company_names[0]}" - this is a VENDOR proposing TO the user's company.
"""

        # Build internal employee context
        employee_text = ""
        if self.config.internal_employees:
            employee_text = "\nInternal Employees (for context only - do NOT create folders for people):\n"
            for name, info in self.config.internal_employees.items():
                role = info.get("role", "")
                team = info.get("team", "")
                employee_text += f"- {name}: {role}, {team} team\n"
            employee_text += "\nPerson names are NOT entities. Categorize by company/project, not person.\n"

        # Build vendor context
        vendor_text = ""
        if self.config.known_vendors:
            vendor_text = "\nKnown Vendors (use Vendors/{name}/ folder):\n"
            for vendor, aliases in self.config.known_vendors.items():
                if aliases:
                    vendor_text += f"- {vendor} (aliases: {', '.join(aliases)})\n"
                else:
                    vendor_text += f"- {vendor}\n"

        # Build customer context (active and terminated)
        customer_text = ""
        if self.config.known_customers_active:
            customer_text = "\nKnown Customers (Active):\n"
            for customer, aliases in self.config.known_customers_active.items():
                if aliases:
                    customer_text += f"- {customer} (aliases: {', '.join(aliases)})\n"
                else:
                    customer_text += f"- {customer}\n"

        if self.config.known_customers_terminated:
            customer_text += "\nKnown Customers (Terminated - still route to Customers/):\n"
            for customer, info in self.config.known_customers_terminated.items():
                reason = info.get("reason", "")
                aliases = info.get("aliases", [])
                alias_str = f" (aliases: {', '.join(aliases)})" if aliases else ""
                customer_text += f"- {customer}{alias_str} - {reason}\n"

        return f"""You are categorizing a file for archive organization.

File metadata:
- Path: {file_info.relative_path}
- Filename: {file_info.filename}
- Extension: {file_info.extension}
- Modified: {file_info.modified_time.strftime('%Y-%m-%d')}
- Size: {file_info.size_bytes:,} bytes
{content_section}
{entity_context}
{self_company_text}
{employee_text}
{vendor_text}
{customer_text}

Approved archive structure:
{structure_text}
{sibling_text}

CATEGORIZATION RULES:

1. VENDOR vs CUSTOMER distinction:
   VENDOR indicators (route to Vendors/{{Vendor Name}}/):
   - "Proposal for Edge Solutions" (proposal TO user's company)
   - "Invoice to Edge Solutions"
   - "Membership", "subscription", "services offered to us"
   - Legal firms, consultancies, service providers selling to us

   CUSTOMER indicators (route to Customers/{{Customer Name}}/):
   - "Proposal to {{company}}" (proposal FROM user to them)
   - "SOW for {{company}}"
   - "Engagement", "project delivery", "customer"
   - Companies we provide services to

2. Security/Risk questionnaires:
   Files containing "security questionnaire", "risk questionnaire", "supply chain risk",
   "vendor assessment", "third party risk" → Governance/Security-Questionnaires/

3. Terminated/failed customers are STILL customers:
   - Files mentioning "terminated", "closed", "failed screening", "background check failed",
     "compliance rejection", "loss of banking relationship" → Customers/{{Company Name}}/
   - Do NOT create separate "Terminated" subfolder

4. Person names are NOT entities:
   - Companies/Organizations → Create entity folders
   - Individual person names → Do NOT create entity folders
   - If a person name is detected, note it as context but categorize by company/project

5. Similar entity names:
   - If detected entity is very similar to user's company name, flag as "unknown" for human review

6. Category routing:
   | Content Type | Route To |
   |--------------|----------|
   | Security questionnaires | Governance/Security-Questionnaires/ |
   | Internal finance/spend docs | Internal/Finance/ |
   | Vendor invoices | Vendors/{{Vendor Name}}/Invoices/ |
   | Vendor proposals | Vendors/{{Vendor Name}}/ |
   | Customer work | Customers/{{Customer Name}}/ |
   | Sales templates | Templates/Sales/ |
   | HR expense forms | HR/Expenses/ |
   | Pre-2024 internal content | Archive-Pre-2025/ |

Categorize this file. Return ONLY valid JSON:
{{
  "category": "Category/Subcategory from structure above",
  "entity_detected": "Company/Organization name if detected (NOT person names), otherwise null",
  "entity_type": "customer" or "vendor" or null,
  "confidence": 1-10,
  "reasoning": "Brief explanation of why this categorization",
  "action": "move"
}}

If you cannot confidently categorize (confidence < {self.config.confidence_threshold}), set action to "unknown".
If the file should be skipped entirely, set action to "skip".
"""

    def _build_critique_prompt(self, result_json: dict) -> str:
        """Build the self-critique prompt."""
        return f"""You categorized this file as: {result_json['category']}
Confidence: {result_json['confidence']}
Reasoning: {result_json['reasoning']}

Now critique your decision:
1. What could be wrong with this categorization?
2. What alternative interpretations exist?
3. After self-review, what is your final category and confidence?

Return ONLY valid JSON:
{{
  "original_category": "{result_json['category']}",
  "original_confidence": {result_json['confidence']},
  "critique": "Your critique here",
  "alternative_interpretations": ["Alt 1", "Alt 2"],
  "final_category": "Final decision",
  "final_confidence": 1-10,
  "changed": true or false
}}
"""

    def _call_api(self, prompt: str, retry_count: int = 0) -> Optional[str]:
        """Call Claude API with retry logic."""
        try:
            response = self.client.messages.create(
                model=self.config.model,
                max_tokens=1024,
                messages=[{"role": "user", "content": prompt}],
            )
            return response.content[0].text
        except anthropic.RateLimitError:
            if retry_count < self.config.max_retries:
                time.sleep(self.config.retry_delay_seconds * (retry_count + 1))
                return self._call_api(prompt, retry_count + 1)
            raise
        except anthropic.APIError as e:
            if retry_count < self.config.max_retries:
                time.sleep(self.config.retry_delay_seconds)
                return self._call_api(prompt, retry_count + 1)
            raise

    def _parse_json_response(self, response: str) -> Optional[dict]:
        """Extract and parse JSON from response."""
        # Try direct parse first
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            pass

        # Try to find JSON in response
        import re

        json_match = re.search(r"\{[\s\S]*\}", response)
        if json_match:
            try:
                return json.loads(json_match.group())
            except json.JSONDecodeError:
                pass

        return None

    def _check_path_category(self, file_info: FileInfo) -> Optional[CategorizationResult]:
        """Check if file path indicates category from existing folder structure."""
        category, confidence, entity = get_category_from_path(str(file_info.path))
        if category and confidence >= 8:
            return CategorizationResult(
                file_info=file_info,
                category=category,
                confidence=confidence,
                entity_detected=entity,
                reasoning=f"Derived from existing folder structure: {file_info.relative_path}",
                action="move",
            )
        return None

    def _check_auto_patterns(self, file_info: FileInfo) -> Optional[CategorizationResult]:
        """Check if filename matches any auto-categorization patterns."""
        if not self.config.auto_category_patterns:
            return None

        for pattern, category in self.config.auto_category_patterns.items():
            if re.match(pattern, file_info.filename, re.IGNORECASE):
                return CategorizationResult(
                    file_info=file_info,
                    category=category,
                    confidence=9,
                    entity_detected=None,
                    reasoning=f"Auto-categorized via filename pattern match: {pattern}",
                    action="move",
                )
        return None

    def _check_generic_filename(self, file_info: FileInfo) -> Optional[CategorizationResult]:
        """Check if filename is a generic/default name that should go to Archive/Review."""
        for pattern in self.config.generic_filename_patterns:
            if re.match(pattern, file_info.filename, re.IGNORECASE):
                return CategorizationResult(
                    file_info=file_info,
                    category="Archive/Review",
                    confidence=8,
                    entity_detected=None,
                    reasoning=f"Generic/default filename detected: {file_info.filename} - needs manual review",
                    action="move",
                )
        return None

    def _has_clear_category_signal(self, filename: str) -> bool:
        """Check if filename has clear signals that don't need content extraction."""
        if not self.config.skip_content_for_clear_signals:
            return False

        for pattern in self.config.clear_category_signals:
            if re.search(pattern, filename, re.IGNORECASE):
                return True

        # Check if filename contains a known entity
        known_entities = self.entity_manager.get_all_entity_names()
        for entity in known_entities:
            if entity.lower() in filename.lower():
                return True

        return False

    def _needs_self_critique(self, confidence: int) -> bool:
        """Determine if self-critique is needed based on confidence thresholds."""
        if not self.config.self_critique_enabled:
            return False
        # Only self-critique for borderline confidence (configurable thresholds)
        return (
            confidence >= self.config.self_critique_threshold_min
            and confidence <= self.config.self_critique_threshold_max
        )

    def categorize(self, file_info: FileInfo) -> CategorizationResult:
        """Categorize a single file using AI."""
        # Step 0: Check if existing folder structure already tells us the category
        path_result = self._check_path_category(file_info)
        if path_result:
            return path_result

        # Check auto-categorization patterns (e.g., Microsoft invoices)
        auto_result = self._check_auto_patterns(file_info)
        if auto_result:
            return auto_result

        # Check for generic/default filenames (Book1.xlsx, Document1.docx, etc.)
        generic_result = self._check_generic_filename(file_info)
        if generic_result:
            return generic_result

        # Optimization: Only extract content if needed
        content_preview = None
        if not self._has_clear_category_signal(file_info.filename):
            content_preview = self.extractor.extract(file_info.path)

        # Get sibling context
        folder_key = str(file_info.path.parent)
        sibling_files = self.folder_categorizations.get(folder_key, [])
        sibling_context = (
            SiblingContext(sibling_files)
            if self.config.sibling_context_enabled and sibling_files
            else None
        )

        # Initial categorization
        prompt = self._build_categorization_prompt(file_info, content_preview, sibling_context)
        response = self._call_api(prompt)

        if not response:
            return self._create_unknown_result(file_info, "API call failed")

        initial_result = self._parse_json_response(response)
        if not initial_result:
            return self._create_unknown_result(file_info, "Failed to parse API response")

        # Self-critique only for borderline confidence (optimization)
        final_result = initial_result
        critique_data = None
        initial_confidence = initial_result.get("confidence", 0)

        if self._needs_self_critique(initial_confidence):
            critique_prompt = self._build_critique_prompt(initial_result)
            critique_response = self._call_api(critique_prompt)

            if critique_response:
                critique_data = self._parse_json_response(critique_response)

                if critique_data and critique_data.get("changed"):
                    final_result = {
                        "category": critique_data.get("final_category", initial_result["category"]),
                        "confidence": critique_data.get(
                            "final_confidence", initial_result["confidence"]
                        ),
                        "entity_detected": initial_result.get("entity_detected"),
                        "reasoning": initial_result["reasoning"],
                        "action": initial_result.get("action", "move"),
                    }

                    # Downgrade to unknown if confidence dropped
                    if final_result["confidence"] < self.config.confidence_threshold:
                        final_result["action"] = "unknown"

        # Determine final action based on confidence
        confidence = final_result.get("confidence", 0)
        action = final_result.get("action", "unknown")

        if confidence < self.config.confidence_threshold and action == "move":
            action = "unknown"

        # Build result
        result = CategorizationResult(
            file_info=file_info,
            category=final_result.get("category", "Unknown"),
            confidence=confidence,
            entity_detected=final_result.get("entity_detected"),
            reasoning=final_result.get("reasoning", ""),
            action=action,
        )

        if critique_data:
            result.original_category = initial_result.get("category")
            result.original_confidence = initial_result.get("confidence")
            result.critique = critique_data.get("critique")
            result.alternatives = critique_data.get("alternative_interpretations")
            result.changed_after_critique = critique_data.get("changed", False)

        # Update sibling context for future files
        if action == "move":
            if folder_key not in self.folder_categorizations:
                self.folder_categorizations[folder_key] = []
            self.folder_categorizations[folder_key].append(
                (file_info.filename, result.category, result.confidence)
            )

        # Learn new entities
        if result.entity_detected:
            self.entity_manager.add_learned_entity(result.entity_detected)

        return result

    def _create_unknown_result(self, file_info: FileInfo, reason: str) -> CategorizationResult:
        """Create an unknown result for error cases."""
        return CategorizationResult(
            file_info=file_info,
            category="Unknown",
            confidence=0,
            entity_detected=None,
            reasoning=reason,
            action="unknown",
        )


class StructureAnalyzer:
    """Analyzes file collection and proposes archive structure."""

    def __init__(self, config: SiftConfig, entity_manager: EntityManager):
        self.config = config
        self.entity_manager = entity_manager
        self.client = config.get_anthropic_client()

    def analyze_and_propose(self, scan_summary: str, sample_filenames: list[str]) -> str:
        """Analyze scanned files and propose archive structure."""
        entity_context = self.entity_manager.get_entity_context_for_prompt()

        sample_text = "\n".join(f"- {f}" for f in sample_filenames[:100])

        prompt = f"""You are designing an archive folder structure for organizing a document collection.

{scan_summary}

{entity_context}

Sample filenames:
{sample_text}

Today's date is December 2025. Based on this analysis, propose an archive folder structure. Consider:
1. Detected entities ({self.config.entity_type}s) should each have a folder
2. Date-based archiving for old files (e.g., Archive-Pre-2025 for files before 2025)
3. Functional categories (Admin, Projects, etc.)
4. The structure should be flat enough to be usable but organized enough to be findable

Return your proposal in this markdown format:

# Proposed Archive Structure

## Recommended Structure
```
├── Category1/
│   ├── Subcategory/
├── Category2/
└── Misc/
```

## Detected Entities
- Entity A (estimated file count)
- Entity B (estimated file count)

## Rationale
Brief explanation of why this structure makes sense for this collection.

## Action Required
Review and approve this structure before continuing.
"""

        response = self.client.messages.create(
            model=self.config.model,
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}],
        )

        return response.content[0].text

    def parse_structure_from_proposal(self, proposal: str) -> list[str]:
        """Extract folder paths from structure proposal."""
        import re

        paths = []

        # Look for lines with folder patterns
        lines = proposal.split("\n")
        for line in lines:
            # Match patterns like "├── Folder/" or "│   ├── Subfolder/"
            match = re.search(r"[├└│\s]*([A-Za-z0-9\-_/{}]+)/", line)
            if match:
                folder = match.group(1).strip()
                if folder and not folder.startswith("{"):
                    paths.append(folder)

        # Also look for category mentions in other formats
        for line in lines:
            if line.strip().startswith("- ") and "/" in line:
                parts = line.strip("- ").split()[0]
                if parts.endswith("/"):
                    paths.append(parts.rstrip("/"))

        return list(set(paths))


class AsyncCategorizer:
    """Async version of Categorizer for parallel processing."""

    def __init__(
        self,
        config: SiftConfig,
        entity_manager: EntityManager,
        extractor: ContentExtractor,
        archive_structure: list[str],
    ):
        self.config = config
        self.entity_manager = entity_manager
        self.extractor = extractor
        self.archive_structure = archive_structure
        self.async_client = config.get_async_anthropic_client()

        # Track categorizations by folder for sibling context
        self.folder_categorizations: dict[str, list[tuple[str, str, int]]] = {}

        # Reuse prompt building from sync categorizer
        self._sync_categorizer = Categorizer(config, entity_manager, extractor, archive_structure)

    async def _call_api_async(self, prompt: str, retry_count: int = 0) -> Optional[str]:
        """Call Claude API asynchronously with retry logic and timeout."""
        try:
            # Add 120 second timeout to prevent hanging
            response = await asyncio.wait_for(
                self.async_client.messages.create(
                    model=self.config.model,
                    max_tokens=1024,
                    messages=[{"role": "user", "content": prompt}],
                ),
                timeout=120.0
            )
            return response.content[0].text
        except asyncio.TimeoutError:
            if retry_count < self.config.max_retries:
                await asyncio.sleep(self.config.retry_delay_seconds * (retry_count + 1))
                return await self._call_api_async(prompt, retry_count + 1)
            raise
        except anthropic.RateLimitError:
            if retry_count < self.config.max_retries:
                await asyncio.sleep(self.config.retry_delay_seconds * (retry_count + 1))
                return await self._call_api_async(prompt, retry_count + 1)
            raise
        except anthropic.APIError:
            if retry_count < self.config.max_retries:
                await asyncio.sleep(self.config.retry_delay_seconds)
                return await self._call_api_async(prompt, retry_count + 1)
            raise

    async def categorize_async(self, file_info: FileInfo) -> CategorizationResult:
        """Categorize a single file using AI asynchronously."""
        # Step 0: Check if existing folder structure already tells us the category
        path_result = self._sync_categorizer._check_path_category(file_info)
        if path_result:
            return path_result

        # Check auto-categorization patterns
        auto_result = self._sync_categorizer._check_auto_patterns(file_info)
        if auto_result:
            return auto_result

        # Check for generic/default filenames
        generic_result = self._sync_categorizer._check_generic_filename(file_info)
        if generic_result:
            return generic_result

        # Optimization: Only extract content if needed
        content_preview = None
        if not self._sync_categorizer._has_clear_category_signal(file_info.filename):
            content_preview = self.extractor.extract(file_info.path)

        # Get sibling context
        folder_key = str(file_info.path.parent)
        sibling_files = self.folder_categorizations.get(folder_key, [])
        sibling_context = (
            SiblingContext(sibling_files)
            if self.config.sibling_context_enabled and sibling_files
            else None
        )

        # Initial categorization (async)
        prompt = self._sync_categorizer._build_categorization_prompt(
            file_info, content_preview, sibling_context
        )
        response = await self._call_api_async(prompt)

        if not response:
            return self._sync_categorizer._create_unknown_result(file_info, "API call failed")

        initial_result = self._sync_categorizer._parse_json_response(response)
        if not initial_result:
            return self._sync_categorizer._create_unknown_result(
                file_info, "Failed to parse API response"
            )

        # Self-critique only for borderline confidence
        final_result = initial_result
        critique_data = None
        initial_confidence = initial_result.get("confidence", 0)

        if self._sync_categorizer._needs_self_critique(initial_confidence):
            critique_prompt = self._sync_categorizer._build_critique_prompt(initial_result)
            critique_response = await self._call_api_async(critique_prompt)

            if critique_response:
                critique_data = self._sync_categorizer._parse_json_response(critique_response)

                if critique_data and critique_data.get("changed"):
                    final_result = {
                        "category": critique_data.get(
                            "final_category", initial_result["category"]
                        ),
                        "confidence": critique_data.get(
                            "final_confidence", initial_result["confidence"]
                        ),
                        "entity_detected": initial_result.get("entity_detected"),
                        "reasoning": initial_result["reasoning"],
                        "action": initial_result.get("action", "move"),
                    }

                    if final_result["confidence"] < self.config.confidence_threshold:
                        final_result["action"] = "unknown"

        # Determine final action
        confidence = final_result.get("confidence", 0)
        action = final_result.get("action", "unknown")

        if confidence < self.config.confidence_threshold and action == "move":
            action = "unknown"

        # Build result
        result = CategorizationResult(
            file_info=file_info,
            category=final_result.get("category", "Unknown"),
            confidence=confidence,
            entity_detected=final_result.get("entity_detected"),
            reasoning=final_result.get("reasoning", ""),
            action=action,
        )

        if critique_data:
            result.original_category = initial_result.get("category")
            result.original_confidence = initial_result.get("confidence")
            result.critique = critique_data.get("critique")
            result.alternatives = critique_data.get("alternative_interpretations")
            result.changed_after_critique = critique_data.get("changed", False)

        # Update sibling context
        if action == "move":
            if folder_key not in self.folder_categorizations:
                self.folder_categorizations[folder_key] = []
            self.folder_categorizations[folder_key].append(
                (file_info.filename, result.category, result.confidence)
            )

        # Learn new entities
        if result.entity_detected:
            self.entity_manager.add_learned_entity(result.entity_detected)

        return result

    async def categorize_batch_async(
        self, files: list[FileInfo], progress_callback=None
    ) -> list[CategorizationResult]:
        """Process a batch of files in parallel."""
        import sys
        batch_size = self.config.parallel_batch_size
        results = []
        total_batches = (len(files) + batch_size - 1) // batch_size

        for i in range(0, len(files), batch_size):
            batch_num = (i // batch_size) + 1
            batch = files[i : i + batch_size]

            # Log batch start
            print(f"\n[Batch {batch_num}/{total_batches}] Processing {len(batch)} files...", flush=True)

            tasks = [self.categorize_async(f) for f in batch]
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)

            errors_in_batch = 0
            for j, result in enumerate(batch_results):
                if isinstance(result, Exception):
                    # Convert exception to unknown result
                    errors_in_batch += 1
                    result = self._sync_categorizer._create_unknown_result(
                        batch[j], f"Error: {str(result)}"
                    )
                results.append(result)

                if progress_callback:
                    progress_callback(len(results), len(files))

            # Log batch completion
            if errors_in_batch > 0:
                print(f"[Batch {batch_num}] Complete - {errors_in_batch} errors", flush=True)
            else:
                print(f"[Batch {batch_num}] Complete", flush=True)
            sys.stdout.flush()

        return results
