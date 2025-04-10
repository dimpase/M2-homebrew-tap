class Linbox < Formula
  desc "Finite Field Linear Algebra Routines"
  homepage "https://linalg.org/"
  url "https://github.com/linbox-team/linbox/releases/download/v1.7.0/linbox-1.7.0.tar.gz"
  sha256 "6d2159fd395be0298362dd37f6c696676237bc8e2757341fbc46520e3b466bcc"
  license "LGPL-2.1-or-later"
  revision 1

  head "https://github.com/linbox-team/linbox.git", using: :git, branch: "master"

  bottle do
    root_url "https://ghcr.io/v2/macaulay2/tap"
    rebuild 1
    sha256 cellar: :any, arm64_sequoia: "62047cb27b472f12dfeab11930b275d525b3c2f96dd826920c3f6e7b69938b38"
    sha256 cellar: :any, arm64_sonoma:  "0e363e7e399c90a11b53e93bc07078493009f4d21f7da928c9cd4ac171f7aaef"
    sha256 cellar: :any, ventura:       "37852730a92a5f70c8a9184be21c3bb6aa54614f2da062941cf581bb0a721716"
  end

  depends_on "autoconf" => :build
  depends_on "automake" => :build
  depends_on "libtool" => :build
  depends_on "pkg-config" => :build

  depends_on "fflas-ffpack"
  depends_on "flint"
  depends_on "givaro"
  depends_on "gmp"
  depends_on "libomp" if OS.mac?
  depends_on "ntl"
  depends_on "openblas" unless OS.mac?

  patch do
    url "https://github.com/linbox-team/linbox/commit/d1f618fb0ee4a84be3ccddcfc28b257f34e1cbf7.patch?full_index=1"
    sha256 "02d540bee9a0f482820ec2b002c443dd6bafc3d5177f3e7c439712fe0c9fe99c"
  end

  patch do
    url "https://github.com/linbox-team/linbox/commit/4a1e1395804d4630ec556c61ba3f2cb67e140248.patch?full_index=1"
    sha256 "e8f9df3c22ab119d8e363519d623aada86d2f804a7c06ff77efc4291698ca5d7"
  end

  def install
    ENV.cxx11
    if OS.mac?
      libomp = Formula["libomp"]
      ENV["OMPFLAGS"] = "-Xpreprocessor -fopenmp -I#{libomp.opt_include} #{libomp.opt_lib}/libomp.dylib"
    else
      ENV["OMPFLAGS"] = "-fopenmp"
    end
    ENV["CBLAS_LIBS"] = ENV["LIBS"] = OS.mac? ? "-framework Accelerate" : "-lopenblas"
    system "autoreconf", "-vif"
    system "./configure",
           "--enable-openmp",
           "--disable-dependency-tracking",
           "--disable-silent-rules",
           "--prefix=#{prefix}"
    system "make", "install"
  end

  test do
    system "true"
  end
end
