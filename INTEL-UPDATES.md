# Maintaining the Intel bottle distribution

The stable distribution branches are `intel-bottles` in `dimpase/M2-homebrew-tap` and `dimpase/homebrew-core`. Dated release tags and their bottle files remain immutable snapshots. The installation script selects exact tested commits, so an upstream change cannot silently replace a working dependency set.

## Automated upstream checks

The **Check Intel bottle updates** GitHub Actions workflow runs daily at 09:23 UTC. It can also be launched using **Actions → Check Intel bottle updates → Run workflow**, or:

```sh
gh workflow run intel-bottle-updates.yml --repo dimpase/M2-homebrew-tap
```

The workflow runs on a disposable GitHub-hosted Intel macOS 15 VM. It reads the current Homebrew core and Macaulay2 tap recipes, resolves M2's runtime dependency closure, and compares versions and recipe hashes with the published baseline. Its report identifies added, removed, and changed formulae and compatible upstream bottles for both macOS 15 and 26. Changes to recipe code with no version bump are included; top-level bottle metadata changes alone are ignored.

Read the run summary or download the `intel-bottle-update-report` artifact. It includes the exact upstream commits and a machine-readable runtime inventory. A successful check means the report was generated; it does not mean an updated bottle set is ready.

## Publishing an update

1. Use the reported upstream commits to prepare isolated candidate snapshots for both forks. Carry forward the headless M2 build fix while upstream still needs it.
2. Reuse private bottles only when their recipe and dependency compatibility are established. Build missing runtime bottles on Intel macOS 15 so the resulting set can serve both macOS 15 and 26. Audit build prerequisites separately; the scheduled inventory covers runtime dependencies.
3. Keep builds sequential and maintain the disk guards used by the existing local builder: at least 25 GiB free before starting, with interruption below 20 GiB. The monitoring workflow does not build packages or use the personal Mac.
4. Publish the candidate bottles and a new immutable release index. Update the candidate installer with exact core and tap commits and the new index checksum.
5. Run `intel-runner-smoke.yml` against the candidate distribution branch. Require clean installation, all runtime bottle receipts, linkage checks, and M2 formula tests to pass on both `macos-15-intel` and `macos-26-intel`.
6. After both tests pass, advance `intel-bottles` in both forks, publish the verified installer and evidence, and refresh `automation/intel-baseline.json` on the default branch from the new upstream recipes and runtime inventory.

The scheduled job deliberately has read-only repository permissions. Building and publishing new bottles remains a separate operation; it never merges upstream directly into the working distribution. This avoids pairing new formula versions with old bottle checksums. Full automatic publication would require a build pipeline and credentials able to update both forks.

GitHub schedules run from the default branch, so the checker and baseline are installed on `main`; the working formula distribution stays on `intel-bottles`. If a public repository has no activity for 60 days, GitHub may disable its scheduled workflows; re-enable this workflow in Actions if necessary.
