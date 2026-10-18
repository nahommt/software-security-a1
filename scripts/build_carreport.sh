#!/bin/sh
set -eu

root="$(cd "$(dirname "$0")/.." && pwd)"
out="$root/report-service/wheels"

rm -rf "$out"
mkdir -p "$out"

docker run --rm \
  -v "$root/packages/carreport:/src:ro" \
  -v "$out:/out" \
  python:3.12-slim \
  sh -c "cp -r /src /tmp/carreport && pip wheel --no-deps --wheel-dir /out /tmp/carreport"

ls "$out"
