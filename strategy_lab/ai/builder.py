"""AI strategy builder: generate, edit, explain and translate Pine Script, always ending in a *validated* spec.

Pipeline for every task:

1. send the static system prompt + the task message, with the reply schema as structured output;
2. parse the reply (JSON → envelope → transport conversion → Pydantic → spec validator, with the market's
   data context);
3. on any error, up to ``MAX_REPAIRS`` repair rounds in the same conversation, quoting the exact errors;
4. then one escalation to the provider's stronger model (fresh conversation, given the failed reply and its
   errors);
5. then fail cleanly with every remaining error. A spec is only ever returned when it validates.

A refusal ("refusal" in the reply, or the provider's own safety stop) ends the task without a spec. Budget
errors propagate: they mean "stop and report", never "retry".
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, ValidationError

from strategy_lab.ai import prompts
from strategy_lab.ai.config import llm_config
from strategy_lab.ai.ledger import Ledger, Usage
from strategy_lab.ai.providers import make_provider
from strategy_lab.ai.providers.base import (
    LLMProvider,
    ProviderError,
    RefusalError,
    ReplyError,
    TruncatedError,
    Turn,
)
from strategy_lab.ai.transport import from_transport, reply_schema
from strategy_lab.spec.diff import spec_diff
from strategy_lab.spec.schema import StrategySpec
from strategy_lab.spec.validator import Issue, ValidationContext, validate

Task = Literal["generate", "edit", "explain", "from_pine"]
AttemptKind = Literal["first", "repair", "escalation"]
MAX_REPAIRS = 2
MAX_QUESTIONS = 2

# What the stored history can supply per market (DATA.md): BTC has volume and Binance funding; the XAU history
# (HistData) has neither.
DATA_CONTEXT = {
    "BTC-PERP": ValidationContext(has_volume=True, has_funding=True),
    "XAU-PERP": ValidationContext(has_volume=False, has_funding=False),
}


class Envelope(BaseModel):
    """The reply object. Lenient on missing keys: JSON-mode replies are not schema-enforced."""

    model_config = ConfigDict(extra="ignore")

    questions: list[str] = []
    spec: dict[str, Any] | None = None
    changes: list[str] = []
    explanation: str | None = None
    unsupported: list[str] = []
    assumptions: list[str] = []
    refusal: str | None = None


@dataclass
class Attempt:
    provider: str
    model: str
    kind: AttemptKind
    text: str
    errors: list[str]
    usage: Usage | None
    stop: Literal["ok", "refusal", "truncated"] = "ok"  # the provider's stop, for recording and replay

    @property
    def ok(self) -> bool:
        return not self.errors


@dataclass
class BuildResult:
    task: Task
    status: Literal["spec", "questions", "explanation", "refused", "failed"]
    spec: StrategySpec | None = None
    questions: list[str] = field(default_factory=list)
    changes: list[str] = field(default_factory=list)  # as reported by the model (edit)
    diff: list[str] = field(default_factory=list)  # computed from the specs (edit)
    explanation: str | None = None
    unsupported: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    refusal: str | None = None
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    attempts: list[Attempt] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.status != "failed"

    @property
    def first_try_ok(self) -> bool:
        return bool(self.attempts) and self.attempts[0].ok

    @property
    def repairs(self) -> int:
        return sum(a.kind == "repair" for a in self.attempts)

    @property
    def escalated(self) -> bool:
        return any(a.kind == "escalation" for a in self.attempts)

    @property
    def cost_usd(self) -> float:
        return sum(a.usage.cost_usd for a in self.attempts if a.usage)

    @property
    def latency_s(self) -> float:
        return sum(a.usage.latency_s for a in self.attempts if a.usage)


Checker = Callable[[Envelope], "BuildResult | list[str]"]  # a result, or the errors to repair


def _issues(issues: list[Issue]) -> list[str]:
    return [str(i) for i in issues]


def _validated_spec(data: dict[str, Any] | None) -> tuple[StrategySpec | None, list[str], list[str]]:
    """(spec, errors, warnings) for a transport-form spec."""
    if data is None:
        return None, ["$.spec: a spec is required for this task"], []
    canonical, issues = from_transport(data)
    if issues:
        return None, _issues(issues), []
    symbol = canonical.get("market", {}).get("symbol") if isinstance(canonical.get("market"), dict) else None
    result = validate(canonical, DATA_CONTEXT.get(str(symbol)))
    if not result.ok:
        return None, _issues(result.errors), []
    return result.spec, [], _issues(result.warnings)


class Builder:
    """Runs tasks on a writer model, escalating to the provider's stronger model if configured."""

    def __init__(
        self,
        writer: LLMProvider,
        escalation: LLMProvider | None = None,
        schema_defs_key: str | None = None,
    ) -> None:
        self.writer = writer
        self.escalation = escalation
        self.schema = reply_schema(schema_defs_key or writer.config.defs_key)
        self.system = prompts.system_prompt()

    @classmethod
    def for_provider(
        cls, provider: str | None = None, ledger: Ledger | None = None, scope: str = "app"
    ) -> Builder:
        name = provider or llm_config().default_writer
        config = llm_config().providers[name]
        writer = make_provider(name, ledger, scope)
        escalation = make_provider(f"{name}:{config.escalation}", ledger, scope) if config.escalation else None
        return cls(writer, escalation)

    # -- tasks ------------------------------------------------------------------------------------------

    def generate(self, idea: str, answers: str | None = None, allow_questions: bool = True) -> BuildResult:
        allow = allow_questions and not answers

        def check(env: Envelope) -> BuildResult | list[str]:
            if env.refusal:
                return BuildResult("generate", "refused", refusal=env.refusal)
            if env.questions and env.spec is None:
                if not allow:
                    return ["$.questions: questions are not allowed now; build the spec"]
                if len(env.questions) > MAX_QUESTIONS:
                    return [f"$.questions: at most {MAX_QUESTIONS} questions"]
                return BuildResult("generate", "questions", questions=env.questions)
            spec, errors, warnings = _validated_spec(env.spec)
            if spec is None:
                return errors
            spec = spec.model_copy(update={"meta": spec.meta.model_copy(update={"author": "ai"})})
            return BuildResult("generate", "spec", spec=spec, assumptions=env.assumptions, warnings=warnings)

        return self._run("generate", prompts.generate_message(idea, answers, allow), check)

    def edit(self, spec: StrategySpec, request: str) -> BuildResult:
        def check(env: Envelope) -> BuildResult | list[str]:
            if env.refusal:
                return BuildResult("edit", "refused", refusal=env.refusal)
            new, errors, warnings = _validated_spec(env.spec)
            if new is None:
                return errors
            diff = spec_diff(spec, new)
            if not diff:
                return ["$.spec: the spec is unchanged; apply the requested change"]
            return BuildResult(
                "edit",
                "spec",
                spec=new,
                changes=env.changes,
                diff=diff,
                assumptions=env.assumptions,
                warnings=warnings,
            )

        return self._run("edit", prompts.edit_message(spec, request), check)

    def explain(self, spec: StrategySpec) -> BuildResult:
        def check(env: Envelope) -> BuildResult | list[str]:
            if env.refusal:
                return BuildResult("explain", "refused", refusal=env.refusal)
            if not (env.explanation or "").strip():
                return ["$.explanation: the explanation is empty"]
            return BuildResult("explain", "explanation", explanation=env.explanation)

        return self._run("explain", prompts.explain_message(spec), check)

    def from_pine(self, code: str) -> BuildResult:
        def check(env: Envelope) -> BuildResult | list[str]:
            if env.refusal:
                return BuildResult("from_pine", "refused", refusal=env.refusal)
            spec, errors, warnings = _validated_spec(env.spec)
            if spec is None:
                return errors
            spec = spec.model_copy(update={"meta": spec.meta.model_copy(update={"author": "ai"})})
            return BuildResult(
                "from_pine",
                "spec",
                spec=spec,
                unsupported=env.unsupported,
                assumptions=env.assumptions,
                warnings=warnings,
            )

        return self._run("from_pine", prompts.from_pine_message(code), check)

    # -- the loop ---------------------------------------------------------------------------------------

    def _attempt(
        self, provider: LLMProvider, turns: list[Turn], kind: AttemptKind, task: Task, check: Checker
    ) -> tuple[Attempt, BuildResult | None]:
        try:
            data, usage = provider.complete_json(self.system, turns, self.schema, feature=task)
        except RefusalError as exc:
            attempt = Attempt(provider.provider, provider.model, kind, exc.text, [], exc.usage, "refusal")
            return attempt, BuildResult(task, "refused", refusal=str(exc))
        except TruncatedError as exc:
            attempt = Attempt(
                provider.provider, provider.model, kind, exc.text, [str(exc)], exc.usage, "truncated"
            )
            return attempt, None
        except ReplyError as exc:
            return Attempt(provider.provider, provider.model, kind, exc.text, [str(exc)], exc.usage), None
        text = prompts.as_text(data)
        try:
            envelope = Envelope.model_validate(data)
        except ValidationError as exc:
            errors = [f"$.{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors(include_url=False)]
            return Attempt(provider.provider, provider.model, kind, text, errors, usage), None
        outcome = check(envelope)
        if isinstance(outcome, list):
            return Attempt(provider.provider, provider.model, kind, text, outcome, usage), None
        return Attempt(provider.provider, provider.model, kind, text, [], usage), outcome

    def _run(self, task: Task, message: str, check: Checker) -> BuildResult:
        attempts: list[Attempt] = []
        turns: list[Turn] = [("user", message)]
        try:
            for round_ in range(1 + MAX_REPAIRS):
                kind: AttemptKind = "repair" if round_ else "first"
                attempt, result = self._attempt(self.writer, turns, kind, task, check)
                attempts.append(attempt)
                if result is not None:
                    return _finish(result, attempts)
                turns.append(("assistant", attempt.text or "(empty reply)"))
                turns.append(("user", prompts.repair_message(attempt.errors)))
            if self.escalation is not None:
                last = attempts[-1]
                fresh: list[Turn] = [("user", prompts.escalation_message(message, last.text, last.errors))]
                attempt, result = self._attempt(self.escalation, fresh, "escalation", task, check)
                attempts.append(attempt)
                if result is not None:
                    return _finish(result, attempts)
        except ProviderError as exc:
            return _finish(BuildResult(task, "failed", errors=[str(exc)]), attempts)
        return _finish(BuildResult(task, "failed", errors=attempts[-1].errors), attempts)


def _finish(result: BuildResult, attempts: list[Attempt]) -> BuildResult:
    result.attempts = attempts
    return result
