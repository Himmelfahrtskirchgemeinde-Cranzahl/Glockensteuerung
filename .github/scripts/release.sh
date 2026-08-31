#!/usr/bin/env bash
#
# Erstellt bzw. aktualisiert das Release einer VERSIONSGRUPPE.
#
# Statt fuer jede Patch-Version ein eigenes Release ("Glockensteuerung v26.4.11")
# gibt es EIN Release je Gruppe <Jahr>.<Mittelstelle>, z. B. "Release 26.4".
# Dort sammeln sich alle Patches 26.4.0 ... 26.4.9. Sobald der Auto-Tag auf
# 26.5.0 springt, entsteht automatisch das naechste Release "Release 26.5".
#
# Aufruf:  release.sh <tag> <zip> [<zip> ...]
set -euo pipefail

TAG="$1"; shift
ZIPS=("$@")

VER="${TAG#v}"
MA="${VER%%.*}"; REST="${VER#*.}"; MI="${REST%%.*}"
GROUP="${MA}.${MI}"
TITLE="Release ${GROUP}"
ENTRY="- \`${TAG}\` – $(date -u +%Y-%m-%d)"

# Bestehendes Release dieser Gruppe ueber den Titel finden.
EXIST_TAG="$(gh release list --limit 200 --json name,tagName \
  --jq ".[] | select(.name == \"${TITLE}\") | .tagName" 2>/dev/null | head -1 || true)"

if [ -n "${EXIST_TAG}" ]; then
  echo "Release '${TITLE}' vorhanden (Tag ${EXIST_TAG}) -> auf ${TAG} umhaengen."
  OLD_BODY="$(gh release view "${EXIST_TAG}" --json body --jq .body 2>/dev/null || true)"
  # Version nur einmal eintragen (Workflow koennte erneut laufen).
  if printf '%s' "${OLD_BODY}" | grep -qF -- "\`${TAG}\`"; then
    NEW_BODY="${OLD_BODY}"
  else
    NEW_BODY="${OLD_BODY}"$'\n'"${ENTRY}"
  fi
  gh release edit "${EXIST_TAG}" --tag "${TAG}" --title "${TITLE}" --notes "${NEW_BODY}"
  gh release upload "${TAG}" "${ZIPS[@]}" --clobber
else
  echo "Neues Gruppen-Release '${TITLE}' anlegen (Tag ${TAG})."
  gh release create "${TAG}" "${ZIPS[@]}" --title "${TITLE}" --notes "Automatisch gebaute ChurchTools-Extension. Die ZIP unten herunterladen und **unveraendert** in ChurchTools hochladen (kein Entpacken noetig).

## Enthaltene Versionen
${ENTRY}"
fi
