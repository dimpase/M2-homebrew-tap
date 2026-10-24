class Macaulay2 < Formula
  @name = "M2"
  desc "Software system for algebraic geometry research"
  homepage "http://macaulay2.com"
  # Draft: update the release URL/checksum after M2#4758 and M2#4730 are included.
  # The existing release metadata below is a placeholder; see README's draft notes.
  url "https://github.com/Macaulay2/M2/archive/refs/tags/release-1.26.06.tar.gz"
  sha256 "54f9e892941b2b548b90656c2b6d84a6d14c6908d5569bd61e7bb36b8c71bb29"
  license any_of: ["GPL-2.0-only", "GPL-3.0-only"]
  revision 1

  head "https://github.com/Macaulay2/M2/archive/refs/heads/development.tar.gz"

  depends_on "bison" => :build
  depends_on "cmake" => :build
  depends_on "eigen@3" => :build # TODO: drop the "@3"
  depends_on "ninja" => :build
  depends_on "node" => :build
  depends_on "pkgconf" => :build

  depends_on "bdw-gc"
  depends_on "boost"
  depends_on "fflas-ffpack"
  depends_on "flint"
  depends_on "frobby"
  depends_on "gdbm"
  depends_on "givaro"
  depends_on "glpk"
  depends_on "gmp"
  depends_on "jansson"
  depends_on "libffi"
  depends_on "libomp" if OS.mac?
  depends_on "macaulay2/tap/factory"
  depends_on "libxml2" unless OS.mac?
  # Require updated packages with the upstream CMake/pkg-config metadata.
  depends_on "mathic"
  depends_on "mathicgb"
  depends_on "memtailor"
  depends_on "mpfi"
  depends_on "mpfr"
  depends_on "mpsolve"
  depends_on "nauty"
  depends_on "normaliz"
  depends_on "ntl"
  depends_on "openblas" unless OS.mac?
  depends_on "python@3.14" # brew linkage --test expects specific version
  depends_on "readline"
  depends_on "tbb"

  depends_on "cohomcalg" => :recommended
  depends_on "csdp" => :recommended
  depends_on "fourtitwo" => :recommended
  depends_on "gfan" => :recommended
  depends_on "lrs" => :recommended
  depends_on "msolve" => :recommended
  depends_on "topcom" => :recommended

  patch :DATA

  def install
    # Build documentation without launching X11 programs such as xterm.
    ENV.delete("DISPLAY")

    # Don't print the shims prefix path
    inreplace "M2/Macaulay2/packages/Macaulay2Doc/functions/findProgram-doc.m2", "Verbose => true", "Verbose => false"

    # Don't print the shims prefix path
    inreplace "M2/Macaulay2/packages/ForeignFunctions.m2", "get \"!brew --prefix\"", "getenv \"HOMEBREW_PREFIX\""

    # Upstream links quadmath on non-macOS systems, but ARM64 Linux has no libquadmath.
    if OS.linux? && Hardware::CPU.arm?
      inreplace "M2/Macaulay2/d/CMakeLists.txt",
                "target_link_libraries(M2-interpreter PRIVATE quadmath)", ""
    end

    # Homebrew supplies dependency search paths and the platform toolchain settings.
    build_path = "M2/BUILD/build-brew"
    system "cmake", "-S", "M2", "-B", build_path, "-G", "Ninja",
                    "-DGIT_SUBMODULE=OFF", "-DBUILD_NATIVE=OFF", *std_cmake_args
    # Both package-install targets build M2-core through their CMake dependencies.
    package_target = head? ? "install-Macaulay2Doc" : "install-packages"
    system "cmake", "--build", build_path, "--target", package_target
    system "cmake", "--install", build_path
  end

  test do
    system "#{bin}/M2", "--version"
    system "#{bin}/M2", "--check", "1", "-e", "exit 0"
    # seems to fail if the tests take longer than 5min
    # system "#{bin}/M2", "--check", "2", "-e", "exit 0"
    # system "#{bin}/M2", "--check", "3", "-e", "exit 0"
  end
end

__END__

diff --git a/M2/Macaulay2/m2/packages.m2 b/M2/Macaulay2/m2/packages.m2
index 617dac19fa..9d560febc6 100644
--- a/M2/Macaulay2/m2/packages.m2
+++ b/M2/Macaulay2/m2/packages.m2
@@ -225,7 +225,6 @@ needsPackage String  := opts -> pkgname -> (
     and instance(pkg := value PackageDictionary#pkgname, Package)
     and (opts.FileName === null or
 	realpath opts.FileName == realpath pkg#"source file")
-    and pkg.PackageIsLoaded
     then (
 	if any(packageFiles pkg, file -> fileTime file > filesLoaded#file)
 	then loadPackage(pkgname, opts ++ {Reload => true})
-- 
2.43.0

diff --git a/M2/Macaulay2/packages/Topcom.m2 b/M2/Macaulay2/packages/Topcom.m2
index 52af3a2c69..6ffbef38a6 100644
--- a/M2/Macaulay2/packages/Topcom.m2
+++ b/M2/Macaulay2/packages/Topcom.m2
@@ -342,7 +342,7 @@ topcomIsTriangulation(Matrix, List) := Boolean => opts -> (Vin, T) -> (
       << "Index sets do not correspond to full-dimensional simplices" << endl;
       return false;
    );
-   (outfile, errfile) := callTopcom("points2nflips --checktriang -v", {topcomPoints(V, Homogenize=>false), [], T });
+   (outfile, errfile) := callTopcom("points2nflips --checktriang --memopt -v", {topcomPoints(V, Homogenize=>false), [], T });
    not match("not valid", get errfile)
 )
 
-- 
2.43.0
