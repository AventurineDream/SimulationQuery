"""Command-line entry point.

    improv validate PLAN                 # load + validate a ProductionPlan
    improv schema [-o FILE]              # export the JSON Schema (for planners)
    improv backends CONFIG               # discover models on each backend
    improv run PLAN [--config C] [-o F]  # perform the scene -> script.md
    improv migrate [--config C] [--data-root DIR]
    improv preflight SEASON --manifest FILE [--config C]
    improv status [--config C] [--data-root DIR]
    improv recover [--config C] [--data-root DIR] [--decision retry|skip|end]
    improv wellness-policy SEASON --manual-review
    improv repair-diary SEASON --character CHARACTER --run RUN_ID --config CONFIG
    improv serve --dry-run [--config C] [--data-root DIR]
    improv run PLAN --dry-run            # perform with a fake backend (no servers)
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import json
import os
import signal
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from rich.console import Console

from .application import (
    CommandBus,
    DiaryActor,
    DiaryService,
    DryRunSceneFactory,
    LiveSceneFactory,
    PreflightSeason,
    PublicationError,
    PublicationService,
    ResolveRecovery,
    SceneModelManifest,
    SeasonDayCoordinator,
    ServicePaths,
    SetWellnessPolicy,
    WellnessService,
    build_linux_service,
    read_service_status,
    validate_model_manifest,
)
from .casting import CastingError, build_runtimes, resolve_bindings
from .clock import SystemClock
from .config import AppConfig, ServiceSettings
from .domain import ProductionPlan
from .engine import Orchestrator
from .engine.events import SceneEnded, TokenEmitted, TurnCompleted, TurnStarted
from .engine.export import to_markdown
from .engine.orchestrator import ActorRuntime
from .infrastructure import SCHEMA_VERSION, RecordRepository, SQLiteDatabase, SeasonRepository
from .llm.fake import FakeClient
from .web.dashboard import DashboardApplication, DashboardConfig, hash_password, serve_dashboard

console = Console()


def _load_plan(path: str) -> ProductionPlan:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return ProductionPlan.model_validate(data)


def _write(path: str, text: str) -> None:
    p = Path(path)
    if p.parent != Path(""):
        p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def cmd_validate(args: argparse.Namespace) -> int:
    try:
        plan = _load_plan(args.plan)
    except Exception as exc:  # noqa: BLE001 - surface any load/validation error
        console.print(f"[red]Invalid plan:[/red] {exc}")
        return 1
    console.print(f"[green]OK[/green] — {plan.title!r} with {len(plan.cast)} cast members")
    for a in plan.cast:
        bind = a.casting.model or a.casting.model_hint or a.casting.size_class or "unbound"
        console.print(f"  • {a.name}  [dim]({bind})[/dim]")
    console.print(
        f"  strategy=[cyan]{plan.direction.turn_strategy}[/cyan] "
        f"max_turns=[cyan]{plan.constraints.max_turns}[/cyan]"
    )
    return 0


def cmd_schema(args: argparse.Namespace) -> int:
    schema = ProductionPlan.model_json_schema()
    text = json.dumps(schema, indent=2)
    if args.out:
        _write(args.out, text + "\n")
        console.print(f"[green]Wrote[/green] JSON Schema to {args.out}")
    else:
        print(text)
    return 0


def cmd_backends(args: argparse.Namespace) -> int:
    config = AppConfig.load(args.config)

    async def _discover() -> None:
        from .llm.client import make_client

        for handle, backend in config.backends.items():
            client = make_client(
                kind=backend.kind,
                base_url=backend.base_url,
                api_key=backend.api_key,
                timeout=backend.timeout_seconds,
            )
            try:
                models = await client.list_models()
                console.print(f"[green]{handle}[/green] [dim]{backend.base_url}[/dim]")
                for m in models:
                    console.print(f"    {m}")
            except Exception as exc:  # noqa: BLE001
                console.print(f"[red]{handle}[/red] [dim]{backend.base_url}[/dim] — {exc}")

    asyncio.run(_discover())
    return 0


def _build_runtimes(args: argparse.Namespace, plan: ProductionPlan) -> list[ActorRuntime]:
    if args.dry_run:
        fake = FakeClient()
        return [
            ActorRuntime(actor=a, client=fake, model=a.casting.model_hint or "fake")
            for a in plan.cast
        ]

    if not args.config:
        raise SystemExit("run requires --config backends.yaml (or use --dry-run)")
    config = AppConfig.load(args.config)
    bindings = resolve_bindings(plan, config)
    for b in bindings:
        console.print(f"[dim]cast[/dim] {b.actor_name} → {b.backend}:{b.model} ({b.how})")
    return build_runtimes(plan, config, bindings)


async def _perform(plan: ProductionPlan, runtimes: list[ActorRuntime], out_path: str) -> None:
    orch = Orchestrator(plan, runtimes)
    console.rule(f"[bold]{plan.title}")
    if plan.scene.opening_beat:
        console.print(f"[italic dim]{plan.scene.opening_beat}[/italic dim]\n")

    async for event in orch.run():
        if isinstance(event, TurnStarted):
            console.print(f"[bold cyan]{event.speaker}[/bold cyan]: ", end="")
        elif isinstance(event, TokenEmitted):
            console.print(event.text, end="")
        elif isinstance(event, TurnCompleted):
            console.print()  # newline after the streamed line
        elif isinstance(event, SceneEnded):
            console.rule(f"[dim]scene end · {event.reason} · {event.line_count} lines")

    _write(out_path, to_markdown(plan, orch.transcript, runtimes))
    console.print(f"[green]Wrote script[/green] → {out_path}")


def cmd_run(args: argparse.Namespace) -> int:
    try:
        plan = _load_plan(args.plan)
        runtimes = _build_runtimes(args, plan)
    except (CastingError, SystemExit) as exc:
        console.print(f"[red]{exc}[/red]")
        return 1
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]Could not start:[/red] {exc}")
        return 1

    out_path = args.out or f"{_slug(plan.title)}.script.md"
    asyncio.run(_perform(plan, runtimes, out_path))
    return 0


def _service_settings(args: argparse.Namespace) -> ServiceSettings:
    """Load optional service settings, with explicit CLI paths taking precedence."""
    settings = ServiceSettings()
    if getattr(args, "config", None):
        settings = AppConfig.load(args.config).service
    updates = {}
    if getattr(args, "data_root", None):
        updates["data_root"] = Path(args.data_root)
    if getattr(args, "poll_seconds", None) is not None:
        updates["poll_interval_seconds"] = args.poll_seconds
    if getattr(args, "worker_id", None):
        updates["worker_id"] = args.worker_id
    return settings.model_copy(update=updates) if updates else settings


def _service_paths(args: argparse.Namespace) -> ServicePaths:
    return ServicePaths.from_root(_service_settings(args).data_root)


def _print_json_or_readable(payload: dict[str, object], *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, indent=2, sort_keys=True, default=str))
        return
    for key, value in payload.items():
        if isinstance(value, (dict, list)):
            console.print(f"[bold]{key}[/bold]:")
            console.print(json.dumps(value, indent=2, sort_keys=True, default=str))
        else:
            console.print(f"[bold]{key}[/bold]: {value}")


def _open_existing_service_database(paths: ServicePaths) -> SQLiteDatabase:
    if not paths.database_path.exists():
        raise FileNotFoundError(
            f"service state is not initialized at {paths.database_path}; run `improv migrate` first"
        )
    database = SQLiteDatabase(paths.database_path)
    database.migrate()
    return database


def cmd_migrate(args: argparse.Namespace) -> int:
    try:
        paths = _service_paths(args)
        paths.prepare()
        database = SQLiteDatabase(paths.database_path)
        database.migrate()
        integrity = database.connection.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            raise RuntimeError(f"SQLite integrity check failed: {integrity}")
        payload = {
            "database": str(paths.database_path),
            "data_root": str(paths.data_root),
            "schema_version": SCHEMA_VERSION,
            "integrity": integrity,
        }
        _print_json_or_readable(payload, as_json=args.json)
        database.close()
        return 0
    except Exception as exc:  # noqa: BLE001 - CLI should report actionable failures
        console.print(f"[red]Migration failed:[/red] {exc}")
        return 1


def cmd_status(args: argparse.Namespace) -> int:
    database = None
    try:
        paths = _service_paths(args)
        database = _open_existing_service_database(paths)
        payload = read_service_status(database, paths=paths)
        _print_json_or_readable(payload, as_json=args.json)
        return 0
    except Exception as exc:  # noqa: BLE001 - CLI should report actionable failures
        console.print(f"[red]Status unavailable:[/red] {exc}")
        return 1
    finally:
        if database is not None:
            database.close()


def cmd_recover(args: argparse.Namespace) -> int:
    database = None
    try:
        paths = _service_paths(args)
        database = _open_existing_service_database(paths)
        if args.decision is None:
            payload = read_service_status(database, paths=paths)
            pending = {"recoveries": payload["recoveries"]}
            _print_json_or_readable(pending, as_json=args.json)
            return 0
        if not args.season or not args.run:
            raise ValueError("--season and --run are required with --decision")
        command = ResolveRecovery(
            request_id=args.request_id or f"cli-recover:{args.run}:{args.decision}:{uuid4().hex}",
            season_id=args.season,
            run_id=args.run,
            decision=args.decision,
        )
        result = CommandBus(database).execute(command)
        _print_json_or_readable(result.payload, as_json=args.json)
        return 0
    except Exception as exc:  # noqa: BLE001 - CLI should report actionable failures
        console.print(f"[red]Recovery command failed:[/red] {exc}")
        return 1
    finally:
        if database is not None:
            database.close()


def cmd_wellness_policy(args: argparse.Namespace) -> int:
    database = None
    try:
        paths = _service_paths(args)
        database = _open_existing_service_database(paths)
        result = CommandBus(database).execute(
            SetWellnessPolicy(
                request_id=args.request_id
                or f"cli-wellness-policy:{args.season}:{uuid4().hex}",
                season_id=args.season,
                auto_tap_out=not args.manual_review,
            )
        )
        _print_json_or_readable(result.payload, as_json=args.json)
        return 0
    except Exception as exc:  # noqa: BLE001 - CLI should report actionable failures
        console.print(f"[red]Wellness policy update failed:[/red] {exc}")
        return 1
    finally:
        if database is not None:
            database.close()


def cmd_repair_diary(args: argparse.Namespace) -> int:
    """Make one explicit new diary attempt while preserving prior private evidence."""
    database = None
    try:
        paths = _service_paths(args)
        database = _open_existing_service_database(paths)
        season = SeasonRepository(database).get(args.season)
        if season.auto_tap_out:
            raise ValueError(
                f"season {args.season} still has automatic tap-out enabled; "
                "apply `wellness-policy --manual-review` before repairing a diary"
            )

        run = database.connection.execute(
            "SELECT r.run_id, r.season_id, r.status, s.day_number, s.slot_number "
            "FROM runs r JOIN schedule_slots s ON s.slot_id = r.slot_id "
            "WHERE r.run_id = ? AND r.season_id = ?",
            (args.run, args.season),
        ).fetchone()
        if run is None:
            raise ValueError(f"unknown run for season {args.season}: {args.run}")
        if str(run["status"]) != "COMPLETED":
            raise ValueError(
                f"repair context must be a completed run; {args.run} is {run['status']}"
            )

        records = RecordRepository(database)
        diary = records.get_diary(
            season_id=args.season,
            character_id=args.character,
            day_number=int(run["day_number"]),
        )
        if diary is None:
            raise ValueError(
                f"no diary obligation for {args.season}:{args.character}:day:{run['day_number']}"
            )
        if str(diary["status"]) != "PRIVATE" or diary["content_path"]:
            raise ValueError(
                "repair is limited to a private diary without accepted content; "
                f"current status is {diary['status']}"
            )

        config = AppConfig.load(args.config)
        clock = SystemClock()
        scene_factory = LiveSceneFactory(
            database=database,
            roots=paths.roots,
            config=config,
            clock=clock,
        )
        scene = scene_factory({"season_id": args.season, "run_id": args.run})
        scene._hydrate()  # Reuse the accepted, durable scene transcript as context.
        actors = tuple(
            DiaryActor(
                character_id=actor.character_id,
                name=actor.name,
                role_sheet=actor.role_sheet,
                executor=actor.executor,
                known_memory=actor.known_memory,
            )
            for actor in scene.actors
        )
        target = next((actor for actor in actors if actor.character_id == args.character), None)
        if target is None:
            raise ValueError(f"character is not in the season cast: {args.character}")

        day_number = int(run["day_number"])
        diary_service = DiaryService(
            season_id=args.season,
            day_number=day_number,
            actors=actors,
            clock=clock,
            wellness=WellnessService(
                database=database,
                season_id=args.season,
                clock=clock,
                audit_root=paths.roots.private,
                auto_tap_out=season.auto_tap_out,
            ),
        )
        result = asyncio.run(
            diary_service.write_after_run(
                target,
                current_slot_number=int(run["slot_number"]),
                accepted_scene=tuple(scene.transcript.script_view().splitlines()),
                cutoff_at=datetime.max.replace(tzinfo=timezone.utc),
                allow_repair=True,
            )
        )
        _print_json_or_readable(
            {
                "season_id": args.season,
                "character_id": args.character,
                "run_id": args.run,
                "day_number": day_number,
                "slot_number": int(run["slot_number"]),
                "repair": True,
                "diary": result.__dict__,
            },
            as_json=args.json,
        )
        return 0
    except Exception as exc:  # noqa: BLE001 - CLI should report actionable failures
        console.print(f"[red]Diary repair failed:[/red] {exc}")
        return 1
    finally:
        if database is not None:
            database.close()


def cmd_preflight(args: argparse.Namespace) -> int:
    database = None
    try:
        paths = _service_paths(args)
        paths.prepare()
        database = SQLiteDatabase(paths.database_path)
        database.migrate()
        manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
        if not isinstance(manifest, dict) or not manifest:
            raise ValueError("model manifest must be a non-empty JSON object")
        config = AppConfig.load(args.config) if args.config else AppConfig()
        season = SeasonRepository(database).get(args.season)
        actor_ids = [member.character_id for member in season.cast]
        typed_manifest = SceneModelManifest.model_validate(manifest)
        validate_model_manifest(typed_manifest, actor_ids=actor_ids, config=config)
        integrity = database.connection.execute("PRAGMA integrity_check").fetchone()[0]
        checks = {
            "sqlite_integrity": integrity == "ok",
            "persistent_roots": all(
                path.exists() for path in (paths.roots.state, paths.roots.private, paths.roots.public)
            ),
            "model_manifest": True,
        }
        result = CommandBus(database).execute(
            PreflightSeason(
                request_id=args.request_id or f"cli-preflight:{args.season}:{uuid4().hex}",
                season_id=args.season,
                checks=checks,
                model_manifest=manifest,
            )
        )
        _print_json_or_readable(result.payload, as_json=args.json)
        return 0
    except Exception as exc:  # noqa: BLE001 - CLI should report actionable failures
        console.print(f"[red]Preflight failed:[/red] {exc}")
        return 1
    finally:
        if database is not None:
            database.close()


def _publication_decisions(values: list[str] | None) -> dict[str, str]:
    decisions: dict[str, str] = {}
    for value in values or []:
        try:
            diary_id, decision = value.split("=", 1)
        except ValueError as exc:
            raise ValueError("--diary must be DIARY_ID=CLEARED or DIARY_ID=PRIVATE") from exc
        if not diary_id or decision not in {"CLEARED", "PRIVATE"}:
            raise ValueError("--diary must be DIARY_ID=CLEARED or DIARY_ID=PRIVATE")
        if diary_id in decisions:
            raise ValueError(f"duplicate diary decision: {diary_id}")
        decisions[diary_id] = decision
    return decisions


def cmd_publish(args: argparse.Namespace) -> int:
    database = None
    try:
        paths = _service_paths(args)
        database = _open_existing_service_database(paths)
        service = PublicationService(database=database, roots=paths.roots)
        decisions = _publication_decisions(args.diary)
        if args.publication_id:
            result = None
            for diary_id, decision in decisions.items():
                result = service.review_diary(
                    publication_id=args.publication_id,
                    diary_id=diary_id,
                    decision=decision,
                )
            if result is None:
                raise ValueError("--publication-id requires at least one --diary decision")
            published = service.publish(publication_id=args.publication_id)
        else:
            if not all(
                (args.wellness_confirmed, args.privacy_reviewed, args.consent_confirmed)
            ):
                raise ValueError(
                    "first publish approval requires --wellness-confirmed, "
                    "--privacy-reviewed, and --consent-confirmed"
                )
            review = service.begin_review(
                season_id=args.season,
                wellness_confirmed=True,
                privacy_reviewed=True,
                consent_confirmed=True,
                diary_decisions=decisions,
            )
            if review.status != "CLEARED":
                _print_json_or_readable(
                    {
                        "publication_id": review.publication_id,
                        "status": review.status,
                        "eligible_diary_ids": list(review.eligible_diary_ids),
                        "next": "supply --publication-id and --diary DIARY_ID=CLEARED|PRIVATE",
                    },
                    as_json=args.json,
                )
                return 2
            published = service.publish(publication_id=review.publication_id)
        _print_json_or_readable(
            {
                "publication_id": published.publication_id,
                "version": published.version,
                "status": published.status,
                "eligible_diary_ids": list(published.eligible_diary_ids),
                "output_path": published.output_path,
                "manifest_sha256": published.manifest_sha256,
            },
            as_json=args.json,
        )
        return 0
    except Exception as exc:  # noqa: BLE001 - CLI should report actionable failures
        console.print(f"[red]Publication failed:[/red] {exc}")
        return 1
    finally:
        if database is not None:
            database.close()


def cmd_dashboard_hash(args: argparse.Namespace) -> int:
    first = getpass.getpass("Dashboard password: ")
    second = getpass.getpass("Repeat dashboard password: ")
    if first != second:
        console.print("[red]Passwords do not match.[/red]")
        return 1
    print(hash_password(first))
    return 0


def cmd_dashboard(args: argparse.Namespace) -> int:
    password_hash = os.environ.get("IMPROV_DASHBOARD_PASSWORD_HASH", "")
    if not password_hash:
        console.print(
            "[red]Set IMPROV_DASHBOARD_PASSWORD_HASH first.[/red] "
            "Generate it with `improv dashboard-hash`; do not put the plaintext password in config."
        )
        return 2
    settings = _service_settings(args)
    paths = ServicePaths.from_root(settings.data_root)
    environment = (
        getattr(args, "environment", None)
        or os.environ.get("IMPROV_DASHBOARD_ENVIRONMENT")
        or (
            "production"
            if paths.data_root.resolve(strict=False) == Path("/var/lib/improv-troupe")
            else "sandbox"
        )
    )
    try:
        app = DashboardApplication(
            DashboardConfig(
                paths=paths,
                username=os.environ.get("IMPROV_DASHBOARD_USERNAME", "owner"),
                password_hash=password_hash,
                secure_cookie=args.secure_cookie,
                # v2 is the live operator surface.  ``--legacy`` is an
                # explicit rollback switch; ``--enable-v2`` remains accepted
                # for launch-script compatibility.
                enable_v2=not getattr(args, "legacy", False),
                environment=environment,
            )
        )
        server = serve_dashboard(app, host=args.bind, port=args.port)
        console.print(
            f"[green]dashboard running[/green] http://{args.bind}:{args.port} "
            f"data_root={paths.data_root}"
        )
        server.serve_forever()
        return 0
    except KeyboardInterrupt:
        return 0
    except Exception as exc:  # noqa: BLE001 - CLI should report actionable failures
        console.print(f"[red]Dashboard stopped with error:[/red] {exc}")
        return 1
    finally:
        if "server" in locals():
            server.server_close()


def cmd_serve(args: argparse.Namespace) -> int:
    """Run the service loop with either the live or infrastructure-test factory."""
    settings = _service_settings(args)
    paths = ServicePaths.from_root(settings.data_root)
    database = SQLiteDatabase(paths.database_path)
    clock = SystemClock()
    try:
        post_scene = None
        close_day = None
        if args.dry_run:
            scene_factory = DryRunSceneFactory(database)
        else:
            if not args.config:
                console.print(
                    "[red]Live serve requires --config[/red] with backend endpoints; "
                    "use --dry-run for an infrastructure-only poll."
                )
                return 2
            scene_factory = LiveSceneFactory(
                database=database,
                roots=paths.roots,
                config=AppConfig.load(args.config),
                clock=clock,
            )
            day_coordinator = SeasonDayCoordinator(
                database=database,
                clock=clock,
                scene_factory=scene_factory,
            )
            post_scene = day_coordinator.after_scene
            close_day = day_coordinator.close_day
            for season in scene_factory.seasons.list_all():
                if season.status.value in {
                    "ARMED",
                    "RUNNING",
                    "PAUSED",
                    "RECOVERY_REQUIRED",
                    "CLOSING",
                }:
                    scene_factory.validate_season(season.season_id)
        service = build_linux_service(
            paths=paths,
            scene_factory=scene_factory,
            database=database,
            clock=clock,
            worker_id=settings.worker_id,
            poll_interval_seconds=settings.poll_interval_seconds,
            recovery_wait_window=timedelta(seconds=settings.recovery_wait_seconds),
            auto_retry_timeouts=settings.auto_retry_timeouts,
            timeout_retry_max_attempts=settings.timeout_retry_max_attempts,
            post_scene=post_scene,
            close_day=close_day,
        )

        async def _run() -> None:
            if args.once:
                cycle = await service.run_once()
                console.print(
                    f"[green]service poll complete[/green] processed={cycle.processed_items} "
                    f"projected={cycle.projected_artifacts} "
                    f"recoveries={len(cycle.promoted_recoveries)}"
                )
                return
            stop_event = asyncio.Event()
            loop = asyncio.get_running_loop()
            for signum in (signal.SIGINT, signal.SIGTERM):
                try:
                    loop.add_signal_handler(signum, stop_event.set)
                except (NotImplementedError, RuntimeError):
                    signal.signal(signum, lambda *_: stop_event.set())
            console.print(
                f"[green]service running[/green] data_root={paths.data_root} "
                f"poll={settings.poll_interval_seconds:g}s "
                f"recovery_wait={settings.recovery_wait_seconds:g}s"
            )
            await service.run_forever(stop_event=stop_event)
            console.print("[green]service stopped[/green]")

        asyncio.run(_run())
        return 0
    except KeyboardInterrupt:
        return 0
    except Exception as exc:  # noqa: BLE001 - let systemd restart unexpected failures
        console.print(f"[red]Service stopped with error:[/red] {exc}")
        return 1
    finally:
        database.close()


def _slug(title: str) -> str:
    return "".join(c if c.isalnum() else "-" for c in title.lower()).strip("-") or "scene"


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="improv", description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)

    v = sub.add_parser("validate", help="validate a ProductionPlan JSON file")
    v.add_argument("plan")
    v.set_defaults(func=cmd_validate)

    s = sub.add_parser("schema", help="export the ProductionPlan JSON Schema")
    s.add_argument("-o", "--out")
    s.set_defaults(func=cmd_schema)

    b = sub.add_parser("backends", help="list models available on each backend")
    b.add_argument("config")
    b.set_defaults(func=cmd_backends)

    r = sub.add_parser("run", help="perform a scene from a plan")
    r.add_argument("plan")
    r.add_argument("-c", "--config", help="backends.yaml")
    r.add_argument("-o", "--out", help="output script path")
    r.add_argument("--dry-run", action="store_true", help="use a fake backend (no servers)")
    r.set_defaults(func=cmd_run)

    m = sub.add_parser("migrate", help="initialize or migrate persistent service state")
    m.add_argument("-c", "--config", help="service/backends YAML")
    m.add_argument("--data-root", help="persistent service root (default: /var/lib/improv-troupe)")
    m.add_argument("--json", action="store_true", help="emit JSON")
    m.set_defaults(func=cmd_migrate)

    pf = sub.add_parser("preflight", help="record a successful season preflight")
    pf.add_argument("season", help="season id, for example S01")
    pf.add_argument("--manifest", required=True, help="private model manifest JSON")
    pf.add_argument("--request-id", help="stable id for safe command replay")
    pf.add_argument("-c", "--config", help="service/backends YAML")
    pf.add_argument("--data-root", help="persistent service root")
    pf.add_argument("--json", action="store_true", help="emit JSON")
    pf.set_defaults(func=cmd_preflight)

    pub = sub.add_parser("publish", help="review and explicitly publish a closed season")
    pub.add_argument("season", help="season id, for example S01")
    pub.add_argument("--diary", action="append", help="DIARY_ID=CLEARED|PRIVATE; repeatable")
    pub.add_argument("--publication-id", help="revise an existing review before publishing")
    pub.add_argument("--wellness-confirmed", action="store_true")
    pub.add_argument("--privacy-reviewed", action="store_true")
    pub.add_argument("--consent-confirmed", action="store_true")
    pub.add_argument("-c", "--config", help="service/backends YAML")
    pub.add_argument("--data-root", help="persistent service root")
    pub.add_argument("--json", action="store_true", help="emit JSON")
    pub.set_defaults(func=cmd_publish)

    dh = sub.add_parser("dashboard-hash", help="create a scrypt hash for the dashboard password")
    dh.set_defaults(func=cmd_dashboard_hash)

    dash = sub.add_parser("dashboard", help="run the private operator dashboard")
    dash.add_argument("-c", "--config", help="service/backends YAML")
    dash.add_argument("--data-root", help="persistent service root")
    dash.add_argument("--bind", default="127.0.0.1", help="private interface to bind")
    dash.add_argument("--port", type=int, default=8765)
    dash.add_argument("--secure-cookie", action="store_true", help="set Secure on the session cookie")
    dash.add_argument(
        "--environment",
        choices=("sandbox", "production"),
        help="truthful environment label (otherwise inferred from the configured data root)",
    )
    dash.add_argument(
        "--enable-v2",
        action="store_true",
        help="explicitly select the v2 operator dashboard (kept for compatibility)",
    )
    dash.add_argument(
        "--legacy",
        action="store_true",
        help="serve the preserved v1 dashboard as an explicit rollback",
    )
    dash.set_defaults(func=cmd_dashboard)

    st = sub.add_parser("status", help="show durable service, season, queue, and recovery state")
    st.add_argument("-c", "--config", help="service/backends YAML")
    st.add_argument("--data-root", help="persistent service root")
    st.add_argument("--json", action="store_true", help="emit JSON")
    st.set_defaults(func=cmd_status)

    rc = sub.add_parser("recover", help="list or resolve creator recovery requests")
    rc.add_argument("--season", help="season id when resolving a request")
    rc.add_argument("--run", help="run id when resolving a request")
    rc.add_argument("--decision", choices=("retry", "skip", "end"))
    rc.add_argument("--request-id", help="stable id for safe command replay")
    rc.add_argument("-c", "--config", help="service/backends YAML")
    rc.add_argument("--data-root", help="persistent service root")
    rc.add_argument("--json", action="store_true", help="emit JSON")
    rc.set_defaults(func=cmd_recover)

    wp = sub.add_parser(
        "wellness-policy", help="set a season's automatic tap-out policy"
    )
    wp.add_argument("season", help="season id, for example S01")
    policy = wp.add_mutually_exclusive_group(required=True)
    policy.add_argument(
        "--manual-review",
        action="store_true",
        help="record signals and leave actor removal to the creator",
    )
    policy.add_argument(
        "--automatic-tap-out",
        action="store_true",
        help="restore the default three-signal automatic departure",
    )
    wp.add_argument("--request-id", help="stable id for safe command replay")
    wp.add_argument("-c", "--config", help="service/backends YAML")
    wp.add_argument("--data-root", help="persistent service root")
    wp.add_argument("--json", action="store_true", help="emit JSON")
    wp.set_defaults(func=cmd_wellness_policy)

    rd = sub.add_parser(
        "repair-diary", help="make one new private diary attempt for an incomplete record"
    )
    rd.add_argument("season", help="season id, for example S01")
    rd.add_argument("--character", required=True, help="character id to repair")
    rd.add_argument("--run", required=True, help="completed run supplying scene context")
    rd.add_argument("-c", "--config", required=True, help="service/backends YAML")
    rd.add_argument("--data-root", help="persistent service root")
    rd.add_argument("--json", action="store_true", help="emit JSON")
    rd.set_defaults(func=cmd_repair_diary)

    sv = sub.add_parser("serve", help="run the always-on Linux workflow service")
    sv.add_argument("-c", "--config", help="service/backends YAML")
    sv.add_argument("--data-root", help="persistent service root")
    sv.add_argument("--poll-seconds", type=float, help="poll interval override")
    sv.add_argument("--worker-id", help="durable worker identity")
    sv.add_argument("--dry-run", action="store_true", help="complete due scenes without model calls")
    sv.add_argument("--once", action="store_true", help="run one poll and exit")
    sv.set_defaults(func=cmd_serve)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv if argv is not None else sys.argv[1:])
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
