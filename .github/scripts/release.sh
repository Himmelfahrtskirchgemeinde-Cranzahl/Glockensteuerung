#!/usr/bin/env bash
#
# Erstellt bzw. aktualisiert das Release einer VERSIONSGRUPPE.
#
# Statt fuer jede Patch-Version ein eigenes Release ("Glockensteuerung v26.4.11")
# gibt es EIN Release je Gruppe <Jahr>.<Mittelstelle>, z. B. "Release 26.4".
# Dort sammeln sich alle Patches 26.4.0 ... 26.4.9. Sobald der Auto-Tag auf
# 26.5.0 springt, entsteht automatisch das naechste Release "Release 26.5".
#
# In der Beschreibung steht je Version ein Changelog-Abschnitt, gebaut aus den
# 'Changelog:'-Zeilen der Commits (siehe changelog.sh). Neueste Version oben.
#
# Aufruf:  release.sh <tag> <zip> [<zip> ...]
set -euo pipefail

HIER="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

TAG="$1"; shift
ZIPS=("$@")

VER="${TAG#v}"
MA="${VER%%.*}"; REST="${VER#*.}"; MI="${REST%%.*}"
GROUP="${MA}.${MI}"
TITLE="Release ${GROUP}"

INTRO="Automatisch gebaute ChurchTools-Extension. Die ZIP unten herunterladen und **unveraendert** in ChurchTools hochladen (kein Entpacken noetig)."
# Trennt die feste Einleitung von den Versionsabschnitten. Nur so laesst sich
# ein neuer Abschnitt OBEN einfuegen, ohne die bisherigen zu verlieren.
MARKER="<!-- changelog -->"

ABSCHNITT="$(printf '## %s\n\n%s' \
  "${TAG}" \
  "$(bash "${HIER}/changelog.sh" "${TAG}")")"

# Bestehendes Release dieser Gruppe ueber den Titel finden.
EXIST_TAG="$(gh release list --limit 200 --json name,tagName \
  --jq ".[] | select(.name == \"${TITLE}\") | .tagName" 2>/dev/null | head -1 || true)"

NOTES_FILE="$(mktemp)"
trap 'rm -f "${NOTES_FILE}"' EXIT

if [ -n "${EXIST_TAG}" ]; then
  echo "Release '${TITLE}' vorhanden (Tag ${EXIST_TAG}) -> auf ${TAG} umhaengen."
  OLD_BODY="$(gh release view "${EXIST_TAG}" --json body --jq .body 2>/dev/null || true)"

  if printf '%s\n' "${OLD_BODY}" | grep -qxF -- "## ${TAG}"; then
    # Version schon eingetragen (Workflow lief erneut) - Text unveraendert lassen.
    echo "Version ${TAG} steht bereits in der Beschreibung."
    printf '%s' "${OLD_BODY}" > "${NOTES_FILE}"
  else
    # Alles NACH dem Marker sind die bisherigen Versionsabschnitte. Fehlt der
    # Marker (Release aus der Zeit vor dem Changelog), wird der alte Text
    # vollstaendig uebernommen, damit nichts verloren geht.
    if printf '%s' "${OLD_BODY}" | grep -qF -- "${MARKER}"; then
      BISHER="$(printf '%s\n' "${OLD_BODY}" | awk -v m="${MARKER}" 'f{print} $0==m{f=1}' | sed '/./,$!d')"
    else
      # Die Einleitung wird oben neu gesetzt - aus dem uebernommenen Teil also
      # entfernen, sonst stuende sie zweimal im Text. Fuehrende Leerzeilen weg.
      BISHER="$(printf '%s\n' "${OLD_BODY}" | grep -vxF -- "${INTRO}" | sed '/./,$!d')"
    fi
    printf '%s\n\n%s\n\n%s\n\n%s\n' "${INTRO}" "${MARKER}" "${ABSCHNITT}" "${BISHER}" > "${NOTES_FILE}"
  fi

  gh release edit "${EXIST_TAG}" --tag "${TAG}" --title "${TITLE}" --notes-file "${NOTES_FILE}"
  gh release upload "${TAG}" "${ZIPS[@]}" --clobber
else
  echo "Neues Gruppen-Release '${TITLE}' anlegen (Tag ${TAG})."
  printf '%s\n\n%s\n\n%s\n' "${INTRO}" "${MARKER}" "${ABSCHNITT}" > "${NOTES_FILE}"
  gh release create "${TAG}" "${ZIPS[@]}" --title "${TITLE}" --notes-file "${NOTES_FILE}"
fi
