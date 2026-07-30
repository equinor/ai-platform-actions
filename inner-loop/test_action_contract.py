"""Tests for the GitHub Action to inner-loop CLI contract."""

from __future__ import annotations

import os
from pathlib import Path
import re
import subprocess
import sys

import click
import pytest
import yaml

from aip.inner.action_entrypoint import (
    ACTION_INPUTS,
    ACTION_MODE_ENV,
    COMMAND_SPECS,
    LEGACY_OPTION_INPUTS,
    ActionContractError,
    action_input_environment_name,
    adapt_action_environment,
    adapt_legacy_invocation,
    normalize_legacy_argv,
    resolve_invocation,
    UNSUPPORTED_INPUTS,
)


ACTION_PATH = Path(__file__).with_name("action.yaml")
DOCKERFILE_PATH = Path(__file__).with_name("Dockerfile")
SOURCE_BUILD_IMAGE = "Dockerfile"
RELEASE_IMAGE_PATTERN = re.compile(
    r"^docker://ghcr\.io/equinor/ai-platform-actions/inner-loop@sha256:[0-9a-f]{64}$"
)
COMMANDS = tuple(COMMAND_SPECS)
APPLICABLE_CASES = tuple(
    (command, input_name)
    for command, spec in COMMAND_SPECS.items()
    for input_name in sorted(spec.applicable_inputs)
)
INAPPLICABLE_CASES = tuple(
    (command, input_name)
    for command, spec in COMMAND_SPECS.items()
    for input_name in sorted(ACTION_INPUTS - spec.applicable_inputs)
)
REQUIRED_CASES = tuple(
    (command, input_name)
    for command, spec in COMMAND_SPECS.items()
    for input_name in sorted(spec.required_inputs)
)
CONFLICT_CASES = tuple(
    (command, conflict)
    for command, spec in COMMAND_SPECS.items()
    for conflict in spec.conflicting_inputs
)


def _value_for(input_name: str) -> str:
    values = {
        "expires-on": "1234567890",
        "input-type": "uri_file",
        "timeout-minutes": "5",
        "traffic-allocation": "25",
    }
    return values.get(input_name, f"{input_name}-value")


def _valid_inputs(command: tuple[str, str]) -> dict[str, str]:
    spec = COMMAND_SPECS[command]
    values = {name: "" for name in ACTION_INPUTS}
    values.update({
        "verb": command[0],
        "subject": command[1],
        "subscription-id": "subscription-value",
        "resource-group": "resource-group-value",
        "workspace-name": "workspace-name-value",
        spec.positional_input: "positional-value",
    })
    for input_name in spec.required_inputs:
        if input_name not in {"verb", "subject", spec.positional_input}:
            values[input_name] = _value_for(input_name)
    return values


def _action_environment(values: dict[str, str]) -> dict[str, str]:
    environment = {
        action_input_environment_name(name): value
        for name, value in values.items()
    }
    environment[ACTION_MODE_ENV] = "true"
    return environment


def _legacy_argv(
    command: tuple[str, str],
    option_values: dict[str, str] | None = None,
) -> list[str]:
    spec = COMMAND_SPECS[command]
    values = _valid_inputs(command)
    if option_values:
        values.update(option_values)
    argv = [command[0], command[1], values[spec.positional_input]]
    for option, input_name in LEGACY_OPTION_INPUTS.items():
        argv.extend((option, values[input_name]))
    return argv


def test_legacy_deploy_data_omits_empty_unrelated_options_before_cli_import():
    argv = [
        "deploy", "data", "data.yaml",
        "--subscription", "subscription",
        "--resource-group", "resource-group",
        "--workspace-name", "workspace",
        "--registry-name", "",
        "--token", "",
        "--expires-on", "",
        "--tags", "",
        "--promote-stage", "",
        "--image-build-compute", "",
        "--aml-token", "",
        "--traffic-allocation", "",
        "--schedule-name", "",
        "--cron-expression", "",
        "--time-zone", "",
        "--experiment-name", "",
        "--deployment-name", "",
    ]

    assert normalize_legacy_argv(argv) == [
        "deploy", "data", "data.yaml",
        "--subscription", "subscription",
        "--resource-group", "resource-group",
        "--workspace-name", "workspace",
    ]


def test_action_entrypoint_import_does_not_import_cli_or_azure():
    code = (
        "import sys; import aip.inner.action_entrypoint; "
        "assert 'aip.inner.main' not in sys.modules; "
        "assert 'azure.ai.ml' not in sys.modules"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=Path(__file__).parent,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_matrix_has_all_30_registered_pairs():
    counts: dict[str, int] = {}
    for verb, _ in COMMAND_SPECS:
        counts[verb] = counts.get(verb, 0) + 1

    assert len(COMMAND_SPECS) == 30
    assert counts == {
        "deploy": 12,
        "share": 4,
        "waitfor": 8,
        "delete": 2,
        "invoke": 1,
        "promote": 1,
        "rollback": 2,
    }


@pytest.mark.parametrize("command", COMMANDS, ids=lambda value: "-".join(value))
def test_new_action_mode_dispatches_every_command(command: tuple[str, str]):
    invocation = resolve_invocation(
        ["ignored-action-argv"],
        _action_environment(_valid_inputs(command)),
    )

    assert invocation.mode == "action"
    assert invocation.argv[:2] == command


def test_waitfor_job_forwards_aml_token():
    values = _valid_inputs(("waitfor", "job"))
    values["aml-token"] = "aml-token-value"

    invocation = adapt_action_environment(_action_environment(values))

    option_index = invocation.argv.index("--aml-token")
    assert invocation.argv[option_index + 1] == "aml-token-value"


@pytest.mark.parametrize(
    ("command", "input_name"),
    APPLICABLE_CASES,
    ids=lambda value: "-".join(value) if isinstance(value, tuple) else value,
)
def test_every_applicable_input_is_forwarded(
    command: tuple[str, str],
    input_name: str,
):
    spec = COMMAND_SPECS[command]
    values = _valid_inputs(command)
    if input_name in spec.positional_aliases:
        values[spec.positional_input] = ""
        values[input_name] = "alias-value"
    elif input_name not in {"verb", "subject"}:
        values[input_name] = _value_for(input_name)

    invocation = adapt_action_environment(_action_environment(values))

    if input_name in {spec.positional_input, *spec.positional_aliases}:
        assert invocation.argv[2] == values[input_name]
    elif input_name in spec.environment_inputs:
        environment_name = spec.environment_inputs[input_name]
        assert invocation.environment[environment_name] == values[input_name]
    elif input_name in spec.cli_options:
        option = spec.cli_options[input_name]
        option_index = invocation.argv.index(option)
        assert invocation.argv[option_index + 1] == values[input_name]


@pytest.mark.parametrize(
    ("command", "input_name"),
    INAPPLICABLE_CASES,
    ids=lambda value: "-".join(value) if isinstance(value, tuple) else value,
)
def test_every_nonblank_inapplicable_input_is_rejected(
    command: tuple[str, str],
    input_name: str,
):
    values = _valid_inputs(command)
    values[input_name] = "not-applicable-value"

    with pytest.raises(ActionContractError) as error:
        adapt_action_environment(_action_environment(values))

    assert input_name in str(error.value)
    assert "not-applicable-value" not in str(error.value)


@pytest.mark.parametrize("command", COMMANDS, ids=lambda value: "-".join(value))
def test_blank_optional_and_inapplicable_inputs_are_omitted(command: tuple[str, str]):
    spec = COMMAND_SPECS[command]
    values = _valid_inputs(command)
    for input_name in ACTION_INPUTS - spec.required_inputs - {"verb", "subject"}:
        values[input_name] = " \t "

    invocation = adapt_action_environment(_action_environment(values))

    assert all(value.strip() for value in invocation.argv)
    assert all(value.strip() for value in invocation.environment.values())


@pytest.mark.parametrize(
    ("command", "input_name"),
    REQUIRED_CASES,
    ids=lambda value: "-".join(value) if isinstance(value, tuple) else value,
)
def test_every_required_input_is_validated(
    command: tuple[str, str],
    input_name: str,
):
    spec = COMMAND_SPECS[command]
    values = _valid_inputs(command)
    values[input_name] = ""
    if input_name == spec.positional_input:
        for alias in spec.positional_aliases:
            values[alias] = ""

    with pytest.raises(ActionContractError) as error:
        adapt_action_environment(_action_environment(values))

    assert input_name in str(error.value)


@pytest.mark.parametrize(
    ("command", "conflict"),
    CONFLICT_CASES,
    ids=lambda value: "-".join(value) if isinstance(value, tuple) else "-".join(sorted(value)),
)
def test_positional_alias_conflicts_are_rejected(
    command: tuple[str, str],
    conflict: frozenset[str],
):
    values = _valid_inputs(command)
    for input_name in conflict:
        values[input_name] = "conflicting-value"

    with pytest.raises(ActionContractError) as error:
        adapt_action_environment(_action_environment(values))

    for input_name in conflict:
        assert input_name in str(error.value)
    assert "conflicting-value" not in str(error.value)


def test_action_yaml_inputs_are_fully_classified_and_exposed():
    action = yaml.safe_load(ACTION_PATH.read_text(encoding="utf-8"))
    declared_inputs = set(action["inputs"])
    classified_inputs = set(UNSUPPORTED_INPUTS)
    for spec in COMMAND_SPECS.values():
        classified_inputs.update(spec.applicable_inputs)

    assert declared_inputs == ACTION_INPUTS
    assert declared_inputs == classified_inputs
    assert action["runs"]["using"] == "docker"
    image = action["runs"]["image"]
    assert image == SOURCE_BUILD_IMAGE or RELEASE_IMAGE_PATTERN.match(image), image
    assert "args" not in action["runs"]
    assert action["runs"]["env"][ACTION_MODE_ENV] == "true"

    exposed_inputs = {
        name.removeprefix("INPUT_")
        for name in action["runs"]["env"]
        if name.startswith("INPUT_")
    }
    expected_exposure = {
        name.upper().replace("-", "_")
        for name in declared_inputs
    }
    assert exposed_inputs == expected_exposure
    for input_name in declared_inputs:
        environment_name = action_input_environment_name(input_name)
        assert action["runs"]["env"][environment_name] == f"${{{{ inputs.{input_name} }}}}"

    assert "default" not in action["inputs"]["timeout-minutes"]
    assert "default" not in action["inputs"]["input-type"]


def test_matrix_exactly_matches_click_tree():
    from typer.main import get_command

    from aip.inner.main import app

    root = get_command(app)
    assert isinstance(root, click.Group)
    registered_pairs = {
        (verb, subject)
        for verb, group in root.commands.items()
        if isinstance(group, click.Group)
        for subject in group.commands
    }
    assert registered_pairs == set(COMMAND_SPECS)

    for command, spec in COMMAND_SPECS.items():
        group = root.commands[command[0]]
        assert isinstance(group, click.Group), command
        click_command = group.commands[command[1]]
        options = [
            parameter
            for parameter in click_command.params
            if isinstance(parameter, click.Option)
        ]
        arguments = [
            parameter
            for parameter in click_command.params
            if isinstance(parameter, click.Argument)
        ]
        actual_options = {
            option
            for parameter in options
            for option in parameter.opts
            if option.startswith("--")
        }
        expected_options = set(spec.cli_options.values())
        assert actual_options == expected_options, command
        assert len(arguments) == 1, command
        argument_name = arguments[0].name
        assert argument_name is not None, command
        assert argument_name.replace("_", "-") == spec.positional_input, command

        actual_required = {
            option
            for parameter in options
            if parameter.required
            for option in parameter.opts
            if option.startswith("--")
        }
        expected_required = {
            option
            for input_name, option in spec.cli_options.items()
            if input_name in spec.required_inputs
        }
        assert actual_required == expected_required, command


@pytest.mark.parametrize(
    "command",
    (("invoke", "batch-deployment"), ("promote", "batch-deployment"), ("rollback", "batch-deployment")),
)
def test_batch_commands_reject_unknown_options(command: tuple[str, str]):
    from typer.main import get_command

    from aip.inner.main import app

    root = get_command(app)
    assert isinstance(root, click.Group)
    group = root.commands[command[0]]
    assert isinstance(group, click.Group)
    click_command = group.commands[command[1]]
    assert not click_command.context_settings.get("ignore_unknown_options", False)
    assert not click_command.context_settings.get("allow_extra_args", False)


def test_legacy_historical_global_defaults_are_absent_when_inapplicable():
    invocation = adapt_legacy_invocation(
        _legacy_argv(("deploy", "data")),
        {"TIMEOUT_MINUTES": "30", "BATCH_INPUT_TYPE": "uri_folder"},
    )

    assert invocation.mode == "legacy"
    assert invocation.environment == {}


def test_legacy_nondefault_irrelevant_environment_input_is_rejected():
    with pytest.raises(ActionContractError) as error:
        adapt_legacy_invocation(
            _legacy_argv(("deploy", "data")),
            {"TIMEOUT_MINUTES": "31", "BATCH_INPUT_TYPE": "uri_folder"},
        )

    assert "timeout-minutes" in str(error.value)
    assert "31" not in str(error.value)


def test_legacy_applicable_batch_environment_is_preserved():
    invocation = adapt_legacy_invocation(
        _legacy_argv(("invoke", "batch-deployment")),
        {
            "TIMEOUT_MINUTES": "30",
            "BATCH_INPUT_PATH": "azureml:data:1",
            "BATCH_INPUT_TYPE": "uri_file",
            "BATCH_INVOCATION_JOB_NAME": "validation-job",
        },
    )

    assert invocation.environment == {
        "BATCH_INPUT_PATH": "azureml:data:1",
        "BATCH_INPUT_TYPE": "uri_file",
        "BATCH_INVOCATION_JOB_NAME": "validation-job",
    }


def test_legacy_nonblank_irrelevant_option_error_omits_value():
    secret_value = "do-not-echo-this-value"
    with pytest.raises(ActionContractError) as error:
        adapt_legacy_invocation(
            _legacy_argv(
                ("deploy", "data"),
                {"deployment-name": secret_value},
            ),
            {},
        )

    message = str(error.value)
    assert "deployment-name" in message
    assert "deploy data" in message
    assert secret_value not in message


@pytest.mark.parametrize("unsupported_input", sorted(UNSUPPORTED_INPUTS))
def test_unsupported_input_errors_never_include_values(unsupported_input: str):
    secret_value = "sensitive-unsupported-value"
    values = _valid_inputs(("deploy", "data"))
    values[unsupported_input] = secret_value

    with pytest.raises(ActionContractError) as error:
        adapt_action_environment(_action_environment(values))

    message = str(error.value)
    assert unsupported_input in message
    assert "deploy data" in message
    assert secret_value not in message


def test_resolve_detects_legacy_action_mode():
    invocation = resolve_invocation(
        _legacy_argv(("deploy", "data")),
        {
            "GITHUB_ACTIONS": "true",
            "TIMEOUT_MINUTES": "30",
            "BATCH_INPUT_TYPE": "uri_folder",
        },
    )

    assert invocation.mode == "legacy"


def test_direct_container_dispatch_passes_argv_unchanged():
    argv = ["deploy", "data", "data.yaml", "--unknown-direct-option"]

    invocation = resolve_invocation(argv, {})

    assert invocation.mode == "direct"
    assert invocation.argv == tuple(argv)
    assert invocation.environment == {}
    assert invocation.clear_environment == ()


def test_docker_enters_through_action_entrypoint():
    dockerfile = DOCKERFILE_PATH.read_text(encoding="utf-8")

    assert 'ENTRYPOINT ["python", "-m", "aip.inner.action_entrypoint"]' in dockerfile


def test_github_python_cli_without_legacy_shape_remains_direct():
    argv = ["deploy", "data", "data.yaml", "--help"]

    invocation = resolve_invocation(argv, {"GITHUB_ACTIONS": "true"})

    assert invocation.mode == "direct"
    assert invocation.argv == tuple(argv)


def test_direct_python_module_cli_remains_available():
    environment = os.environ.copy()
    environment.pop(ACTION_MODE_ENV, None)
    result = subprocess.run(
        [sys.executable, "-m", "aip.inner.main", "deploy", "data", "--help"],
        cwd=Path(__file__).parent,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "--subscription" in result.stdout


def test_action_validation_exits_before_cli_import_and_hides_secret():
    secret_value = "never-print-this-client-id"
    code = """
import os
import sys
from aip.inner.action_entrypoint import main
os.environ.update({
    "AIP_INNER_ACTION_MODE": "true",
    "INPUT_VERB": "deploy",
    "INPUT_SUBJECT": "data",
    "INPUT_CLIENT_ID": os.environ["TEST_SECRET"],
})
try:
    main()
except SystemExit as error:
    assert error.code == 2
else:
    raise AssertionError("validation did not exit")
assert "aip.inner.main" not in sys.modules
assert "azure.ai.ml" not in sys.modules
"""
    environment = os.environ | {"TEST_SECRET": secret_value}
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=Path(__file__).parent,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "client-id" in result.stderr
    assert "deploy data" in result.stderr
    assert secret_value not in result.stderr