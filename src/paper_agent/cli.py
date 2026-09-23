from __future__ import annotations

import json
import os
import sys
import time
from getpass import getpass
from contextvars import ContextVar
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Any, Optional
from uuid import uuid4

import typer

try:
    from typer import _click as click
except ImportError:  # pragma: no cover - Typer versions using external Click
    import click  # type: ignore[no-redef]

from paper_agent import __version__
from paper_agent.clients import FrowangClient, create_zotero_client
from paper_agent.config import (
    ConfigManager,
    CredentialResolver,
    CredentialStore,
    ZoteroCredentialResolver,
    resolve_app_paths,
)
from paper_agent.protocol import (
    CommandError,
    ErrorCode,
    ExitCode,
    error_envelope,
    success_envelope,
)
from paper_agent.plugins import PluginBundleBuilder
from paper_agent.services import (
    ArtifactSyncService,
    LibraryService,
    SkillInstallService,
    UpdateCheckService,
    WorkspaceService,
    ZoteroImportService,
)
from paper_agent.skills import SkillTarget, resolve_skill_target, resolve_skills_source
from paper_agent.storage import StateStore


app = typer.Typer(
    name="paper-agent",
    help="Shared runtime for Paper Agent skills.",
    add_completion=False,
    no_args_is_help=True,
    pretty_exceptions_enable=False,
)
config_app = typer.Typer(help="Manage Paper Agent configuration.", no_args_is_help=True)
auth_app = typer.Typer(help="Manage Paper Agent credentials.", no_args_is_help=True)
library_app = typer.Typer(help="Manage the remote Frowang paper library.", no_args_is_help=True)
library_tag_app = typer.Typer(help="Manage paper tags.", no_args_is_help=True)
library_note_app = typer.Typer(help="Manage paper notes.", no_args_is_help=True)
library_annotation_app = typer.Typer(help="Manage PDF annotations.", no_args_is_help=True)
library_collection_app = typer.Typer(help="Manage remote collections.", no_args_is_help=True)
library_collab_app = typer.Typer(
    help="Manage collaborative collection invites, join requests, and members.",
    no_args_is_help=True,
)
library_key_app = typer.Typer(help="Manage API keys with a website JWT.", no_args_is_help=True)
zotero_app = typer.Typer(help="Import papers from Zotero.", no_args_is_help=True)
skills_app = typer.Typer(help="Install Paper Agent Skills and build Plugins.", no_args_is_help=True)
workspace_app = typer.Typer(help="Manage project paper workspaces.", no_args_is_help=True)
workspace_names_app = typer.Typer(
    help="Plan and apply readable workspace directory names.",
    no_args_is_help=True,
)
paper_app = typer.Typer(help="Sync papers into the global artifact store.", no_args_is_help=True)
update_app = typer.Typer(help="Check for runtime updates.", no_args_is_help=True)
app.add_typer(config_app, name="config")
app.add_typer(auth_app, name="auth")
app.add_typer(library_app, name="library")
app.add_typer(zotero_app, name="zotero")
app.add_typer(skills_app, name="skills")
app.add_typer(workspace_app, name="workspace")
app.add_typer(paper_app, name="paper")
app.add_typer(update_app, name="update")
library_app.add_typer(library_tag_app, name="tag")
library_app.add_typer(library_note_app, name="note")
library_app.add_typer(library_annotation_app, name="annotation")
library_app.add_typer(library_collection_app, name="collection")
library_app.add_typer(library_collab_app, name="collab")
library_app.add_typer(library_key_app, name="key")
workspace_app.add_typer(workspace_names_app, name="names")

_ACTIVE_COMMAND: ContextVar[str] = ContextVar("paper_agent_command", default="cli")
_REQUEST_ID: ContextVar[str] = ContextVar("paper_agent_request_id", default="")

JsonOption = Annotated[
    bool,
    typer.Option("--json", help="Force the stable JSON envelope."),
]
HumanOption = Annotated[
    bool,
    typer.Option("--human", help="Force human-readable terminal output."),
]


def _request_id() -> str:
    current = _REQUEST_ID.get()
    if current:
        return current
    current = f"local-{uuid4()}"
    _REQUEST_ID.set(current)
    return current


def _validate_output_flags(json_output: bool, human: bool) -> None:
    if json_output and human:
        raise CommandError(
            code=ErrorCode.USAGE_ERROR,
            message="--json and --human cannot be used together",
            exit_code=ExitCode.USAGE_ERROR,
        )


def _write_payload(payload: dict[str, Any], *, human: bool = False) -> None:
    if human:
        rendered = json.dumps(payload, ensure_ascii=False, indent=2)
    else:
        rendered = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    sys.stdout.write(rendered + "\n")


def _stdout_is_tty() -> bool:
    try:
        return sys.stdout.isatty()
    except (AttributeError, OSError):
        return False


def _use_human_output(*, json_output: bool, human: bool) -> bool:
    if human:
        return True
    if json_output:
        return False
    return _stdout_is_tty()


def _skill_targets(data: dict[str, Any]) -> list[dict[str, Any]]:
    targets = data.get("targets")
    if isinstance(targets, list):
        return [item for item in targets if isinstance(item, dict)]
    return [data]


def _skill_target_heading(item: dict[str, Any]) -> str:
    target = item.get("target", {})
    platform = str(target.get("platform", "unknown")).capitalize()
    scope = target.get("scope", "unknown")
    root = target.get("root", "unknown")
    return f"{platform} · {scope} · {root}"


def _render_skill_action(data: dict[str, Any]) -> str:
    labels = (
        ("installed", "Installed"),
        ("updated", "Updated"),
        ("skipped", "Already current"),
        ("uninstalled", "Uninstalled"),
        ("not_installed", "Not installed"),
    )
    lines = [f"Paper Agent Skills {__version__}"]
    for index, item in enumerate(_skill_targets(data)):
        if index:
            lines.append("")
        lines.append(_skill_target_heading(item))
        for key, label in labels:
            values = item.get(key)
            if values:
                lines.append(f"  {label}: {', '.join(str(value) for value in values)}")
    return "\n".join(lines)


def _render_skill_status(data: dict[str, Any]) -> str:
    lines = [f"Paper Agent Skills {__version__}"]
    for index, item in enumerate(_skill_targets(data)):
        if index:
            lines.append("")
        lines.append(_skill_target_heading(item))
        skills = item.get("skills", {})
        for name, details in skills.items():
            status = details.get("status", "unknown")
            version = details.get("installed_version")
            suffix = f" (v{version})" if version else ""
            lines.append(f"  {name}: {status}{suffix}")
            modified = details.get("target_modified", [])
            unmanaged = details.get("unmanaged_files", [])
            if modified:
                lines.append(f"    Modified: {', '.join(str(path) for path in modified)}")
            if unmanaged:
                lines.append(f"    Unmanaged: {', '.join(str(path) for path in unmanaged)}")
    return "\n".join(lines)


def _render_update_check(data: dict[str, Any]) -> str:
    current = data.get("current_version", "unknown")
    status = data.get("status", "unknown")
    if status == "update_available":
        latest = data.get("latest_version", "unknown")
        return (
            f"Paper Agent Skills {current} → new version {latest} available.\n"
            "Run: uv tool install paper-agent-skills --upgrade\n"
            "Then refresh installed Skills: paper-agent skills update --platform all"
        )
    if status == "ok":
        return f"Paper Agent Skills {current} is up to date."
    if status == "disabled":
        return f"Paper Agent Skills {current} (update check disabled)."
    return f"Paper Agent Skills {current} (update status unknown; try --refresh)."


def _render_human(command: str, data: Any) -> str:
    if isinstance(data, dict):
        if command in {"skills.install", "skills.update", "skills.uninstall"}:
            return _render_skill_action(data)
        if command == "skills.status":
            return _render_skill_status(data)
        if command == "update.check":
            return _render_update_check(data)
    return json.dumps(data, ensure_ascii=False, indent=2)


def _emit_success(
    command: str,
    data: Any,
    *,
    json_output: bool = False,
    human: bool = False,
) -> None:
    _ACTIVE_COMMAND.set(command)
    _validate_output_flags(json_output, human)
    if _use_human_output(json_output=json_output, human=human):
        sys.stdout.write(_render_human(command, data) + "\n")
        return
    _write_payload(
        success_envelope(
            data=data,
            command=command,
            runtime_version=__version__,
            request_id=_request_id(),
        )
    )


def _manager() -> tuple[ConfigManager, CredentialResolver]:
    paths = resolve_app_paths()
    return ConfigManager(paths), CredentialResolver(paths)


@app.callback(invoke_without_command=True)
def root(
    ctx: typer.Context,
    version: Annotated[
        bool,
        typer.Option("--version", help="Show the Paper Agent runtime version."),
    ] = False,
) -> None:
    if version:
        typer.echo(__version__)
        raise typer.Exit(ExitCode.SUCCESS)
    if ctx.invoked_subcommand is None:
        raise CommandError(
            code=ErrorCode.USAGE_ERROR,
            message="A command is required",
            exit_code=ExitCode.USAGE_ERROR,
        )


@app.command("capabilities")
def capabilities(
    json_output: JsonOption = False,
    human: HumanOption = False,
) -> None:
    """List runtime capabilities and available commands.

    Safe to call without configuration or credentials. Output is the JSON
    envelope with capability flags and the full command list.
    """
    _emit_success(
        "capabilities",
        {
            "capabilities": [
                "protocol.envelope.v1",
                "config",
                "auth.manage",
                "auth.status",
                "doctor.local",
                "doctor.remote",
                "library",
                "zotero",
                "skills.install",
                "artifacts.text",
                "workspace",
            ],
            "commands": [
                "capabilities",
                "doctor",
                "config init",
                "config show",
                "config migrate",
                "auth status",
                "auth set",
                "auth delete",
                "library list",
                "library search",
                "library show",
                "library upload",
                "library assets",
                "zotero collections",
                "zotero items",
                "zotero upload",
                "zotero status",
                "skills install",
                "skills status",
                "skills diff",
                "skills update",
                "skills uninstall",
                "skills plugin-build",
                "workspace init",
                "workspace add",
                "workspace list",
                "workspace status",
                "workspace sync",
                "workspace remove",
                "workspace names plan",
                "workspace names apply",
                "paper pull",
                "update check",
            ],
        },
        json_output=json_output,
        human=human,
    )


@update_app.command("check")
def update_check(
    refresh: Annotated[
        bool,
        typer.Option("--refresh", help="Bypass the 24h cache and query PyPI now."),
    ] = False,
    json_output: JsonOption = False,
    human: HumanOption = False,
) -> None:
    """Check PyPI for a newer paper-agent-skills release.

    Read-only and cached for 24 hours; network failures degrade to a stale
    cache hit or an ``unknown`` status without failing the command. Disable
    entirely with PAPER_AGENT_DISABLE_UPDATE_CHECK=1.
    """
    _ACTIVE_COMMAND.set("update.check")
    service = UpdateCheckService(resolve_app_paths(), current_version=__version__)
    data = service.check(refresh=refresh)
    _emit_success("update.check", data, json_output=json_output, human=human)


@config_app.command("init")
def config_init(
    json_output: JsonOption = False,
    human: HumanOption = False,
) -> None:
    """Create the configuration file and app directories if missing.

    Idempotent. Output reports the created/existing config and directory paths.
    """
    _ACTIVE_COMMAND.set("config.init")
    manager, _ = _manager()
    result = manager.initialize()
    _emit_success(
        "config.init",
        result.as_dict(manager.paths),
        json_output=json_output,
        human=human,
    )


@config_app.command("show")
def config_show(
    json_output: JsonOption = False,
    human: HumanOption = False,
) -> None:
    """Print the active configuration settings and resolved app paths."""
    _ACTIVE_COMMAND.set("config.show")
    manager, _ = _manager()
    settings = manager.load()
    _emit_success(
        "config.show",
        {
            "settings": settings.as_dict(),
            "paths": manager.paths.as_dict(),
        },
        json_output=json_output,
        human=human,
    )


@config_app.command("migrate")
def config_migrate(
    json_output: JsonOption = False,
    human: HumanOption = False,
) -> None:
    """Migrate the configuration file to the current schema version."""
    _ACTIVE_COMMAND.set("config.migrate")
    manager, _ = _manager()
    result = manager.migrate()
    _emit_success(
        "config.migrate",
        result.as_dict(),
        json_output=json_output,
        human=human,
    )


@auth_app.command("status")
def auth_status(
    json_output: JsonOption = False,
    human: HumanOption = False,
) -> None:
    """Show whether a Frowang API key is configured and from which source.

    Never prints the key itself; output reports configured state and source
    (for example environment:FROWANG_API_KEY).
    """
    _ACTIVE_COMMAND.set("auth.status")
    _, credentials = _manager()
    status = credentials.status()
    _emit_success(
        "auth.status",
        status.as_dict(),
        json_output=json_output,
        human=human,
    )


def _read_frowang_secret(*, from_stdin: bool) -> str:
    if from_stdin:
        value = sys.stdin.read(16_385)
        if len(value) > 16_384:
            raise CommandError(
                code=ErrorCode.AUTH_INVALID,
                message="Frowang API key is too long",
                exit_code=ExitCode.CONFIG_OR_AUTH,
                details={"maximum_characters": 16_384},
            )
        return value.strip()
    return getpass("Frowang API key: ", stream=sys.stderr)


@auth_app.command("set")
def auth_set(
    from_stdin: Annotated[
        bool,
        typer.Option(
            "--stdin",
            help="Read the Frowang API key from standard input until EOF.",
        ),
    ] = False,
    json_output: JsonOption = False,
    human: HumanOption = False,
) -> None:
    """Store a Frowang API key in the local credential store.

    Prompts interactively on stderr by default. For scripts:
    `echo "$FROWANG_API_KEY" | paper-agent auth set --stdin`
    """
    _ACTIVE_COMMAND.set("auth.set")
    manager, _ = _manager()
    result = CredentialStore(manager.paths).set_frowang(
        _read_frowang_secret(from_stdin=from_stdin)
    )
    _emit_success(
        "auth.set",
        result.as_dict(),
        json_output=json_output,
        human=human,
    )


@auth_app.command("delete")
def auth_delete(
    json_output: JsonOption = False,
    human: HumanOption = False,
) -> None:
    """Delete the stored Frowang API key.

    Only removes the locally stored key; environment-provided credentials
    (for example FROWANG_API_KEY) are left unchanged.
    """
    _ACTIVE_COMMAND.set("auth.delete")
    manager, _ = _manager()
    result = CredentialStore(manager.paths).delete_frowang()
    _emit_success(
        "auth.delete",
        result.as_dict(),
        json_output=json_output,
        human=human,
    )


def _directory_check(path: Path) -> dict[str, Any]:
    exists = path.is_dir()
    writable = exists and os.access(path, os.W_OK)
    return {
        "status": "ok" if writable else "warning",
        "path": str(path),
        "exists": exists,
        "writable": writable,
    }


@library_app.callback(invoke_without_command=True)
def library_root(
    ctx: typer.Context,
    api_key: Annotated[
        Optional[str],
        typer.Option("--api-key", help="Explicit Frowang API key."),
    ] = None,
    base_url: Annotated[
        Optional[str],
        typer.Option("--base-url", help="Override the active Frowang base URL."),
    ] = None,
) -> None:
    ctx.ensure_object(dict)
    ctx.obj["api_key"] = api_key
    ctx.obj["base_url"] = base_url
    if ctx.invoked_subcommand is None:
        raise CommandError(
            code=ErrorCode.USAGE_ERROR,
            message="A library command is required",
            exit_code=ExitCode.USAGE_ERROR,
        )


def _library_service(ctx: typer.Context) -> LibraryService:
    manager, credentials = _manager()
    settings = manager.load()
    profile = settings.profiles[settings.active_profile]
    obj = ctx.ensure_object(dict)
    api_key = obj.get("api_key") or credentials.resolve().value
    base_url = obj.get("base_url") or profile.frowang.base_url
    client = FrowangClient(
        api_key=api_key,
        base_url=base_url,
        timeout_seconds=profile.frowang.timeout_seconds,
    )
    ctx.call_on_close(client.close)
    return LibraryService(client)


def _library_success(
    command: str,
    data: Any,
    *,
    json_output: bool,
    human: bool,
) -> None:
    _emit_success(
        command,
        data,
        json_output=json_output,
        human=human,
    )


@library_app.command("list")
def library_list(
    ctx: typer.Context,
    limit: Annotated[int, typer.Option(help="Maximum number of papers.")] = 20,
    offset: Annotated[int, typer.Option(help="Result offset.")] = 0,
    tag: Annotated[Optional[str], typer.Option(help="Filter by tag.")] = None,
    sort_by: Annotated[str, typer.Option("--sort-by", help="Sort field.")] = "created_at",
    order: Annotated[str, typer.Option(help="ASC or DESC.")] = "DESC",
    json_output: JsonOption = False,
    human: HumanOption = False,
) -> None:
    """List papers in the remote Frowang library.

    Returns a paginated list of paper objects; page with --limit/--offset
    and filter with --tag.
    """
    _ACTIVE_COMMAND.set("library.list")
    data = _library_service(ctx).list_papers(
        limit=limit, offset=offset, tag=tag, sort_by=sort_by, order=order
    )
    _library_success("library.list", data, json_output=json_output, human=human)


@library_app.command("search")
def library_search(
    ctx: typer.Context,
    query: Annotated[str, typer.Argument(help="Search query.")],
    scope: Annotated[str, typer.Option(help="discovery, metadata, or title.")] = "discovery",
    limit: Annotated[int, typer.Option(help="Maximum results.")] = 10,
    json_output: JsonOption = False,
    human: HumanOption = False,
) -> None:
    """Search papers by query.

    --scope selects the search mode: discovery (default), metadata, or title.
    Returns matching paper objects with scores.
    """
    _ACTIVE_COMMAND.set("library.search")
    data = _library_service(ctx).search(query, scope=scope, limit=limit)
    _library_success("library.search", data, json_output=json_output, human=human)


@library_app.command("search-layered")
def library_search_layered(
    ctx: typer.Context,
    query: Annotated[str, typer.Argument(help="Search query.")],
    layer: Annotated[str, typer.Option("--layer", help="L1, L2, L3, or all.")] = "all",
    layers: Annotated[
        Optional[str],
        typer.Option("--layers", help="Layer subset for all, for example L1,L3."),
    ] = None,
    limit: Annotated[int, typer.Option(help="Maximum results.")] = 20,
    json_output: JsonOption = False,
    human: HumanOption = False,
) -> None:
    """Search across layered paper content.

    Layers: L1 metadata, L2 summary, L3 full text. Select one with --layer
    (L1, L2, L3, or all) or a subset with --layers, for example --layers L1,L3.
    """
    _ACTIVE_COMMAND.set("library.search-layered")
    data = _library_service(ctx).search_layered(
        query, layer=layer, layers=layers, limit=limit
    )
    _library_success(
        "library.search-layered", data, json_output=json_output, human=human
    )


@library_app.command("show")
def library_show(
    ctx: typer.Context,
    paper_id: Annotated[str, typer.Argument(help="Paper short ID or UUID.")],
    json_output: JsonOption = False,
    human: HumanOption = False,
) -> None:
    """Show full details for one paper."""
    _ACTIVE_COMMAND.set("library.show")
    data = _library_service(ctx).show(paper_id)
    _library_success("library.show", data, json_output=json_output, human=human)


def _content_to_file(service: LibraryService, paper_id: str, kind: str, save: Path) -> dict[str, object]:
    content = service.get_content(paper_id, kind)
    destination = save.expanduser().resolve()
    temporary = destination.with_name(f".{destination.name}.{uuid4().hex}.tmp")
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with temporary.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
        os.replace(temporary, destination)
    except OSError as exc:
        raise CommandError(
            code=ErrorCode.LOCAL_IO_ERROR,
            message="Paper Agent could not save paper content",
            exit_code=ExitCode.LOCAL_IO_OR_INTEGRITY,
            details={"path": str(destination), "error_type": type(exc).__name__},
        ) from exc
    finally:
        if temporary.exists():
            temporary.unlink()
    return {
        "path": str(destination),
        "bytes": len(content.encode("utf-8")),
        "kind": kind,
        "paper_id": paper_id,
    }


def _emit_content_command(
    ctx: typer.Context,
    *,
    paper_id: str,
    kind: str,
    save: Path,
    json_output: bool,
    human: bool,
) -> None:
    command = f"library.{kind}"
    _ACTIVE_COMMAND.set(command)
    data = _content_to_file(_library_service(ctx), paper_id, kind, save)
    _library_success(command, data, json_output=json_output, human=human)


@library_app.command("fulltext")
def library_fulltext(
    ctx: typer.Context,
    paper_id: Annotated[str, typer.Argument(help="Paper short ID or UUID.")],
    save: Annotated[Path, typer.Option("--save", help="Required output Markdown path.")],
    json_output: JsonOption = False,
    human: HumanOption = False,
) -> None:
    """Download the paper's full-text Markdown to a local file.

    Writes atomically to the --save path; output reports path and byte count.
    """
    _emit_content_command(
        ctx, paper_id=paper_id, kind="fulltext", save=save,
        json_output=json_output, human=human,
    )


@library_app.command("summary")
def library_summary(
    ctx: typer.Context,
    paper_id: Annotated[str, typer.Argument(help="Paper short ID or UUID.")],
    save: Annotated[Path, typer.Option("--save", help="Required output Markdown path.")],
    json_output: JsonOption = False,
    human: HumanOption = False,
) -> None:
    """Download the paper's summary Markdown to a local file.

    Writes atomically to the --save path; output reports path and byte count.
    """
    _emit_content_command(
        ctx, paper_id=paper_id, kind="summary", save=save,
        json_output=json_output, human=human,
    )


@library_app.command("deep")
def library_deep(
    ctx: typer.Context,
    paper_id: Annotated[str, typer.Argument(help="Paper short ID or UUID.")],
    save: Annotated[Path, typer.Option("--save", help="Required output Markdown path.")],
    json_output: JsonOption = False,
    human: HumanOption = False,
) -> None:
    """Download the paper's deep-read report Markdown to a local file.

    Writes atomically to the --save path; output reports path and byte count.
    """
    _emit_content_command(
        ctx, paper_id=paper_id, kind="deep", save=save,
        json_output=json_output, human=human,
    )


@library_app.command("assets")
def library_assets(
    ctx: typer.Context,
    paper_id: Annotated[str, typer.Argument(help="Paper short ID or UUID.")],
    json_output: JsonOption = False,
    human: HumanOption = False,
) -> None:
    """List downloadable asset URLs for a paper (PDF, screenshots, and more).

    Feed URLs from the output to `library download-asset`.
    """
    _ACTIVE_COMMAND.set("library.assets")
    data = _library_service(ctx).assets(paper_id)
    _library_success("library.assets", data, json_output=json_output, human=human)


def _json_to_file(data: Any, *, kind: str, paper_id: str, save: Path) -> dict[str, object]:
    rendered = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    destination = save.expanduser().resolve()
    temporary = destination.with_name(f".{destination.name}.{uuid4().hex}.tmp")
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with temporary.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(rendered)
        os.replace(temporary, destination)
    except OSError as exc:
        raise CommandError(
            code=ErrorCode.LOCAL_IO_ERROR,
            message="Paper Agent could not save paper content",
            exit_code=ExitCode.LOCAL_IO_OR_INTEGRITY,
            details={"path": str(destination), "error_type": type(exc).__name__},
        ) from exc
    finally:
        if temporary.exists():
            temporary.unlink()
    return {
        "path": str(destination),
        "bytes": len(rendered.encode("utf-8")),
        "kind": kind,
        "paper_id": paper_id,
    }


@library_app.command("metadata")
def library_metadata(
    ctx: typer.Context,
    paper_id: Annotated[str, typer.Argument(help="Paper short ID or UUID.")],
    save: Annotated[
        Optional[Path],
        typer.Option("--save", help="Optional output JSON path."),
    ] = None,
    json_output: JsonOption = False,
    human: HumanOption = False,
) -> None:
    """Show the extracted metadata JSON for a paper.

    With --save, writes the JSON to that path instead and reports the file.
    """
    _ACTIVE_COMMAND.set("library.metadata")
    data = _library_service(ctx).metadata(paper_id)
    if save is not None:
        data = _json_to_file(data, kind="metadata", paper_id=paper_id, save=save)
    _library_success("library.metadata", data, json_output=json_output, human=human)


@library_app.command("attribute-tree")
def library_attribute_tree(
    ctx: typer.Context,
    paper_id: Annotated[str, typer.Argument(help="Paper short ID or UUID.")],
    save: Annotated[
        Optional[Path],
        typer.Option("--save", help="Optional output JSON path."),
    ] = None,
    json_output: JsonOption = False,
    human: HumanOption = False,
) -> None:
    """Show the extracted attribute-tree JSON for a paper.

    With --save, writes the JSON to that path instead and reports the file.
    """
    _ACTIVE_COMMAND.set("library.attribute-tree")
    data = _library_service(ctx).attribute_tree(paper_id)
    if save is not None:
        data = _json_to_file(data, kind="attribute_tree", paper_id=paper_id, save=save)
    _library_success(
        "library.attribute-tree", data, json_output=json_output, human=human
    )


_SCREENSHOT_TERMINAL_STATUSES = {"completed", "failed"}
_SCREENSHOT_POLL_INTERVAL_SECONDS = 2.5


def _wait_for_screenshots(
    service: LibraryService,
    paper_id: str,
    job_id: str,
    *,
    timeout_seconds: float,
) -> Any:
    deadline = time.monotonic() + timeout_seconds
    while True:
        data = service.screenshots(paper_id, job_id=job_id)
        status = data.get("status") if isinstance(data, dict) else None
        if status in _SCREENSHOT_TERMINAL_STATUSES:
            return data
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise CommandError(
                code=ErrorCode.REMOTE_ERROR,
                message="Timed out waiting for paper screenshots",
                exit_code=ExitCode.NETWORK_OR_REMOTE,
                details={
                    "paper_id": paper_id,
                    "job_id": job_id,
                    "timeout_seconds": timeout_seconds,
                    "last_status": status,
                },
                retryable=True,
            )
        time.sleep(min(_SCREENSHOT_POLL_INTERVAL_SECONDS, remaining))


@library_app.command("screenshots")
def library_screenshots(
    ctx: typer.Context,
    paper_id: Annotated[str, typer.Argument(help="Paper short ID or UUID.")],
    job_id: Annotated[
        Optional[str],
        typer.Option("--job-id", help="Poll a specific screenshot generation job."),
    ] = None,
    generate: Annotated[
        bool,
        typer.Option("--generate", help="Trigger asynchronous screenshot generation."),
    ] = False,
    no_pdf: Annotated[
        bool,
        typer.Option("--no-pdf", help="Skip PDF first-pages screenshots."),
    ] = False,
    no_html: Annotated[
        bool,
        typer.Option("--no-html", help="Skip deep-report screenshots."),
    ] = False,
    force: Annotated[
        bool,
        typer.Option("--force", help="Clear old screenshots and regenerate."),
    ] = False,
    wait: Annotated[
        bool,
        typer.Option("--wait", help="Poll the job until it completes or fails."),
    ] = False,
    timeout: Annotated[
        float,
        typer.Option("--timeout", help="Maximum seconds to wait with --wait."),
    ] = 300.0,
    json_output: JsonOption = False,
    human: HumanOption = False,
) -> None:
    """List screenshot records, or trigger asynchronous screenshot generation.

    With --generate, starts a server-side job (optionally narrowed with
    --no-pdf/--no-html); add --wait to poll until it completes or fails.
    """
    _ACTIVE_COMMAND.set("library.screenshots")
    service = _library_service(ctx)
    if generate:
        if no_pdf and no_html:
            raise CommandError(
                code=ErrorCode.USAGE_ERROR,
                message="--no-pdf and --no-html cannot be used together",
                exit_code=ExitCode.USAGE_ERROR,
            )
        data = service.create_screenshots(
            paper_id,
            capture_pdf=not no_pdf,
            capture_html=not no_html,
            force_rescreenshot=force,
        )
        if wait:
            job = data.get("job_id") if isinstance(data, dict) else None
            if not isinstance(job, str) or not job:
                raise CommandError(
                    code=ErrorCode.REMOTE_ERROR,
                    message="Frowang screenshot response did not include a job_id",
                    exit_code=ExitCode.NETWORK_OR_REMOTE,
                    details={"paper_id": paper_id},
                )
            data = _wait_for_screenshots(
                service, paper_id, job, timeout_seconds=timeout
            )
    else:
        data = service.screenshots(paper_id, job_id=job_id)
    _library_success("library.screenshots", data, json_output=json_output, human=human)


@library_app.command("download-asset")
def library_download_asset(
    ctx: typer.Context,
    asset_url: Annotated[str, typer.Argument(help="Asset URL returned by library assets.")],
    destination: Annotated[Path, typer.Argument(help="Local output path.")],
    json_output: JsonOption = False,
    human: HumanOption = False,
) -> None:
    """Download an asset URL (from `library assets`) to a local path."""
    _ACTIVE_COMMAND.set("library.download-asset")
    data = _library_service(ctx).download_asset(asset_url, destination)
    _library_success(
        "library.download-asset", data, json_output=json_output, human=human
    )


@library_app.command("upload")
def library_upload(
    ctx: typer.Context,
    file: Annotated[Path, typer.Argument(help="PDF path.")],
    json_output: JsonOption = False,
    human: HumanOption = False,
) -> None:
    """Upload a PDF to the remote library.

    Creates remote paper state; server-side processing (metadata, full text)
    runs asynchronously after upload.
    """
    _ACTIVE_COMMAND.set("library.upload")
    data = _library_service(ctx).upload(file)
    _library_success("library.upload", data, json_output=json_output, human=human)


@library_app.command("upload-many")
def library_upload_many(
    ctx: typer.Context,
    files: Annotated[list[Path], typer.Argument(help="PDF paths.")],
    json_output: JsonOption = False,
    human: HumanOption = False,
) -> None:
    """Upload several PDFs to the remote library in one call."""
    _ACTIVE_COMMAND.set("library.upload-many")
    data = _library_service(ctx).upload_many(files)
    _library_success("library.upload-many", data, json_output=json_output, human=human)


@library_app.command("upload-dir")
def library_upload_dir(
    ctx: typer.Context,
    directory: Annotated[Path, typer.Argument(help="Directory containing PDFs.")],
    json_output: JsonOption = False,
    human: HumanOption = False,
) -> None:
    """Upload every PDF found directly in a directory (not recursive)."""
    _ACTIVE_COMMAND.set("library.upload-dir")
    path = directory.expanduser().resolve()
    if not path.is_dir():
        raise CommandError(
            code=ErrorCode.USAGE_ERROR,
            message="Upload directory does not exist",
            exit_code=ExitCode.USAGE_ERROR,
            details={"path": str(path)},
        )
    data = _library_service(ctx).upload_many(
        sorted(item for item in path.iterdir() if item.suffix.lower() == ".pdf")
    )
    _library_success("library.upload-dir", data, json_output=json_output, human=human)


@library_app.command("reprocess")
def library_reprocess(
    ctx: typer.Context,
    paper_id: Annotated[str, typer.Argument(help="Paper short ID or UUID.")],
    json_output: JsonOption = False,
    human: HumanOption = False,
) -> None:
    """Re-run server-side processing for a paper."""
    _ACTIVE_COMMAND.set("library.reprocess")
    data = _library_service(ctx).reprocess(paper_id)
    _library_success("library.reprocess", data, json_output=json_output, human=human)


@library_app.command("update-metadata")
def library_update_metadata(
    ctx: typer.Context,
    paper_id: Annotated[str, typer.Argument(help="Paper short ID or UUID.")],
    title: Annotated[Optional[str], typer.Option(help="New title.")] = None,
    authors: Annotated[Optional[str], typer.Option(help="Comma-separated authors.")] = None,
    abstract: Annotated[Optional[str], typer.Option(help="New abstract.")] = None,
    doi: Annotated[Optional[str], typer.Option(help="DOI.")] = None,
    journal: Annotated[Optional[str], typer.Option(help="Journal.")] = None,
    year: Annotated[Optional[str], typer.Option("--year", help="Publication year.")] = None,
    json_output: JsonOption = False,
    human: HumanOption = False,
) -> None:
    """Update metadata fields of a paper; only provided fields are changed.

    Example: paper-agent library update-metadata P-123 --title "New title" --year 2024
    """
    _ACTIVE_COMMAND.set("library.update-metadata")
    fields: dict[str, Any] = {
        "title": title,
        "authors": [item.strip() for item in authors.split(",")] if authors is not None else None,
        "abstract": abstract,
        "doi": doi,
        "journal": journal,
        "publication_year": year,
    }
    data = _library_service(ctx).update_metadata(paper_id, fields)
    _library_success(
        "library.update-metadata", data, json_output=json_output, human=human
    )


@library_app.command("delete")
def library_delete(
    ctx: typer.Context,
    paper_id: Annotated[str, typer.Argument(help="Paper short ID or UUID.")],
    json_output: JsonOption = False,
    human: HumanOption = False,
) -> None:
    """Delete a paper and its assets from the remote library."""
    _ACTIVE_COMMAND.set("library.delete")
    data = _library_service(ctx).delete(paper_id)
    _library_success("library.delete", data, json_output=json_output, human=human)


@library_tag_app.command("add")
def library_tag_add(
    ctx: typer.Context,
    paper_id: Annotated[str, typer.Argument(help="Paper short ID or UUID.")],
    tags: Annotated[list[str], typer.Argument(help="Tags to add.")],
    json_output: JsonOption = False,
    human: HumanOption = False,
) -> None:
    """Add one or more tags to a paper (existing tags are kept).

    Example: paper-agent library tag add P-123 machine-learning survey
    """
    _ACTIVE_COMMAND.set("library.tag.add")
    data = _library_service(ctx).add_tags(paper_id, tags)
    _library_success("library.tag.add", data, json_output=json_output, human=human)


@library_tag_app.command("set")
def library_tag_set(
    ctx: typer.Context,
    paper_id: Annotated[str, typer.Argument(help="Paper short ID or UUID.")],
    tags: Annotated[list[str], typer.Argument(help="Full replacement tag set.")],
    json_output: JsonOption = False,
    human: HumanOption = False,
) -> None:
    """Replace all tags of a paper with the given set."""
    _ACTIVE_COMMAND.set("library.tag.set")
    data = _library_service(ctx).set_tags(paper_id, tags)
    _library_success("library.tag.set", data, json_output=json_output, human=human)


@library_tag_app.command("remove")
def library_tag_remove(
    ctx: typer.Context,
    paper_id: Annotated[str, typer.Argument(help="Paper short ID or UUID.")],
    tag: Annotated[str, typer.Argument(help="Tag to remove.")],
    json_output: JsonOption = False,
    human: HumanOption = False,
) -> None:
    """Remove one tag from a paper."""
    _ACTIVE_COMMAND.set("library.tag.remove")
    data = _library_service(ctx).remove_tag(paper_id, tag)
    _library_success("library.tag.remove", data, json_output=json_output, human=human)


@library_note_app.command("list")
def library_note_list(
    ctx: typer.Context,
    paper_id: Annotated[str, typer.Argument(help="Paper short ID or UUID.")],
    json_output: JsonOption = False,
    human: HumanOption = False,
) -> None:
    """List notes attached to a paper."""
    _ACTIVE_COMMAND.set("library.note.list")
    data = _library_service(ctx).list_notes(paper_id)
    _library_success("library.note.list", data, json_output=json_output, human=human)


@library_note_app.command("add")
def library_note_add(
    ctx: typer.Context,
    paper_id: Annotated[str, typer.Argument(help="Paper short ID or UUID.")],
    content: Annotated[str, typer.Argument(help="Note text (quote it if it contains spaces).")],
    json_output: JsonOption = False,
    human: HumanOption = False,
) -> None:
    """Add a note to a paper.

    Example: paper-agent library note add P-123 "Relevant to section 3"
    """
    _ACTIVE_COMMAND.set("library.note.add")
    data = _library_service(ctx).add_note(paper_id, content)
    _library_success("library.note.add", data, json_output=json_output, human=human)


@library_annotation_app.command("list")
def library_annotation_list(
    ctx: typer.Context,
    paper_id: Annotated[str, typer.Argument(help="Paper short ID or UUID.")],
    since: Annotated[
        Optional[str],
        typer.Option("--since", help="Only annotations updated after this ISO 8601 timestamp."),
    ] = None,
    json_output: JsonOption = False,
    human: HumanOption = False,
) -> None:
    """List PDF annotations of a paper.

    Use --since with an ISO 8601 timestamp for incremental sync.
    """
    _ACTIVE_COMMAND.set("library.annotation.list")
    data = _library_service(ctx).list_annotations(paper_id, since=since)
    _library_success(
        "library.annotation.list", data, json_output=json_output, human=human
    )


@library_annotation_app.command("comment")
def library_annotation_comment(
    ctx: typer.Context,
    paper_id: Annotated[str, typer.Argument(help="Paper short ID or UUID.")],
    annotation_id: Annotated[str, typer.Argument(help="Annotation ID from `library annotation list`.")],
    comment: Annotated[str, typer.Argument(help="Comment text to append.")],
    json_output: JsonOption = False,
    human: HumanOption = False,
) -> None:
    """Append a comment to a PDF annotation."""
    _ACTIVE_COMMAND.set("library.annotation.comment")
    data = _library_service(ctx).append_annotation_comment(
        paper_id, annotation_id, comment
    )
    _library_success(
        "library.annotation.comment", data, json_output=json_output, human=human
    )


@library_collection_app.command("list")
def library_collection_list(
    ctx: typer.Context,
    json_output: JsonOption = False,
    human: HumanOption = False,
) -> None:
    """List remote collections (with keys, names, and nesting)."""
    _ACTIVE_COMMAND.set("library.collection.list")
    data = _library_service(ctx).list_collections()
    _library_success(
        "library.collection.list", data, json_output=json_output, human=human
    )


@library_collection_app.command("create")
def library_collection_create(
    ctx: typer.Context,
    name: Annotated[str, typer.Argument(help="Collection name.")],
    parent: Annotated[
        Optional[str],
        typer.Option("--parent", help="Parent collection key to nest under."),
    ] = None,
    json_output: JsonOption = False,
    human: HumanOption = False,
) -> None:
    """Create a remote collection.

    Example: paper-agent library collection create "Reading list" --parent ABC123
    """
    _ACTIVE_COMMAND.set("library.collection.create")
    data = _library_service(ctx).create_collection(name, parent)
    _library_success(
        "library.collection.create", data, json_output=json_output, human=human
    )


@library_collection_app.command("update")
def library_collection_update(
    ctx: typer.Context,
    key: Annotated[str, typer.Argument(help="Collection key.")],
    name: Annotated[Optional[str], typer.Option("--name", help="New collection name.")] = None,
    parent: Annotated[
        Optional[str],
        typer.Option("--parent", help="New parent collection key; pass null to detach."),
    ] = None,
    sort_order: Annotated[Optional[int], typer.Option("--sort", help="Sort order integer.")] = None,
    json_output: JsonOption = False,
    human: HumanOption = False,
) -> None:
    """Update a collection's name, parent, or sort order; only provided fields change."""
    _ACTIVE_COMMAND.set("library.collection.update")
    fields: dict[str, Any] = {}
    if name is not None:
        fields["name"] = name
    if parent is not None:
        fields["parent_key"] = None if parent == "null" else parent
    if sort_order is not None:
        fields["sort_order"] = sort_order
    data = _library_service(ctx).update_collection(key, fields)
    _library_success(
        "library.collection.update", data, json_output=json_output, human=human
    )


@library_collection_app.command("delete")
def library_collection_delete(
    ctx: typer.Context,
    key: Annotated[str, typer.Argument(help="Collection key.")],
    json_output: JsonOption = False,
    human: HumanOption = False,
) -> None:
    """Delete a remote collection."""
    _ACTIVE_COMMAND.set("library.collection.delete")
    data = _library_service(ctx).delete_collection(key)
    _library_success(
        "library.collection.delete", data, json_output=json_output, human=human
    )


@library_collection_app.command("items")
def library_collection_items(
    ctx: typer.Context,
    key: Annotated[str, typer.Argument(help="Collection key.")],
    json_output: JsonOption = False,
    human: HumanOption = False,
) -> None:
    """List papers in a collection."""
    _ACTIVE_COMMAND.set("library.collection.items")
    data = _library_service(ctx).collection_items(key)
    _library_success(
        "library.collection.items", data, json_output=json_output, human=human
    )


@library_collection_app.command("add")
def library_collection_add(
    ctx: typer.Context,
    key: Annotated[str, typer.Argument(help="Collection key.")],
    task_ids: Annotated[list[str], typer.Argument(help="Paper IDs to add.")],
    json_output: JsonOption = False,
    human: HumanOption = False,
) -> None:
    """Add papers to a collection."""
    _ACTIVE_COMMAND.set("library.collection.add")
    data = _library_service(ctx).add_collection_items(key, task_ids)
    _library_success("library.collection.add", data, json_output=json_output, human=human)


@library_collection_app.command("remove")
def library_collection_remove(
    ctx: typer.Context,
    key: Annotated[str, typer.Argument(help="Collection key.")],
    task_ids: Annotated[list[str], typer.Argument(help="Paper IDs to remove.")],
    json_output: JsonOption = False,
    human: HumanOption = False,
) -> None:
    """Remove papers from a collection."""
    _ACTIVE_COMMAND.set("library.collection.remove")
    data = _library_service(ctx).remove_collection_items(key, task_ids)
    _library_success(
        "library.collection.remove", data, json_output=json_output, human=human
    )


@library_key_app.command("create")
def library_key_create(
    ctx: typer.Context,
    jwt_token: Annotated[
        str,
        typer.Option("--jwt-token", help="Website JWT authorizing key management."),
    ],
    name: Annotated[str, typer.Option(help="Key name.")] = "default",
    json_output: JsonOption = False,
    human: HumanOption = False,
) -> None:
    """Create a Frowang API key using a website JWT.

    The new key is shown once in the output; store it with
    `paper-agent auth set --stdin`.
    """
    _ACTIVE_COMMAND.set("library.key.create")
    data = _library_service(ctx).create_api_key(jwt_token, name)
    _library_success("library.key.create", data, json_output=json_output, human=human)


@library_key_app.command("list")
def library_key_list(
    ctx: typer.Context,
    jwt_token: Annotated[
        str,
        typer.Option("--jwt-token", help="Website JWT authorizing key management."),
    ],
    json_output: JsonOption = False,
    human: HumanOption = False,
) -> None:
    """List existing Frowang API keys for the JWT's account."""
    _ACTIVE_COMMAND.set("library.key.list")
    data = _library_service(ctx).list_api_keys(jwt_token)
    _library_success("library.key.list", data, json_output=json_output, human=human)


@library_key_app.command("revoke")
def library_key_revoke(
    ctx: typer.Context,
    key_id: Annotated[str, typer.Argument(help="API key ID to revoke.")],
    jwt_token: Annotated[
        str,
        typer.Option("--jwt-token", help="Website JWT authorizing key management."),
    ],
    json_output: JsonOption = False,
    human: HumanOption = False,
) -> None:
    """Revoke a Frowang API key (permanent; the key stops working)."""
    _ACTIVE_COMMAND.set("library.key.revoke")
    data = _library_service(ctx).revoke_api_key(key_id, jwt_token)
    _library_success("library.key.revoke", data, json_output=json_output, human=human)


# ── 协作收藏夹：邀请、申请审批与成员管理 ────────────────────────────


@library_collab_app.command("enable")
def library_collab_enable(
    ctx: typer.Context,
    collection_key: Annotated[str, typer.Argument(help="Collection key (tree root, e.g. C-38).")],
    json_output: JsonOption = False,
    human: HumanOption = False,
) -> None:
    """Enable collaboration on a collection and (re)generate its invite link.

    One active invite per collection; regenerating revokes the previous link.
    The plaintext invite_url is returned only once — copy it to the invitee.
    """
    _ACTIVE_COMMAND.set("library.collab.enable")
    data = _library_service(ctx).create_collab_invite(collection_key)
    _library_success("library.collab.enable", data, json_output=json_output, human=human)


@library_collab_app.command("invite-status")
def library_collab_invite_status(
    ctx: typer.Context,
    collection_key: Annotated[str, typer.Argument(help="Collection key (tree root).")],
    json_output: JsonOption = False,
    human: HumanOption = False,
) -> None:
    """Show the active invite status of a collaborative collection."""
    _ACTIVE_COMMAND.set("library.collab.invite-status")
    data = _library_service(ctx).collab_invite_status(collection_key)
    _library_success("library.collab.invite-status", data, json_output=json_output, human=human)


@library_collab_app.command("invite-revoke")
def library_collab_invite_revoke(
    ctx: typer.Context,
    collection_key: Annotated[str, typer.Argument(help="Collection key (tree root).")],
    invite_id: Annotated[str, typer.Argument(help="Invite ID from invite-status.")],
    json_output: JsonOption = False,
    human: HumanOption = False,
) -> None:
    """Revoke an invite link (pending applications remain reviewable)."""
    _ACTIVE_COMMAND.set("library.collab.invite-revoke")
    data = _library_service(ctx).revoke_collab_invite(collection_key, invite_id)
    _library_success("library.collab.invite-revoke", data, json_output=json_output, human=human)


@library_collab_app.command("invite-preview")
def library_collab_invite_preview(
    ctx: typer.Context,
    token: Annotated[str, typer.Argument(help="Invite token (last segment of the invite URL).")],
    json_output: JsonOption = False,
    human: HumanOption = False,
) -> None:
    """Preview an invite: collection name, owner, member count, my state."""
    _ACTIVE_COMMAND.set("library.collab.invite-preview")
    data = _library_service(ctx).collab_invite_preview(token)
    _library_success("library.collab.invite-preview", data, json_output=json_output, human=human)


@library_collab_app.command("apply")
def library_collab_apply(
    ctx: typer.Context,
    token: Annotated[str, typer.Argument(help="Invite token (last segment of the invite URL).")],
    json_output: JsonOption = False,
    human: HumanOption = False,
) -> None:
    """Apply to join a collaborative collection via its invite token.

    Idempotent: returns applied / already_applied / already_member.
    Afterwards poll `invite-preview` for viewer_state=approved.
    """
    _ACTIVE_COMMAND.set("library.collab.apply")
    data = _library_service(ctx).apply_collab_invite(token)
    _library_success("library.collab.apply", data, json_output=json_output, human=human)


@library_collab_app.command("requests")
def library_collab_requests(
    ctx: typer.Context,
    collection_key: Annotated[str, typer.Argument(help="Collection key (tree root).")],
    status: Annotated[
        Optional[str],
        typer.Option("--status", help="pending | approved | rejected | all (default pending)."),
    ] = None,
    json_output: JsonOption = False,
    human: HumanOption = False,
) -> None:
    """List join requests (owner only) with requester_user_id for review."""
    _ACTIVE_COMMAND.set("library.collab.requests")
    data = _library_service(ctx).list_join_requests(collection_key, status=status)
    _library_success("library.collab.requests", data, json_output=json_output, human=human)


@library_collab_app.command("approve")
def library_collab_approve(
    ctx: typer.Context,
    collection_key: Annotated[str, typer.Argument(help="Collection key (tree root).")],
    request_id: Annotated[str, typer.Argument(help="Join request ID from `collab requests`.")],
    json_output: JsonOption = False,
    human: HumanOption = False,
) -> None:
    """Approve one join request (owner only)."""
    _ACTIVE_COMMAND.set("library.collab.approve")
    data = _library_service(ctx).approve_join_request(collection_key, request_id)
    _library_success("library.collab.approve", data, json_output=json_output, human=human)


@library_collab_app.command("approve-all")
def library_collab_approve_all(
    ctx: typer.Context,
    collection_key: Annotated[str, typer.Argument(help="Collection key (tree root).")],
    json_output: JsonOption = False,
    human: HumanOption = False,
) -> None:
    """Approve every pending join request (owner only)."""
    _ACTIVE_COMMAND.set("library.collab.approve-all")
    data = _library_service(ctx).approve_all_join_requests(collection_key)
    _library_success("library.collab.approve-all", data, json_output=json_output, human=human)


@library_collab_app.command("reject")
def library_collab_reject(
    ctx: typer.Context,
    collection_key: Annotated[str, typer.Argument(help="Collection key (tree root).")],
    request_id: Annotated[str, typer.Argument(help="Join request ID from `collab requests`.")],
    json_output: JsonOption = False,
    human: HumanOption = False,
) -> None:
    """Reject one join request (owner only)."""
    _ACTIVE_COMMAND.set("library.collab.reject")
    data = _library_service(ctx).reject_join_request(collection_key, request_id)
    _library_success("library.collab.reject", data, json_output=json_output, human=human)


@library_collab_app.command("members")
def library_collab_members(
    ctx: typer.Context,
    collection_key: Annotated[str, typer.Argument(help="Collection key (tree root).")],
    json_output: JsonOption = False,
    human: HumanOption = False,
) -> None:
    """List the owner and members of a collaborative collection."""
    _ACTIVE_COMMAND.set("library.collab.members")
    data = _library_service(ctx).list_collab_members(collection_key)
    _library_success("library.collab.members", data, json_output=json_output, human=human)


@library_collab_app.command("remove-member")
def library_collab_remove_member(
    ctx: typer.Context,
    collection_key: Annotated[str, typer.Argument(help="Collection key (tree root).")],
    member_user_id: Annotated[str, typer.Argument(help="Member user ID to remove.")],
    json_output: JsonOption = False,
    human: HumanOption = False,
) -> None:
    """Remove a member from a collaborative collection (owner only)."""
    _ACTIVE_COMMAND.set("library.collab.remove-member")
    data = _library_service(ctx).remove_collab_member(collection_key, member_user_id)
    _library_success("library.collab.remove-member", data, json_output=json_output, human=human)


@library_collab_app.command("leave")
def library_collab_leave(
    ctx: typer.Context,
    collection_key: Annotated[str, typer.Argument(help="Collection key (tree root).")],
    json_output: JsonOption = False,
    human: HumanOption = False,
) -> None:
    """Leave a collaborative collection (member self-service)."""
    _ACTIVE_COMMAND.set("library.collab.leave")
    data = _library_service(ctx).leave_collab_collection(collection_key)
    _library_success("library.collab.leave", data, json_output=json_output, human=human)


@library_collab_app.command("info")
def library_collab_info(
    ctx: typer.Context,
    collection_key: Annotated[str, typer.Argument(help="Collection key (tree root).")],
    json_output: JsonOption = False,
    human: HumanOption = False,
) -> None:
    """Show my role, member count, and pending request count."""
    _ACTIVE_COMMAND.set("library.collab.info")
    data = _library_service(ctx).collab_info(collection_key)
    _library_success("library.collab.info", data, json_output=json_output, human=human)


@library_collab_app.command("pending-summary")
def library_collab_pending_summary(
    ctx: typer.Context,
    json_output: JsonOption = False,
    human: HumanOption = False,
) -> None:
    """Summarize pending join requests across all collaborative collections I own."""
    _ACTIVE_COMMAND.set("library.collab.pending-summary")
    data = _library_service(ctx).collab_pending_summary()
    _library_success("library.collab.pending-summary", data, json_output=json_output, human=human)


@zotero_app.callback(invoke_without_command=True)
def zotero_root(
    ctx: typer.Context,
    api_key: Annotated[
        Optional[str],
        typer.Option("--api-key", help="Explicit Frowang API key for upload commands."),
    ] = None,
    base_url: Annotated[
        Optional[str],
        typer.Option("--base-url", help="Override the active Frowang base URL."),
    ] = None,
    zotero_api_key: Annotated[
        Optional[str],
        typer.Option("--zotero-api-key", help="Explicit Zotero Web API key."),
    ] = None,
    storage_dir: Annotated[
        Optional[Path],
        typer.Option("--storage-dir", help="Override the local Zotero storage directory."),
    ] = None,
) -> None:
    ctx.ensure_object(dict)
    ctx.obj.update(
        {
            "frowang_api_key": api_key,
            "frowang_base_url": base_url,
            "zotero_api_key": zotero_api_key,
            "zotero_storage_dir": storage_dir,
        }
    )
    if ctx.invoked_subcommand is None:
        raise CommandError(
            code=ErrorCode.USAGE_ERROR,
            message="A Zotero command is required",
            exit_code=ExitCode.USAGE_ERROR,
        )


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _zotero_import_service(
    ctx: typer.Context,
    *,
    require_frowang: bool,
) -> ZoteroImportService:
    manager, frowang_credentials = _manager()
    settings = manager.load()
    profile = settings.profiles[settings.active_profile]
    obj = ctx.ensure_object(dict)
    zotero_settings = profile.zotero
    storage_override = obj.get("zotero_storage_dir")
    if storage_override is not None:
        zotero_settings = replace(
            zotero_settings,
            storage_dir=str(storage_override.expanduser().resolve()),
        )
    zotero_key = obj.get("zotero_api_key")
    if zotero_settings.mode == "remote" and not zotero_key:
        zotero_key = ZoteroCredentialResolver(manager.paths).resolve().value
    zotero_client = create_zotero_client(zotero_settings, api_key=zotero_key)

    library: Optional[LibraryService] = None
    if require_frowang:
        frowang_key = obj.get("frowang_api_key") or frowang_credentials.resolve().value
        frowang_client = FrowangClient(
            api_key=frowang_key,
            base_url=obj.get("frowang_base_url") or profile.frowang.base_url,
            timeout_seconds=profile.frowang.timeout_seconds,
        )
        ctx.call_on_close(frowang_client.close)
        library = LibraryService(frowang_client)

    return ZoteroImportService(
        zotero=zotero_client,
        library=library,
        state_store=StateStore(manager.paths.state_db),
        profile=settings.active_profile,
        clock=_utc_now,
    )


def _zotero_state_context() -> tuple[ConfigManager, str, str, StateStore]:
    manager, _ = _manager()
    settings = manager.load()
    library_id = settings.active.zotero.library_id
    store = StateStore(manager.paths.state_db)
    store.initialize()
    return manager, settings.active_profile, library_id, store


@zotero_app.command("collections")
def zotero_collections(
    ctx: typer.Context,
    json_output: JsonOption = False,
    human: HumanOption = False,
) -> None:
    """List Zotero collections from the configured library."""
    _ACTIVE_COMMAND.set("zotero.collections")
    data = _zotero_import_service(ctx, require_frowang=False).collections()
    _emit_success(
        "zotero.collections", data, json_output=json_output, human=human
    )


@zotero_app.command("items")
def zotero_items(
    ctx: typer.Context,
    collection_key: Annotated[str, typer.Argument(help="Zotero collection key.")],
    recursive: Annotated[
        bool,
        typer.Option("--recursive", "-r", help="Include child collections."),
    ] = False,
    json_output: JsonOption = False,
    human: HumanOption = False,
) -> None:
    """List items in a Zotero collection; --recursive includes child collections."""
    _ACTIVE_COMMAND.set("zotero.items")
    data = _zotero_import_service(ctx, require_frowang=False).items(
        collection_key, recursive=recursive
    )
    _emit_success("zotero.items", data, json_output=json_output, human=human)


@zotero_app.command("upload")
def zotero_upload(
    ctx: typer.Context,
    collection_key: Annotated[str, typer.Argument(help="Zotero collection key.")],
    frowang_name: Annotated[
        Optional[str],
        typer.Option("--name", "-n", help="Override the root Frowang collection name."),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Preview without remote or state changes."),
    ] = False,
    no_sync: Annotated[
        bool,
        typer.Option("--no-sync", help="Ignore existing item sync records."),
    ] = False,
    json_output: JsonOption = False,
    human: HumanOption = False,
) -> None:
    """Upload a Zotero collection to Frowang.

    Creates a matching remote collection tree, uploads item PDFs, and records
    local sync state. Use --dry-run to preview without any remote or state
    changes.
    """
    _ACTIVE_COMMAND.set("zotero.upload")
    data = _zotero_import_service(
        ctx, require_frowang=not dry_run
    ).upload_collection(
        collection_key,
        frowang_name=frowang_name,
        dry_run=dry_run,
        no_sync=no_sync,
    )
    _emit_success("zotero.upload", data, json_output=json_output, human=human)


@zotero_app.command("upload-one")
def zotero_upload_one(
    ctx: typer.Context,
    item_key: Annotated[str, typer.Argument(help="Zotero item key.")],
    target: Annotated[
        Optional[str],
        typer.Option("--target", "-t", help="Target Frowang collection ID."),
    ] = None,
    no_sync: Annotated[
        bool,
        typer.Option("--no-sync", help="Ignore an existing item sync record."),
    ] = False,
    json_output: JsonOption = False,
    human: HumanOption = False,
) -> None:
    """Upload a single Zotero item to Frowang and record sync state.

    Use --target to place the paper in a specific Frowang collection.
    """
    _ACTIVE_COMMAND.set("zotero.upload-one")
    data = _zotero_import_service(ctx, require_frowang=True).upload_one(
        item_key,
        target_collection=target,
        no_sync=no_sync,
    )
    _emit_success(
        "zotero.upload-one", data, json_output=json_output, human=human
    )


@zotero_app.command("status")
def zotero_status(
    limit: Annotated[int, typer.Option(help="Maximum recent records.")] = 20,
    json_output: JsonOption = False,
    human: HumanOption = False,
) -> None:
    """Show recent Zotero sync records from the local state database."""
    _ACTIVE_COMMAND.set("zotero.status")
    _, profile, library_id, store = _zotero_state_context()
    data = store.zotero_status(profile, library_id, limit=limit)
    _emit_success("zotero.status", data, json_output=json_output, human=human)


@zotero_app.command("migrate-state")
def zotero_migrate_state(
    source: Annotated[Path, typer.Argument(help="Legacy sync_state.json path.")],
    json_output: JsonOption = False,
    human: HumanOption = False,
) -> None:
    """Import a legacy sync_state.json into the local state database."""
    _ACTIVE_COMMAND.set("zotero.migrate-state")
    _, profile, library_id, store = _zotero_state_context()
    data = store.import_legacy_zotero_json(
        source,
        profile=profile,
        library_id=library_id,
    )
    _emit_success(
        "zotero.migrate-state", data, json_output=json_output, human=human
    )


def _skill_services(
    platform: str,
    scope: str,
    project_root: Optional[Path],
) -> list[tuple[SkillInstallService, Any]]:
    normalized = platform.strip().lower()
    if normalized not in {"codex", "claude", "all"}:
        raise CommandError(
            code=ErrorCode.USAGE_ERROR,
            message="platform must be codex, claude, or all",
            exit_code=ExitCode.USAGE_ERROR,
            details={"platform": platform},
        )
    manager, _ = _manager()
    source = resolve_skills_source()
    store = StateStore(manager.paths.state_db)
    platforms = ["codex", "claude"] if normalized == "all" else [normalized]
    result: list[tuple[SkillInstallService, Any]] = []
    for item in platforms:
        target = resolve_skill_target(
            item,
            scope,
            project_root=project_root,
        )
        result.append(
            (
                SkillInstallService(
                    source=source,
                    state_store=store,
                    package_version=__version__,
                    clock=_utc_now,
                ),
                target,
            )
        )
    return result


def _multi_target_result(items: list[dict[str, Any]]) -> dict[str, Any]:
    return items[0] if len(items) == 1 else {"targets": items}


@skills_app.command("list")
def skills_list(
    json_output: JsonOption = False,
    human: HumanOption = False,
) -> None:
    """List Skills available in the canonical source.

    Output includes the source root and each skill's manifest snapshot.
    """
    _ACTIVE_COMMAND.set("skills.list")
    source = resolve_skills_source()
    data = {
        "source_root": str(source.root),
        "skills": [source.snapshot(name).as_dict() for name in source.skill_names()],
    }
    _emit_success("skills.list", data, json_output=json_output, human=human)


def _run_skill_target_command(
    command: str,
    *,
    platform: str,
    scope: str,
    project_root: Optional[Path],
    names: Optional[list[str]],
    force: bool = False,
) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    for service, target in _skill_services(platform, scope, project_root):
        if command == "install":
            result = service.install(target, names, force=force)
        elif command == "update":
            result = service.update(target, names, force=force)
        elif command == "uninstall":
            result = service.uninstall(target, names, force=force)
        elif command == "status":
            result = service.status(target, names)
        elif command == "diff":
            result = service.diff(target, names)
        else:  # pragma: no cover - internal command dispatch
            raise AssertionError(command)
        results.append(result)
    return _multi_target_result(results)


@skills_app.command("install")
def skills_install(
    platform: Annotated[str, typer.Option("--platform", help="codex, claude, or all.")],
    skills: Annotated[Optional[list[str]], typer.Argument(help="Skills; empty means all.")] = None,
    scope: Annotated[str, typer.Option(help="user or project.")] = "user",
    project_root: Annotated[
        Optional[Path],
        typer.Option("--project-root", help="Required for project scope."),
    ] = None,
    force: Annotated[bool, typer.Option(help="Explicitly overwrite modified managed files.")] = False,
    json_output: JsonOption = False,
    human: HumanOption = False,
) -> None:
    """Install Skills into an agent platform's skill directory.

    Writes managed files and records the installation in local state.
    Example: paper-agent skills install --platform claude paper-library
    """
    _ACTIVE_COMMAND.set("skills.install")
    data = _run_skill_target_command(
        "install",
        platform=platform,
        scope=scope,
        project_root=project_root,
        names=skills,
        force=force,
    )
    _emit_success("skills.install", data, json_output=json_output, human=human)


@skills_app.command("update")
def skills_update(
    platform: Annotated[str, typer.Option("--platform", help="codex, claude, or all.")],
    skills: Annotated[Optional[list[str]], typer.Argument(help="Skills; empty means all.")] = None,
    scope: Annotated[str, typer.Option(help="user or project.")] = "user",
    project_root: Annotated[Optional[Path], typer.Option("--project-root", help="Required for project scope.")] = None,
    force: Annotated[bool, typer.Option(help="Explicitly overwrite modified managed files.")] = False,
    json_output: JsonOption = False,
    human: HumanOption = False,
) -> None:
    """Update installed Skills to the runtime's bundled version."""
    _ACTIVE_COMMAND.set("skills.update")
    data = _run_skill_target_command(
        "update",
        platform=platform,
        scope=scope,
        project_root=project_root,
        names=skills,
        force=force,
    )
    _emit_success("skills.update", data, json_output=json_output, human=human)


@skills_app.command("status")
def skills_status(
    platform: Annotated[str, typer.Option("--platform", help="codex, claude, or all.")],
    skills: Annotated[Optional[list[str]], typer.Argument(help="Skills; empty means all.")] = None,
    scope: Annotated[str, typer.Option(help="user or project.")] = "user",
    project_root: Annotated[Optional[Path], typer.Option("--project-root", help="Required for project scope.")] = None,
    json_output: JsonOption = False,
    human: HumanOption = False,
) -> None:
    """Show installation status and drift for managed Skills."""
    _ACTIVE_COMMAND.set("skills.status")
    data = _run_skill_target_command(
        "status",
        platform=platform,
        scope=scope,
        project_root=project_root,
        names=skills,
    )
    _emit_success("skills.status", data, json_output=json_output, human=human)


@skills_app.command("diff")
def skills_diff(
    platform: Annotated[str, typer.Option("--platform", help="codex, claude, or all.")],
    skills: Annotated[Optional[list[str]], typer.Argument(help="Skills; empty means all.")] = None,
    scope: Annotated[str, typer.Option(help="user or project.")] = "user",
    project_root: Annotated[Optional[Path], typer.Option("--project-root", help="Required for project scope.")] = None,
    json_output: JsonOption = False,
    human: HumanOption = False,
) -> None:
    """Show file diffs between installed Skills and the canonical source."""
    _ACTIVE_COMMAND.set("skills.diff")
    data = _run_skill_target_command(
        "diff",
        platform=platform,
        scope=scope,
        project_root=project_root,
        names=skills,
    )
    _emit_success("skills.diff", data, json_output=json_output, human=human)


@skills_app.command("uninstall")
def skills_uninstall(
    platform: Annotated[str, typer.Option("--platform", help="codex, claude, or all.")],
    skills: Annotated[Optional[list[str]], typer.Argument(help="Skills; empty means all.")] = None,
    scope: Annotated[str, typer.Option(help="user or project.")] = "user",
    project_root: Annotated[Optional[Path], typer.Option("--project-root", help="Required for project scope.")] = None,
    force: Annotated[bool, typer.Option(help="Remove modified managed files.")] = False,
    json_output: JsonOption = False,
    human: HumanOption = False,
) -> None:
    """Remove managed Skills from an agent platform's skill directory.

    Modified managed files are kept unless --force is given.
    """
    _ACTIVE_COMMAND.set("skills.uninstall")
    data = _run_skill_target_command(
        "uninstall",
        platform=platform,
        scope=scope,
        project_root=project_root,
        names=skills,
        force=force,
    )
    _emit_success("skills.uninstall", data, json_output=json_output, human=human)


@skills_app.command("plugin-build")
def skills_plugin_build(
    destination: Annotated[Path, typer.Argument(help="Output Plugin directory.")],
    force: Annotated[bool, typer.Option(help="Replace an existing generated bundle.")] = False,
    json_output: JsonOption = False,
    human: HumanOption = False,
) -> None:
    """Build a Plugin bundle from the canonical Skill source into a directory."""
    _ACTIVE_COMMAND.set("skills.plugin-build")
    data = PluginBundleBuilder(resolve_skills_source()).build(
        destination,
        version=__version__,
        force=force,
    )
    _emit_success(
        "skills.plugin-build", data, json_output=json_output, human=human
    )


def _remote_options(ctx: typer.Context, api_key: Optional[str], base_url: Optional[str]) -> None:
    ctx.ensure_object(dict)
    ctx.obj["api_key"] = api_key
    ctx.obj["base_url"] = base_url
    if ctx.invoked_subcommand is None:
        raise CommandError(
            code=ErrorCode.USAGE_ERROR,
            message="A command is required",
            exit_code=ExitCode.USAGE_ERROR,
        )


@workspace_app.callback(invoke_without_command=True)
def workspace_root(
    ctx: typer.Context,
    api_key: Annotated[Optional[str], typer.Option("--api-key", help="Explicit Frowang API key.")] = None,
    base_url: Annotated[Optional[str], typer.Option("--base-url", help="Override the active Frowang base URL.")] = None,
) -> None:
    _remote_options(ctx, api_key, base_url)


@paper_app.callback(invoke_without_command=True)
def paper_root(
    ctx: typer.Context,
    api_key: Annotated[Optional[str], typer.Option("--api-key", help="Explicit Frowang API key.")] = None,
    base_url: Annotated[Optional[str], typer.Option("--base-url", help="Override the active Frowang base URL.")] = None,
) -> None:
    _remote_options(ctx, api_key, base_url)


def _artifact_service(ctx: typer.Context) -> ArtifactSyncService:
    manager, credentials = _manager()
    settings = manager.load()
    profile_name = settings.active_profile
    profile = settings.active
    obj = ctx.ensure_object(dict)
    api_key = obj.get("api_key") or credentials.resolve().value
    base_url = obj.get("base_url") or profile.frowang.base_url
    client = FrowangClient(
        api_key=api_key,
        base_url=base_url,
        timeout_seconds=profile.frowang.timeout_seconds,
    )
    ctx.call_on_close(client.close)
    return ArtifactSyncService(
        library=LibraryService(client),
        state_store=StateStore(manager.paths.state_db),
        data_dir=manager.paths.data_dir,
        profile=profile_name,
        base_url=base_url,
        clock=_utc_now,
    )


def _workspace_service(ctx: typer.Context, *, remote: bool) -> WorkspaceService:
    manager, _ = _manager()
    settings = manager.load()
    return WorkspaceService(
        artifact_sync=_artifact_service(ctx) if remote else None,
        state_store=StateStore(manager.paths.state_db),
        papers_dir_name=settings.workspace.papers_dir,
        clock=_utc_now,
    )


@paper_app.command("pull")
def paper_pull(
    ctx: typer.Context,
    paper_id: Annotated[str, typer.Argument(help="Paper short ID or UUID.")],
    json_output: JsonOption = False,
    human: HumanOption = False,
) -> None:
    """Sync a paper's artifacts into the global artifact store.

    Downloads full text, summary, and assets into the shared data directory;
    output lists written paths.
    """
    _ACTIVE_COMMAND.set("paper.pull")
    data = _artifact_service(ctx).sync(paper_id)
    _emit_success("paper.pull", data, json_output=json_output, human=human)


@workspace_app.command("init")
def workspace_init(
    ctx: typer.Context,
    project_root: Annotated[Path, typer.Argument(help="Existing project root.")],
    json_output: JsonOption = False,
    human: HumanOption = False,
) -> None:
    """Initialize a paper workspace in a project root.

    Creates the workspace directory structure and registers it in local state.
    """
    _ACTIVE_COMMAND.set("workspace.init")
    data = _workspace_service(ctx, remote=False).init(project_root)
    _emit_success("workspace.init", data, json_output=json_output, human=human)


@workspace_app.command("add")
def workspace_add(
    ctx: typer.Context,
    project_root: Annotated[Path, typer.Argument(help="Initialized project root.")],
    paper_ids: Annotated[list[str], typer.Argument(help="Paper short IDs or UUIDs.")],
    json_output: JsonOption = False,
    human: HumanOption = False,
) -> None:
    """Add papers to a workspace, downloading their artifacts.

    Writes paper files under the workspace's papers directory and updates
    local sync state.
    """
    _ACTIVE_COMMAND.set("workspace.add")
    data = _workspace_service(ctx, remote=True).add(project_root, paper_ids)
    _emit_success("workspace.add", data, json_output=json_output, human=human)


@workspace_app.command("list")
def workspace_list(
    ctx: typer.Context,
    project_root: Annotated[Path, typer.Argument(help="Initialized project root.")],
    json_output: JsonOption = False,
    human: HumanOption = False,
) -> None:
    """List papers in a workspace."""
    _ACTIVE_COMMAND.set("workspace.list")
    data = _workspace_service(ctx, remote=False).list(project_root)
    _emit_success("workspace.list", data, json_output=json_output, human=human)


@workspace_app.command("status")
def workspace_status(
    ctx: typer.Context,
    project_root: Annotated[Path, typer.Argument(help="Initialized project root.")],
    json_output: JsonOption = False,
    human: HumanOption = False,
) -> None:
    """Show per-paper sync status of a workspace (current, drifted, missing)."""
    _ACTIVE_COMMAND.set("workspace.status")
    data = _workspace_service(ctx, remote=False).status(project_root)
    _emit_success("workspace.status", data, json_output=json_output, human=human)


@workspace_app.command("sync")
def workspace_sync(
    ctx: typer.Context,
    project_root: Annotated[Path, typer.Argument(help="Initialized project root.")],
    paper_ids: Annotated[
        Optional[list[str]], typer.Argument(help="Optional workspace paper IDs.")
    ] = None,
    json_output: JsonOption = False,
    human: HumanOption = False,
) -> None:
    """Sync workspace papers with the artifact store.

    Without paper IDs, syncs all papers registered in the workspace.
    """
    _ACTIVE_COMMAND.set("workspace.sync")
    data = _workspace_service(ctx, remote=True).sync(project_root, paper_ids)
    _emit_success("workspace.sync", data, json_output=json_output, human=human)


@workspace_app.command("remove")
def workspace_remove(
    ctx: typer.Context,
    project_root: Annotated[Path, typer.Argument(help="Initialized project root.")],
    paper_ids: Annotated[list[str], typer.Argument(help="Workspace paper IDs.")],
    force: Annotated[bool, typer.Option(help="Remove modified managed files.")] = False,
    json_output: JsonOption = False,
    human: HumanOption = False,
) -> None:
    """Remove papers from a workspace, deleting their managed files.

    Modified files are kept unless --force is given.
    """
    _ACTIVE_COMMAND.set("workspace.remove")
    data = _workspace_service(ctx, remote=False).remove(
        project_root, paper_ids, force=force
    )
    _emit_success("workspace.remove", data, json_output=json_output, human=human)


@workspace_names_app.command("plan")
def workspace_names_plan(
    ctx: typer.Context,
    project_root: Annotated[Path, typer.Argument(help="Initialized project root.")],
    paper_ids: Annotated[
        Optional[list[str]], typer.Argument(help="Optional workspace paper IDs.")
    ] = None,
    json_output: JsonOption = False,
    human: HumanOption = False,
) -> None:
    """Plan readable directory names for workspace papers.

    Preview only: prints the proposed renames without touching the filesystem.
    """
    _ACTIVE_COMMAND.set("workspace.names.plan")
    data = _workspace_service(ctx, remote=False).names_plan(project_root, paper_ids)
    _emit_success("workspace.names.plan", data, json_output=json_output, human=human)


@workspace_names_app.command("apply")
def workspace_names_apply(
    ctx: typer.Context,
    project_root: Annotated[Path, typer.Argument(help="Initialized project root.")],
    paper_ids: Annotated[
        Optional[list[str]], typer.Argument(help="Optional workspace paper IDs.")
    ] = None,
    json_output: JsonOption = False,
    human: HumanOption = False,
) -> None:
    """Apply the planned readable directory names, renaming paper directories."""
    _ACTIVE_COMMAND.set("workspace.names.apply")
    data = _workspace_service(ctx, remote=False).names_apply(project_root, paper_ids)
    _emit_success("workspace.names.apply", data, json_output=json_output, human=human)


@app.command("doctor")
def doctor(
    remote: Annotated[
        bool,
        typer.Option("--remote/--no-remote", help="Check Frowang connectivity and authentication."),
    ] = True,
    zotero_check: Annotated[
        bool,
        typer.Option("--zotero/--no-zotero", help="Check the configured Zotero connection."),
    ] = True,
    skills_check: Annotated[
        bool,
        typer.Option("--skills/--no-skills", help="Check managed Skill installations."),
    ] = True,
    json_output: JsonOption = False,
    human: HumanOption = False,
) -> None:
    """Run local and remote diagnostics.

    Output is a checks map covering directories, config, credentials, Frowang
    connectivity, Zotero, and Skill installations; overall status is ok or
    warning. Read-only except for directory probes.
    """
    _ACTIVE_COMMAND.set("doctor")
    manager, credentials = _manager()
    paths = manager.paths

    checks: dict[str, Any] = {
        "runtime": {"status": "ok", "version": __version__},
        "directories": {
            "status": "ok",
            "items": {
                "config": _directory_check(paths.config_dir),
                "data": _directory_check(paths.data_dir),
                "cache": _directory_check(paths.cache_dir),
                "log": _directory_check(paths.log_dir),
            },
        },
    }
    directory_items = checks["directories"]["items"]
    if any(item["status"] != "ok" for item in directory_items.values()):
        checks["directories"]["status"] = "warning"

    if paths.config_file.is_file():
        settings = manager.load()
        checks["config"] = {
            "status": "ok",
            "schema_version": settings.schema_version,
            "active_profile": settings.active_profile,
            "path": str(paths.config_file),
        }
    else:
        checks["config"] = {
            "status": "warning",
            "reason": "not_initialized",
            "path": str(paths.config_file),
        }

    credential_status = credentials.status()
    checks["credentials"] = {
        "status": "ok" if credential_status.configured else "warning",
        **credential_status.as_dict(),
    }
    if remote:
        checks["update"] = UpdateCheckService(paths, current_version=__version__).check()
    else:
        checks["update"] = {"status": "not_run", "reason": "disabled_by_option"}
    if not remote:
        checks["remote"] = {"status": "not_run", "reason": "disabled_by_option"}
    elif not paths.config_file.is_file():
        checks["remote"] = {"status": "not_run", "reason": "config_not_initialized"}
    elif not credential_status.configured:
        checks["remote"] = {"status": "not_run", "reason": "credentials_missing"}
    else:
        settings = manager.load()
        profile = settings.profiles[settings.active_profile]
        credential = credentials.resolve()
        client = FrowangClient(
            api_key=credential.value,
            base_url=profile.frowang.base_url,
            timeout_seconds=profile.frowang.timeout_seconds,
            max_get_retries=0,
        )
        try:
            LibraryService(client).list_papers(limit=1)
        except CommandError as exc:
            checks["remote"] = {
                "status": "warning",
                "code": exc.code.value,
                "message": exc.message,
                "retryable": exc.retryable,
            }
        finally:
            client.close()
        if "remote" not in checks:
            checks["remote"] = {
                "status": "ok",
                "base_url": profile.frowang.base_url,
                "credential_source": credential.source,
            }

    if not zotero_check:
        checks["zotero"] = {"status": "not_run", "reason": "disabled_by_option"}
    elif not paths.config_file.is_file():
        checks["zotero"] = {"status": "not_run", "reason": "config_not_initialized"}
    else:
        settings = manager.load()
        zotero_settings = settings.active.zotero
        zotero_key: Optional[str] = None
        zotero_credential_source: Optional[str] = None
        try:
            if zotero_settings.mode == "remote":
                zotero_credential = ZoteroCredentialResolver(paths).resolve()
                zotero_key = zotero_credential.value
                zotero_credential_source = zotero_credential.source
            zotero_client = create_zotero_client(
                zotero_settings,
                api_key=zotero_key,
            )
            zotero_client.check()
        except CommandError as exc:
            checks["zotero"] = {
                "status": "warning",
                "mode": zotero_settings.mode,
                "code": exc.code.value,
                "message": exc.message,
                "retryable": exc.retryable,
            }
        else:
            checks["zotero"] = {
                "status": "ok",
                "mode": zotero_settings.mode,
                "library_id": zotero_settings.library_id,
                "storage_dir": (
                    str(zotero_client.storage_dir)
                    if zotero_client.storage_dir
                    else None
                ),
                "credential_source": zotero_credential_source,
            }

    if not skills_check:
        checks["skill_installations"] = {
            "status": "not_run",
            "reason": "disabled_by_option",
        }
    else:
        store = StateStore(paths.state_db)
        records = store.list_skill_installations()
        installation_items: list[dict[str, Any]] = []
        try:
            source = resolve_skills_source()
            service = SkillInstallService(
                source=source,
                state_store=store,
                package_version=__version__,
                clock=_utc_now,
            )
            grouped: dict[tuple[str, str, str, str], list[str]] = {}
            for record in records:
                key = (
                    record["platform"],
                    record["scope"],
                    record["mode"],
                    record["target_root"],
                )
                grouped.setdefault(key, []).append(record["skill_name"])
            for (platform, scope, mode, root), names in grouped.items():
                target = SkillTarget(platform, scope, mode, Path(root))
                status_result = service.status(target, names)
                installation_items.append(status_result)
        except CommandError as exc:
            checks["skill_installations"] = {
                "status": "warning",
                "code": exc.code.value,
                "message": exc.message,
            }
        else:
            drifted = any(
                skill["status"] != "current"
                for item in installation_items
                for skill in item["skills"].values()
            )
            checks["skill_installations"] = {
                "status": "warning" if drifted else "ok",
                "count": len(records),
                "items": installation_items,
            }

    overall = "ok"
    if any(check.get("status") == "warning" for check in checks.values()):
        overall = "warning"

    _emit_success(
        "doctor",
        {
            "status": overall,
            "checks": checks,
            "paths": paths.as_dict(),
        },
        json_output=json_output,
        human=human,
    )


def main() -> None:
    _REQUEST_ID.set(f"local-{uuid4()}")
    try:
        app(standalone_mode=False)
    except CommandError as exc:
        _write_payload(
            error_envelope(
                error=exc,
                command=_ACTIVE_COMMAND.get(),
                runtime_version=__version__,
                request_id=_request_id(),
            )
        )
        raise SystemExit(int(exc.exit_code)) from None
    except click.ClickException as exc:
        # no_args_is_help raises NoArgsIsHelpError after printing the help
        # text; exit without wrapping it in a JSON error envelope.
        if type(exc).__name__ == "NoArgsIsHelpError":
            raise SystemExit(int(exc.exit_code)) from None
        error = CommandError(
            code=ErrorCode.USAGE_ERROR,
            message=exc.format_message(),
            exit_code=ExitCode.USAGE_ERROR,
        )
        _write_payload(
            error_envelope(
                error=error,
                command="cli",
                runtime_version=__version__,
                request_id=_request_id(),
            )
        )
        raise SystemExit(int(ExitCode.USAGE_ERROR)) from None
    except click.exceptions.Exit as exc:
        raise SystemExit(exc.exit_code) from None
    except Exception as exc:
        error = CommandError(
            code=ErrorCode.INTERNAL_ERROR,
            message="Unexpected Paper Agent error",
            exit_code=ExitCode.INTERNAL_ERROR,
            details={"error_type": type(exc).__name__},
        )
        _write_payload(
            error_envelope(
                error=error,
                command=_ACTIVE_COMMAND.get(),
                runtime_version=__version__,
                request_id=_request_id(),
            )
        )
        raise SystemExit(int(ExitCode.INTERNAL_ERROR)) from None
