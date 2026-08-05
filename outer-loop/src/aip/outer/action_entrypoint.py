"""Translate GitHub Action inputs into the command-specific outer-loop CLI."""

from __future__ import annotations

from dataclasses import dataclass
import os
import sys
from typing import Mapping, Sequence


ACTION_MODE_ENV = "AIP_OUTER_ACTION_MODE"

ACTION_INPUTS = frozenset({
    "verb",
    "subject",
    "token",
    "expires-on",
    "mlflow-url",
    "experiment-name",
    "run-id",
    "run-ids",
    "run-name",
    "child-run-name",
    "thresholds-file",
    "ranking-criteria-file",
    "policy-config-file",
    "subscription-id",
    "resource-group",
    "workspace-name",
    "model-name",
    "model-version",
    "endpoint-name",
    "deployment-name",
    "max-evidence-age-minutes",
    "min-sample-count",
})

UNSUPPORTED_INPUTS = frozenset({
    "subscription-id",
    "resource-group",
    "workspace-name",
})

COMMON_OPTIONS = ("token", "expires-on", "mlflow-url")
MONITORING_OPTIONS = (
    "experiment-name",
    "model-name",
    "model-version",
    "endpoint-name",
    "deployment-name",
    "max-evidence-age-minutes",
    "min-sample-count",
)


@dataclass(frozen=True)
class CommandSpec:
    option_inputs: tuple[str, ...]
    required_inputs: frozenset[str]
    required_alternatives: tuple[frozenset[str], ...] = ()

    @property
    def applicable_inputs(self) -> frozenset[str]:
        return frozenset({"verb", "subject", *self.option_inputs})


@dataclass(frozen=True)
class AdaptedInvocation:
    argv: tuple[str, ...]
    mode: str


class ActionContractError(ValueError):
    """An action input does not satisfy the selected command contract."""


def _spec(
    *option_inputs: str,
    required_inputs: tuple[str, ...],
    required_alternatives: tuple[tuple[str, ...], ...] = (),
) -> CommandSpec:
    options = COMMON_OPTIONS + option_inputs
    return CommandSpec(
        option_inputs=options,
        required_inputs=frozenset({"verb", "subject", *required_inputs}),
        required_alternatives=tuple(
            frozenset(alternatives) for alternatives in required_alternatives
        ),
    )


COMMAND_SPECS = {
    ("evaluate", "gate"): _spec(
        "experiment-name",
        "run-id",
        "child-run-name",
        "thresholds-file",
        required_inputs=("mlflow-url", "experiment-name", "thresholds-file"),
    ),
    ("evaluate", "policy"): _spec(
        *MONITORING_OPTIONS,
        "policy-config-file",
        required_inputs=("mlflow-url", "policy-config-file"),
        required_alternatives=(("experiment-name", "model-name"),),
    ),
    ("compare", "candidates"): _spec(
        "experiment-name",
        "run-ids",
        "run-name",
        "child-run-name",
        "ranking-criteria-file",
        required_inputs=("mlflow-url", "experiment-name", "ranking-criteria-file"),
    ),
    ("report", "experiment"): _spec(
        "experiment-name",
        required_inputs=("mlflow-url", "experiment-name"),
    ),
    ("check", "monitoring"): _spec(
        *MONITORING_OPTIONS,
        required_inputs=("mlflow-url",),
        required_alternatives=(("experiment-name", "model-name"),),
    ),
}


def action_input_environment_name(input_name: str) -> str:
    return f"INPUT_{input_name.upper().replace('-', '_')}"


def _is_nonblank(value: str | None) -> bool:
    return value is not None and bool(value.strip())


def _command_name(command: tuple[str, str]) -> str:
    return " ".join(command)


def adapt_action_environment(environ: Mapping[str, str]) -> AdaptedInvocation:
    values = {
        input_name: environ.get(action_input_environment_name(input_name), "")
        for input_name in ACTION_INPUTS
    }
    verb = values["verb"].strip()
    subject = values["subject"].strip()
    if not verb:
        raise ActionContractError("Input 'verb' is required")
    if not subject:
        raise ActionContractError("Input 'subject' is required")

    command = (verb, subject)
    if command not in COMMAND_SPECS:
        raise ActionContractError("The selected verb and subject are not supported")
    spec = COMMAND_SPECS[command]
    command_name = _command_name(command)

    for input_name in sorted(UNSUPPORTED_INPUTS):
        if _is_nonblank(values[input_name]):
            raise ActionContractError(
                f"Input '{input_name}' is unsupported for command '{command_name}'"
            )

    for input_name in sorted(ACTION_INPUTS - spec.applicable_inputs - UNSUPPORTED_INPUTS):
        if _is_nonblank(values[input_name]):
            raise ActionContractError(
                f"Input '{input_name}' is not valid for command '{command_name}'"
            )

    for input_name in sorted(spec.required_inputs):
        if not _is_nonblank(values[input_name]):
            raise ActionContractError(
                f"Input '{input_name}' is required for command '{command_name}'"
            )

    for alternatives in spec.required_alternatives:
        if not any(_is_nonblank(values[input_name]) for input_name in alternatives):
            names = "' or '".join(sorted(alternatives))
            raise ActionContractError(
                f"Input '{names}' is required for command '{command_name}'"
            )

    argv = [*command]
    for input_name in spec.option_inputs:
        if _is_nonblank(values[input_name]):
            argv.extend((f"--{input_name}", values[input_name]))
    return AdaptedInvocation(tuple(argv), "action")


def resolve_invocation(
    argv: Sequence[str],
    environ: Mapping[str, str],
) -> AdaptedInvocation:
    if environ.get(ACTION_MODE_ENV, "").strip().lower() in {"1", "true", "yes"}:
        return adapt_action_environment(environ)
    return AdaptedInvocation(tuple(argv), "direct")


def main() -> None:
    try:
        invocation = resolve_invocation(sys.argv[1:], os.environ)
    except ActionContractError as error:
        print(f"Input validation failed: {error}", file=sys.stderr)
        raise SystemExit(2) from None

    sys.argv[1:] = invocation.argv

    from .main import app

    app()


if __name__ == "__main__":
    main()