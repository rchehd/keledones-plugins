#!/usr/bin/env bash
set -euo pipefail

export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
export DEBIAN_FRONTEND=noninteractive
grep -qi 'microsoft-standard-WSL2' /proc/sys/kernel/osrelease
uname -r

report_dir=$1
work_dir=$(mktemp -d)
mkdir "$work_dir/source" "$work_dir/reports" "$work_dir/browser"
trap 'cp -R "$work_dir/reports/." "$report_dir/"' EXIT

apt-get update -qq
apt-get install -y --no-install-recommends ca-certificates composer curl git php-cli php-curl php-mbstring php-xml php-zip python3 python3-venv unzip xz-utils

node_url=https://nodejs.org/dist/latest-v22.x
curl --retry 3 -fsSL "$node_url/SHASUMS256.txt" -o "$work_dir/SHASUMS256.txt"
read -r checksum archive < <(awk '$2 ~ /^node-v22\.[0-9]+\.[0-9]+-linux-x64\.tar\.xz$/ {print $1, $2}' "$work_dir/SHASUMS256.txt")
curl --retry 3 -fsSL "$node_url/$archive" -o "$work_dir/$archive"
(
  cd "$work_dir"
  printf '%s  %s\n' "$checksum" "$archive" | sha256sum -c
  tar -xJf "$archive" -C /usr/local --strip-components=1
)

git -c safe.directory="$PWD" archive HEAD | tar -x -C "$work_dir/source"
cd "$work_dir/source/plugins/ready-check"
cp dependencies/browser/package{,-lock}.json "$work_dir/browser/"
npm ci --ignore-scripts --prefix "$work_dir/browser"
node "$work_dir/browser/node_modules/playwright-core/cli.js" install-deps chromium

useradd --create-home --shell /bin/bash ready-check-ci
chown -R ready-check-ci:ready-check-ci "$work_dir"
runuser -u ready-check-ci -- env PATH="$PATH" PYTHONIOENCODING=utf-8 PYTHONUNBUFFERED=1 bash -e -o pipefail -c '
  python3 -B scripts/ready-check.py validate-package
  python3 -B -m unittest discover -s tests -v
  python3 -B tests/smoke_setup.py --report-dir "$1" 2>&1 | tee "$1/integration.log"
' bash "$work_dir/reports"
