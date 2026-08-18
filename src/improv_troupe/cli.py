"""Command-line entry point.

    improv validate PLAN                 # load + validate a ProductionPlan
    improv schema [-o FILE]              # export the JSON Schema (for planners)
    improv backends CONFIG               # discover models on each backend
    improv run PLAN [--config C] [-o F]  # perform the scene -> script.md
    improv run PLAN --dry-run            # perform with a fake backend (no servers)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from rich.console import Console

from .casting import CastingError, build_runtimes, resolve_bindings
from .config import AppConfig
from .domain import ProductionPlan
from .engine import Orchestrator
from .engine.events import SceneEnded, TokenEmitted, TurnCompleted, TurnStarted
from .engine.export import to_markdown
from .engine.orchestrator import ActorRuntime
from .llm.fake import FakeClient

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
        from .llm.client import LLMClient

        for handle, backend in config.backends.items():
            client = LLMClient(base_url=backend.base_url, api_key=backend.api_key)
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

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv if argv is not None else sys.argv[1:])
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
