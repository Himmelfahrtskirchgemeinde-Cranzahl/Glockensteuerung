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
#
# Ein eigenes Quelltext-Archiv des Gateways gibt es nicht mehr: GitHub haengt
# an jedes Release ohnehin "Source code" an, und darin steckt der Ordner
# gateway/ vollstaendig. Zwei Wege zum selben Quelltext verwirren nur.
#
# In der BESCHREIBUNG steht nur der Changelog - und, falls eine Datei dazukommt
# oder wegfaellt, dieser eine Unterschied. Was welche Datei tut, steht im README
# und aendert sich nicht von Version zu Version; in einer Release-Beschreibung
# verstellte es nur den Blick auf das, was neu ist.
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



# Die Versionsnummer aus dem Dateinamen nehmen: Nur unter festem Namen bleibt der
# Dauerlink gueltig, und welche Version darin steckt, sagt der Titel des Release.
# Aus 'glockensteuerung-v26.6.7.zip' wird 'glockensteuerung.zip'.
DATEIEN=()
for z in "${ZIPS[@]}"; do
  [ -f "${z}" ] || continue
  basis="$(basename "${z}")"
  # Die vierte Stelle (Hotfix) MUSS im Muster stehen: Ohne sie griff die
  # Umbenennung bei 'glockensteuerung-v26.9.4.1.zip' nicht, die Datei behielt
  # ihren versionierten Namen - und der Dauerlink
  # /releases/latest/download/glockensteuerung.zip lief ins Leere. Genau so ist
  # es im Release 26.9.4.1 passiert.
  fest="$(printf '%s' "${basis}" | sed -E 's/-v[0-9]+\.[0-9]+\.[0-9]+(\.[0-9]+)?(-[0-9]+-g[0-9a-f]+)?\.zip$/.zip/')"
  if [ "${fest}" = "${basis}" ]; then
    DATEIEN+=("${z}")          # traegt schon einen festen Namen
  else
    cp "${z}" "${ARBEIT}/${fest}"
    DATEIEN+=("${ARBEIT}/${fest}")
  fi
done

# Welche Dateien trug das vorherige Release? Kommt eine dazu oder faellt eine
# weg, ist das eine Aenderung wie jede andere - und die einzige Angabe zu den
# Dateien, die in einer Release-Beschreibung etwas zu suchen hat. Die immer
# gleiche Aufzaehlung, was welche Datei tut, stand frueher hier und half
# niemandem: Wer aktualisiert, will wissen, was sich geaendert hat.
vorheriger_tag() {
  git tag -l 'v*' --sort=-v:refname \
    | grep -E '^v[0-9]+\.[0-9]+\.[0-9]+(\.[0-9]+)?$' \
    | grep -A1 -x -F "$1" | tail -n +2 | head -1 || true
}

# WICHTIG: Erst hier, nach der Schleife oben. Stand das frueher davor, war
# DATEIEN noch leer - und jede Datei des vorherigen Release galt als entfallen.
# Im Release 26.8.7 stand deshalb "Entfaellt: Glockensteuerung-Gateway.exe",
# waehrend die Datei unveraendert darunter lag.
JETZT_NAMEN="$(for d in "${DATEIEN[@]}"; do basename "${d}"; done | sort -u)"
VORHER="$(vorheriger_tag "${TAG}")"
VORHER_NAMEN=""
if [ -n "${VORHER}" ]; then
  VORHER_NAMEN="$(gh release view "${VORHER}" --json assets \
    --jq '.assets[].name' 2>/dev/null | sort -u || true)"
fi

DAZU=""
WEG=""
if [ -n "${VORHER_NAMEN}" ]; then
  DAZU="$(comm -23 <(printf '%s\n' "${JETZT_NAMEN}") <(printf '%s\n' "${VORHER_NAMEN}") || true)"
  WEG="$(comm -13 <(printf '%s\n' "${JETZT_NAMEN}") <(printf '%s\n' "${VORHER_NAMEN}") || true)"
fi

{
  # Nur der Changelog. Er ist das, worum es in einem Release geht.
  bash "${HIER}/changelog.sh" "${TAG}"
  if [ -n "${DAZU}" ] || [ -n "${WEG}" ]; then
    # Auf der obersten Ebene, neben "Erweiterung" und "Gateway": Eine neue
    # Datei betrifft den Download, nicht die Oberflaeche - im Fenster "Was ist
    # neu" der Erweiterung hat sie deshalb nichts zu suchen. Stuende sie eine
    # Ebene tiefer, erschiene sie dort als Versionsnummer.
    printf '\n## Dateien\n\n'
    while IFS= read -r name; do
      [ -n "${name}" ] || continue
      printf '* **Neu:** `%s`\n' "${name}"
    done <<< "${DAZU}"
    while IFS= read -r name; do
      [ -n "${name}" ] || continue
      printf '* **Entfällt:** `%s`\n' "${name}"
    done <<< "${WEG}"
  fi
  # Hier endet der Changelog. Die Extension zeigt beim Klick auf die
  # Versionsnummer den Teil VOR dieser Marke. Sie bleibt stehen, auch wenn
  # danach nichts mehr folgt: Ohne sie muesste die Extension raten, wo der
  # Changelog anfaengt - und schnitte die einleitende Zeile einer
  # Korrektur-Version mit ab.
  printf '\n<!-- changelog-ende -->\n'
} > "${NOTES_FILE}"

# Ein bestehendes Release ist unveraenderlich - bei einem erneuten Lauf desselben
# Tags bleibt es unangetastet, statt mit einem Fehler abzubrechen.
if gh release view "${TAG}" >/dev/null 2>&1; then
  echo "Release ${TAG} besteht bereits - nichts zu tun."
  exit 0
fi

echo "Release '${TITLE}' anlegen (Tag ${TAG})."
gh release create "${TAG}" "${DATEIEN[@]}" --title "${TITLE}" --notes-file "${NOTES_FILE}"
