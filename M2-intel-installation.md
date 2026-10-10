# Installing Macaulay2 bottles on an Intel Mac

These bottles install **Macaulay2 1.26.06_1 on Intel Macs running macOS 15 (Sequoia) or macOS 26 (Tahoe)**, using Homebrew at `/usr/local`. The same bottles passed clean installation tests on macOS 15.7.9 and 26.6.1.

## 1. Check your system

Open Terminal and run:

```bash
uname -m
sw_vers -productVersion
brew --prefix
```

The results should be:

- `x86_64` for the architecture.
- A macOS version beginning with `15` or `26`.
- `/usr/local` for the Homebrew prefix.

If Homebrew is missing, install it using the [official Homebrew installation instructions](https://docs.brew.sh/Installation), then repeat these checks.

## 2. Download and run the installer

Download the installer from our release:

```bash
curl -fL \
  https://github.com/dimpase/M2-homebrew-tap/releases/download/intel-sequoia-20261009/install-m2-intel.sh \
  -o install-m2-intel.sh
```

Inspect it before running:

```bash
less install-m2-intel.sh
```

Press `q` to leave `less`, then run:

```bash
bash install-m2-intel.sh
```

The installer verifies the release index and formula versions, downloads M2 and its runtime dependencies, checks that all 41 runtime packages were installed from bottles, and runs M2's linkage and formula tests. It saves installation receipts in `m2-intel-pour-report.json` in the current directory.

Run the installer without `sudo`. Use it without arguments; `--clean-ci` is reserved for disposable GitHub-hosted test runners.

## 3. Start Macaulay2

```bash
/usr/local/bin/M2
```

Enter `exit` to quit.

## Homebrew configuration and updates

**The installer switches your Homebrew core and M2 taps to our forks and pins their formula versions.** This affects subsequent Homebrew operations using those taps.

The selected snapshots are:

- Core: `dimpase/homebrew-core` at `c1ebdca2ff4b1ccb46a02c3946f8bc6f9814b117`.
- M2: `dimpase/M2-homebrew-tap` at `5ded09e4d7921926d21eb2bb86c77c1a7d298f37`, installed under the canonical `macaulay2/tap` name.

The installer is intended for a fresh Homebrew installation. Existing dependencies built from source can cause its bottle verification to fail. It refuses dirty tap checkouts and does not uninstall packages on a personal Mac.

Avoid `brew update` or `brew upgrade` while relying on this pinned snapshot: they may select formula versions for which this release has no bottles. For later installations using this snapshot, keep automatic updates and official API metadata disabled:

```bash
export HOMEBREW_NO_AUTO_UPDATE=1
export HOMEBREW_NO_INSTALL_FROM_API=1
```

## Release and verification

- [Bottle release, checksums, and detailed documentation](https://github.com/dimpase/M2-homebrew-tap/releases/tag/intel-sequoia-20261009).
- [Successful clean installation tests on Intel macOS 15 and 26](https://github.com/dimpase/M2-homebrew-tap/actions/runs/38073059626).

Both test runners installed all 41 runtime packages from bottles and passed M2's linkage and formula tests, without runtime dependency source builds. These are two macOS versions on the same Intel x86_64 architecture; this installer is for Intel Macs.
