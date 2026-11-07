#!/bin/sh
# Download the latest resident APK built by GitHub Actions into ./downloads/ (served at /downloads/).
# Uses GITHUB_TOKEN if set, otherwise the token stored for git (needed while the repo is private).
set -eu
cd "$(dirname "$0")/.."
REPO=ryantaufiks/Elix-PMS
TOKEN=${GITHUB_TOKEN:-$(printf 'protocol=https\nhost=github.com\n\n' | git credential fill 2>/dev/null | sed -n 's/^password=//p')}
AUTH=${TOKEN:+-H "Authorization: Bearer $TOKEN"}

URL=$(eval curl -fsSL $AUTH -H "Accept: application/vnd.github+json" \
  "https://api.github.com/repos/$REPO/releases/tags/resident-latest" |
  python3 -c "import sys, json; print(next(a['url'] for a in json.load(sys.stdin)['assets'] if a['name'] == 'elix-resident.apk'))")

mkdir -p downloads
eval curl -fsSL $AUTH -H "Accept: application/octet-stream" -o downloads/elix-resident.apk.part "$URL"
mv downloads/elix-resident.apk.part downloads/elix-resident.apk
ls -l downloads/elix-resident.apk
