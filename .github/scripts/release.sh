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

# Der Dauerlink wird in jeder Beschreibung genannt. Auf die Reihenfolge kommt es
# an: '/releases/latest/download/<datei>' liefert die Datei des NEUESTEN Release,
# '/releases/download/latest/<datei>' dagegen die eines Release mit dem Tag
# "latest" - also eine feste, alte Datei. Die beiden Formen sehen fast gleich
# aus; steht der richtige in jeder Beschreibung, wird der falsche nicht
# weitergegeben.
REPO="${GITHUB_REPOSITORY:-}"
if [ -z "${REPO}" ]; then
  REPO="$(git remote get-url origin 2>/dev/null \
    | sed -E 's#^.*github\.com[:/]##; s#\.git$##')"
fi

{
  printf 'Automatisch gebaute ChurchTools-Extension. Die ZIP unten herunterladen und\n'
  printf '**unveraendert** in ChurchTools hochladen (kein Entpacken noetig).\n\n'
  if [ -n "${REPO}" ]; then
    printf 'Dauerlink zur jeweils neuesten Fassung (bleibt immer gleich):\n'
    printf 'https://github.com/%s/releases/latest/download/glockensteuerung.zip\n\n' "${REPO}"
  fi
  # Ab hier beginnt der Changelog. Die Extension zeigt beim Klick auf die
  # Versionsnummer nur den Teil hinter dieser Marke - Einleitung und Dauerlink
  # gehoeren nicht in das Fenster "Was ist neu".
  printf '<!-- changelog -->\n\n'
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
