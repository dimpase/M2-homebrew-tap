class Lrs < Formula
  desc "Vertex enumeration/convex hull problems"
  homepage "https://cgm.cs.mcgill.ca/~avis/C/lrs.html"
  url "https://cgm.cs.mcgill.ca/~avis/C/lrslib/archive/lrslib-073.tar.gz"
  sha256 "c49a4ebd856183473d1d5a62785fcdfe1057d5d671d4b96f3a1250eb1afe4e83"
  license "GPL-2.0-only"

  bottle do
    root_url "https://ghcr.io/v2/macaulay2/tap"
    rebuild 2
    sha256 cellar: :any, arm64_tahoe:   "6429a452aa15a9c791f9671fa47ea871ecb6ae0feccafd62e334edaf255f1823"
    sha256 cellar: :any, arm64_sequoia: "694725874b58ab1bbc7ae1017be72b7c2f81385342777b1f8d3d51f473a29130"
    sha256 cellar: :any, arm64_linux:   "7abebf7ccf5264fa5a8125bfadb7c258c01951302aafc2cb0551ccd8dd990598"
    sha256 cellar: :any, x86_64_linux:  "577028404a9d4d17b30dad0cfe4b609f69676231d9b767ce61ab9cae01c23420"
  end

  depends_on "gmp"

  on_macos do
    on_intel do
      bottle do
        root_url "https://github.com/dimpase/M2-homebrew-tap/releases/download/intel-sequoia-20261009"
        rebuild 3
        sha256 cellar: :any, sequoia: "15f7ef761a50bb2686c5187ecb8a7f95527a592e1c6e00cda40be3cd0e2a6531"
      end
    end
  end

  def install
    system "make", "lrs", "prefix=#{prefix}", "CC=#{ENV.cc} -std=gnu17",
           "INCLUDEDIR=#{Formula["gmp"].include}",
           "LIBDIR=#{Formula["gmp"].lib}"
    bin.install "lrs"
  end

  test do
    system "true"
  end
end
