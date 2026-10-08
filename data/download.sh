#!/usr/bin/env bash
# Re-fetch the demo corpus: official US state driver's manuals (public domain).
# Verified working 2026-08-28. State agencies move URLs; if one 404s, search
# "<state> driver manual pdf" on the agency site and update the line.
set -e
cd "$(dirname "$0")"
UA="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
get(){ if [ -s "$1" ]; then echo "have $1"; else echo "-> $1"; curl -fsSL -A "$UA" -o "$1" "$2"; fi; }
get california-driver-handbook.pdf   "https://www.dmv.ca.gov/portal/file/california-driver-handbook-pdf/"
get florida-driver-handbook.pdf      "https://www.flhsmv.gov/pdf/handbooks/englishdriverhandbook.pdf"
get newjersey-driver-manual.pdf      "https://www.nj.gov/mvc/pdf/license/drivermanual.pdf"
get virginia-drivers-manual.pdf      "https://www.dmv.virginia.gov/sites/default/files/forms/dmv39.pdf"
get wisconsin-motorists-handbook.pdf "https://wisconsindot.gov/Documents/dmv/shared/bds126-motorists-handbook.pdf"
echo "done"
