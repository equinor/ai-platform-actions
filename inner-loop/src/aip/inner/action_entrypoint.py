"""Translate GitHub Action inputs into the command-specific inner-loop CLI."""

from __future__ import annotations

from dataclasses import dataclass
import os
import sys
from typing import Mapping, Sequence


ACTION_MODE_ENV = "AIP_INNER_ACTION_MODE"

ACTION_INPUTS = frozenset({
    "verb",
    "subject",
    "token",
    "expires-on",
    "aml-token",
    "tenant-id",
    "subscription-id",
    "resource-group",
    "workspace-name",
    "registry-name",
    "client-id",
    "filepath",
    "component-ref",
    "registry-env-ref",
    "data-ref",
    "env-ref",
    "model-ref",
    "job-name",
    "endpoint-name",
    "deployment-name",
    "deployment-resource",
    "traffic-allocation",
    "tags",
    "promote-stage",
    "image-build-compute",
    "timeout-minutes",
    "job-ref",
    "schedule-name",
    "cron-expression",
    "time-zone",
    "experiment-name",
    "input-path",
    "input-type",
    "invocation-job-name",
    "expected-current-deployment",
})

UNSUPPORTED_INPUTS = frozenset({"client-id", "tenant-id", "image-build-compute"})
POSITIONAL_INPUTS = frozenset({
    "filepath",
    "component-ref",
    "data-ref",
    "env-ref",
    "model-ref",
    "job-name",
    "job-ref",
    "endpoint-name",
    "deployment-resource",
})

CLI_OPTIONS = {
    "subscription-id": "--subscription",
    "resource-group": "--resource-group",
    "workspace-name": "--workspace-name",
    "token": "--token",
    "expires-on": "--expires-on",
    "aml-token": "--aml-token",
    "registry-name": "--registry-name",
    "tags": "--tags",
    "promote-stage": "--promote-stage",
    "traffic-allocation": "--traffic-allocation",
    "schedule-name": "--schedule-name",
    "cron-expression": "--cron-expression",
    "time-zone": "--time-zone",
    "experiment-name": "--experiment-name",
    "deployment-name": "--deployment-name",
    "input-path": "--input-path",
    "input-type": "--input-type",
    "invocation-job-name": "--invocation-job-name",
    "expected-current-deployment": "--expected-current-deployment",
}

COMMON_REQUIRED = frozenset({
    "verb",
    "subject",
    "subscription-id",
    "resource-group",
    "workspace-name",
})
COMMON_OPTION_INPUTS = ("subscription-id", "resource-group", "workspace-name", "token", "expires-on")


@dataclass(frozen=True)
class CommandSpec:
    positional_input: str
    positional_aliases: tuple[str, ...]
    required_inputs: frozenset[str]
    cli_options: Mapping[str, str]
    environment_inputs: Mapping[str, str]
    conflicting_inputs: tuple[frozenset[str], ...]

    @property
    def applicable_inputs(self) -> frozenset[str]:
        return frozenset({
            "verb",
            "subject",
            self.positional_input,
            *self.positional_aliases,
            *self.cli_options,
            *self.environment_inputs,
        })


@dataclass(frozen=True)
class AdaptedInvocation:
    argv: tuple[str, ...]
    environment: Mapping[str, str]
    clear_environment: tuple[str, ...]
    mode: str


class ActionContractError(ValueError):
    """An action input does not satisfy the selected command contract."""


def _spec(
    positional_input: str,
    *,
    positional_aliases: tuple[str, ...] = (),
    required_inputs: tuple[str, ...] = (),
    option_inputs: tuple[str, ...] = (),
    environment_inputs: Mapping[str, str] | None = None,
) -> CommandSpec:
    options = COMMON_OPTION_INPUTS + option_inputs
    conflicts = (
        (frozenset({positional_input, *positional_aliases}),)
        if positional_aliases
        else ()
    )
    return CommandSpec(
        positional_input=positional_input,
        positional_aliases=positional_aliases,
        required_inputs=COMMON_REQUIRED | {positional_input, *required_inputs},
        cli_options={name: CLI_OPTIONS[name] for name in options},
        environment_inputs=environment_inputs or {},
        conflicting_inputs=conflicts,
    )


_DEPLOY_YAML_OPTIONS = ("tags",)
_DEPLOY_AML_OPTIONS = ("aml-token", "tags")
_SHARE_OPTIONS = ("registry-name", "tags", "promote-stage")
_WAIT_OPTIONS = ("tags",)
_WAIT_ENV = {"timeout-minutes": "TIMEOUT_MINUTES"}

COMMAND_SPECS = {
    ("deploy", "data"): _spec("filepath", option_inputs=_DEPLOY_YAML_OPTIONS),
    ("deploy", "environment"): _spec("filepath", option_inputs=_DEPLOY_YAML_OPTIONS),
    ("deploy", "component"): _spec("filepath", option_inputs=_DEPLOY_YAML_OPTIONS),
    ("deploy", "model"): _spec("filepath", option_inputs=_DEPLOY_YAML_OPTIONS),
    ("deploy", "job"): _spec(
        "filepath",
        option_inputs=_DEPLOY_AML_OPTIONS + ("experiment-name",),
    ),
    ("deploy", "sweep-job"): _spec(
        "filepath",
        option_inputs=_DEPLOY_AML_OPTIONS + ("experiment-name",),
    ),
    ("deploy", "feature-set"): _spec("filepath", option_inputs=_DEPLOY_YAML_OPTIONS),
    ("deploy", "online-endpoint"): _spec("filepath", option_inputs=_DEPLOY_YAML_OPTIONS),
    ("deploy", "online-deployment"): _spec(
        "filepath",
        option_inputs=("traffic-allocation", "tags"),
    ),
    ("deploy", "batch-endpoint"): _spec("filepath", option_inputs=_DEPLOY_AML_OPTIONS),
    ("deploy", "batch-deployment"): _spec("filepath", option_inputs=_DEPLOY_AML_OPTIONS),
    ("deploy", "schedule"): _spec(
        "job-ref",
        positional_aliases=("job-name",),
        required_inputs=("schedule-name", "cron-expression"),
        option_inputs=("schedule-name", "cron-expression", "time-zone"),
    ),
    ("share", "data"): _spec(
        "data-ref",
        required_inputs=("registry-name",),
        option_inputs=_SHARE_OPTIONS,
    ),
    ("share", "environment"): _spec(
        "env-ref",
        required_inputs=("registry-name",),
        option_inputs=_SHARE_OPTIONS,
    ),
    ("share", "model"): _spec(
        "model-ref",
        required_inputs=("registry-name",),
        option_inputs=_SHARE_OPTIONS,
    ),
    ("share", "component"): _spec(
        "component-ref",
        required_inputs=("registry-name", "registry-env-ref"),
        option_inputs=_SHARE_OPTIONS,
        environment_inputs={"registry-env-ref": "REGISTRY_ENV_REF"},
    ),
    ("waitfor", "data"): _spec(
        "data-ref",
        option_inputs=_WAIT_OPTIONS,
        environment_inputs=_WAIT_ENV,
    ),
    ("waitfor", "environment"): _spec(
        "env-ref",
        option_inputs=_WAIT_OPTIONS,
        environment_inputs=_WAIT_ENV,
    ),
    ("waitfor", "component"): _spec(
        "component-ref",
        option_inputs=_WAIT_OPTIONS,
        environment_inputs=_WAIT_ENV,
    ),
    ("waitfor", "model"): _spec(
        "model-ref",
        option_inputs=_WAIT_OPTIONS,
        environment_inputs=_WAIT_ENV,
    ),
    ("waitfor", "job"): _spec(
        "job-name",
        positional_aliases=("job-ref",),
        option_inputs=_WAIT_OPTIONS,
        environment_inputs=_WAIT_ENV,
    ),
    ("waitfor", "online-endpoint"): _spec(
        "endpoint-name",
        option_inputs=_WAIT_OPTIONS,
        environment_inputs=_WAIT_ENV,
    ),
    ("waitfor", "online-deployment"): _spec(
        "deployment-resource",
        option_inputs=_WAIT_OPTIONS,
        environment_inputs=_WAIT_ENV,
    ),
    ("waitfor", "sweep-job"): _spec(
        "job-name",
        positional_aliases=("job-ref",),
        option_inputs=_WAIT_OPTIONS,
        environment_inputs=_WAIT_ENV,
    ),
    ("delete", "online-endpoint"): _spec("endpoint-name"),
    ("delete", "online-deployment"): _spec("deployment-resource"),
    ("invoke", "batch-deployment"): _spec(
        "endpoint-name",
        required_inputs=("deployment-name", "input-path"),
        option_inputs=(
            "deployment-name",
            "input-path",
            "input-type",
            "invocation-job-name",
            "experiment-name",
            "aml-token",
        ),
        environment_inputs={
            "input-path": "BATCH_INPUT_PATH",
            "input-type": "BATCH_INPUT_TYPE",
            "invocation-job-name": "BATCH_INVOCATION_JOB_NAME",
        },
    ),
    ("promote", "batch-deployment"): _spec(
        "endpoint-name",
        required_inputs=("deployment-name",),
        option_inputs=("deployment-name", "expected-current-deployment", "aml-token"),
        environment_inputs={"expected-current-deployment": "EXPECTED_CURRENT_DEPLOYMENT"},
    ),
    ("rollback", "batch-deployment"): _spec(
        "endpoint-name",
        required_inputs=("deployment-name",),
        option_inputs=("deployment-name", "expected-current-deployment", "aml-token"),
        environment_inputs={"expected-current-deployment": "EXPECTED_CURRENT_DEPLOYMENT"},
    ),
    ("rollback", "online-deployment"): _spec(
        "endpoint-name",
        option_inputs=("deployment-name", "aml-token"),
    ),
}

LEGACY_OPTION_INPUTS = {
    "--subscription": "subscription-id",
    "--resource-group": "resource-group",
    "--workspace-name": "workspace-name",
    "--registry-name": "registry-name",
    "--token": "token",
    "--expires-on": "expires-on",
    "--tags": "tags",
    "--promote-stage": "promote-stage",
    "--image-build-compute": "image-build-compute",
    "--aml-token": "aml-token",
    "--traffic-allocation": "traffic-allocation",
    "--schedule-name": "schedule-name",
    "--cron-expression": "cron-expression",
    "--time-zone": "time-zone",
    "--experiment-name": "experiment-name",
    "--deployment-name": "deployment-name",
}
LEGACY_OPTION_ORDER = tuple(LEGACY_OPTION_INPUTS)
LEGACY_ENV_INPUTS = {
    "TIMEOUT_MINUTES": "timeout-minutes",
    "REGISTRY_ENV_REF": "registry-env-ref",
    "BATCH_INPUT_PATH": "input-path",
    "BATCH_INPUT_TYPE": "input-type",
    "BATCH_INVOCATION_JOB_NAME": "invocation-job-name",
    "EXPECTED_CURRENT_DEPLOYMENT": "expected-current-deployment",
}
LEGACY_INAPPLICABLE_DEFAULTS = {
    "timeout-minutes": "30",
    "input-type": "uri_folder",
}


def action_input_environment_name(input_name: str) -> str:
    return f"INPUT_{input_name.upper().replace('-', '_')}"


def _is_nonblank(value: str | None) -> bool:
    return value is not None and bool(value.strip())


def _command_name(verb: str, subject: str) -> str:
    return f"{verb} {subject}"


def _get_spec(values: Mapping[str, str]) -> tuple[tuple[str, str], CommandSpec]:
    verb = values.get("verb", "").strip()
    subject = values.get("subject", "").strip()
    if not verb:
        raise ActionContractError("Input 'verb' is required")
    if not subject:
        raise ActionContractError("Input 'subject' is required")
    command = (verb, subject)
    if command not in COMMAND_SPECS:
        raise ActionContractError(f"Command '{_command_name(*command)}' is not supported")
    return command, COMMAND_SPECS[command]


def _adapt_values(
    raw_values: Mapping[str, str],
    *,
    mode: str,
) -> AdaptedInvocation:
    values = {name: str(raw_values.get(name, "")) for name in ACTION_INPUTS}
    command, spec = _get_spec(values)
    command_name = _command_name(*command)

    for input_name in sorted(UNSUPPORTED_INPUTS):
        if _is_nonblank(values[input_name]):
            raise ActionContractError(
                f"Input '{input_name}' is unsupported for command '{command_name}'"
            )

    positional_values = [
        name for name in POSITIONAL_INPUTS if _is_nonblank(values[name])
    ]
    if len(positional_values) > 1:
        names = "', '".join(sorted(positional_values))
        raise ActionContractError(
            f"Inputs '{names}' conflict for command '{command_name}'"
        )

    applicable = spec.applicable_inputs
    if mode == "legacy":
        for input_name, historical_default in LEGACY_INAPPLICABLE_DEFAULTS.items():
            if input_name not in applicable and values[input_name] == historical_default:
                values[input_name] = ""

    for input_name in sorted(ACTION_INPUTS - applicable - UNSUPPORTED_INPUTS):
        if _is_nonblank(values[input_name]):
            raise ActionContractError(
                f"Input '{input_name}' is not valid for command '{command_name}'"
            )

    positional_names = (spec.positional_input, *spec.positional_aliases)
    positional_name = next(
        (name for name in positional_names if _is_nonblank(values[name])),
        None,
    )
    for input_name in sorted(spec.required_inputs - {spec.positional_input}):
        if not _is_nonblank(values[input_name]):
            raise ActionContractError(
                f"Input '{input_name}' is required for command '{command_name}'"
            )
    if positional_name is None:
        raise ActionContractError(
            f"Input '{spec.positional_input}' is required for command '{command_name}'"
        )

    argv = [*command, values[positional_name]]
    environment: dict[str, str] = {}
    for input_name, option in spec.cli_options.items():
        if input_name in spec.environment_inputs:
            continue
        if _is_nonblank(values[input_name]):
            argv.extend((option, values[input_name]))
    for input_name, environment_name in spec.environment_inputs.items():
        if _is_nonblank(values[input_name]):
            environment[environment_name] = values[input_name]

    return AdaptedInvocation(
        argv=tuple(argv),
        environment=environment,
        clear_environment=tuple(LEGACY_ENV_INPUTS),
        mode=mode,
    )


def adapt_action_environment(environ: Mapping[str, str]) -> AdaptedInvocation:
    values = {
        input_name: environ.get(action_input_environment_name(input_name), "")
        for input_name in ACTION_INPUTS
    }
    return _adapt_values(values, mode="action")


def is_legacy_full_argv(argv: Sequence[str]) -> bool:
    if len(argv) != 3 + (2 * len(LEGACY_OPTION_ORDER)):
        return False
    return tuple(argv[3::2]) == LEGACY_OPTION_ORDER


def adapt_legacy_invocation(
    argv: Sequence[str],
    environ: Mapping[str, str],
) -> AdaptedInvocation:
    if not is_legacy_full_argv(argv):
        raise ActionContractError("Legacy action arguments do not match the historical action contract")

    command = (argv[0].strip(), argv[1].strip())
    if command not in COMMAND_SPECS:
        raise ActionContractError(f"Command '{_command_name(*command)}' is not supported")
    spec = COMMAND_SPECS[command]
    values = {"verb": command[0], "subject": command[1], spec.positional_input: argv[2]}
    for option, value in zip(argv[3::2], argv[4::2], strict=True):
        values[LEGACY_OPTION_INPUTS[option]] = value
    for environment_name, input_name in LEGACY_ENV_INPUTS.items():
        values[input_name] = environ.get(environment_name, "")
    return _adapt_values(values, mode="legacy")


def normalize_legacy_argv(
    argv: Sequence[str],
    environ: Mapping[str, str] | None = None,
) -> list[str]:
    return list(adapt_legacy_invocation(argv, environ or {}).argv)


def resolve_invocation(
    argv: Sequence[str],
    environ: Mapping[str, str],
) -> AdaptedInvocation:
    if environ.get(ACTION_MODE_ENV, "").strip().lower() in {"1", "true", "yes"}:
        return adapt_action_environment(environ)
    if (
        environ.get("GITHUB_ACTIONS", "").strip().lower() == "true"
        and is_legacy_full_argv(argv)
    ):
        return adapt_legacy_invocation(argv, environ)
    return AdaptedInvocation(tuple(argv), {}, (), "direct")


def main() -> None:
    try:
        invocation = resolve_invocation(sys.argv[1:], os.environ)
    except ActionContractError as error:
        print(f"Input validation failed: {error}", file=sys.stderr)
        raise SystemExit(2) from None

    for environment_name in invocation.clear_environment:
        os.environ.pop(environment_name, None)
    os.environ.update(invocation.environment)
    sys.argv[1:] = invocation.argv

    from .main import app

    app()


if __name__ == "__main__":
    main()