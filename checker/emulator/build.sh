#!/usr/bin/env bash
# Build a local copy of ChromeOS's printing sandbox so PPDs can be tested
# without a Chromebook:
#
#   * foomatic_shell  - ChromeOS's restricted shell for PPD commands, built
#                       from chromiumos/platform2 source with tiny stand-ins
#                       for libchrome/brillo (stub/, fsmain.cc)
#   * foomatic-rip    - from cups-filters 1.28 (the version ChromeOS ships),
#                       with ChromeOS's own patches applied, wired to the
#                       foomatic_shell above
#
# Sources are downloaded at build time, not stored in this repository.
# Output goes to checker/emulator/build/ (git-ignored).
#
# Needs: git curl g++ gcc make pkg-config patch, plus the cups-filters build
# deps. On Debian/Ubuntu:
#   sudo apt install git curl g++ make pkg-config patch ghostscript cups \
#        libcups2-dev libqpdf-dev liblcms2-dev libfreetype-dev libfontconfig-dev \
#        libjpeg-dev libpng-dev libtiff-dev zlib1g-dev libdbus-1-dev
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
B="$HERE/build"
mkdir -p "$B"
cd "$B"

CF_VER=1.28.17
CF_URLS=(
  "https://github.com/OpenPrinting/cups-filters/releases/download/$CF_VER/cups-filters-$CF_VER.tar.xz"
  "http://archive.ubuntu.com/ubuntu/pool/main/c/cups-filters/cups-filters_1.28.15.orig.tar.xz"
)

echo "== 1/4 ChromeOS foomatic_shell source (chromiumos/platform2)"
if [ ! -d platform2/foomatic_shell ]; then
  git clone -q --depth 1 --filter=blob:none --no-checkout \
      https://chromium.googlesource.com/chromiumos/platform2 platform2
  git -C platform2 sparse-checkout set foomatic_shell
  git -C platform2 checkout -q
fi

echo "== 2/4 ChromeOS cups-filters patches (chromiumos-overlay)"
if [ ! -d overlay/net-print/cups-filters ]; then
  git clone -q --depth 1 --filter=blob:none --no-checkout \
      https://chromium.googlesource.com/chromiumos/overlays/chromiumos-overlay overlay
  git -C overlay sparse-checkout set net-print/cups-filters
  git -C overlay checkout -q
fi

echo "== 3/4 build foomatic_shell"
FS="$B/foomatic_shell_bin"
g++ -std=c++20 -O1 -I "$HERE/stub" -I platform2 "$HERE/fsmain.cc" \
    platform2/foomatic_shell/{grammar,scanner,parser,verifier,shell,process_launcher}.cc \
    -o "$FS"
"$FS" -c "printf 'ok\n'" >/dev/null
if "$FS" -c "ls /" >/dev/null 2>&1; then
  echo "foomatic_shell should have rejected 'ls'"; exit 1
fi

echo "== 4/4 build foomatic-rip from cups-filters with ChromeOS patches"
# Run a quiet build step; on failure show the end of its log instead of failing silently.
step() { local log="$1"; shift
  if ! "$@" > "$log" 2>&1; then
    echo "FAILED: $*  (last lines of $log follow)" >&2; tail -n 40 "$log" >&2; exit 1
  fi; }
# Rebuild if missing, or if it points at a foomatic_shell in another place
# (for example after the checkout was moved).
if [ -x cups-filters/foomatic-rip ] && ! grep -q "\"$FS\"" cups-filters/filter/foomatic-rip/foomaticrip.c; then
  sed -i "s|char modern_shell\[\] = \"[^\"]*\";|char modern_shell[] = \"$FS\";|" \
      cups-filters/filter/foomatic-rip/foomaticrip.c
  step cups-filters/make.log make -C cups-filters -s foomatic-rip
fi
if [ ! -x cups-filters/foomatic-rip ]; then
  rm -rf cups-filters cf.tar.xz
  for u in "${CF_URLS[@]}"; do
    if curl -fsSL -m 120 -o cf.tar.xz "$u"; then break; fi
  done
  mkdir cups-filters && tar xJf cf.tar.xz -C cups-filters --strip-components=1
  cd cups-filters
  P="$B/overlay/net-print/cups-filters/files"
  for p in cups-filters-1.21.6-foomatic-shell.patch cups-filters-1.28.5-remove-bbox-gs-device.patch; do
    patch -p1 --forward -s < "$P/$p" || true
  done
  # Point foomatic-rip at our foomatic_shell build instead of /usr/bin.
  sed -i "s|char modern_shell\[\] = \"/usr/bin/foomatic_shell\";|char modern_shell[] = \"$FS\";|" \
      filter/foomatic-rip/foomaticrip.c
  grep -q "$FS" filter/foomatic-rip/foomaticrip.c
  step configure.log ./configure -q --disable-avahi --disable-ldap --disable-mutool --disable-ghostscript \
      --disable-poppler --disable-pdftoraster --disable-imagefilters --disable-driverless \
      --disable-braille --disable-dbus --with-pdftops=gs --without-php --disable-exif \
      --with-rcdir=no
  step make.log make -s -j"$(nproc)" foomatic-rip
  cd "$B"
fi
echo
echo "Built:"
echo "  $FS"
echo "  $B/cups-filters/foomatic-rip"
