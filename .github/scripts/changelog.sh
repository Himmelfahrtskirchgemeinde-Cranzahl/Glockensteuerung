#!/usr/bin/env bash
#
# Baut den Changelog-Abschnitt EINER Version fuer die Release-Beschreibung.
#
# Quelle sind 'Changelog:'-Zeilen in den Commits seit dem vorherigen Versions-Tag.
# Aufbau einer solchen Zeile (im Commit ganz unten, mehrere sind erlaubt):
#
#     Changelog: <Art> | <Bereich> | <Satz fuer Anwender>
#
#   <Art>     Verbesserung | Fehler | Löschung      (auch ohne Umlaut/im Plural)
#   <Bereich> frei, z. B. Allgemein, Steuerung, Automatik, Gerät, Gateway
#   <Satz>    ein ganzer Satz in Anwendersprache, nicht der Commit-Betreff
#
# Der Satz und der Bereich werden gelesen, nicht ausgefuehrt: Sie gehoeren in
# richtiges Deutsch, mit Umlauten und Anfuehrungszeichen. Quelltext und
# Konsolenausgaben bleiben dagegen bewusst bei ASCII - die Windows-Konsole
# verschluckt sich je nach Zeichensatz an Umlauten, eine Release-Beschreibung
# auf github.com nicht.
#
# Warum ueberhaupt so? Commit-Betreffe beschreiben die AENDERUNG AM CODE
# ("Termin-Titel exakt vergleichen statt Veranstaltungsart"). Eine Release-Notiz
# muss beschreiben, was sich fuer die Gemeinde aendert. Das laesst sich nicht
# automatisch uebersetzen, also wird es beim Commit mitgeschrieben.
#
# Commits ohne solche Zeile tauchen im Changelog nicht auf - das ist Absicht:
# CI-Anpassungen, Refactorings und Tippfehler interessieren Anwender nicht.
#
# Wird eine Aenderung noch vor der Veroeffentlichung wieder verworfen, nimmt ein
# spaeterer Commit ihre Zeile zurueck - Wort fuer Wort, nur unter anderem Namen:
#
#     Changelog-entfaellt: <Art> | <Bereich> | <derselbe Satz>
#
# Aufruf:  changelog.sh <tag> [<vorheriger-tag>]
#          Ohne zweiten Parameter wird der vorherige Versions-Tag selbst gesucht.
set -euo pipefail

# Umlaute muessen unversehrt durch grep, sed, awk und sort kommen. Ohne
# UTF-8-Locale arbeiten die Werkzeuge byteweise; das geht fuer den Text gut,
# 'tolower' auf der Art ("Löschung") aber nur zufaellig. Eine vorhandene Locale
# wird deshalb gesetzt - und keine erfunden, sonst warnt jedes Werkzeug.
if [ -z "${LC_ALL:-}" ]; then
  for kandidat in C.UTF-8 C.utf8 en_US.UTF-8 de_DE.UTF-8; do
    if locale -a 2>/dev/null | grep -qix -- "${kandidat}"; then
      export LC_ALL="${kandidat}"
      break
    fi
  done
fi

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

# Felder trimmen und einheitlich mit " | " zusammensetzen. Nur so laesst sich
# ein Eintrag spaeter zuverlaessig wiederfinden - ob jemand "Verbesserung|Geraet"
# oder "Verbesserung  |  Geraet" geschrieben hat, darf keine Rolle spielen.
norm() {
  awk -F'|' '{
    art=$1; ber=$2; txt=$3; for (i=4; i<=NF; i++) txt = txt "|" $i;
    gsub(/^[ \t]+|[ \t]+$/, "", art);
    gsub(/^[ \t]+|[ \t]+$/, "", ber);
    gsub(/^[ \t]+|[ \t]+$/, "", txt);
    if (art == "" && ber == "" && txt == "") next;
    print art " | " ber " | " txt
  }'
}

sammle() {  # sammle <Trailer-Name>
  git log --no-merges --format='%B' "${RANGE}" 2>/dev/null \
    | grep -E "^[[:space:]]*$1:" \
    | sed -E "s/^[[:space:]]*$1:[[:space:]]*//" \
    | norm \
    | sort -u || true
}

# Alle Changelog-Zeilen des Bereichs einsammeln. Doppelte entfernen: Ein Commit
# kann ueber einen Merge zweimal in der Liste auftauchen.
ENTRIES="$(sammle 'Changelog')"

# Zurueckgezogene Eintraege abziehen.
#
# Wird eine Aenderung im selben Release-Zeitraum wieder verworfen oder ersetzt,
# bliebe ihr Satz sonst im Changelog stehen und behauptete etwas Falsches - die
# Zeile im alten Commit laesst sich ja nicht mehr aendern. Ein spaeterer Commit
# nimmt sie mit derselben Zeile unter anderem Namen zurueck:
#
#     Changelog-entfaellt: <Art> | <Bereich> | <derselbe Satz>
#
# Nach der Veroeffentlichung wirkt das nicht mehr: Der naechste Release-Bereich
# beginnt beim neuen Tag, beide Zeilen liegen dann dahinter.
ZURUECK="$(sammle 'Changelog-entfaellt')"
if [ -n "${ZURUECK}" ]; then
  ENTRIES="$(printf '%s\n' "${ENTRIES}" \
    | grep -vxF -f <(printf '%s\n' "${ZURUECK}") || true)"
fi

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
