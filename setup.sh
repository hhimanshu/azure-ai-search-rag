#!/usr/bin/env bash
# Creates .venv in the repo root and installs the pinned packages, so the
# notebooks run as soon as you pick .venv as the interpreter in VS Code.
# Safe to run again: it reuses an existing .venv.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

PY=""
for candidate in python3.12 python3.13 python3.11 python3.10 python3; do
  if command -v "$candidate" >/dev/null 2>&1 \
     && "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)'; then
    PY="$candidate"
    break
  fi
done
if [[ -z "$PY" ]]; then
  echo "Python 3.10 or later is required. Install it, then run ./setup.sh again." >&2
  exit 1
fi

if [[ -d .venv ]]; then
  echo "Reusing the existing .venv"
else
  echo "Creating .venv with $("$PY" --version)"
  "$PY" -m venv .venv
fi

VENV_PY=".venv/bin/python"
[[ -x "$VENV_PY" ]] || VENV_PY=".venv/Scripts/python.exe"

"$VENV_PY" -m pip install --quiet --upgrade pip
"$VENV_PY" -m pip install --quiet -r requirements.txt
"$VENV_PY" -c "import azure.identity, azure.search.documents, azure.storage.blob, openai, dotenv, ipykernel; print('Packages OK')"

echo
echo "Done. In VS Code, open this folder, open a notebook, and pick the .venv interpreter."
