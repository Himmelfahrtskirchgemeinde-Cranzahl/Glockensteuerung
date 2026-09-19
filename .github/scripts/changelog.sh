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
# Korrekturen ERGAENZEN, Neuerungen ERSETZEN:
#
#   Bringt eine Version ausschliesslich behobene Fehler, wird der Changelog der
#   letzten Funktionsversion mitgenommen und die Korrektur angehaengt. Sonst
#   stuende im Fenster "Was ist neu" einer Korrektur-Version nur noch die
#   Korrektur - und alles, was die Fassung davor gebracht hat, waere fuer jeden
#   verschwunden, der erst jetzt aktualisiert.
#
#   Bringt eine Version dagegen Neuerungen, faengt der Changelog frisch an:
#   Dann gehoert die neue Fassung in den Blick, nicht die alte.
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

# Vorherigen Versions-Tag suchen: versionssortiert, damit v26.10.0 nach
# v26.9.9 kommt (alphabetisch waere es umgekehrt).
vorheriger_tag() {  # vorheriger_tag <tag>
  git tag -l 'v*' --sort=-v:refname \
    | grep -E '^v[0-9]+\.[0-9]+\.[0-9]+$' \
    | grep -A1 -x -F "$1" | tail -n +2 | head -1 || true
}

if [ -z "${PREV}" ]; then
  PREV="$(vorheriger_tag "${TAG}")"
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

# Alle Changelog-Zeilen EINES Bereichs, Zurueckgezogenes bereits abgezogen.
#
# Zurueckgezogene Eintraege: Wird eine Aenderung im selben Release-Zeitraum
# wieder verworfen oder ersetzt, bliebe ihr Satz sonst im Changelog stehen und
# behauptete etwas Falsches - die Zeile im alten Commit laesst sich ja nicht
# mehr aendern. Ein spaeterer Commit nimmt sie mit derselben Zeile unter
# anderem Namen zurueck:
#
#     Changelog-entfaellt: <Art> | <Bereich> | <derselbe Satz>
eintraege_fuer() {  # eintraege_fuer <range>
  RANGE="$1"
  local eintraege zurueck
  # Doppelte entfernen: Ein Commit kann ueber einen Merge zweimal auftauchen.
  eintraege="$(sammle 'Changelog')"
  zurueck="$(sammle 'Changelog-entfaellt')"
  if [ -n "${zurueck}" ]; then
    eintraege="$(printf '%s\n' "${eintraege}" \
      | grep -vxF -f <(printf '%s\n' "${zurueck}") || true)"
  fi
  printf '%s' "${eintraege}"
}

# Sind das ausschliesslich behobene Fehler?
nur_fehler() {  # nur_fehler <eintraege>
  [ -n "$1" ] || return 1
  ! printf '%s\n' "$1" | awk -F'|' '
      { art=$1; gsub(/^[ \t]+|[ \t]+$/, "", art);
        if (tolower(art) !~ /fehler|bugfix|behoben/) { gefunden=1 } }
      END { exit gefunden ? 0 : 1 }'
}

ENTRIES="$(eintraege_fuer "${RANGE}")"

# Ein reines Fehlerbehebungs-Release ERGAENZT den Changelog, statt ihn zu
# ersetzen.
#
# Sonst stuende im Fenster "Was ist neu" einer Korrektur-Version nur noch die
# Korrektur - und alles, was die Fassung davor gebracht hat, waere fuer jeden
# verschwunden, der erst jetzt aktualisiert. Deshalb wird der betrachtete
# Bereich Tag um Tag zurueckgeschoben, bis er etwas anderes als Fehler enthaelt.
# Herauskommt: die Neuerungen der letzten Funktionsversion samt aller seither
# behobenen Fehler. Ein Release MIT Neuerungen faengt dagegen frisch an - dort
# gehoert die neue Fassung in den Blick, nicht die alte.
BASIS="${PREV}"
SEIT=""
SCHRITTE=0
while [ -n "${BASIS}" ] && [ "${SCHRITTE}" -lt 20 ] \
      && { [ -z "${ENTRIES}" ] || nur_fehler "${ENTRIES}"; }; do
  DAVOR="$(vorheriger_tag "${BASIS}")"
  [ -n "${DAVOR}" ] || break
  BASIS="${DAVOR}"
  ENTRIES="$(eintraege_fuer "${BASIS}..${TAG}")"
  SEIT="${BASIS}"
  SCHRITTE=$((SCHRITTE + 1))
done

if [ -z "${ENTRIES}" ]; then
  echo "_Nur interne Anpassungen - fuer Anwender aendert sich nichts._"
  exit 0
fi

# Sagt, worauf sich die Liste bezieht - sonst waere unklar, warum in einer
# Korrektur-Version Neuerungen stehen, die man schon kennt.
if [ -n "${SEIT}" ]; then
  printf '_Diese Liste zeigt alles seit Version %s: die Korrekturen dieser_\n' "${SEIT#v}"
  printf '_Fassung und die Neuerungen, die seither dazugekommen sind._\n\n'
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
