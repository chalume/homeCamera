#!/usr/bin/env bash
set -euo pipefail

DIR="${1:-captures}"

if [[ ! -d "$DIR" ]]; then
  echo "No capture directory yet: $DIR"
  exit 0
fi

find "$DIR" -maxdepth 1 -type f \( -name '*.jpg' -o -name '*.jpeg' \) -print \
  | sort -r \
  | head -20
