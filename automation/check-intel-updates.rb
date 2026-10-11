require "json"
require "digest"
require "formula"
require "utils/bottles"

baseline = JSON.parse(File.read(ARGV.fetch(0)))
root = Formula["macaulay2/tap/macaulay2"]
deps = root.recursive_dependencies do |_dependent, dep|
  Dependable::PRUNE if dep.build? || dep.test? || dep.optional?
end
formulae = (deps.map(&:to_formula) + [root]).uniq(&:full_name)
previous = baseline.fetch("formulae").to_h { |row| [row.fetch("name"), row] }
rows = formulae.map do |f|
  source = f.path.read.gsub(/^  bottle do\n.*?^  end\n/m, "")
  digest = Digest::SHA256.hexdigest(source)
  old = previous[f.full_name]
  tags = %i[sequoia tahoe].to_h do |system|
    tag = Utils::Bottles::Tag.from_symbol(system)
    match = f.bottle_specification.tag_specification_for(tag)
    [system.to_s, match&.tag&.to_s]
  end
  { "name" => f.full_name, "version" => f.pkg_version.to_s,
    "previous_version" => old && old.fetch("version"),
    "recipe_sha256" => digest,
    "changed" => old.nil? || old.fetch("recipe_sha256") != digest || old.fetch("version") != f.pkg_version.to_s,
    "upstream_bottle_tags" => tags }
end
removed = previous.keys - rows.map { |row| row.fetch("name") }
changed = rows.select { |row| row.fetch("changed") }
missing = rows.select { |row| row.fetch("upstream_bottle_tags").values.any?(&:nil?) }
report = { "baseline_release" => baseline.fetch("release"),
  "upstream_core_commit" => Formula["gmp"].tap_git_head,
  "upstream_m2_commit" => root.tap_git_head,
  "update_needed" => !changed.empty? || !removed.empty?,
  "changed_formulae" => changed.map { |row| row.fetch("name") },
  "removed_formulae" => removed,
  "missing_upstream_intel_bottles" => missing.map { |row| row.fetch("name") },
  "formulae" => rows }
File.write("intel-update-report.json", JSON.pretty_generate(report) + "\n")
lines = ["# Intel bottle update check", "",
  "Published baseline: #{baseline.fetch('release')}", "",
  "Upstream core: `#{report.fetch('upstream_core_commit')}`",
  "Upstream M2 tap: `#{report.fetch('upstream_m2_commit')}`", "",
  "Runtime formulae: #{rows.length}; changed/new recipes: #{changed.length}; removed: #{removed.length}.", "",
  "| Formula | Published version | Upstream version | macOS 15 bottle | macOS 26 bottle |",
  "| --- | --- | --- | --- | --- |"]
changed.each do |row|
  tags = row.fetch("upstream_bottle_tags")
  lines << "| #{row.fetch('name')} | #{row['previous_version'] || 'new'} | #{row.fetch('version')} | #{tags['sequoia'] || 'missing'} | #{tags['tahoe'] || 'missing'} |"
end
lines += ["", "Missing compatible upstream Intel bottles: #{missing.map { |row| row.fetch('name') }.join(', ')}.", "",
  "Existing private bottles are additional to this upstream inventory. Reuse requires unchanged recipes and compatible dependency versions; a version match alone is insufficient.", "",
  "The stable branches and published installer have not been changed. Build missing bottles in a candidate snapshot, verify the complete runtime closure on both Intel runners, then publish and advance the baseline together."]
File.write("intel-update-report.md", lines.join("\n") + "\n")
puts lines.join("\n")
