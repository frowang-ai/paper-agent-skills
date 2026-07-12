# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.8.0] - 2026-07-12

### Added

- **Unified Runtime**: Complete Python 3.13+ runtime with shared configuration, credentials, and JSON CLI protocol.
- **Library Service**: Frowang Paper API client with search, show, upload, fulltext, and asset management.
- **Zotero Import**: Local and remote Zotero integration with collection mapping and sync state.
- **Skill Installer**: Cross-platform standalone installer for Codex and Claude Code with `list/install/status/diff/update/uninstall`.
- **Plugin Builder**: Dual-platform plugin bundle generation for Codex and Claude marketplaces.
- **Global Artifact Store**: User-level paper cache with profile isolation, SHA-256 verification, and cache hit optimization.
- **Project Workspace**: Local paper workspace with `init/add/list/status/sync/remove` and user file protection.
- **Readable Directory Naming**: `year-author-short-title--short-id-v1` protocol for human-friendly paper directories.
- **Auth Management**: `auth set/status/delete` commands with hidden input and `--stdin` for secure credential handling.
- **Doctor Command**: Comprehensive health check for runtime, credentials, remote connectivity, and skill installations.
- **Layered Search**: L1 metadata, L2 attribute tree, and L3 full-text search support.
- **Error Protocol**: Stable error codes with JSON envelope and proper exit codes.

### Changed

- Upgraded from Python 3.9+ to Python 3.13+ baseline.
- Migrated from standalone `.env` files to unified `platformdirs`-based configuration.
- Restructured skills from monolithic to modular architecture.

### Security

- All credentials stored in user-level `credentials.env` with proper file permissions.
- API keys never exposed in stdout, logs, or command history.
- Asset downloads validate origin, path, and SHA-256 integrity.

## [0.7.0] - 2026-07-12

### Added

- Workspace directory naming protocol with `year-author-short-title--short-id-v1` format.
- `workspace names plan/apply` commands for explicit directory renaming.
- User file preservation during workspace sync and rename operations.

### Changed

- New paper directories now use readable names instead of short IDs.
- Existing directories require explicit `names apply` to migrate.

## [0.6.0] - 2026-07-11

### Added

- Global Artifact Store with paper pull and cache management.
- Project workspace with paper materialization and local rg search.
- SQLite state storage for papers, revisions, and workspaces.

### Changed

- Separated artifact sync from workspace materialization.
- Improved error handling for network and file operations.

## [0.5.0] - 2026-06-19

### Added

- Initial release of paper-agent-skills runtime.
- Frowang Paper API client and library service.
- Zotero import with local/remote mode support.
- Cross-platform skill installer for Codex and Claude Code.
- Plugin bundle builder for marketplace distribution.
- Unified configuration and credential management.

[0.8.0]: https://github.com/frowang-ai/paper-agent-skills/releases/tag/v0.8.0
[0.7.0]: https://github.com/frowang-ai/paper-agent-skills/releases/tag/v0.7.0
[0.6.0]: https://github.com/frowang-ai/paper-agent-skills/releases/tag/v0.6.0
[0.5.0]: https://github.com/frowang-ai/paper-agent-skills/releases/tag/v0.5.0
