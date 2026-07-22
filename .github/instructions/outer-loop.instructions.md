---
description: "Use when modifying outer-loop action inputs, Docker entrypoints, action_entrypoint.py, Typer commands, command signatures, monitoring defaults, or action contract tests. Prevents GitHub Action and CLI drift."
applyTo: "outer-loop/**"
---
# Outer-loop action contract

Keep the GitHub Action transport, adapter matrix, Docker entrypoint, and Typer command tree synchronized.

## Ownership

- `action.yaml` declares the public GitHub Action inputs and exposes every input as `INPUT_<UPPER_SNAKE_NAME>` under `runs.env`.
- `src/aip/outer/action_entrypoint.py` owns action-mode adaptation plus structural validation of command applicability and required inputs.
- `src/aip/outer/main.py` and the verb modules own the direct Typer CLI, semantic validation, defaults, and command behavior.
- `Dockerfile` must enter through `python -m aip.outer.action_entrypoint`. Direct users must still be able to invoke `python -m aip.outer.main`.
- `test_action_contract.py` enforces synchronization between all of these surfaces.

## Required synchronization

When adding, removing, renaming, requiring, or changing the default of an input or command, update all applicable surfaces in the same change:

1. The input declaration and `INPUT_*` exposure in `action.yaml`.
2. `ACTION_INPUTS`, option groups, and the relevant `COMMAND_SPECS` entry in `action_entrypoint.py`.
3. The corresponding Typer registration and command signature.
4. The command examples and input documentation when the public contract changes.
5. Contract-test expectations, including the registered command-pair set.

The adapter matrix and Typer tree must expose exactly the same command pairs, option names, and unconditionally required options. Every declared action input must be classified as applicable to at least one command or explicitly listed in `UNSUPPORTED_INPUTS`.

## Invariants

- Do not restore a universal `runs.args` list in `action.yaml`; action mode must omit blank and inapplicable options.
- Do not point the Dockerfile directly at `aip.outer.main`.
- Keep `action_entrypoint.py` standard-library-only and importable without importing `aip.outer.main`, Azure SDK modules, MLflow, or command modules. Validate before the deferred CLI import. Errors may name a recognized verb-subject pair, but must not echo raw unsupported selectors or any other input values.
- Preserve direct CLI passthrough. Do not add inner-loop-style legacy action argument handling without a demonstrated outer-loop compatibility requirement.
- Keep command-specific defaults in Typer. In particular, do not add action-level defaults for `max-evidence-age-minutes` or `min-sample-count`; they would appear nonblank for unrelated commands.
- Keep workspace inputs explicitly unsupported until a Typer command consumes them. Never silently discard a nonblank declared input.
- Keep Typer strict. Do not enable `ignore_unknown_options` or `allow_extra_args` to accommodate global action arguments.
- Keep cross-field semantic rules in command modules when they depend on command behavior. Mirror only structural alternatives needed to build a valid CLI invocation in `required_alternatives`.

## Validation

Run the focused contract suite after every contract change:

```powershell
Set-Location outer-loop
uv run python -m unittest -v test_action_contract.py
```

The change is incomplete if the action metadata, Docker module, command matrix, strict-parser, and Typer-tree synchronization assertions do not pass.