#!/usr/bin/env bash
#
# Packt den Gateway-Dienst als ZIP fuer den Rechner, auf dem er laeuft.
#
# Die Extension gehoert nach ChurchTools, der Gateway auf einen Windows- oder
# Linux-Rechner in der Gemeinde. Bisher liess sich nur das Repository klonen -
# fuer jemanden, der kein Git benutzt, eine unnoetige Huerde.
#
# Was NICHT hineingehoert und deshalb ausdruecklich ausgeschlossen ist:
#   .env         die echten Zugangsdaten (Geraetepasswort, Postfach, Serie)
#   .venv        die virtuelle Umgebung des Baurechners
#   __pycache__  uebersetzte Zwischenstaende
#
# Aufgenommen werden alle Python-Module des Ordners und die drei Beigaben. Eine
# gepflegte Namensliste waere zwar noch enger, wuerde aber bei jedem neuen Modul
# vergessen - und ein Dienst, dem eine Datei fehlt, faellt erst auf dem Rechner
# der Gemeinde auf. Zugangsdaten stehen ohnehin nie in einem Modul, sondern in
# der .env; dass keine mitreist, prueft das Skript am Ende ausdruecklich nach.
#
# Aufruf:  gateway-zip.sh [<version>] <zielverzeichnis>
#          Ohne Version wird sie wie bei der Extension aus 'git describe' geholt.
set -euo pipefail

if [ "$#" -ge 2 ]; then
  VERSION="$1"; ZIEL="$2"
else
  ZIEL="${1:?Aufruf: gateway-zip.sh [<version>] <zielverzeichnis>}"
  # Dieselbe Quelle wie scripts/package.js, damit beide Archive einer
  # Veroeffentlichung dieselbe Nummer tragen.
  VERSION="$(git describe --tags --always --match 'v*' 2>/dev/null | sed 's/^v//')"
  VERSION="${VERSION:-0.0.0}"
fi

WURZEL="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
QUELLE="${WURZEL}/gateway"

BEIGABEN=(requirements.txt README.md .env.example)

ARBEIT="$(mktemp -d)"
trap 'rm -rf "${ARBEIT}"' EXIT
INNEN="${ARBEIT}/glockensteuerung-gateway"
mkdir -p "${INNEN}"

# Nur die oberste Ebene: Unterordner des Arbeitsplatzes (.venv, __pycache__)
# bleiben damit von vornherein draussen.
ANZAHL=0
while IFS= read -r f; do
  cp "${f}" "${INNEN}/"
  ANZAHL=$((ANZAHL + 1))
done < <(find "${QUELLE}" -maxdepth 1 -name '*.py' -type f | sort)

if [ "${ANZAHL}" -lt 5 ]; then
  echo "ABBRUCH: nur ${ANZAHL} Python-Dateien gefunden - das kann nicht stimmen." >&2
  exit 1
fi

# Der Dienst selbst muss dabei sein, sonst ist das Archiv wertlos.
for f in scheduler.py "${BEIGABEN[@]}"; do
  if [ -f "${QUELLE}/${f}" ]; then
    cp "${QUELLE}/${f}" "${INNEN}/${f}"
  else
    echo "FEHLT: gateway/${f}" >&2
    exit 1
  fi
done

# Version im Archiv festhalten. Wer spaeter fragt, welcher Stand auf dem
# Rechner liegt, muss sonst raten - der Ordnername verraet es nicht.
printf '%s\n' "${VERSION}" > "${INNEN}/VERSION"

# Sicherheitsnetz: Eine .env darf unter keinen Umstaenden mitreisen. Ein
# Tippfehler in der Liste oben wuerde sonst Zugangsdaten veroeffentlichen.
if find "${INNEN}" -name '.env' -o -name '*.env' ! -name '.env.example' | grep -q .; then
  echo "ABBRUCH: Im Archiv liegt eine .env - das darf nicht veroeffentlicht werden." >&2
  exit 1
fi

# Absolut machen: Gepackt wird aus einem anderen Verzeichnis heraus, ein
# relativer Zielpfad zeigte von dort ins Leere.
mkdir -p "${ZIEL}"
ZIEL="$(cd "${ZIEL}" && pwd)"
ARCHIV="${ZIEL}/glockensteuerung-gateway-v${VERSION}.zip"
rm -f "${ARCHIV}"
( cd "${ARBEIT}" && zip -q -r "${ARCHIV}" glockensteuerung-gateway )

echo "${ARCHIV}"
