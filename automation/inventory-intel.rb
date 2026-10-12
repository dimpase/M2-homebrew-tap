require "json"
require "digest"
require "formula"
require "utils/bottles"
root = Formula["macaulay2/tap/macaulay2"]
runtime = root.recursive_dependencies do |_dependent, dep|
  Dependable::PRUNE if dep.build? || dep.test? || dep.optional?
end
runtime_names = (runtime.map(&:to_formula) + [root]).map(&:full_name).uniq
rows = {}
visit = lambda do |f|
  next if rows.key?(f.full_name)
  raise "Unsupported tap: #{f.tap}" unless ["homebrew/core", "macaulay2/tap"].include?(f.tap.name)
  deps = f.deps.reject { |d| d.test? || d.optional? || (f == root && d.build? && d.name == "node") }
  edges = deps.map { |d| { "name" => d.to_formula.full_name, "build" => d.build? } }
  tag = Utils::Bottles::Tag.from_symbol(:sequoia)
  spec = f.bottle_specification.tag_specification_for(tag)
  bottle = spec && f.bottle_for_tag(tag)
  source = f.path.read.gsub(/^  bottle do\n.*?^  end\n/m, "")
  rows[f.full_name] = { "name" => f.full_name, "short_name" => f.name, "version" => f.pkg_version.to_s,
    "repository" => f.tap.name == "homebrew/core" ? "core" : "m2",
    "path" => f.path.relative_path_from(f.tap.path).to_s,
    "recipe_sha256" => Digest::SHA256.hexdigest(source), "dependencies" => edges,
    "bottle_tag" => spec&.tag&.to_s, "bottle_url" => bottle&.url, "bottle_sha256" => spec&.checksum&.to_s }
  deps.each { |d| visit.call(d.to_formula) }
end
visit.call(root)
File.write(ARGV.fetch(0), JSON.pretty_generate({ "runtime_names" => runtime_names, "formulae" => rows.values }) + "\n")
puts "Inventoried #{rows.length} runtime/build formulae"
