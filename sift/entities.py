"""
Entity detection and management for Sift.
Handles customer/project name detection, fuzzy matching, and learning.
"""

import json
from pathlib import Path
from typing import Optional

try:
    from rapidfuzz import fuzz, process
    HAS_RAPIDFUZZ = True
except ImportError:
    HAS_RAPIDFUZZ = False


class EntityManager:
    """Manages entity detection and mapping."""

    def __init__(self, mappings_path: Path):
        self.mappings_path = mappings_path
        self.entity_type = "customer"
        self.mappings: dict[str, list[str]] = {}
        self.learned_entities: list[str] = []
        self.fuzzy_pending: list[dict] = []

        self._load()

    def _load(self):
        """Load entity mappings from file."""
        if self.mappings_path.exists():
            try:
                with open(self.mappings_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.entity_type = data.get("entity_type", "customer")
                    self.mappings = data.get("entity_mappings", {})
                    self.learned_entities = data.get("learned_entities", [])
                    self.fuzzy_pending = data.get("fuzzy_matches_pending_confirmation", [])
            except (json.JSONDecodeError, KeyError):
                pass

    def save(self):
        """Save entity mappings to file."""
        self.mappings_path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "entity_type": self.entity_type,
            "entity_mappings": self.mappings,
            "learned_entities": self.learned_entities,
            "fuzzy_matches_pending_confirmation": self.fuzzy_pending,
        }

        with open(self.mappings_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def get_all_entity_names(self) -> list[str]:
        """Get list of all known entity canonical names."""
        return list(self.mappings.keys()) + self.learned_entities

    def get_all_aliases(self) -> dict[str, str]:
        """Get mapping of all aliases to canonical names."""
        aliases = {}
        for canonical, alias_list in self.mappings.items():
            aliases[canonical.lower()] = canonical
            for alias in alias_list:
                aliases[alias.lower()] = canonical

        for entity in self.learned_entities:
            aliases[entity.lower()] = entity

        return aliases

    def find_entity(self, text: str, threshold: int = 80) -> Optional[str]:
        """
        Find an entity match in the given text.
        Returns the canonical entity name if found, None otherwise.
        """
        text_lower = text.lower()
        aliases = self.get_all_aliases()

        # Direct substring match first
        for alias, canonical in aliases.items():
            if alias in text_lower:
                return canonical

        # Fuzzy match on words (if rapidfuzz available)
        if HAS_RAPIDFUZZ:
            words = text.split()
            for word in words:
                if len(word) < 3:
                    continue

                matches = process.extract(
                    word.lower(),
                    list(aliases.keys()),
                    scorer=fuzz.ratio,
                    limit=1,
                )

                if matches and matches[0][1] >= threshold:
                    return aliases[matches[0][0]]

        return None

    def add_learned_entity(self, entity_name: str):
        """Add a newly learned entity."""
        if entity_name not in self.learned_entities and entity_name not in self.mappings:
            self.learned_entities.append(entity_name)
            self.save()

    def add_alias(self, canonical: str, alias: str):
        """Add an alias for an existing entity."""
        if canonical in self.mappings:
            if alias not in self.mappings[canonical]:
                self.mappings[canonical].append(alias)
                self.save()
        elif canonical in self.learned_entities:
            # Promote to full mapping with alias
            self.learned_entities.remove(canonical)
            self.mappings[canonical] = [alias]
            self.save()

    def add_fuzzy_pending(self, detected: str, possible_match: str, confidence: int, file_path: str):
        """Add a fuzzy match pending confirmation."""
        entry = {
            "detected": detected,
            "possible_match": possible_match,
            "confidence": confidence,
            "file_path": file_path,
        }

        # Avoid duplicates
        for existing in self.fuzzy_pending:
            if existing["detected"] == detected and existing["possible_match"] == possible_match:
                return

        self.fuzzy_pending.append(entry)
        self.save()

    def confirm_fuzzy_match(self, detected: str, canonical: str):
        """Confirm a fuzzy match and add as alias."""
        self.add_alias(canonical, detected)

        # Remove from pending
        self.fuzzy_pending = [
            p for p in self.fuzzy_pending if p["detected"] != detected
        ]
        self.save()

    def reject_fuzzy_match(self, detected: str):
        """Reject fuzzy match and add as new entity."""
        self.add_learned_entity(detected)

        # Remove from pending
        self.fuzzy_pending = [
            p for p in self.fuzzy_pending if p["detected"] != detected
        ]
        self.save()

    def get_entity_context_for_prompt(self) -> str:
        """Get entity list formatted for AI prompt."""
        entities = self.get_all_entity_names()
        if not entities:
            return "No known entities yet."

        return f"Known {self.entity_type}s: " + ", ".join(entities)
