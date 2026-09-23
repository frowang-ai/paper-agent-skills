# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.9.5] - 2026-09-24

### Added

- **Quote Annotations**: `library annotation locate` and `library annotation add` create PDF
  highlights or underlines from original text in private and collaborative papers. The server
  resolves coordinates; callers can select an ambiguous candidate, pin the document revision,
  and explicitly accept coarse OCR locations. Stable request IDs prevent duplicate annotations
  when retrying the same command.

## [0.9.4] - 2026-09-23

### Added

- **Collab Relationship Management**: New `paper-agent library collab` command group exposing the
  server's collaborative-collection lifecycle to agents (requires server deploy of
  `llm_read_paper_ai_workflow` with X-API-Key auth on `collection_collab.py`):
  `enable` (enable collab + generate invite link), `invite-status`, `invite-revoke`,
  `invite-preview`, `apply` (join via invite token), `requests` (list join requests with
  `requester_user_id`), `approve` / `approve-all` / `reject`, `members`, `remove-member`,
  `leave`, `info`, `pending-summary`. Enables agent-to-agent workflows: one agent enables
  collab and hands the invite token to another agent, which applies and polls
  `invite-preview` until approved.

## [0.9.3] - 2026-09-23

### Added

- **Collaborative Copies**: All `library` paper-level commands now accept `collab~<collection_key>~<paper_id>`
  scoped IDs (as returned by `library collection items` for shared collections). Notes, annotations, tags,
  metadata, and detail route to the workspace endpoints (`/collections/{root}/papers/{id}/...`), so writes
  land on the shared copy visible to all members instead of the owner's private library. New module
  `paper_agent.collab` centralizes scoped-ID parsing and routing.
  - `note add` on a collab ID sends JSON body per workspace contract (private notes keep query param).
  - `annotation list` on a collab ID returns the shared full snapshot (all members); `--since` is rejected.
  - `annotation comment` on a collab ID verifies the write landed and fails loudly on read-only
    (other-author) annotations instead of the server's silent skip.
  - `reprocess` maps to the workspace `actions/reprocess` pipeline; `delete` and screenshot generation
    reject collab IDs with a clear usage error.
  - Read-only commands without workspace equivalents (`fulltext`/`summary`/`deep`/`assets`/
    `attribute-tree`/screenshots GET) fall back to the underlying paper ID, which the server authorizes
    via collab visibility.

## [0.9.2] - 2026-09-07

### Added

- **Update Check**: New `paper-agent update check [--refresh]` command and a `update` entry in
  `doctor` output. Queries the PyPI JSON API with a 24h atomic cache, 3s timeout, silent
  degradation on network failure, and `PAPER_AGENT_DISABLE_UPDATE_CHECK=1` opt-out. Upgrade
  itself stays with the agent: `uv tool install paper-agent-skills --upgrade` plus
  `paper-agent skills update --platform all`.

### Changed

- **Auth Guidance**: The three production Skills now invite users to hand the Frowang API key
  directly to the agent for configuration via `paper-agent auth set --stdin` (terminal hidden
  input remains available), replacing the strict "independent stdin channel only" wording.
  User-facing reminder added: the key has full access to the paper library — do not share it.

## [0.9.1] - 2026-07-28

### Fixed

- **Version Reporting**: `paper-agent --version` and runtime version fields now read from installed package metadata (single source of truth: `pyproject.toml`), fixing 0.9.0 reporting itself as 0.8.2.

## [0.9.0] - 2026-07-28

### Added

- **Paper Metadata API**: New `paper-agent library metadata P-xxx [--save]` command exposing the server-side extraction metadata (title/authors/DOI/journal/`citations.apa`) via `GET /papers/{id}/metadata`.
- **Attribute Tree API**: New `paper-agent library attribute-tree P-xxx [--save]` command via `GET /papers/{id}/attribute-tree`; payload is small enough for direct agent context use.
- **Paper Screenshots**: New `paper-agent library screenshots P-xxx` command — query existing screenshots, `--job-id` for generation progress, `--generate` (with `--no-pdf`/`--no-html`/`--force`) to trigger PDF first-pages + deep-report HTML screenshots, `--wait`/`--timeout` to poll until completion. Returns absolute `https://frowang.com/paper-api` URLs.
- **Workspace Attribute Tree**: `workspace add` now also downloads `attribute_tree.json` (optional, `required: false`), enabling low-token local search across paper attribute trees.

### Changed

- **Workspace Metadata Semantics**: workspace `metadata.json` now contains the server extraction metadata (including `citations.apa`) instead of the paper record. Paper record and processing status remain available live via `library show`. Existing cached revisions are not migrated and stay compatible.

## [0.8.2] - 2026-07-12

### Changed

- **Adaptive CLI Output**: Interactive terminals now receive readable Skill install/status summaries, while pipes, redirected output, Agents, and explicit `--json` keep the stable JSON envelope.

## [0.8.1] - 2026-07-12

### Added

- **OpenAI Agents**: Added `agents/openai.yaml` configuration files for `paper-library` and `zotero-upload` skills.
- **Manifest Update**: Updated `skills/manifest.json` to include new agent configurations.

### Removed

- **Legacy Scripts**: Removed obsolete wrapper scripts from `skills/paper-library/scripts/` and `skills/zotero-upload/scripts/`.
- **Legacy .env Examples**: Removed `.env.example` files (replaced by `auth set` command).

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

[0.8.2]: https://github.com/frowang-ai/paper-agent-skills/releases/tag/v0.8.2
[0.8.1]: https://github.com/frowang-ai/paper-agent-skills/releases/tag/v0.8.1
[0.8.0]: https://github.com/frowang-ai/paper-agent-skills/releases/tag/v0.8.0
[0.7.0]: https://github.com/frowang-ai/paper-agent-skills/releases/tag/v0.7.0
[0.6.0]: https://github.com/frowang-ai/paper-agent-skills/releases/tag/v0.6.0
[0.5.0]: https://github.com/frowang-ai/paper-agent-skills/releases/tag/v0.5.0
