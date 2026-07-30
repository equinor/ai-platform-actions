# Build and release guidance

How work should move from a feature branch, through review and merge, into tagged source releases and Docker images.

> Repository snapshot: 2026-07-23 — Branch: `impl-ol-us` / PR #45.
> A styled, printable version of this document is available at [build-and-releaseguidance.html](build-and-releaseguidance.html).

## Contents

- [Recommended strategy](#recommended-strategy)
- [Verified current state](#verified-current-state)
- [Delivery flow](#delivery-flow)
- [Pull requests](#pull-requests)
- [Merging](#merging)
- [Docker image building](#docker-image-building)
- [How and when to version](#how-and-when-to-version)
- [Stable release runbook](#stable-release-runbook)
- [Tag semantics and consumer guidance](#tag-semantics-and-consumer-guidance)
- [Failure response](#failure-response)
- [Known gaps and recommended hardening](#known-gaps-and-recommended-hardening)
- [Evidence and scope](#evidence-and-scope)

## Recommended strategy

**Use a mainline workflow.** Branch from `main`, open a PR back to `main`, run the relevant tests and both Docker builds before merge, merge only reviewed green work, and create a repository-wide SemVer release from an explicitly tagged and verified `main` commit. Publishing the GitHub Release, not merging or pushing a tag, is what starts image publication.

This recommendation follows the repository's recent practice. The older GitFlow text in the root README describes feature work through `develop`, but `develop` was 30 commits behind `main` and zero commits ahead when analyzed. Recent releases and PRs have gone directly to `main`.

| Status | Guidance |
| --- | --- |
| ✅ Use now | Short-lived branch → PR to `main` → validated merge → explicit stable release. |
| Transition | PR #45 introduces the outer-loop action and changes both action definitions to build from their referenced Dockerfiles. |
| ❌ Do not assume | Reviews, tests, or merge methods are not currently enforced by a branch ruleset. |

## Verified current state

The following facts were checked against the local repository and GitHub using `gh` on 2026-07-23.

| Area | Observed behavior | Operational meaning |
| --- | --- | --- |
| Default branch | `main` | All recent release work and PRs #38 through #46 targeted `main`. |
| `develop` | Exists, last updated 2026-02-12; 30 commits behind `main`, zero ahead. | It is not serving as the current integration branch. Do not route new work through it unless the team explicitly revives and resynchronizes it. |
| Branch enforcement | No repository rulesets; `main` reports no branch protection. | Reviews, checks, and no-direct-push behavior are conventions, not controls. |
| Merge settings | Merge commits, squash merges, and rebase merges are all enabled. Auto-merge is off. Branch auto-delete is off. | Choose deliberately. Recent history uses merge commits with `Merge pull request #...` subjects. |
| PR checks | GitHub CodeQL default setup is active. The active PR had successful action and Python CodeQL checks. | There is no checked-in PR workflow that runs the Python tests or Docker builds. |
| Image trigger | `release: published` only. | Merging to `main`, pushing a branch, or pushing a tag alone does not publish images. |
| Image matrix in this branch | `inner-loop` and `outer-loop`, with `fail-fast: false`. | The two builds are independent. One can publish while the other fails. |
| Release history | `v1.0.0-rc`, `v1.0.0`, `v1.0.1`, `v1.0.2`, `v1.0.3`; latest published 2026-05-04. | The repository already uses `vMAJOR.MINOR.PATCH` tags and GitHub Releases. |
| Version source | Both Python projects still declare `0.1.0`. | The GitHub Release tag is the effective repository version; package metadata is not currently synchronized to releases. |

> **Transition around PR #45**
> On `origin/main` at analysis time, only the inner-loop release image was built and the inner action referenced `ghcr.io/.../inner-loop:latest`. This branch adds the outer-loop build matrix and changes both action definitions to `image: Dockerfile`. Once merged, calls pinned to a repository ref build from that ref's Docker context; the GHCR release images remain available to direct image consumers but are not referenced by these action definitions.

## Delivery flow

| Stage | Step | What happens |
| --- | --- | --- |
| 01 | Branch | Start from current `main`. Keep scope reviewable and commits understandable. |
| 02 | PR | Target `main`. Document what, why, compatibility, and validation. |
| 03 | Merge | Merge reviewed, tested work. A merge does not publish a Docker image. |
| 04 | Release | Tag the exact validated `main` SHA and publish a GitHub Release. |
| 05 | Images | The release event builds each loop and pushes exact, major, and latest tags. |

> **Trigger boundary**
> The only checked-in build workflow listens for a published release. Drafting a release is safe for review; publishing it is the deployment action.

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

No checked-in PR workflow currently runs these tests. The author must run the suites relevant to the changed action and report the result in the PR.

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

A merge updates source on `main`. It does not run `Build and Push` and does not change GHCR image tags. Delete the feature branch manually because automatic deletion is disabled.

```powershell
git switch main
git pull --ff-only
git branch -d feature/<short-description>
git push origin --delete feature/<short-description>
```

## Docker image building

The checked-in workflow is [`.github/workflows/build-and-push-image.yaml`](../.github/workflows/build-and-push-image.yaml). In this branch it runs a two-item matrix.

| Property | Current value | Consequence |
| --- | --- | --- |
| Event | GitHub Release `published` | Draft releases and plain tag pushes do not build. |
| Runner | `ubuntu-latest` | No explicit multi-platform build is configured. |
| Contexts | `inner-loop`, `outer-loop` | Each directory is an independent image build context. |
| Registry auth | `GITHUB_TOKEN` with `packages: write` | No separate registry secret is required. |
| Tags | `latest`, exact release tag, derived major tag | A stable release such as `v1.2.3` pushes `latest`, `v1.2.3`, and `v1`. |
| Failure mode | `fail-fast: false` | One image may publish tags even if the other image fails. |
| Dependency lock | Inner uses `uv sync --locked`; outer currently resolves with `uv sync`. | The outer lock file is tracked, but its Dockerfile does not copy or enforce it, so the outer image build remains less reproducible. |

### What does not build an image

- Pushing a feature branch.
- Opening or updating a PR.
- Merging a PR into `main`.
- Creating or pushing only a Git tag.
- Saving a GitHub Release as a draft.

### What does build and push

Publishing the GitHub Release. The release tag's commit becomes the checkout SHA, and both Docker contexts are built from that source snapshot.

> **Prerelease hazard**
> The workflow does not inspect `github.event.release.prerelease`. Publishing a future prerelease would also overwrite `latest` and the major image tag. Until the workflow separates prerelease tags, do not publish prereleases through this workflow if stable consumers use either floating image tag.

## How and when to version

Use one repository-wide semantic version because one GitHub Release currently builds both loop images together. Team policy should use `vMAJOR.MINOR.PATCH`; the workflow does not currently validate or enforce that format.

| Change | Version | Examples in this repository |
| --- | --- | --- |
| Patch | `v1.0.3` → `v1.0.4` | Bug fix, dependency/security update, documentation correction with no contract change. |
| Minor | `v1.0.3` → `v1.1.0` | New backward-compatible verb/subject, new optional input, or new output. |
| Major | `v1.0.3` → `v2.0.0` | Removed or renamed input, changed requiredness, incompatible output, or changed command semantics. |

### Release when

- The intended set of changes is already merged into `main`.
- The exact main SHA has passed the relevant tests and both Docker builds.
- Public action-contract changes are documented.
- The release notes explain user-visible changes and migration steps.
- The team is prepared to monitor both image jobs and respond to a partial publication.

### Do not release merely because

- A PR was merged. Accumulate compatible changes if there is no delivery need.
- A tag name was reserved. Tags should identify validated commits, not planned work.
- One loop passed while the other loop is unverified. The release publishes both.

## Stable release runbook

This sequence deliberately separates tag creation, draft review, publication, workflow verification, and floating-tag movement.

### 1. Choose the SemVer increment

Review changes since the latest release. The latest release at analysis time was `v1.0.3`.

```powershell
git fetch origin main --tags
git log --first-parent v1.0.3..origin/main
git diff --stat v1.0.3..origin/main
```

### 2. Pin the candidate SHA

Release only from up-to-date `main`. Record the SHA in the release notes or operational record.

```powershell
git switch main
git pull --ff-only
$ReleaseSha = git rev-parse HEAD
git status --short
$ReleaseSha
```

The working tree should be clean.

### 3. Validate that exact source

Run the relevant Python suites and build both Docker contexts. Do not validate one commit and tag another.

```powershell
Push-Location inner-loop
uv sync --locked
uv run --with pytest pytest -q
Pop-Location

Push-Location outer-loop
uv sync
uv run --with pytest pytest -q
Pop-Location

docker build --tag aip-inner-loop:$ReleaseSha ./inner-loop
docker build --tag aip-outer-loop:$ReleaseSha ./outer-loop
```

### 4. Create and push an annotated exact tag

Use one spelling consistently: `vMAJOR.MINOR.PATCH`.

```powershell
$Version = "v1.1.0"  # Example; choose from the actual change set.
git tag -a $Version $ReleaseSha -m "Release $Version"
git push origin $Version
```

A tag push alone does not trigger the image workflow.

### 5. Create a draft GitHub Release

`--verify-tag` prevents GitHub CLI from silently creating a tag at a different target.

```powershell
gh release create $Version `
  --repo equinor/ai-platform-actions `
  --verify-tag `
  --draft `
  --generate-notes `
  --title $Version
```

Edit generated notes into a user-facing summary with breaking changes, migration steps, validation, and the release SHA. The draft does not build images.

### 6. Publish the stable release

Publishing is the deployment event. Do this only when release notes and source are final.

```powershell
gh release edit $Version `
  --repo equinor/ai-platform-actions `
  --draft=false `
  --prerelease=false `
  --latest
```

### 7. Watch both matrix jobs

```powershell
gh run list `
  --repo equinor/ai-platform-actions `
  --workflow build-and-push-image.yaml `
  --limit 5

gh run watch <run-id> `
  --repo equinor/ai-platform-actions `
  --exit-status
```

Inspect the matrix details and confirm both `inner-loop` and `outer-loop` succeeded. A green run, not merely a published release page, completes image publication.

### 8. Verify and only then move source aliases

Confirm the exact release is usable. If the team supports a floating Git tag such as `v1`, move it only after the exact release and both images are healthy. Record that movement because Git tags and Docker tags are independent.

## Tag semantics and consumer guidance

| Reference | Moves when | Recommended use |
| --- | --- | --- |
| `v1.2.3` Git tag | Created once for the exact release SHA. | Preferred source-action reference for a stable, auditable release. |
| `v1` Git tag | Only when someone or automation force-updates it. | Rolling major source reference only if the team actively maintains it. |
| `v1.2.3` image tag | Pushed by the release workflow. | Preferred human-readable GHCR pin; use a digest for strongest immutability. |
| `v1` image tag | Overwritten on every published release whose derived major is `v1`, including prereleases under the current workflow. | Rolling major compatibility channel. |
| `latest` image tag | Overwritten on every published release, including prereleases under the current workflow. | Development only; avoid for controlled production rollouts. |
| `main` source ref | Every merge or push to `main`. | Fast-moving development use, not a reproducible production pin. |

> ❌ **The current Git tag `v1` is stale**
> It points to the `v1.0.1` commit, while the latest GitHub Release is `v1.0.3`. The image workflow's `v1` Docker tag is a separate reference and is updated independently. Do not describe `uses: ...@v1` as latest-v1 behavior until the source tag is repaired and its update procedure is automated.

### Recommended consumer pins

| Consumer | Production preference | Development preference |
| --- | --- | --- |
| GitHub Action source | For the first release containing PR #45 and later: exact release tag or full commit SHA. Releases through `v1.0.3` pin action metadata but still load `inner-loop:latest` at runtime. | `@main` when deliberately testing unreleased behavior. |
| Direct GHCR image | Digest, then exact release tag. | Major tag or `latest` when automatic updates are acceptable. |

## Failure response

### PR checks fail

1. Do not merge.
2. Reproduce locally where possible.
3. Push a focused fix to the same branch.
4. Update the PR validation record and wait for checks.

### One release image fails

1. Do not move a floating source tag such as `v1`.
2. Record which image and which tags were already pushed; `fail-fast: false` allows partial publication.
3. If the failure is transient and source is correct, rerun only after understanding whether successful tags will be overwritten.
4. If source is wrong, prepare a new patch release. Do not retag a published exact version to different source.

### Bad release was published

1. Mark the release status clearly in its notes.
2. Fix forward with a new patch version.
3. Move floating image/source channels only to the fixed release.
4. Do not reuse an exact SemVer tag for different content.

## Known gaps and recommended hardening

These are repository findings, not prerequisites for understanding the current flow. They are the highest-value improvements to make the documented strategy enforceable.

| Priority | Gap | Recommended change |
| --- | --- | --- |
| P0 | No branch protection or ruleset on `main`. | Require PRs, one approval, CodeQL, and a new test/build check; block force pushes and deletion. |
| P0 | No PR workflow runs tests or Docker builds. | Add a pull-request workflow for inner tests, outer tests, and both Docker builds. Make it required. |
| P0 | Prereleases overwrite stable image channels. | For prereleases, push only the exact prerelease tag. Move `latest` and major tags only for stable releases. |
| P1 | The two-image matrix can partially publish. | Build and validate both first, then promote tags only after both succeed. |
| P1 | Floating Git tag `v1` is stale. | Either automate its post-success update or stop advertising major source tags. |
| P1 | The tracked outer lock file is ignored by the Docker build. | Copy `outer-loop/uv.lock` into the image context and build with `uv sync --locked`. |
| P1 | Release tag syntax is not validated. | Reject tags that do not match `vMAJOR.MINOR.PATCH` or an explicitly supported prerelease form before deriving image tags. |
| P2 | README describes an inactive GitFlow and protections that do not exist. | Replace it with the mainline policy or formally restore and protect `develop`. |
| P2 | Release workflow publishes no SBOM, provenance, signature, or explicit platform list. | Add attestations and define supported architectures as supply-chain requirements mature. |
| P2 | Action definitions in PR #45 use local Dockerfiles while release images are still published. | Decide whether GHCR is a supported direct artifact or the action runtime, then document and test one intentional model. |

## Evidence and scope

This guide describes the repository and GitHub configuration as observed on 2026-07-23. GitHub settings can change independently of this file, so re-check them when changing policy.

- [Build and Push workflow](../.github/workflows/build-and-push-image.yaml): release event, permissions, matrix, and image tags.
- [CONTRIBUTING.md](../CONTRIBUTING.md): SemVer intent and general PR contribution guidance.
- [README.md](../README.md): documented GitFlow strategy, compared with actual branch and PR history.
- [Inner-loop action metadata](../inner-loop/action.yaml) and [outer-loop action metadata](../outer-loop/action.yaml): runtime image mode in PR #45.
- [PR #45](https://github.com/equinor/ai-platform-actions/pull/45): active transition introducing outer-loop and action entrypoint changes.
- [GitHub Releases](https://github.com/equinor/ai-platform-actions/releases): release tags, dates, and notes.
- [Build and Push runs](https://github.com/equinor/ai-platform-actions/actions/workflows/build-and-push-image.yaml): successful release-triggered executions.
- GitHub API via `gh`: default branch, merge-method settings, rulesets, branch protection, workflow inventory, PR history, release metadata, and current checks.

> **Scope limit**
> The authenticated GitHub token did not have `read:packages`, so package-version metadata was not independently enumerated through the Packages API. Workflow behavior and successful historical runs establish what the release process attempts to publish; release operators should still inspect GHCR after each release.
