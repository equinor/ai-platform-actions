"""Tests for the GitHub Action to outer-loop CLI contract."""

from __future__ import annotations

import os
from pathlib import Path
import re
import subprocess
import sys
import unittest

import click
import yaml
from typer.main import get_command

from aip.outer.action_entrypoint import (
    ACTION_INPUTS,
    ACTION_MODE_ENV,
    COMMAND_SPECS,
    UNSUPPORTED_INPUTS,
    ActionContractError,
    action_input_environment_name,
    adapt_action_environment,
    resolve_invocation,
)


ROOT = Path(__file__).parent
ACTION_PATH = ROOT / "action.yaml"
DOCKERFILE_PATH = ROOT / "Dockerfile"
SOURCE_BUILD_IMAGE = "Dockerfile"
RELEASE_IMAGE_PATTERN = re.compile(
    r"^docker://ghcr\.io/equinor/ai-platform-actions/outer-loop@sha256:[0-9a-f]{64}$"
)
ACTION_ENVIRONMENT_KEYS = {
    ACTION_MODE_ENV,
    *(action_input_environment_name(name) for name in ACTION_INPUTS),
}


def _value_for(input_name: str) -> str:
    values = {
        "expires-on": "1234567890",
        "max-evidence-age-minutes": "60",
        "min-sample-count": "10",
    }
    return values.get(input_name, f"{input_name}-value")


def _valid_inputs(command: tuple[str, str]) -> dict[str, str]:
    spec = COMMAND_SPECS[command]
    values = {name: "" for name in ACTION_INPUTS}
    values.update({"verb": command[0], "subject": command[1]})
    for input_name in spec.required_inputs - {"verb", "subject"}:
        values[input_name] = _value_for(input_name)
    for alternatives in spec.required_alternatives:
        input_name = sorted(alternatives)[0]
        values[input_name] = _value_for(input_name)
    return values


def _action_environment(values: dict[str, str]) -> dict[str, str]:
    environment = {
        action_input_environment_name(name): value
        for name, value in values.items()
    }
    environment[ACTION_MODE_ENV] = "true"
    return environment


class TestOuterActionContract(unittest.TestCase):
    def test_action_entrypoint_import_does_not_import_cli_or_azure(self):
        code = (
            "import sys; import aip.outer.action_entrypoint; "
            "assert 'aip.outer.main' not in sys.modules; "
            "assert 'azure.identity' not in sys.modules"
        )
        result = subprocess.run(
            [sys.executable, "-c", code],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_matrix_has_all_registered_pairs(self):
        self.assertEqual(set(COMMAND_SPECS), {
            ("evaluate", "gate"),
            ("evaluate", "policy"),
            ("compare", "candidates"),
            ("report", "experiment"),
            ("check", "monitoring"),
        })

    def test_action_mode_dispatches_every_command(self):
        for command in COMMAND_SPECS:
            with self.subTest(command=command):
                invocation = resolve_invocation(
                    ["ignored-action-argv"],
                    _action_environment(_valid_inputs(command)),
                )
                self.assertEqual(invocation.mode, "action")
                self.assertEqual(invocation.argv[:2], command)

    def test_every_applicable_input_is_forwarded(self):
        for command, spec in COMMAND_SPECS.items():
            for input_name in spec.option_inputs:
                with self.subTest(command=command, input_name=input_name):
                    values = _valid_inputs(command)
                    values[input_name] = _value_for(input_name)
                    invocation = adapt_action_environment(_action_environment(values))
                    option = f"--{input_name}"
                    option_index = invocation.argv.index(option)
                    self.assertEqual(invocation.argv[option_index + 1], values[input_name])

    def test_blank_optional_inputs_are_omitted(self):
        for command, spec in COMMAND_SPECS.items():
            with self.subTest(command=command):
                values = _valid_inputs(command)
                selected_alternatives = {
                    next(
                        input_name for input_name in alternatives
                        if values[input_name]
                    )
                    for alternatives in spec.required_alternatives
                }
                optional_inputs = (
                    spec.applicable_inputs
                    - spec.required_inputs
                    - selected_alternatives
                    - {"verb", "subject"}
                )
                for input_name in optional_inputs:
                    values[input_name] = " \t "
                invocation = adapt_action_environment(_action_environment(values))
                self.assertTrue(all(value.strip() for value in invocation.argv))

    def test_nonblank_inapplicable_inputs_are_rejected(self):
        for command, spec in COMMAND_SPECS.items():
            inapplicable = ACTION_INPUTS - spec.applicable_inputs - UNSUPPORTED_INPUTS
            for input_name in inapplicable:
                with self.subTest(command=command, input_name=input_name):
                    values = _valid_inputs(command)
                    values[input_name] = "sensitive-inapplicable-value"
                    with self.assertRaises(ActionContractError) as error:
                        adapt_action_environment(_action_environment(values))
                    self.assertIn(input_name, str(error.exception))
                    self.assertNotIn(values[input_name], str(error.exception))

    def test_required_inputs_and_alternatives_are_validated(self):
        for command, spec in COMMAND_SPECS.items():
            for input_name in spec.required_inputs:
                with self.subTest(command=command, input_name=input_name):
                    values = _valid_inputs(command)
                    values[input_name] = ""
                    with self.assertRaises(ActionContractError) as error:
                        adapt_action_environment(_action_environment(values))
                    self.assertIn(input_name, str(error.exception))
            for alternatives in spec.required_alternatives:
                with self.subTest(command=command, alternatives=alternatives):
                    values = _valid_inputs(command)
                    for input_name in alternatives:
                        values[input_name] = ""
                    with self.assertRaises(ActionContractError) as error:
                        adapt_action_environment(_action_environment(values))
                    for input_name in alternatives:
                        self.assertIn(input_name, str(error.exception))

    def test_unsupported_inputs_are_rejected_without_echoing_values(self):
        for input_name in UNSUPPORTED_INPUTS:
            with self.subTest(input_name=input_name):
                values = _valid_inputs(("report", "experiment"))
                values[input_name] = "sensitive-unsupported-value"
                with self.assertRaises(ActionContractError) as error:
                    adapt_action_environment(_action_environment(values))
                self.assertIn(input_name, str(error.exception))
                self.assertNotIn(values[input_name], str(error.exception))

    def test_action_yaml_inputs_are_classified_and_exposed(self):
        action = yaml.safe_load(ACTION_PATH.read_text(encoding="utf-8"))
        declared_inputs = set(action["inputs"])
        classified_inputs = set(UNSUPPORTED_INPUTS)
        for spec in COMMAND_SPECS.values():
            classified_inputs.update(spec.applicable_inputs)

        self.assertEqual(declared_inputs, ACTION_INPUTS)
        self.assertEqual(declared_inputs, classified_inputs)
        self.assertEqual(action["runs"]["using"], "docker")
        image = action["runs"]["image"]
        self.assertTrue(
            image == SOURCE_BUILD_IMAGE or RELEASE_IMAGE_PATTERN.match(image),
            f"unexpected runs.image: {image}",
        )
        self.assertNotIn("args", action["runs"])
        self.assertEqual(action["runs"]["env"][ACTION_MODE_ENV], "true")
        self.assertEqual(set(action["runs"]["env"]), ACTION_ENVIRONMENT_KEYS)
        for input_name in declared_inputs:
            environment_name = action_input_environment_name(input_name)
            self.assertEqual(
                action["runs"]["env"][environment_name],
                f"${{{{ inputs.{input_name} }}}}",
            )
        self.assertNotIn("default", action["inputs"]["max-evidence-age-minutes"])
        self.assertNotIn("default", action["inputs"]["min-sample-count"])
        universally_required = set.intersection(*(
            set(spec.required_inputs) for spec in COMMAND_SPECS.values()
        ))
        metadata_required = {
            name for name, definition in action["inputs"].items()
            if definition.get("required", False)
        }
        self.assertEqual(metadata_required, universally_required)

    def test_matrix_exactly_matches_typer_tree(self):
        from aip.outer.main import app

        root = get_command(app)
        self.assertIsInstance(root, click.Group)
        registered_pairs = {
            (verb, subject)
            for verb, group in root.commands.items()
            if isinstance(group, click.Group)
            for subject in group.commands
        }
        self.assertEqual(registered_pairs, set(COMMAND_SPECS))

        for command, spec in COMMAND_SPECS.items():
            with self.subTest(command=command):
                group = root.commands[command[0]]
                self.assertIsInstance(group, click.Group)
                click_command = group.commands[command[1]]
                options = [
                    parameter
                    for parameter in click_command.params
                    if isinstance(parameter, click.Option)
                ]
                actual_options = {
                    option
                    for parameter in options
                    for option in parameter.opts
                    if option.startswith("--")
                }
                self.assertEqual(actual_options, {f"--{name}" for name in spec.option_inputs})
                actual_required = {
                    option
                    for parameter in options
                    if parameter.required
                    for option in parameter.opts
                    if option.startswith("--")
                }
                expected_required = {
                    f"--{name}"
                    for name in spec.required_inputs - {"verb", "subject"}
                }
                self.assertEqual(actual_required, expected_required)
                self.assertFalse(click_command.context_settings.get("ignore_unknown_options", False))
                self.assertFalse(click_command.context_settings.get("allow_extra_args", False))

                option_defaults = {
                    option
                    for parameter in options
                    for option in parameter.opts
                    if option.startswith("--")
                }
                if "--max-evidence-age-minutes" in option_defaults:
                    parameter = next(
                        item for item in options
                        if "--max-evidence-age-minutes" in item.opts
                    )
                    self.assertEqual(parameter.default, 1440)
                if "--min-sample-count" in option_defaults:
                    parameter = next(
                        item for item in options
                        if "--min-sample-count" in item.opts
                    )
                    self.assertEqual(parameter.default, 1)

    def test_docker_and_direct_entrypoints_remain_distinct(self):
        dockerfile = DOCKERFILE_PATH.read_text(encoding="utf-8")
        self.assertIn(
            'ENTRYPOINT ["python", "-m", "aip.outer.action_entrypoint"]',
            dockerfile,
        )
        argv = ["report", "experiment", "--help"]
        invocation = resolve_invocation(argv, {})
        self.assertEqual(invocation.mode, "direct")
        self.assertEqual(invocation.argv, tuple(argv))

    def test_action_validation_exits_before_cli_import(self):
        code = """
import os
import sys
from aip.outer.action_entrypoint import main
os.environ.update({
    "AIP_OUTER_ACTION_MODE": "true",
    "INPUT_VERB": "report",
    "INPUT_SUBJECT": "experiment",
    "INPUT_RUN_ID": os.environ["TEST_SECRET"],
})
try:
    main()
except SystemExit as error:
    assert error.code == 2
else:
    raise AssertionError("validation did not exit")
assert "aip.outer.main" not in sys.modules
assert "azure.identity" not in sys.modules
"""
        secret_value = "never-print-this-run-id"
        result = subprocess.run(
            [sys.executable, "-c", code],
            cwd=ROOT,
            env=os.environ | {"TEST_SECRET": secret_value},
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("run-id", result.stderr)
        self.assertNotIn(secret_value, result.stderr)

    def test_unsupported_command_error_does_not_echo_selectors(self):
        secret_value = "sensitive-selector-value"
        values = {name: "" for name in ACTION_INPUTS}
        values.update({"verb": secret_value, "subject": "unknown-subject"})

        with self.assertRaises(ActionContractError) as error:
            adapt_action_environment(_action_environment(values))

        message = str(error.exception)
        self.assertNotIn(secret_value, message)
        self.assertNotIn(values["subject"], message)


if __name__ == "__main__":
    unittest.main()