from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping, Optional
from uuid import uuid4

from dotenv import dotenv_values

from paper_agent.protocol import CommandError, ErrorCode, ExitCode

from .paths import AppPaths


_NEW_KEY = "FROWANG_API_KEY"
_LEGACY_KEY = "PAPER_API_KEY"
_FROWANG_KEYS = frozenset({_NEW_KEY, _LEGACY_KEY})
_ASSIGNMENT_PATTERN = re.compile(
    r"^\s*(?:export\s+)?(?P<key>[A-Za-z_][A-Za-z0-9_]*)\s*="
)


@dataclass(frozen=True)
class ResolvedCredential:
    value: str = field(repr=False)
    source: str


@dataclass(frozen=True)
class CredentialStatus:
    configured: bool
    source: Optional[str]
    provider: str = "frowang"

    def as_dict(self) -> dict[str, object]:
        return {
            "provider": self.provider,
            "configured": self.configured,
            "source": self.source,
        }


@dataclass(frozen=True)
class CredentialMutationResult:
    changed: bool
    stored: bool
    source: Optional[str]
    credentials_file: str
    provider: str = "frowang"

    def as_dict(self) -> dict[str, object]:
        return {
            "provider": self.provider,
            "changed": self.changed,
            "stored": self.stored,
            "source": self.source,
            "credentials_file": self.credentials_file,
            "external_sources_unchanged": True,
        }


def _clean(value: object) -> Optional[str]:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _auth_invalid(message: str, **details: object) -> CommandError:
    return CommandError(
        code=ErrorCode.AUTH_INVALID,
        message=message,
        exit_code=ExitCode.CONFIG_OR_AUTH,
        details=details,
    )


def _local_io_error(operation: str, path: Path, exc: OSError) -> CommandError:
    return CommandError(
        code=ErrorCode.LOCAL_IO_ERROR,
        message="Paper Agent could not update the credentials file",
        exit_code=ExitCode.LOCAL_IO_OR_INTEGRITY,
        details={
            "operation": operation,
            "path": str(path),
            "error_type": type(exc).__name__,
        },
    )


def _quote_dotenv(value: str) -> str:
    return "'{}'".format(value.replace("'", "\\'"))


def _atomic_write_credentials(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


class CredentialStore:
    """Manage credentials owned by Paper Agent without exposing their values."""

    def __init__(self, paths: AppPaths) -> None:
        self.paths = paths

    def _read(self) -> str:
        path = self.paths.credentials_file
        if not path.exists():
            return "# Paper Agent credentials. Never commit this file.\n"
        try:
            return path.read_text(encoding="utf-8")
        except OSError as exc:
            raise _local_io_error("read_credentials", path, exc) from exc

    def _write_if_changed(self, original: str, updated: str) -> bool:
        if updated == original and self.paths.credentials_file.is_file():
            return False
        try:
            _atomic_write_credentials(self.paths.credentials_file, updated)
        except OSError as exc:
            raise _local_io_error(
                "write_credentials", self.paths.credentials_file, exc
            ) from exc
        return True

    @staticmethod
    def _without_frowang_assignments(content: str) -> list[str]:
        kept: list[str] = []
        for line in content.splitlines(keepends=True):
            match = _ASSIGNMENT_PATTERN.match(line)
            if match and match.group("key") in _FROWANG_KEYS:
                continue
            kept.append(line)
        return kept

    def set_frowang(self, value: str) -> CredentialMutationResult:
        cleaned = _clean(value)
        if cleaned is None:
            raise _auth_invalid("Frowang API key cannot be empty")
        if "\n" in cleaned or "\r" in cleaned or "\x00" in cleaned:
            raise _auth_invalid("Frowang API key must be a single text line")
        if len(cleaned) > 16_384:
            raise _auth_invalid(
                "Frowang API key is too long",
                maximum_characters=16_384,
            )

        original = self._read()
        kept = self._without_frowang_assignments(original)
        if kept and not kept[-1].endswith(("\n", "\r")):
            kept[-1] += "\n"
        kept.append(f"{_NEW_KEY}={_quote_dotenv(cleaned)}\n")
        changed = self._write_if_changed(original, "".join(kept))
        return CredentialMutationResult(
            changed=changed,
            stored=True,
            source=f"credentials.env:{_NEW_KEY}",
            credentials_file=str(self.paths.credentials_file),
        )

    def delete_frowang(self) -> CredentialMutationResult:
        if not self.paths.credentials_file.exists():
            return CredentialMutationResult(
                changed=False,
                stored=False,
                source=None,
                credentials_file=str(self.paths.credentials_file),
            )
        original = self._read()
        updated = "".join(self._without_frowang_assignments(original))
        changed = self._write_if_changed(original, updated)
        return CredentialMutationResult(
            changed=changed,
            stored=False,
            source=None,
            credentials_file=str(self.paths.credentials_file),
        )


def _select(
    values: Mapping[str, object], *, source_prefix: str
) -> Optional[ResolvedCredential]:
    current = _clean(values.get(_NEW_KEY))
    legacy = _clean(values.get(_LEGACY_KEY))
    if current and legacy and current != legacy:
        raise CommandError(
            code=ErrorCode.CONFIG_INVALID,
            message="Conflicting Frowang API key aliases",
            exit_code=ExitCode.CONFIG_OR_AUTH,
            details={"sources": [f"{source_prefix}:{_NEW_KEY}", f"{source_prefix}:{_LEGACY_KEY}"]},
        )
    if current:
        return ResolvedCredential(current, f"{source_prefix}:{_NEW_KEY}")
    if legacy:
        return ResolvedCredential(legacy, f"{source_prefix}:{_LEGACY_KEY}")
    return None


class CredentialResolver:
    def __init__(self, paths: AppPaths) -> None:
        self.paths = paths

    def resolve(
        self, env: Optional[Mapping[str, str]] = None
    ) -> ResolvedCredential:
        environment = env if env is not None else __import__("os").environ
        resolved = _select(environment, source_prefix="environment")
        if resolved:
            return resolved

        if self.paths.credentials_file.is_file():
            try:
                file_values = dotenv_values(self.paths.credentials_file)
            except OSError as exc:
                raise CommandError(
                    code=ErrorCode.CONFIG_INVALID,
                    message="Credentials file cannot be read",
                    exit_code=ExitCode.CONFIG_OR_AUTH,
                    details={
                        "credentials_file": str(self.paths.credentials_file),
                        "error_type": type(exc).__name__,
                    },
                ) from exc
            resolved = _select(file_values, source_prefix="credentials.env")
            if resolved:
                return resolved

        raise CommandError(
            code=ErrorCode.AUTH_MISSING,
            message="Frowang API key is not configured",
            exit_code=ExitCode.CONFIG_OR_AUTH,
            details={"accepted_environment_variables": [_NEW_KEY, _LEGACY_KEY]},
        )

    def status(self, env: Optional[Mapping[str, str]] = None) -> CredentialStatus:
        try:
            resolved = self.resolve(env)
        except CommandError as exc:
            if exc.code == ErrorCode.AUTH_MISSING:
                return CredentialStatus(configured=False, source=None)
            raise
        return CredentialStatus(configured=True, source=resolved.source)


class ZoteroCredentialResolver:
    """Resolve the optional Zotero Web API credential for remote mode."""

    def __init__(self, paths: AppPaths) -> None:
        self.paths = paths

    def resolve(
        self, env: Optional[Mapping[str, str]] = None
    ) -> ResolvedCredential:
        environment = env if env is not None else __import__("os").environ
        value = _clean(environment.get("ZOTERO_API_KEY"))
        if value:
            return ResolvedCredential(value, "environment:ZOTERO_API_KEY")

        if self.paths.credentials_file.is_file():
            try:
                file_values = dotenv_values(self.paths.credentials_file)
            except OSError as exc:
                raise CommandError(
                    code=ErrorCode.CONFIG_INVALID,
                    message="Credentials file cannot be read",
                    exit_code=ExitCode.CONFIG_OR_AUTH,
                    details={
                        "credentials_file": str(self.paths.credentials_file),
                        "error_type": type(exc).__name__,
                    },
                ) from exc
            value = _clean(file_values.get("ZOTERO_API_KEY"))
            if value:
                return ResolvedCredential(value, "credentials.env:ZOTERO_API_KEY")

        raise CommandError(
            code=ErrorCode.AUTH_MISSING,
            message="Zotero API key is not configured for remote mode",
            exit_code=ExitCode.CONFIG_OR_AUTH,
            details={"accepted_environment_variables": ["ZOTERO_API_KEY"]},
        )

    def status(self, env: Optional[Mapping[str, str]] = None) -> CredentialStatus:
        try:
            resolved = self.resolve(env)
        except CommandError as exc:
            if exc.code == ErrorCode.AUTH_MISSING:
                return CredentialStatus(configured=False, source=None, provider="zotero")
            raise
        return CredentialStatus(
            configured=True,
            source=resolved.source,
            provider="zotero",
        )
