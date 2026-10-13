# Maintaining the Intel bottle distribution

The stable branches are `intel-bottles` in `dimpase/M2-homebrew-tap` and `dimpase/homebrew-core`. Published release tags preserve immutable bottle snapshots. The installer pins exact core and M2 metadata commits and verifies its release index checksum.

## Automatic updates

The **Update Intel bottles** workflow on `main` runs daily at 09:23 UTC. It can also be launched from **Actions → Update Intel bottles → Run workflow**, or:

```sh
gh workflow run intel-bottle-updates.yml --repo dimpase/M2-homebrew-tap --ref main -f publish=true
```

Use `publish=false` to build and test a candidate without advancing the working branches. The candidate remains marked as a prerelease.

The workflow:

1. Resolves M2's current runtime closure from exact upstream core and tap commits. It compares package versions and recipe hashes with the last verified baseline. If nothing relevant changed, later jobs are skipped.
2. Prepares candidates in a disposable Intel macOS 15 VM. It keeps existing private bottle overrides only for unchanged recipes with unchanged runtime dependency recipes and versions. Changes propagate to affected runtime dependents. It separately resolves build prerequisites.
3. Pours compatible bottles and builds missing bottles sequentially. M2 uses the checksum-pinned official Node 26.11.1 Intel binary as a build-only tool. Builds require at least 25 GiB free and are interrupted below 20 GiB. Validated bottle artifacts are cached so retries can resume without rebuilding them.
4. Saves source-build receipts, formula tests, linkage logs, and an audit of runtime Mach-O files for X11 linkage. A staging job creates candidate branches and a prerelease, then generates the index and installer with exact metadata pins.
5. Runs clean installation tests in separate fresh `macos-15-intel` and `macos-26-intel` VMs. Every runtime package must pour from a bottle; M2 linkage and formula tests must pass.
6. Verifies both sets of receipts and every uploaded asset digest, fast-forwards the two stable branches, marks the release verified/latest, and refreshes the default-branch monitoring baseline. Compilation or test failures leave the working distribution unchanged. Candidate releases and logs remain available for diagnosis.

The source-build job and both installation tests receive no publishing credentials. Staging and promotion use short-lived GitHub App tokens restricted to the two forks. The App ID is the `INTEL_BOTTLES_APP_ID` Actions variable, and the key is the `INTEL_BOTTLES_APP_PRIVATE_KEY` Actions secret in the M2 fork.

## Installing the current verified snapshot

Download the installer from the stable branch, inspect it, and run it on Intel macOS 15 or 26 with Homebrew at `/usr/local`:

```sh
curl -fL https://raw.githubusercontent.com/dimpase/M2-homebrew-tap/intel-bottles/install-m2-intel.sh -o install-m2-intel.sh
less install-m2-intel.sh
bash install-m2-intel.sh
```

The script pins the tested metadata pair. Existing source-built dependencies can fail its bottle-only receipt checks. It does not uninstall packages on a personal Mac.

## Operational limits and recovery

GitHub-hosted jobs have a six-hour execution limit. A failed build retains diagnostic artifacts and validated bottle cache entries; rerun the workflow to retry. Cache restoration requires the same dependency/source inventory. Never substitute an old bottle solely because its package version matches.

A promotion spanning two repositories is not atomic. The installer remains pinned to an exact pair, and candidates descend from recorded stable heads; concurrent branch changes stop promotion. If publication fails after one branch advances, inspect the candidate state and finish or revert that promotion before retrying. Keep previous releases available for rollback.

Only formula and alias directories are synchronized from upstream, so publishing does not require permission to modify GitHub workflow files. Review upstream workflow and infrastructure changes separately. The local headless M2 fix is carried only while upstream lacks it.

Schedules run from the default branch. If GitHub disables the scheduled workflow after prolonged repository inactivity, re-enable it in Actions. When Intel hosted runners retire, configure an Intel macOS 15 self-hosted build runner and retain both installation environments where available.
