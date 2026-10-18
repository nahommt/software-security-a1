#!/bin/sh
set -eu

root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$root"

if [ ! -f report-service/wheels/carreport-0.1.0-py3-none-any.whl ]; then
  ./scripts/build_carreport.sh
fi

docker compose --profile test build auth-gateway-test car-service-test report-service-test

status=0
for service in auth-gateway-test car-service-test report-service-test; do
  echo "=== $service ==="
  if ! docker compose --profile test run --rm "$service"; then
    status=1
  fi
done

exit "$status"
