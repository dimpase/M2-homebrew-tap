#!/bin/bash
# Install the pinned Intel Sequoia Macaulay2 bottle set.
set -euo pipefail

test "$(uname -m)" = x86_64
test "$(sw_vers -productVersion | cut -d. -f1)" = 15
brew_cmd=/usr/local/Homebrew/bin/brew
test "$($brew_cmd --prefix)" = /usr/local

export HOMEBREW_NO_AUTO_UPDATE=1 HOMEBREW_NO_INSTALL_FROM_API=1
export HOMEBREW_NO_ANALYTICS=1 HOMEBREW_NO_INSTALL_CLEANUP=1
export HOMEBREW_NO_INSTALLED_DEPENDENTS_CHECK=1
export HOMEBREW_CORE_GIT_REMOTE=https://github.com/dimpase/homebrew-core.git
unset DISPLAY
core_commit=c1ebdca2ff4b1ccb46a02c3946f8bc6f9814b117
m2_commit=5ded09e4d7921926d21eb2bb86c77c1a7d298f37
m2_remote=https://github.com/dimpase/M2-homebrew-tap.git
release_root=https://github.com/dimpase/M2-homebrew-tap/releases/download/intel-sequoia-20261009
report=${M2_BOTTLE_REPORT:-m2-intel-pour-report.json}
task_tmp=$(mktemp -d)
trap 'rm -rf "$task_tmp"' EXIT

curl -fL --retry 3 "$release_root/index.json" -o "$task_tmp/index.json"
printf '%s  %s\n' 98d0f6efb4743a90b0052b1a3709c43206e641a65fb04d7850d7d22ce37eee4f "$task_tmp/index.json" | shasum -a 256 -c -

# Preserve uncommitted work in any existing tap checkout.
for tap in homebrew/core macaulay2/tap; do
  tap_dir=$($brew_cmd --repository "$tap")
  if test -d "$tap_dir/.git" && test -n "$(/usr/bin/git -C "$tap_dir" status --porcelain)"; then
    echo "Tap checkout has uncommitted changes: $tap_dir" >&2
    exit 1
  fi
done
$brew_cmd tap --custom-remote --force homebrew/core "$HOMEBREW_CORE_GIT_REMOTE"
$brew_cmd tap --custom-remote macaulay2/tap "$m2_remote"
core_dir=$($brew_cmd --repository homebrew/core)
m2_dir=$($brew_cmd --repository macaulay2/tap)
/usr/bin/git -C "$core_dir" fetch --depth=1 origin "$core_commit"
/usr/bin/git -C "$core_dir" checkout --detach "$core_commit"
/usr/bin/git -C "$m2_dir" fetch --depth=1 origin "$m2_commit"
/usr/bin/git -C "$m2_dir" checkout --detach "$m2_commit"

# Homebrew versions that implement tap trust require custom remotes to be trusted.
if $brew_cmd help trust >/dev/null 2>&1; then
  $brew_cmd trust --tap "$HOMEBREW_CORE_GIT_REMOTE" "$m2_remote"
fi

cat > "$task_tmp/check.rb" <<'RUBY'
require "json"
require "formula"
require "utils/bottles"
index = JSON.parse(File.read(ARGV.fetch(0)))
mode = ARGV.fetch(1)
root = Formula["macaulay2/tap/macaulay2"]
deps = root.recursive_dependencies do |_dependent, dep|
  Dependable::PRUNE if dep.build? || dep.test? || dep.optional?
end
formulae = (deps.map(&:to_formula) + [root]).uniq(&:full_name)
expected = index.fetch("runtime_formulae").to_h { |row| [row.fetch("name"), row.fetch("version")] }
actual = formulae.to_h { |f| [f.full_name, f.pkg_version.to_s] }
raise "Runtime formula versions differ from the release index" unless actual == expected
rows = formulae.map do |f|
  tag = f.bottle_specification.tag_specification_for(Utils::Bottles.tag)
  raise "No compatible bottle for #{f.full_name}" unless tag && f.bottle_for_tag(Utils::Bottles.tag)
  row = { formula: f.full_name, version: f.pkg_version.to_s, bottle_tag: tag.tag.to_s }
  if mode == "after"
    receipt = JSON.parse((f.prefix/"INSTALL_RECEIPT.json").read)
    raise "#{f.full_name} was not poured from a bottle" unless receipt.fetch("poured_from_bottle")
    row[:poured_from_bottle] = true
    row[:source_tap_commit] = receipt.fetch("source")["tap_git_head"]
  end
  row
end
if mode == "after"
  File.write(ARGV.fetch(2), JSON.pretty_generate({ platform: Utils::Bottles.tag.to_s,
    core_commit: index.fetch("core_commit"), m2_commit: index.fetch("m2_commit"), formulae: rows }) + "\n")
elsif mode == "names"
  puts formulae.map(&:full_name)
else
  puts "Verified #{rows.length} runtime formula versions and compatible bottles"
end
RUBY
$brew_cmd ruby "$task_tmp/check.rb" "$task_tmp/index.json" before

# Only a disposable GitHub-hosted CI runner may remove preinstalled runtime kegs.
if test "${1:-}" = --clean-ci; then
  test "${RUNNER_ENVIRONMENT:-}" = github-hosted
  $brew_cmd ruby "$task_tmp/check.rb" "$task_tmp/index.json" names > "$task_tmp/formulae"
  while IFS= read -r formula; do
    if test -n "$($brew_cmd list --versions "$formula" 2>/dev/null || true)"; then
      $brew_cmd uninstall --force --ignore-dependencies "$formula"
    fi
  done < "$task_tmp/formulae"
elif test "$#" -ne 0; then
  echo 'Usage: install-m2-intel.sh [--clean-ci]' >&2
  exit 1
fi

$brew_cmd install --force-bottle macaulay2/tap/macaulay2
$brew_cmd ruby "$task_tmp/check.rb" "$task_tmp/index.json" after "$report"
$brew_cmd linkage --test macaulay2/tap/macaulay2
$brew_cmd test macaulay2/tap/macaulay2
echo "Verified bottle installation; receipts recorded in $report"
