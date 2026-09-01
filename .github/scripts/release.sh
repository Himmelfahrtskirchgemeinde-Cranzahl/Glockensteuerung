#!/usr/bin/env bash
#
# Erstellt das Release EINER Version.
#
# Frueher sammelte ein Release je Versionsgruppe ("Release 26.5") alle Patches
# 26.5.0 ... 26.5.9: Das bestehende Release wurde auf den neuen Tag umgehaengt
# und bekam die neue ZIP dazu. Das geht nicht mehr - im Repository sind
# UNVERAENDERLICHE Releases aktiv. Ein veroeffentlichtes Release laesst danach
# weder seinen Tag wechseln noch Dateien nachtragen:
#
#     HTTP 422: tag_name cannot be changed when release is immutable
#
# Also bekommt jede Version ihr eigenes Release. Das ist ohnehin die Form, auf
# die GitHub mit dieser Einstellung hinauswill.
#
# Jedes Release traegt ZWEI Dateien:
#   glockensteuerung-v<version>.zip   das Archiv dieser Version
#   glockensteuerung.zip              derselbe Inhalt unter festem Namen
#
# Der feste Name macht den Dauerlink moeglich, ohne je ein Release nachtraeglich
# anfassen zu muessen: GitHub liefert unter
#   /releases/latest/download/glockensteuerung.zip
# stets die Datei des neuesten Releases. Ein eigenes, rollierendes
# "latest"-Release braucht es dafuer nicht mehr.
#
# Aufruf:  release.sh <tag> <zip> [<zip> ...]
set -euo pipefail

HIER="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

TAG="$1"; shift
ZIPS=("$@")

TITLE="Version ${TAG#v}"

NOTES_FILE="$(mktemp)"
ARBEIT="$(mktemp -d)"
trap 'rm -rf "${NOTES_FILE}" "${ARBEIT}"' EXIT

{
  printf 'Automatisch gebaute ChurchTools-Extension. Die ZIP unten herunterladen und\n'
  printf '**unveraendert** in ChurchTools hochladen (kein Entpacken noetig).\n\n'
  bash "${HIER}/changelog.sh" "${TAG}"
} > "${NOTES_FILE}"

# Feste Kopie daneben legen. Ohne sie gaebe es keinen Link zum Weitergeben - der
# Name der versionierten ZIP wechselt ja mit jeder Version.
DATEIEN=("${ZIPS[@]}")
if [ "${#ZIPS[@]}" -gt 0 ] && [ -f "${ZIPS[0]}" ]; then
  cp "${ZIPS[0]}" "${ARBEIT}/glockensteuerung.zip"
  DATEIEN+=("${ARBEIT}/glockensteuerung.zip")
fi

# Ein bestehendes Release ist unveraenderlich - bei einem erneuten Lauf desselben
# Tags bleibt es unangetastet, statt mit einem Fehler abzubrechen.
if gh release view "${TAG}" >/dev/null 2>&1; then
  echo "Release ${TAG} besteht bereits - nichts zu tun."
  exit 0
fi

echo "Release '${TITLE}' anlegen (Tag ${TAG})."
gh release create "${TAG}" "${DATEIEN[@]}" --title "${TITLE}" --notes-file "${NOTES_FILE}"
