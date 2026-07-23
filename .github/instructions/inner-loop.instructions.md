---
description: "Use when modifying inner-loop action inputs, Docker entrypoints, action_entrypoint.py, Typer commands, command signatures, or action contract tests. Prevents GitHub Action and CLI drift."
applyTo: "inner-loop/**"
---
# Inner-loop action contract

Keep the GitHub Action transport, adapter matrix, Docker entrypoint, and Typer command tree synchronized.

## Ownership

- `action.yaml` declares the public GitHub Action inputs and exposes every input as `INPUT_<UPPER_SNAKE_NAME>` under `runs.env`.
- `src/aip/inner/action_entrypoint.py` owns action-mode adaptation, command applicability, required inputs, aliases, legacy action invocation compatibility, and deferred CLI import.
- `src/aip/inner/main.py` and the verb modules own the direct Typer CLI and command behavior.
- `Dockerfile` must enter through `python -m aip.inner.action_entrypoint`. Direct users must still be able to invoke `python -m aip.inner.main`.
- `test_action_contract.py` enforces synchronization between all of these surfaces.

## Required synchronization

When adding, removing, renaming, requiring, or changing the default of an input or command, update all applicable surfaces in the same change:

1. The input declaration and `INPUT_*` exposure in `action.yaml`.
2. `ACTION_INPUTS`, `CLI_OPTIONS`, and the relevant `COMMAND_SPECS` entry in `action_entrypoint.py`.
3. The corresponding Typer registration and command signature.
4. The command examples and input documentation when the public contract changes.
5. Contract-test expectations, including command counts when a command pair changes.

The adapter matrix and Typer tree must expose exactly the same command pairs, options, required options, and positional argument for each command. Every declared action input must be classified as applicable to at least one command or explicitly unsupported.

## Invariants

- Do not restore a universal `runs.args` list in `action.yaml`; action mode must omit blank and inapplicable options.
- Do not point the Dockerfile directly at `aip.inner.main`.
- Keep `action_entrypoint.py` importable without importing `aip.inner.main`, Azure SDK modules, or command modules. Validate before the deferred CLI import. Errors may name a recognized verb-subject pair, but must not echo raw unsupported selectors or any other input values.
- Preserve direct CLI passthrough and historical full-argument action compatibility unless an explicit migration removes them.
- Keep command-specific defaults in Typer or adapter logic rather than as global action defaults when a default would make an input appear nonblank for unrelated commands.
- Reject nonblank inapplicable, conflicting, and unsupported inputs. Do not enable Click/Typer unknown-option passthrough to conceal contract drift.
- Preserve environment-only mappings and cleanup for values that cannot be represented safely or compatibly as CLI options.

## Validation

Run the focused contract suite after every contract change:

```powershell
Set-Location inner-loop
uv run pytest test_action_contract.py -q
```

The change is incomplete if the action metadata, command matrix, and Typer-tree synchronization assertions do not pass.