# Build and release guidance

How work should move from a feature branch, through review and merge, into a dispatched release that publishes Docker images and pins the action definitions to their digests.

> Repository snapshot: 2026-07-30 — Branch: `ol-eval-gate-and-comp`.
> A styled, printable version of this document is available at [build-and-releaseguidance.html](build-and-releaseguidance.html).

## Contents

- [Recommended strategy](#recommended-strategy)
- [Verified current state](#verified-current-state)
- [Delivery flow](#delivery-flow)
- [Pull requests](#pull-requests)
- [Merging](#merging)
- [The Release workflow](#the-release-workflow)
- [How and when to version](#how-and-when-to-version)
- [Release runbook](#release-runbook)
- [Tag semantics and consumer guidance](#tag-semantics-and-consumer-guidance)
- [Failure response](#failure-response)
- [Known gaps and recommended hardening](#known-gaps-and-recommended-hardening)
- [Evidence and scope](#evidence-and-scope)

## Recommended strategy

**Use a mainline workflow with a dispatched release.** Branch from `main`, open a PR back to `main`, run the relevant tests and both Docker builds before merge, merge only reviewed green work, then run the `Release` workflow manually. Merging, pushing a tag, or drafting a GitHub Release publishes nothing. The workflow dispatch is the single deployment action, and the workflow itself creates the tag and the release.

One dispatch does five things in order: build and push both images, rewrite both `action.yaml` files to reference the published image digests, commit that on a new `release/<version>` branch, tag it, and publish the GitHub Release. A consumer pinned to a release tag therefore pulls a fixed image instead of building a Dockerfile at job start.

The older GitFlow text in the root README describes feature work through `develop`, but `develop` is not the integration branch. Recent releases and PRs have gone directly to `main`.

| Status | Guidance |
| --- | --- |
| ✅ Use now | Short-lived branch → PR to `main` → validated merge → `Release` workflow dispatch. |
| ⚠️ Know this | The release commit lives only on `release/<version>` and is never merged back, so `main` always carries `image: Dockerfile`. |
| ❌ Do not do | Do not create release tags or GitHub Releases by hand. The workflow aborts if the tag or the release branch already exists. |

## Verified current state

Workflow, script, action, Dockerfile, and tag facts were read from the local repository on 2026-07-30. Rows marked *(GitHub-side)* were last checked through `gh` on 2026-07-23 and have not been re-verified; GitHub settings change independently of this file.

| Area | Observed behavior | Operational meaning |
| --- | --- | --- |
| Release workflow | [`.github/workflows/release.yaml`](../.github/workflows/release.yaml), named `Release`. It is the only workflow file in the repository. | All build and publish behavior is in one job. There is no PR workflow. |
| Trigger | `workflow_dispatch` with `version`, `source-ref` (default `main`), and `update-major-tag` (default `true`). | A human starts every release. Pushes, merges, tag pushes, and manually created releases publish nothing. |
| Permissions | `contents: write`, `packages: write`. | The job pushes a branch and tags, creates a release, and pushes images using `GITHUB_TOKEN`. No extra registry secret. |
| Version validation | `^v[0-9]+\.[0-9]+\.[0-9]+(-[0-9A-Za-z.]+)?$`, hard failure otherwise. | `v1.1.2` and `v1.1.2-rc1` are accepted; `1.1.2` and `v1.1` are rejected before anything is published. |
| Release immutability | The job aborts if `refs/tags/<version>` or `refs/heads/release/<version>` already exists on the remote. | An exact version cannot be re-cut. A late failure usually forces a new version number. |
| Image build | Two sequential `docker/build-push-action@v6` steps, `inner-loop` then `outer-loop`. No matrix. | If inner-loop fails, outer-loop never runs. If outer-loop fails, inner-loop is already published. |
| Image tags | Always the exact version. Additionally `<major>` and `latest` only when the version has no prerelease suffix. | Prereleases cannot disturb the stable floating channels. |
| Digest pinning | [`.github/scripts/pin_action_image.py`](../.github/scripts/pin_action_image.py) rewrites `runs.image` from `Dockerfile` to `docker://ghcr.io/equinor/ai-platform-actions/<loop>@sha256:…`. | The script fails unless the current value is exactly `Dockerfile`, so it cannot double-pin. |
| Release commit | New branch `release/<version>`, one bot commit, an annotated tag on it, release created with `--target release/<version> --generate-notes`. | The release tag is **not** an ancestor of `main`. `git log main` will not contain it. |
| Major tag | `git tag --force` and `git push --force`, gated on `update-major-tag` and a non-prerelease version. | `v1` is maintained automatically and points at the newest stable `v1.x.y` release commit. |
| Action definitions on `main` | [inner-loop](../inner-loop/action.yaml) and [outer-loop](../outer-loop/action.yaml) both use `runs.using: docker` with `image: Dockerfile`. | `@main` consumers build the image in every job; release consumers pull a pinned digest. |
| Local tags present | `v1.0.0-rc`, `v1.0.0`, `v1.0.1`, `v1.0.2`, `v1.0.3`, `v1.1.0`, `v1.1.1`, plus the floating `v1`. | The repository is on the `v1` major line. |
| Version source | Both `pyproject.toml` files still declare `0.1.0`. | The Git tag is the only version of record. Package metadata is not synchronized to releases. |
| Dependency lock | inner-loop copies `uv.lock` and runs `uv sync --locked`; outer-loop copies only `pyproject.toml` and runs `uv sync`. | Outer-loop release images are not reproducible even though `outer-loop/uv.lock` is tracked. |
| Branch enforcement *(GitHub-side)* | No repository rulesets; `main` reported no branch protection. | Reviews and checks are conventions, not controls. |
| Merge settings *(GitHub-side)* | Merge commits, squash, and rebase all enabled. Auto-merge off. Branch auto-delete off. | Choose deliberately. Recent history uses merge commits. |
| PR checks *(GitHub-side)* | GitHub CodeQL default setup is active. | CodeQL is the only automatic PR signal; no checked-in workflow runs the Python tests or Docker builds. |

> **What changed, and why old instructions are dangerous**
> The previous `build-and-push-image.yaml` workflow was deleted in commit `d54d6dc`. It triggered on `release: published` and built a two-item matrix with `fail-fast: false`. Any instruction that says "publishing the GitHub Release starts the build", or that tells you to `git tag` and `gh release create` by hand, describes that removed workflow. Following it now pre-creates the refs that make the current workflow abort.

## Delivery flow

| Stage | Step | What happens |
| --- | --- | --- |
| 01 | Branch | Start from current `main`. Keep scope reviewable and commits understandable. |
| 02 | PR | Target `main`. Document what, why, compatibility, and validation. |
| 03 | Merge | Merge reviewed, tested work. Nothing is built or published. |
| 04 | Dispatch | Run the `Release` workflow with a version and a source ref. |
| 05 | Publish | The job pushes both images, pins the digests, creates and tags `release/<version>`, publishes the release, and moves `v<major>`. |

> **Trigger boundary**
> `workflow_dispatch` is the only trigger in the repository. Do not pre-create the tag or the GitHub Release; the workflow creates both, and pre-existing refs make it abort.

## Pull requests

**Recommended:** use short-lived branches from `main`. The current repository behavior does not justify the additional `develop` and release-branch hops described in the root README.

### Start and push a branch

```powershell
git fetch origin
git switch main
git pull --ff-only
git switch -c feature/<short-description>

# Make the change, then validate it.
git status --short
git add <intentional-paths>
git commit -m "Describe the behavior change"
git push --set-upstream origin HEAD
```

### Validation before requesting review

No checked-in PR workflow runs these tests, and neither does the release workflow. The author must run the suites relevant to the changed action and report the result in the PR. This is the only point in the delivery flow where the test suites are guaranteed to run at all.

```powershell
Push-Location inner-loop
uv sync --locked
uv run --with pytest pytest -q
Pop-Location

Push-Location outer-loop
uv sync
uv run --with pytest pytest -q
Pop-Location

docker build --tag aip-inner-loop:pr ./inner-loop
docker build --tag aip-outer-loop:pr ./outer-loop
```

### Create the PR

Target `main`. A useful PR body has four parts: what changed, why it changed, a concise change list, and exact validation evidence. Use a body file for multiline text.

```powershell
$Body = Join-Path $env:TEMP "ai-platform-actions-pr.md"
@'
## What
One-sentence outcome.

## Why
Problem and motivation.

## Changes
- Important implementation change
- Compatibility or documentation change

## Validation
- `...`: passed
- Docker builds: passed
'@ | Set-Content -Path $Body

gh pr create --base main --title "<clear title>" --body-file $Body
gh pr checks --watch
```

### PR checklist

- [ ] Branch was created from current `main`.
- [ ] Relevant Python tests pass locally.
- [ ] Changed Docker contexts build successfully.
- [ ] Action metadata, entrypoints, and Typer signatures remain synchronized.
- [ ] README and examples reflect public behavior.
- [ ] PR explains compatibility and release impact.

## Merging

**Current:** GitHub allows merge commits, squash, and rebase. Recent repository history uses merge commits. There is no enforced review count and no required status check.

**Recommended:** continue with merge commits until the team explicitly chooses a different history policy. This preserves PR boundaries and matches recent history. Do not mix methods casually within one release.

### Merge gate

1. At least one human has reviewed changes that affect runtime or release behavior.
2. CodeQL is green.
3. The PR reports local Python tests and Docker builds.
4. The branch is up to date enough that the tested result represents the merge result.
5. Breaking changes and release-version implications are called out.

> ❌ **Repository controls are weaker than the README claims**
> As analyzed, a direct push or an unreviewed merge is technically possible. Treat the gate above as mandatory team procedure until branch protection is configured.

### After merge

A merge updates source on `main`. It does not build or push images and does not change GHCR image tags; only a `Release` workflow dispatch does. Delete the feature branch manually because automatic deletion is disabled.

```powershell
git switch main
git pull --ff-only
git branch -d feature/<short-description>
git push origin --delete feature/<short-description>
```

## The Release workflow

The only checked-in workflow is [`.github/workflows/release.yaml`](../.github/workflows/release.yaml). One job builds the images, pins the action definitions to them, and creates the release.

### Inputs

| Input | Required | Default | Meaning |
| --- | --- | --- | --- |
| `version` | yes | — | Release tag, for example `v1.1.2` or `v1.1.2-rc1`. Regex-validated. |
| `source-ref` | yes | `main` | Branch or commit the release is built from. |
| `update-major-tag` | no | `true` | Move `v<major>` to this release. Skipped for prereleases. |

### Step order and what each step commits you to

The order matters operationally: images are pushed several steps before the release exists.

| # | Step | Effect when it succeeds | State when it fails |
| --- | --- | --- | --- |
| 1 | Validate release inputs | Derives the major tag, the prerelease flag, and both image tag lists. | Nothing published. |
| 2 | Checkout `source-ref` | Full history fetched. | Nothing published. |
| 3 | Verify release refs are free | Confirms the tag and `release/<version>` do not exist on the remote. | Nothing published. |
| 4 | Build and push inner-loop | inner-loop image pushed under every applicable tag. | Nothing published. |
| 5 | Build and push outer-loop | outer-loop image pushed under every applicable tag. | **inner-loop is already published**, including `latest` and `v<major>` for stable versions. |
| 6 | Pin action definitions | Both `action.yaml` files rewritten to digest references. | Both images published; no release. |
| 7 | Create release branch and tag | `release/<version>` and the annotated tag pushed. | Both images published; no release. |
| 8 | Publish GitHub release | Release created, marked prerelease when applicable. | Tag and branch exist, so the same version can no longer be re-run. |
| 9 | Move major tag | `v<major>` force-updated to the release commit. | Release is complete; only the floating tag is stale. |
| 10 | Report release | Job summary with release, commit, branch, and both digests. | Cosmetic. |

Runner is `ubuntu-latest` and no platform list is configured, so images are single-platform `linux/amd64`.

### Image tags produced

The namespace is `ghcr.io/equinor/ai-platform-actions`, and both loops always receive the same tag set.

| Version dispatched | Tags pushed for each loop |
| --- | --- |
| `v1.2.3` | `v1.2.3`, `v1`, `latest` |
| `v1.2.3-rc1` | `v1.2.3-rc1` only |

### What does not publish anything

- Pushing a feature branch, or opening or updating a PR.
- Merging a PR into `main`.
- Creating or pushing a Git tag by hand.
- Creating a GitHub Release by hand.

Only a `Release` workflow dispatch publishes. Creating the tag or the release manually is worse than inert: it makes the workflow abort at step 3 for that version.

### Digest pinning

[`.github/scripts/pin_action_image.py`](../.github/scripts/pin_action_image.py) rewrites the `runs.image` line of an action definition on the release branch only.

```yaml
# on main
runs:
  using: docker
  image: Dockerfile

# on release/v1.1.2
runs:
  using: docker
  image: docker://ghcr.io/equinor/ai-platform-actions/inner-loop@sha256:<digest>
```

The script rejects any reference that is not `ghcr.io/<path>@sha256:<64 hex>`, and rejects any file whose `runs.image` is not currently exactly `Dockerfile`. Together these guards mean a release cannot pin to a mutable tag and cannot re-pin an already pinned file.

> ⚠️ **Images are published before the release exists**
> Steps 4 and 5 push to GHCR before anything is tagged. A failure at step 6 or 7 leaves both images published, including moved `latest` and `v<major>` tags, with no release and no Git record of what they contain. See [Failure response](#failure-response).

## How and when to version

Use one repository-wide semantic version because one dispatch builds, tags, and releases both loops together. The workflow enforces `vMAJOR.MINOR.PATCH` with an optional prerelease suffix and fails before any build if the string does not match.

| Change | Version | Examples in this repository |
| --- | --- | --- |
| Patch | `v1.1.1` → `v1.1.2` | Bug fix, dependency/security update, documentation correction with no contract change. |
| Minor | `v1.1.1` → `v1.2.0` | New backward-compatible verb/subject, new optional input, or new output. |
| Major | `v1.1.1` → `v2.0.0` | Removed or renamed input, changed requiredness, incompatible output, or changed command semantics. |

### Prereleases

Dispatch a version such as `v1.2.0-rc1`. The workflow pushes only that exact image tag, marks the GitHub Release as a prerelease, and skips the major-tag move. `latest` and `v1` are left untouched, so a prerelease is safe to publish while stable consumers sit on floating tags.

### Release when

- The intended set of changes is already merged into `main`.
- The exact `source-ref` has passed the relevant tests and both Docker builds. **The release workflow runs no tests**; validation is entirely the operator's responsibility.
- Public action-contract changes are documented.
- The version number is unused. The workflow aborts if the tag or the release branch already exists.
- Someone is available to watch the run and respond to a mid-run failure.

### Do not release merely because

- A PR was merged. Accumulate compatible changes if there is no delivery need.
- A version number was reserved. Versions should identify validated source, not planned work.
- One loop passed while the other loop is unverified. One dispatch publishes both.

## Release runbook

The workflow performs the tagging, the release, and the floating-tag movement. The operator's job is everything before the dispatch and everything after the run.

### 1. Choose the SemVer increment

Review changes since the latest release.

```powershell
git fetch origin main --tags
$Previous = "v1.1.1"   # Latest release at the time of writing.
git log --first-parent "$Previous..origin/main"
git diff --stat "$Previous..origin/main"
```

### 2. Validate the source ref locally

The release workflow runs no tests. Validate the exact commit you are about to release.

```powershell
git switch main
git pull --ff-only
git status --short

Push-Location inner-loop
uv sync --locked
uv run --with pytest pytest -q
Pop-Location

Push-Location outer-loop
uv sync
uv run --with pytest pytest -q
Pop-Location

docker build --tag aip-inner-loop:candidate ./inner-loop
docker build --tag aip-outer-loop:candidate ./outer-loop
```

The working tree should be clean and both suites green before you continue.

### 3. Confirm the release refs are free

The workflow checks this as well, but checking first avoids burning a run.

```powershell
$Version = "v1.1.2"   # Example; choose from the actual change set.
git ls-remote --tags origin "refs/tags/$Version"
git ls-remote --heads origin "refs/heads/release/$Version"
```

Both commands should print nothing.

### 4. Dispatch the Release workflow

```powershell
gh workflow run release.yaml `
  --repo equinor/ai-platform-actions `
  --field version=$Version `
  --field source-ref=main `
  --field update-major-tag=true
```

Use `--field update-major-tag=false` when the release must not become the head of its major line, for example a backport onto an older line. Prerelease versions skip the major tag automatically.

### 5. Watch the run

```powershell
gh run list `
  --repo equinor/ai-platform-actions `
  --workflow release.yaml `
  --limit 5

gh run watch <run-id> `
  --repo equinor/ai-platform-actions `
  --exit-status
```

The job summary records the release, the release commit, the release branch, and both image digests. Keep it: that summary is the only place the two digests appear together.

### 6. Verify the published result

```powershell
git fetch origin --tags
git show "${Version}:inner-loop/action.yaml" | Select-String "image:"
git show "${Version}:outer-loop/action.yaml" | Select-String "image:"
git rev-parse "v1^{commit}" "${Version}^{commit}"

docker buildx imagetools inspect "ghcr.io/equinor/ai-platform-actions/inner-loop:$Version"
docker buildx imagetools inspect "ghcr.io/equinor/ai-platform-actions/outer-loop:$Version"
```

Both action definitions should show a `docker://...@sha256:` reference. For a stable release, `v1` and the exact tag should resolve to the same commit.

### 7. Replace the generated release notes

The workflow publishes `--generate-notes` output. Replace it with a user-facing summary covering user-visible changes, breaking changes, migration steps, and the validation performed in step 2.

```powershell
gh release edit $Version --repo equinor/ai-platform-actions --notes-file release-notes.md
```

### 8. Smoke-test a consumer pin

Run a real workflow against `equinor/ai-platform-actions/inner-loop@$Version` and confirm the job pulls the pinned image instead of building a Dockerfile. That step log is the proof that pinning took effect.

## Tag semantics and consumer guidance

| Reference | Moves when | Recommended use |
| --- | --- | --- |
| `v1.2.3` Git tag | Created once by the workflow on the `release/v1.2.3` commit. The workflow refuses to reuse it. | Preferred source pin. `uses: equinor/ai-platform-actions/inner-loop@v1.2.3` loads a digest-pinned image. |
| `v1` Git tag | Force-moved by the workflow on every stable `v1.x.y` release, unless `update-major-tag=false`. Prereleases never move it. | Rolling major source channel. It is now maintained automatically. |
| `release/v1.2.3` branch | Created once, never updated, never merged into `main`. | Audit trail for exactly what a release contained. Do not branch feature work from it. |
| `main` source ref | Every merge or push. `runs.image` is `Dockerfile` here. | Development only. Every consuming job rebuilds the image. |
| `v1.2.3` image tag | Pushed once by the workflow. | Direct GHCR consumers; a digest is still stronger. |
| `v1` image tag | Overwritten on every stable release with major `v1`. Prereleases never move it. | Rolling major compatibility channel. |
| `latest` image tag | Overwritten on every stable release. Prereleases never move it. | Development only; avoid for controlled production rollouts. |

> **Git tags and image tags move at different times**
> The `v1` image tag is written during the build step; the `v1` Git tag is written in the last step. If a run fails in between, the image channel has moved and the source channel has not. Check both after any failed run.

### Recommended consumer pins

| Consumer | Production preference | Development preference |
| --- | --- | --- |
| GitHub Action source | Exact release tag, for example `@v1.1.1`. It resolves to a digest-pinned image and skips the Docker build entirely. A full commit SHA on the release branch is equivalent. | `@main` when deliberately testing unreleased behavior; expect a Docker build in every job. |
| Direct GHCR image | Digest, then exact release tag. | `v1` or `latest` when automatic updates are acceptable. |

> **Older releases are not pinned**
> Only releases cut by the current workflow carry digest-pinned action definitions. Before relying on a pin, confirm it: `git show <tag>:inner-loop/action.yaml | Select-String "image:"` should print a `docker://...@sha256:` reference, not `Dockerfile`.

## Failure response

### PR checks fail

1. Do not merge.
2. Reproduce locally where possible.
3. Push a focused fix to the same branch.
4. Update the PR validation record and wait for checks.

### The release run failed

Recovery depends entirely on how far the job got, because images are pushed before anything is tagged. Read the step list in the failed run before acting.

| Failed at | What already exists | Recovery |
| --- | --- | --- |
| Validate inputs, or verify refs are free | Nothing. | Fix the version string, or choose an unused version, and redispatch. |
| Build and push inner-loop | Nothing. | Fix the source, merge it, redispatch the same version. |
| Build and push outer-loop | inner-loop images are published. For a stable version, `latest` and `v<major>` already point at them. | The floating image channels now serve an unreleased inner-loop build. Fix the source and redispatch the same version so both loops are overwritten together, or cut a corrective release promptly. |
| Pin, commit, tag, or push | Both images are published under every applicable tag. No branch, tag, or release. | The refs are still free, so the same version can be redispatched and will overwrite the images. |
| Publish GitHub release | Tag and `release/<version>` branch exist. Both images published. No release. | The same version can no longer be redispatched. Create the release by hand against the existing ref: `gh release create <version> --target release/<version> --generate-notes`. Delete the tag and branch and redispatch only if nothing consumes them yet. |
| Move major tag | The release is complete. Only the `v<major>` Git tag is stale. | Move it manually: `git tag -f v1 <version>; git push -f origin refs/tags/v1`. |

> ❌ **Do not delete a published exact tag in order to retry**
> Consumers may already resolve it, and the image under that version tag has already been pushed. Fix forward with a new patch version.

### Bad release was published

1. Mark the release status clearly in its notes.
2. Fix forward with a new patch version dispatched through the workflow.
3. Confirm the corrective release moved the `latest` and `v<major>` image tags and the `v<major>` Git tag.
4. Do not reuse an exact SemVer version for different content.

## Known gaps and recommended hardening

These are repository findings, not prerequisites for understanding the current flow. They are the highest-value improvements to make the documented strategy enforceable.

| Priority | Gap | Recommended change |
| --- | --- | --- |
| P0 | The release workflow runs no tests. It builds and publishes whatever `source-ref` points at. | Add a test job for the inner and outer suites that gates the build steps, or require a green required check on the source ref. |
| P0 | Images are pushed before the release is tagged, so a late failure moves `latest` and `v<major>` with no matching release. | Build both loops first, then push or promote the floating tags only after tagging succeeds. |
| P0 | No pull-request workflow. `release.yaml` is the only workflow in the repository. | Add a PR workflow for inner tests, outer tests, and both Docker builds, and make it required. |
| P0 | No branch protection or ruleset on `main` *(observed 2026-07-23, not re-verified)*. | Require PRs, one approval, CodeQL, and the new test/build check; block force pushes and deletion. |
| P1 | No `concurrency` group. Two dispatches can interleave and race on the floating GHCR tags. | Add a `concurrency` group so releases serialize. |
| P1 | `source-ref` is trusted without any relationship to `main`. A release can be cut from an unmerged branch. | Reject refs not reachable from `main`, or record the deviation in the release notes. |
| P1 | Release commits exist only on `release/*` and never return to `main`. | Intended, but undocumented in the repository itself. Decide a retention policy for accumulating release branches. |
| P1 | The tracked outer lock file is ignored by the Docker build. | Copy `outer-loop/uv.lock` into the image context and build with `uv sync --locked`, matching inner-loop. |
| P2 | Package metadata in both `pyproject.toml` files is frozen at `0.1.0`. | Either synchronize it during the release, or state explicitly that the Git tag is the only version of record. |
| P2 | Release workflow publishes no SBOM, provenance, signature, or explicit platform list. | Add attestations and declare supported architectures as supply-chain requirements mature. |
| P2 | README describes an inactive GitFlow and protections that do not exist. | Replace it with the mainline plus dispatched-release policy described here. |

## Evidence and scope

Workflow, script, action, Dockerfile, and tag facts were read from the local repository on 2026-07-30 on branch `ol-eval-gate-and-comp`. GitHub-side settings were last checked on 2026-07-23 and are marked as such in [Verified current state](#verified-current-state). GitHub settings change independently of this file, so re-check them when changing policy.

- [Release workflow](../.github/workflows/release.yaml): dispatch inputs, permissions, validation, build order, pinning, tagging, and release publication.
- [Digest pinning script](../.github/scripts/pin_action_image.py): the reference format and the `Dockerfile`-only precondition.
- [Inner-loop action metadata](../inner-loop/action.yaml) and [outer-loop action metadata](../outer-loop/action.yaml): `runs.image` on `main`.
- [Inner-loop Dockerfile](../inner-loop/Dockerfile) and [outer-loop Dockerfile](../outer-loop/Dockerfile): lock-file handling difference.
- [repository-version-consistency.md](../repository-version-consistency.md): the versioning and pinning intent this workflow implements.
- [CONTRIBUTING.md](../CONTRIBUTING.md): SemVer intent and general PR contribution guidance.
- [README.md](../README.md): documented GitFlow strategy, which no longer matches actual practice.
- [GitHub Releases](https://github.com/equinor/ai-platform-actions/releases): release tags, dates, and notes.
- [Release workflow runs](https://github.com/equinor/ai-platform-actions/actions/workflows/release.yaml): dispatch history and job summaries.

> **Scope limit**
> GHCR package metadata was not enumerated through the Packages API. The workflow definition establishes which tags a release attempts to publish; operators should still inspect GHCR after each release, especially after a failed run.
