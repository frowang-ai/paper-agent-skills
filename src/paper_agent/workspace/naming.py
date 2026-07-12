from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Mapping, Optional


PROTOCOL_NAME = "year-author-short-title--short-id-v1"
MAX_DIRECTORY_LENGTH = 120
MAX_TITLE_LENGTH = 60
MAX_AUTHOR_PART_LENGTH = 20


@dataclass(frozen=True)
class WorkspaceDirectoryName:
    directory: str
    protocol: str
    generated_from_revision: str

    def as_dict(self) -> dict[str, str]:
        return {
            "protocol": self.protocol,
            "generated_from_revision": self.generated_from_revision,
        }


def _slug(value: object, *, fallback: str, limit: int) -> str:
    normalized = unicodedata.normalize("NFKC", str(value or "")).strip()
    characters: list[str] = []
    separator_pending = False
    for character in normalized:
        if character.isalnum():
            if separator_pending and characters:
                characters.append("-")
            characters.append(character)
            separator_pending = False
        else:
            separator_pending = bool(characters)
    result = "".join(characters).strip("-")
    if not result:
        result = fallback
    return result[:limit].rstrip("-") or fallback


def _year(metadata: Mapping[str, Any]) -> str:
    for key in ("publication_year", "year"):
        value = metadata.get(key)
        if isinstance(value, int) and 1000 <= value <= 2999:
            return str(value)
        if isinstance(value, str) and re.fullmatch(r"\d{4}", value.strip()):
            parsed = int(value)
            if 1000 <= parsed <= 2999:
                return str(parsed)
    for key in ("publication_date", "published_at", "date"):
        value = metadata.get(key)
        if isinstance(value, str):
            match = re.search(r"(?<!\d)(\d{4})(?!\d)", value)
            if match and 1000 <= int(match.group(1)) <= 2999:
                return match.group(1)
    return "n.d."


def _author_values(raw: object) -> list[object]:
    if isinstance(raw, list):
        return raw
    if isinstance(raw, str):
        stripped = raw.strip()
        if not stripped:
            return []
        try:
            decoded = json.loads(stripped)
        except json.JSONDecodeError:
            return [part.strip() for part in re.split(r";|\band\b", stripped) if part.strip()]
        return decoded if isinstance(decoded, list) else [decoded]
    return []


def _family_name(author: object) -> str:
    value: object = author
    if isinstance(author, Mapping):
        value = (
            author.get("family")
            or author.get("last_name")
            or author.get("lastName")
            or author.get("name")
            or ""
        )
    text = str(value or "").strip()
    if not text:
        return ""
    if "," in text:
        text = text.split(",", 1)[0].strip()
    elif re.search(r"\s", text):
        text = text.split()[-1]
    return _slug(
        text,
        fallback="Unknown",
        limit=MAX_AUTHOR_PART_LENGTH,
    )


def _authors(metadata: Mapping[str, Any]) -> str:
    names = [
        family
        for author in _author_values(metadata.get("authors"))
        if (family := _family_name(author))
    ]
    if not names:
        return "Unknown"
    if len(names) == 1:
        return names[0]
    if len(names) == 2:
        return f"{names[0]}-{names[1]}"
    return f"{names[0]}-et-al"


def _identity(short_id: Optional[str], paper_id: str) -> str:
    if short_id:
        return _slug(short_id, fallback="paper", limit=24)
    compact = "".join(character for character in paper_id if character.isalnum())
    return f"id-{(compact[:8] or 'unknown')}"


class WorkspaceDirectoryNamingProtocol:
    name = PROTOCOL_NAME

    def generate(
        self,
        *,
        metadata: Mapping[str, Any],
        paper_id: str,
        short_id: Optional[str],
        revision: str,
    ) -> WorkspaceDirectoryName:
        year = _year(metadata)
        author = _authors(metadata)
        identity = _identity(short_id, paper_id)
        prefix = f"{year}-{author}-"
        suffix = f"--{identity}"
        available = min(
            MAX_TITLE_LENGTH,
            max(1, MAX_DIRECTORY_LENGTH - len(prefix) - len(suffix)),
        )
        title = _slug(
            metadata.get("title"),
            fallback="Untitled-Paper",
            limit=available,
        )
        directory = f"{prefix}{title}{suffix}"
        if len(directory) > MAX_DIRECTORY_LENGTH:
            overflow = len(directory) - MAX_DIRECTORY_LENGTH
            author = author[: max(1, len(author) - overflow)].rstrip("-") or "Unknown"
            prefix = f"{year}-{author}-"
            available = min(
                MAX_TITLE_LENGTH,
                max(1, MAX_DIRECTORY_LENGTH - len(prefix) - len(suffix)),
            )
            title = _slug(title, fallback="Untitled-Paper", limit=available)
            directory = f"{prefix}{title}{suffix}"
        return WorkspaceDirectoryName(
            directory=directory,
            protocol=self.name,
            generated_from_revision=revision,
        )
