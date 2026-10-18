#!/bin/sh
set -eu

root="$(cd "$(dirname "$0")/.." && pwd)"
dir="$root/secrets"

mkdir -p "$dir"
chmod 700 "$dir"

if [ ! -f "$dir/jwt_private.pem" ]; then
  openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:3072 -out "$dir/jwt_private.pem"
  openssl pkey -in "$dir/jwt_private.pem" -pubout -out "$dir/jwt_public.pem"
fi

if [ ! -f "$dir/seed_users.json" ]; then
  alice="$(openssl rand -base64 18)"
  bob="$(openssl rand -base64 18)"
  dealer="$(openssl rand -base64 18)"
  printf '{"alice": "%s", "bob": "%s", "dealer": "%s"}\n' "$alice" "$bob" "$dealer" > "$dir/seed_users.json"
fi

chmod 644 "$dir/jwt_private.pem" "$dir/jwt_public.pem" "$dir/seed_users.json"
ls "$dir"
