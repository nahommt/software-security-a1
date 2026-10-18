#!/bin/sh
set -eu

root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$root"

if [ ! -f secrets/seed_users.json ] || [ ! -f secrets/jwt_private.pem ]; then
  ./scripts/generate_secrets.sh
fi

docker compose --profile seed build auth-seed car-seed
docker compose --profile seed run --rm auth-seed
docker compose --profile seed run --rm car-seed
