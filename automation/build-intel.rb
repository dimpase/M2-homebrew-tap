require "formula"
require "formula_installer"
require "install"
require "reinstall"
f = Formula[ARGV.fetch(0)]
node = Pathname(ENV.fetch("INTEL_NODE_TOOL"))
external_node = f.full_name == "macaulay2/tap/macaulay2"
missing = f.deps.reject do |dep|
  dep.optional? || dep.test? || dep.to_formula.latest_version_installed? ||
    (external_node && dep.build? && dep.name == "node")
end
raise "Missing prerequisites: #{missing.map(&:name).join(', ')}" unless missing.empty?
if external_node
  ENV.delete("DISPLAY")
  raise "Unexpected Node build tool" unless Utils.safe_popen_read(node/"bin/node", "--version").strip == "v26.11.1"
  python_dep = f.deps.find { |dep| dep.name.start_with?("python@") }
  python = python_dep&.to_formula
  tools = [node/"bin", python && python.libexec/"bin", python&.bin, HOMEBREW_PREFIX/"bin"].compact.join(File::PATH_SEPARATOR)
  ENV["HOMEBREW_PATH"] = "#{tools}:#{ENV.fetch('HOMEBREW_PATH')}"
  ENV["PATH"] = "#{tools}:#{ENV.fetch('PATH')}"
end
class PreparedIntelInstaller < FormulaInstaller
  def compute_dependencies(use_cache: true)
    []
  end
end
keg = f.opt_prefix.directory? ? Keg.new(f.opt_prefix.realpath) : nil
installer = (external_node ? PreparedIntelInstaller : FormulaInstaller).new(f,
  build_bottle: true, verbose: true, env: external_node ? "std" : nil,
  installed_on_request: true, link_keg: !f.keg_only?)
Homebrew::Install.perform_preinstall_checks_once
raise "Source fetch failed" unless Homebrew::Install.fetch_formulae([installer]).include?(installer)
context = Homebrew::Reinstall::InstallationContext.new(formula_installer: installer, keg: keg,
  formula: f, options: Options.new, link_keg: !f.keg_only?)
Homebrew::Reinstall.reinstall_formula(context)
