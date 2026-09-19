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
# Jedes Release traegt dieselben Dateien unter festem Namen:
#   glockensteuerung.zip            die Erweiterung fuer ChurchTools
#   Glockensteuerung-Gateway.exe    der Dienst fuer Windows, fertig gebaut
#   glockensteuerung-gateway.zip    derselbe Dienst als Quelltext
#
# Ohne Versionsnummer im Dateinamen: Das Release heisst "Version 26.6.7", damit
# ist die Zuordnung eindeutig. Zwei Dateien mit demselben Inhalt und nur anderem
# Namen danebenzulegen, brachte niemandem etwas. Die gebauten Archive tragen die
# Nummer weiterhin - dort, als Bauergebnis, ist sie nuetzlich.
#
# Der feste Name macht den Dauerlink moeglich, ohne je ein Release nachtraeglich
# anfassen zu muessen: GitHub liefert unter
#   /releases/latest/download/glockensteuerung.zip
# stets die Datei des neuesten Releases. Ein eigenes, rollierendes
# "latest"-Release braucht es dafuer nicht mehr.
#
# Ausgeschrieben stehen diese Links im README, nicht mehr in jeder
# Release-Beschreibung: Dort wiederholten sie bei jeder Version dasselbe und
# schoben den Changelog - das Einzige, was sich aendert - nach unten aus dem
# Blick.
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
  printf 'Automatisch gebauter Stand. Unten liegen drei Dateien:\n\n'
  printf '* **glockensteuerung.zip** - die Erweiterung. Unveraendert in ChurchTools\n'
  printf '  hochladen, kein Entpacken noetig.\n'
  printf '* **Glockensteuerung-Gateway.exe** - der Dienst fuer Windows, fertig\n'
  printf '  gebaut. Neben die vorhandene .env legen, Doppelklick, "1" waehlen -\n'
  printf '  danach laeuft er als Windows-Dienst, auch ohne Anmeldung.\n'
  printf '* **glockensteuerung-gateway.zip** - derselbe Dienst als Quelltext,\n'
  printf '  fuer Linux oder eigenen Python-Betrieb (siehe README darin).\n\n'
  # Ab hier beginnt der Changelog. Die Extension zeigt beim Klick auf die
  # Versionsnummer nur den Teil hinter dieser Marke - Einleitung und Dauerlink
  # gehoeren nicht in das Fenster "Was ist neu".
  printf '<!-- changelog -->\n\n'
  bash "${HIER}/changelog.sh" "${TAG}"
} > "${NOTES_FILE}"

# Die Versionsnummer aus dem Dateinamen nehmen: Nur unter festem Namen bleibt der
# Dauerlink gueltig, und welche Version darin steckt, sagt der Titel des Release.
# Aus 'glockensteuerung-gateway-v26.6.7.zip' wird 'glockensteuerung-gateway.zip'.
DATEIEN=()
for z in "${ZIPS[@]}"; do
  [ -f "${z}" ] || continue
  basis="$(basename "${z}")"
  fest="$(printf '%s' "${basis}" | sed -E 's/-v[0-9]+\.[0-9]+\.[0-9]+(-[0-9]+-g[0-9a-f]+)?\.zip$/.zip/')"
  if [ "${fest}" = "${basis}" ]; then
    DATEIEN+=("${z}")          # traegt schon einen festen Namen
  else
    cp "${z}" "${ARBEIT}/${fest}"
    DATEIEN+=("${ARBEIT}/${fest}")
  fi
done

# Ein bestehendes Release ist unveraenderlich - bei einem erneuten Lauf desselben
# Tags bleibt es unangetastet, statt mit einem Fehler abzubrechen.
if gh release view "${TAG}" >/dev/null 2>&1; then
  echo "Release ${TAG} besteht bereits - nichts zu tun."
  exit 0
fi

echo "Release '${TITLE}' anlegen (Tag ${TAG})."
gh release create "${TAG}" "${DATEIEN[@]}" --title "${TITLE}" --notes-file "${NOTES_FILE}"
