#!/usr/bin/env bash
# Stable path for the lock script; the real one ships inside the mb package.
exec bash "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/../mb/src/mb/lock.sh" "$@"
