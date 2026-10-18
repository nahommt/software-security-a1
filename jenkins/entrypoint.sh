#!/bin/bash
set -euo pipefail

SOCK=/var/run/docker.sock

if [ -S "$SOCK" ]; then
    sock_gid="$(stat -c '%g' "$SOCK")"
    if [ "$sock_gid" = "0" ]; then
        usermod -aG root jenkins
    else
        if ! getent group dockerhost >/dev/null 2>&1; then
            groupadd -g "$sock_gid" dockerhost
        fi
        usermod -aG dockerhost jenkins
    fi
fi

exec runuser -u jenkins -- /usr/local/bin/jenkins.sh "$@"
