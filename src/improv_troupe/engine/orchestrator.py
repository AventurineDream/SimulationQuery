"""The performance engine: run a ProductionPlan turn by turn, emitting events."""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import AsyncIterator

from ..domain import Actor, ProductionPlan
from ..llm.client import ChatClient
from .events import Event, SceneEnded, TokenEmitted, TurnCompleted, TurnStarted
from .parsing import clean_line
from .prompts import build_messages
from .transcript import Transcript


@dataclass
class ActorRuntime:
    """An Actor bound to a concrete backend client + model id."""

    actor: Actor
    client: ChatClient
    model: str

    @property
    def name(self) -> str:
        return self.actor.name


class Orchestrator:
    """Drives the scene. Depends only on the ChatClient protocol."""

    def __init__(self, plan: ProductionPlan, runtimes: list[ActorRuntime]):
        if not runtimes:
            raise ValueError("need at least one bound actor to perform")
        self.plan = plan
        self.runtimes = runtimes
        self._by_name = {r.name: r for r in runtimes}
        self.transcript = Transcript()

    async def run(self) -> AsyncIterator[Event]:
        # Seed the opening beat as a stage direction.
        if self.plan.scene.opening_beat:
            self.transcript.add_direction(self.plan.scene.opening_beat)

        order = self._speaking_order()
        max_turns = self.plan.constraints.max_turns

        for index in range(max_turns):
            runtime = self.runtimes[order[index % len(order)]]
            speaker = runtime.name
            yield TurnStarted(index=index, speaker=speaker)

            messages = build_messages(self.plan, runtime.actor, self.transcript)
            buffer: list[str] = []
            async for token in runtime.client.stream_chat(
                model=runtime.model,
                messages=messages,
                **runtime.actor.params.model_dump(exclude_none=True),
            ):
                buffer.append(token)
                yield TokenEmitted(speaker=speaker, text=token)

            others = [n for n in self._by_name if n != speaker]
            line = clean_line("".join(buffer), speaker, others)
            if not line:
                line = "[says nothing]"
            turn = self.transcript.add_line(speaker, line)
            yield TurnCompleted(index=index, turn=turn)

        yield SceneEnded(reason="max_turns", line_count=self.transcript.line_count)

    def _speaking_order(self) -> list[int]:
        """Return a list of runtime indices giving turn order for the run."""
        names = [r.name for r in self.runtimes]
        start = 0
        if self.plan.direction.first_speaker in names:
            start = names.index(self.plan.direction.first_speaker)

        rotation = [(start + i) % len(names) for i in range(len(names))]

        if self.plan.direction.turn_strategy == "random":
            rng = random.Random(self.plan.direction.seed)
            order: list[int] = []
            prev = -1
            for _ in range(self.plan.constraints.max_turns):
                choices = [i for i in range(len(names)) if i != prev] or [0]
                pick = rng.choice(choices)
                order.append(pick)
                prev = pick
            return order

        # round_robin: repeat the rotation enough times to cover max_turns.
        reps = (self.plan.constraints.max_turns // len(rotation)) + 1
        return (rotation * reps)[: self.plan.constraints.max_turns]
