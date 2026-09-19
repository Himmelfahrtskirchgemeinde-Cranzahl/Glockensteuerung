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

# Mit --art wird nichts ausgegeben ausser einem Wort: was fuer eine Art von
# Aenderungen seit dem vorherigen Tag zusammengekommen ist. Der Workflow
# entscheidet daran, ob die naechste Version eine Hotfix-Stelle bekommt
# (26.8.9.1) oder weiterzaehlt (26.9.0) - und zwar mit DERSELBEN Regel, nach der
# hier der Changelog ergaenzt oder ersetzt wird. Zwei Stellen, die dasselbe
# unterschiedlich entscheiden, waeren eine sichere Fehlerquelle.
NUR_ART=0
if [ "${1:-}" = "--art" ]; then NUR_ART=1; shift; fi

TAG="${1:?Aufruf: changelog.sh [--art] <tag> [<vorheriger-tag>]}"
PREV="${2:-}"

# Vorherigen Versions-Tag suchen: versionssortiert, damit v26.10.0 nach
# v26.9.9 kommt (alphabetisch waere es umgekehrt).
vorheriger_tag() {  # vorheriger_tag <tag>
  git tag -l 'v*' --sort=-v:refname \
    | grep -E '^v[0-9]+\.[0-9]+\.[0-9]+(\.[0-9]+)?$' \
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

if [ "${NUR_ART}" = "1" ]; then
  ERSTE="$(eintraege_fuer "${RANGE}")"
  if [ -z "${ERSTE}" ]; then
    echo "nichts"
  elif nur_fehler "${ERSTE}"; then
    echo "fehler"
  else
    echo "neuerung"
  fi
  exit 0
fi

# Ein reines Fehlerbehebungs-Release ERGAENZT den Changelog, statt ihn zu
# ersetzen - und zeigt beides, jede Version unter ihrer eigenen Nummer.
#
# Sonst stuende im Fenster "Was ist neu" einer Korrektur-Version nur noch die
# Korrektur, und alles, was die Fassung davor gebracht hat, waere fuer jeden
# verschwunden, der erst jetzt aktualisiert. Gezeigt wird deshalb bis zur
# letzten Version zurueck, die Neuerungen brachte - diese eingeschlossen.
declare -A JE_VERSION
VERSIONEN=()
X="${TAG}"
SCHRITTE=0
while [ -n "${X}" ] && [ "${SCHRITTE}" -lt 20 ]; do
  P="$(vorheriger_tag "${X}")"
  if [ -n "${P}" ]; then R="${P}..${X}"; else R="${X}"; fi
  E="$(eintraege_fuer "${R}")"
  if [ -n "${E}" ]; then
    JE_VERSION["${X}"]="${E}"
    VERSIONEN+=("${X}")
  fi
  # Sobald eine Version etwas anderes als behobene Fehler brachte, ist die
  # Funktionsversion erreicht - weiter zurueck gehoert nicht mehr dazu.
  if [ -n "${E}" ] && ! nur_fehler "${E}"; then break; fi
  X="${P}"
  SCHRITTE=$((SCHRITTE + 1))
done

ENTRIES=""
for v in "${VERSIONEN[@]:-}"; do
  [ -n "${v}" ] || continue
  ENTRIES="${ENTRIES}${ENTRIES:+$'\n'}${JE_VERSION[$v]}"
done

if [ -z "${ENTRIES}" ]; then
  echo "_Nur interne Anpassungen - fuer Anwender aendert sich nichts._"
  exit 0
fi

# Getrennt nach Teil: Was in ChurchTools zu sehen ist, und was auf dem Rechner
# der Gemeinde laeuft. Beides in einer Liste zu mischen half niemandem - wer die
# Erweiterung hochlaedt, interessiert sich nicht fuer den Dienst, und die
# Erweiterung zeigt im Fenster "Was ist neu" ohnehin nur ihren eigenen Teil.
#
# Entschieden wird am BEREICH. Die Liste hier ist die Abmachung; alles, was
# nicht daraufsteht, gehoert zur Erweiterung. Steht ein neuer Bereich an, gehoert
# er ergaenzt - im README steht, welche Namen ueblich sind.
GATEWAY_BEREICHE="^(automatik|gateway|dienst|installation|e-?mail|postausgang)$"

nur_teil() {  # nur_teil <gateway|erweiterung>
  printf '%s\n' "${ENTRIES}" | awk -F'|' -v m="${GATEWAY_BEREICHE}" -v w="$1" '
    { ber=$2; gsub(/^[ \t]+|[ \t]+$/, "", ber);
      ist = (tolower(ber) ~ m) ? "gateway" : "erweiterung";
      if (ist == w) print }'
}

# Nach Art gruppieren, in fester Reihenfolge. Innerhalb einer Art nach Bereich,
# wobei "Allgemein" immer zuerst steht (der Rest alphabetisch).
emit_group() {
  local want="$1" ueberschrift="$2" gefunden=0

  local bereiche
  bereiche="$(printf '%s\n' "${AKTUELL}" \
    | awk -F'|' -v w="${want}" '
        { art=$1; gsub(/^[ \t]+|[ \t]+$/, "", art); if (tolower(art) ~ w) {
            b=$2; gsub(/^[ \t]+|[ \t]+$/, "", b); print b } }' \
    | sort -u \
    | awk '{ if (tolower($0)=="allgemein") first=$0; else rest=rest $0 "\n" }
           END { if (first) print first; printf "%s", rest }')"

  [ -n "${bereiche}" ] || return 0

  printf '#### %s\n\n' "${ueberschrift}"
  while IFS= read -r bereich; do
    [ -n "${bereich}" ] || continue
    printf '* **%s**\n' "${bereich}"
    printf '%s\n' "${AKTUELL}" \
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
alle_gruppen() {
  emit_group 'l(o|ö)*e*schung' 'Löschungen'
  emit_group 'verbesserung|neu|funktion' 'Verbesserungen'
  emit_group 'fehler|bugfix|behoben' 'Behobene Fehler'
}

# Hat ein Teil in irgendeiner Version etwas beizutragen?
teil_hat_etwas() {  # teil_hat_etwas <teil>
  local v
  for v in "${VERSIONEN[@]:-}"; do
    [ -n "${v}" ] || continue
    ENTRIES="${JE_VERSION[$v]}"
    [ -z "$(nur_teil "$1")" ] || return 0
  done
  return 1
}

# Ueberschriftentiefe: ## Teil, ### Version, #### Gruppe. Die Erweiterung
# zeigt im Fenster "Was ist neu" nur ihren eigenen Teil und stellt die
# Versionsnummer heraus - so ist zu sehen, was in welcher Fassung kam.
teil_ausgeben() {  # teil_ausgeben <teil> <ueberschrift>
  teil_hat_etwas "$1" || return 0
  printf '## %s\n\n' "$2"
  local v
  for v in "${VERSIONEN[@]:-}"; do
    [ -n "${v}" ] || continue
    ENTRIES="${JE_VERSION[$v]}"
    AKTUELL="$(nur_teil "$1")"
    [ -n "${AKTUELL}" ] || continue
    printf '### Version %s\n\n' "${v#v}"
    alle_gruppen
  done
}

teil_ausgeben erweiterung 'Erweiterung (in ChurchTools)'
teil_ausgeben gateway 'Gateway (Dienst auf dem Rechner)'
