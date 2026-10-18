#!/bin/sh
set -eu

if [ "$#" -ne 1 ]; then
  echo "usage: $0 <service-dir>" >&2
  exit 1
fi

root="$(cd "$(dirname "$0")/.." && pwd)"
service="$root/$1"

docker run --rm \
  -v "$service:/work" \
  -w /work \
  python:3.12-slim \
  sh -c '
    pip install --quiet --disable-pip-version-check pip-tools==7.4.1 &&
    pip-compile --quiet --generate-hashes --strip-extras --allow-unsafe --no-header \
      --output-file requirements.txt requirements.in &&
    if [ -f requirements-dev.in ]; then
      pip-compile --quiet --generate-hashes --strip-extras --allow-unsafe --no-header \
        --output-file requirements-dev.txt requirements-dev.in
    fi
  '
