#!/usr/bin/env bash
#
# Baut den Changelog-Abschnitt EINER Version fuer die Release-Beschreibung.
#
# Quelle sind 'Changelog:'-Zeilen in den Commits seit dem vorherigen Versions-Tag.
# Aufbau einer solchen Zeile (im Commit ganz unten, mehrere sind erlaubt):
#
#     Changelog: <Art> | <Bereich> | <Satz fuer Anwender>
#
#   <Art>     Verbesserung | Fehler | Loeschung      (auch mit Umlaut/Plural)
#   <Bereich> frei, z. B. Allgemein, Steuerung, Automatik, Geraet, Gateway
#   <Satz>    ein ganzer Satz in Anwendersprache, nicht der Commit-Betreff
#
# Warum ueberhaupt so? Commit-Betreffe beschreiben die AENDERUNG AM CODE
# ("Termin-Titel exakt vergleichen statt Veranstaltungsart"). Eine Release-Notiz
# muss beschreiben, was sich fuer die Gemeinde aendert. Das laesst sich nicht
# automatisch uebersetzen, also wird es beim Commit mitgeschrieben.
#
# Commits ohne solche Zeile tauchen im Changelog nicht auf - das ist Absicht:
# CI-Anpassungen, Refactorings und Tippfehler interessieren Anwender nicht.
#
# Aufruf:  changelog.sh <tag> [<vorheriger-tag>]
#          Ohne zweiten Parameter wird der vorherige Versions-Tag selbst gesucht.
set -euo pipefail

TAG="${1:?Aufruf: changelog.sh <tag> [<vorheriger-tag>]}"
PREV="${2:-}"

if [ -z "${PREV}" ]; then
  # Vorherigen Versions-Tag suchen: versionssortiert, damit v26.10.0 nach
  # v26.9.9 kommt (alphabetisch waere es umgekehrt).
  PREV="$(git tag -l 'v*' --sort=-v:refname \
    | grep -E '^v[0-9]+\.[0-9]+\.[0-9]+$' \
    | grep -A1 -x -F "${TAG}" | tail -n +2 | head -1 || true)"
fi

if [ -n "${PREV}" ]; then RANGE="${PREV}..${TAG}"; else RANGE="${TAG}"; fi

# Alle Changelog-Zeilen des Bereichs einsammeln. Doppelte entfernen: Ein Commit
# kann ueber einen Merge zweimal in der Liste auftauchen.
ENTRIES="$(git log --no-merges --format='%B' "${RANGE}" 2>/dev/null \
  | grep -E '^[[:space:]]*Changelog:' \
  | sed -E 's/^[[:space:]]*Changelog:[[:space:]]*//' \
  | sort -u || true)"

if [ -z "${ENTRIES}" ]; then
  echo "_Nur interne Anpassungen - fuer Anwender aendert sich nichts._"
  exit 0
fi

# Nach Art gruppieren, in fester Reihenfolge. Innerhalb einer Art nach Bereich,
# wobei "Allgemein" immer zuerst steht (der Rest alphabetisch).
emit_group() {
  local want="$1" ueberschrift="$2" gefunden=0

  local bereiche
  bereiche="$(printf '%s\n' "${ENTRIES}" \
    | awk -F'|' -v w="${want}" '
        { art=$1; gsub(/^[ \t]+|[ \t]+$/, "", art); if (tolower(art) ~ w) {
            b=$2; gsub(/^[ \t]+|[ \t]+$/, "", b); print b } }' \
    | sort -u \
    | awk '{ if (tolower($0)=="allgemein") first=$0; else rest=rest $0 "\n" }
           END { if (first) print first; printf "%s", rest }')"

  [ -n "${bereiche}" ] || return 0

  printf '### %s\n\n' "${ueberschrift}"
  while IFS= read -r bereich; do
    [ -n "${bereich}" ] || continue
    printf '* **%s**\n' "${bereich}"
    printf '%s\n' "${ENTRIES}" \
      | awk -F'|' -v w="${want}" -v b="${bereich}" '
          { art=$1; ber=$2;
            gsub(/^[ \t]+|[ \t]+$/, "", art); gsub(/^[ \t]+|[ \t]+$/, "", ber);
            if (tolower(art) ~ w && ber == b) {
              # Alles ab dem dritten Feld ist der Text (er darf "|" enthalten).
              text=$3; for (i=4; i<=NF; i++) text = text "|" $i;
              gsub(/^[ \t]+|[ \t]+$/, "", text);
              print "   * " text
            } }'
    gefunden=1
  done <<< "${bereiche}"
  printf '\n'
  return 0
}

# Reihenfolge wie in den ChurchTools-Release-Notes.
emit_group 'l(o|ö)*e*schung' 'Löschungen'
emit_group 'verbesserung|neu|funktion' 'Verbesserungen'
emit_group 'fehler|bugfix|behoben' 'Behobene Fehler'
