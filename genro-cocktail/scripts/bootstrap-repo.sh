#!/usr/bin/env bash
# M0 bootstrap — lift genro-cocktail/ out of genro-asgi into its own repository,
# PRESERVING the kit's commit history (git subtree split).
#
# Prerequisites: git, gh (GitHub CLI) authenticated with rights on the target org.
# Run from the ROOT of a genro-asgi clone, on the kit branch:
#
#   git clone -b claude/genro-cocktail-roadmap-ldcwgz https://github.com/genropy/genro-asgi
#   cd genro-asgi
#   ./genro-cocktail/scripts/bootstrap-repo.sh            # -> genropy/genro-cocktail
#   ./genro-cocktail/scripts/bootstrap-repo.sh me/my-fork # any owner/name works
set -euo pipefail

REPO="${1:-genropy/genro-cocktail}"
DESCRIPTION="A playful cocktail lab on the new Genropy stack — the classics teach, sliders remix, the ledger remembers. Game, showcase, laboratory."

if [ ! -d genro-cocktail ]; then
    echo "error: run from the root of the genro-asgi clone (genro-cocktail/ not found)" >&2
    exit 1
fi

echo "→ splitting genro-cocktail/ history out of $(git rev-parse --abbrev-ref HEAD)…"
SPLIT_SHA=$(git subtree split -P genro-cocktail HEAD)
echo "  split commit: $SPLIT_SHA"

if gh repo view "$REPO" >/dev/null 2>&1; then
    echo "→ repository $REPO already exists, pushing into it"
else
    echo "→ creating $REPO (private — flip visibility when you like)"
    gh repo create "$REPO" --private --description "$DESCRIPTION"
fi

echo "→ pushing the kit as main…"
git push "https://github.com/$REPO.git" "$SPLIT_SHA:refs/heads/main"

echo
echo "Done: https://github.com/$REPO"
echo "Next:  git clone https://github.com/$REPO && cd ${REPO#*/}"
echo "       read HANDOFF.md — then let the workflow run W1…W6."
