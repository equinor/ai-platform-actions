# Test Overview

This repository has two independently runnable Python test suites, one for each Docker-based GitHub Action. The tests use `pytest`; most are unit or contract tests that replace Azure SDK, Azure Resource Manager, MLflow, and HTTP interactions with mocks or fake transports.

## At a Glance

| Area | Test modules | Collected pytest items | Primary test level |
| --- | ---: | ---: | --- |
| Inner loop | 6 | 1,409 | Action-contract matrix and unit tests |
| Outer loop | 2 | 87 | Action contracts, unit tests, and command-level tests |
| Total | 8 | 1,496 | Isolated/local tests |

The item count is from `pytest --collect-only` on 2026-08-05. It is higher than the number of test functions because the inner-loop contract tests are heavily parameterized across commands and inputs.

## Test Approach

The suites deliberately avoid live Azure dependencies:

- Azure SDK clients, credentials, ARM responses, MLflow backends, and HTTP sessions are mocked or replaced with in-memory fakes.
- Command behavior is exercised through Typer's `CliRunner` where command parsing and exit status matter.
- Files used by commands and GitHub output are created in temporary locations.
- Action contracts inspect `action.yaml`, the Dockerfile, action environment variables, and the registered Typer/Click command tree.

This makes the tests fast and deterministic, and gives especially strong protection against action/CLI drift. It does not verify an authenticated request against a real Azure ML workspace or MLflow server.

## Inner-Loop Tests

The inner-loop action manages Azure ML asset and endpoint operations. Its test suite is centered on the 30-command action interface and its Azure Resource Manager integration boundary.

| Test module | Items | What it verifies |
| --- | ---: | --- |
| [`inner-loop/test_action_contract.py`](../inner-loop/test_action_contract.py) | 1,326 | The complete 30-command action matrix: all applicable action inputs are forwarded, non-applicable and unsupported inputs are rejected without leaking values, required inputs and aliases are validated, blanks are omitted, and legacy invocation remains compatible. It also verifies `action.yaml` exposure, Docker/direct entrypoints, lazy import behavior, and exact agreement between the action contract and the Typer/Click command tree. |
| [`inner-loop/test_arm.py`](../inner-loop/test_arm.py) | 38 | ARM URL construction, API-version use, pagination, registry resource-group discovery, error redaction, integer-version parsing and selection, archived-version counting, and archived-container recovery behavior. Requests are handled by a recording fake transport. |
| [`inner-loop/test_batch_lifecycle.py`](../inner-loop/test_batch_lifecycle.py) | 9 | Batch endpoint and deployment creation, tag handling, GitHub outputs, idempotent default-deployment changes, concurrent-change protection, update verification, promotion/rollback, and pinned deployment invocation. |
| [`inner-loop/test_deploy_versioning.py`](../inner-loop/test_deploy_versioning.py) | 3 | Data-asset version assignment from existing workspace versions, ignoring non-integer versions, and the no-existing-asset case. |
| [`inner-loop/test_util.py`](../inner-loop/test_util.py) | 32 | Credential scope routing, `GITHUB_OUTPUT` writing, safe tag parsing, and Azure ML asset-reference parsing for simple, workspace, and registry forms. |
| [`inner-loop/test_waitfor_job.py`](../inner-loop/test_waitfor_job.py) | 1 | Separate routing of ARM and Azure ML tokens for job polling. |

The contract matrix is the dominant source of inner-loop depth. It enumerates command/input combinations rather than sampling a small subset, so a new input, command, or CLI option has a high chance of breaking a focused contract assertion.

## Outer-Loop Tests

The outer-loop action evaluates model evidence, compares runs, and reports decisions. Its tests cover decision logic, CLI boundaries, and normalized access to MLflow-compatible APIs.

| Test module | Items | What it verifies |
| --- | ---: | --- |
| [`outer-loop/test_action_contract.py`](../outer-loop/test_action_contract.py) | 13 | The five registered commands, action-mode dispatch, action-input classification and forwarding, required alternatives, rejected unsupported/inapplicable inputs without secret leakage, YAML environment mapping, CLI command-tree consistency, and separation of Docker and direct CLI entrypoints. |
| [`outer-loop/test_outer.py`](../outer-loop/test_outer.py) | 72 | Weighted candidate scoring and metric directions; policy threshold, priority, and default decisions; fail-closed monitoring-evidence checks; deterministic decision outputs; `evaluate gate` threshold boundaries; backend selection; and Azure ML/MLflow proxy request, pagination, filtering, normalization, parent-child run selection, missing-resource, and missing-metric handling. |

Several outer-loop tests invoke commands through `CliRunner`. These are local integration-style tests of parsing, validation, output, and exit codes, while still mocking backend calls.

## Running the Tests

Run the action suites from their own directories so each uses its own project metadata and source layout.

```powershell
Push-Location inner-loop
uv sync --locked
uv run --with pytest pytest -q
Pop-Location

Push-Location outer-loop
uv sync
uv run --with pytest pytest -q
Pop-Location
```

For a fast inventory without executing test bodies:

```powershell
Push-Location inner-loop
uv run --with pytest pytest --collect-only -q
Pop-Location

Push-Location outer-loop
uv run --with pytest pytest --collect-only -q
Pop-Location
```

The inner-loop project requires Python 3.13 or later; outer-loop requires Python 3.12 or later. Both projects configure pytest to treat warnings as errors, with narrowly scoped ignores for current Azure ML and Marshmallow deprecation warnings.

## Automation and Coverage Limits

No checked-in GitHub Actions workflow runs these tests. The repository's only workflow, [`release.yaml`](../.github/workflows/release.yaml), builds and publishes images and pins action image digests. The contributor guidance requires authors to run the relevant suites before requesting review; see [build and release guidance](build-and-releaseguidance.md).

There is no configured coverage-reporting tool or minimum coverage threshold. The current test suite does not include:

- Live Azure ML workspace, registry, endpoint, job, or managed identity tests.
- Live MLflow service compatibility tests.
- Docker-container execution tests for the action entrypoints.
- A pull-request or continuous-integration test workflow.
- Browser, UI, performance, load, or security scanning tests.

Those boundaries are useful when interpreting a green test run: it validates the repository's action contracts, local control flow, and mocked protocol behavior, but not cloud credentials, Azure service behavior, image runtime behavior, or deployment-time integration.