# Macaulay2 bottles for Intel macOS 15 and 26

The `intel-sequoia-20261009` release supplies Macaulay2 1.26.06_1, LRS, ten missing Homebrew-core runtime bottles, and the simdjson build prerequisite. Existing compatible Intel bottles supply the other runtime dependencies. The release contains checksums, source commits, installation receipts, and compressed build logs.

Use a native Intel macOS 15 or 26 Homebrew installation at `/usr/local`. Download and inspect `install-m2-intel.sh` from the release, then run:

```sh
bash install-m2-intel.sh
```

The script selects these exact metadata snapshots:

- Core: `dimpase/homebrew-core` at `c1ebdca2ff4b1ccb46a02c3946f8bc6f9814b117`.
- M2: `dimpase/M2-homebrew-tap` at `5ded09e4d7921926d21eb2bb86c77c1a7d298f37`, installed under the canonical `macaulay2/tap` name so qualified dependencies resolve correctly.

It switches the two tap remotes, refuses dirty tap checkouts, verifies the release index checksum and every runtime formula version, and selects Git metadata rather than the official formula API. It then installs M2, checks that all 41 runtime formulae were poured from bottles, and runs linkage and formula tests. The receipt report is saved as `m2-intel-pour-report.json`.

This snapshot is intended for a fresh installation. An existing dependency built from source will fail the bottle-only receipt check. The script never uninstalls packages on a personal machine; its `--clean-ci` option removes preinstalled runtime kegs only on a disposable GitHub-hosted runner.

The pinned snapshots should be kept together. Ordinary `brew update` or an installation using official API metadata can select different formula versions, for which this release may not have Intel bottles. Later installs against this snapshot should continue to set `HOMEBREW_NO_AUTO_UPDATE=1` and `HOMEBREW_NO_INSTALL_FROM_API=1`.

M2's build used official Intel Node 26.11.1 as a build-only tool, with its published SHA256 verified. Users pouring the M2 bottle do not need Node, Rust, or LLVM. `DISPLAY` was unset during documentation generation, and the installed runtime closure had no X11 linkage.

The manual `intel-runner-smoke.yml` workflow on the release branch validates installation on fresh `macos-15-intel` and `macos-26-intel` runners and preserves the receipt report and logs. Source-build and local formula tests passed before publication; clean-runner results are recorded by that workflow.

Clean installation verified on Intel macOS 15.7.9: [workflow run 38069712724](https://github.com/dimpase/M2-homebrew-tap/actions/runs/38069712724). All 41 runtime formulae were poured from bottles; M2 linkage and formula tests passed. The release includes `clean-install-report.json` and `clean-install-logs.tar.gz`.

The same Sequoia bottles also passed clean installation on Intel macOS 26.6.1, with macOS 15.7.9 rechecked in the same [workflow run 38073059626](https://github.com/dimpase/M2-homebrew-tap/actions/runs/38073059626). Both jobs poured all 41 runtime formulae from bottles and passed M2 linkage and formula tests. No runtime dependency source builds or new bottle builds were needed. The release includes `clean-install-macos-15-report.json`, `clean-install-macos-26-report.json`, and corresponding `clean-install-macos-15-logs.tar.gz` and `clean-install-macos-26-logs.tar.gz` evidence. These are two macOS versions on the same x86_64 architecture; Apple Silicon is outside this installer’s scope.
