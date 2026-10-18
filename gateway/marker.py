"""
Marker im Kalendertitel: einzelne Laeutungen abschalten, ohne eine Regel
anzufassen.

Im Titel eines Termins steht hinter einem Pluszeichen, was NICHT laeuten soll:

    Gottesdienst +AUSA           alles aus - fuer diesen Termin laeutet nichts
    Gottesdienst +AUSVL          nur die Regel mit dem Kuerzel "VL" faellt aus
    Gottesdienst +AUSVL +AUSNL   mehrere auf einmal

Gross- und Kleinschreibung ist egal, ein Doppelpunkt darf dazwischen stehen
(`+AUS:VL`). `+AUS` ohne Zusatz gilt wie `+AUSA`.

WICHTIG: Der Marker wird aus dem Titel GESCHNITTEN, bevor er mit dem Titel
einer Regel verglichen wird. Sonst passte "Gottesdienst +AUSA" nicht mehr auf
die Regel "Gottesdienst" - der Marker haette dort zwar zufaellig die richtige
Wirkung, bei einer Regel ohne Titelfilter aber gar keine.

Dieselbe Grammatik steht in der Erweiterung in `extension/src/marker.ts`.
Weichen die beiden voneinander ab, zeigt die Vorschau etwas anderes an, als
wirklich laeutet - die Stellen gehoeren zusammen geaendert.
"""
from __future__ import annotations
import re
from dataclasses import dataclass, field

# Dieses Kuerzel steht fuer "alles" und darf keiner Regel gehoeren.
ALLE = "A"

# Woraus ein Kuerzel bestehen darf.
KUERZEL_ZEICHEN = re.compile(r"^[A-Za-z0-9ÄÖÜäöüß_-]+$")

# Das Pluszeichen ist der Indikator, "AUS" das Steuerwort. Beides zusammen
# kommt in einem Termin-Titel sonst nicht vor - anders als ein "+" allein.
_MUSTER = re.compile(
    r"\+AUS(?::?([A-Za-zÄÖÜäöüß0-9_-]+))?",
    re.IGNORECASE,
)

_MEHRFACH_LEER = re.compile(r"\s{2,}")


@dataclass
class Befund:
    """Was im Titel stand, und was davon uebrig bleibt."""

    titel: str = ""             # Titel ohne die Marker - damit wird verglichen
    alles_aus: bool = False     # stand "+AUSA" (oder "+AUS") darin?
    kuerzel: list[str] = field(default_factory=list)   # genannte Kuerzel, gross
    gefunden: bool = False      # stand ueberhaupt ein Marker im Titel?


def lesen(roh: str | None) -> Befund:
    """Titel zerlegen: was bleibt, und was soll ausfallen?"""
    text = (roh or "").strip()
    befund = Befund(titel=text)
    if "+" not in text:
        return befund                    # haeufigster Fall, ohne Regex

    gesehen: set[str] = set()

    def ersetzen(treffer: re.Match) -> str:
        befund.gefunden = True
        k = (treffer.group(1) or "").upper()
        if not k or k == ALLE:
            befund.alles_aus = True
        elif k not in gesehen:
            gesehen.add(k)
            befund.kuerzel.append(k)
        return " "

    rest = _MUSTER.sub(ersetzen, text)
    # Mehrfache Leerzeichen entstehen durch das Herausschneiden.
    befund.titel = _MEHRFACH_LEER.sub(" ", rest).strip()
    return befund


def ausgenommen(befund: Befund, kuerzel: str | None) -> bool:
    """Faellt die Regel mit diesem Kuerzel bei diesem Termin aus?"""
    if befund.alles_aus:
        return True
    k = (kuerzel or "").strip().upper()
    return bool(k) and k in befund.kuerzel


def unbekannte(befund: Befund, bekannte) -> list[str]:
    """Kuerzel, die im Titel stehen, aber zu keiner Regel gehoeren.

    Das ist der gefaehrliche Fall: Wer sich vertippt, glaubt, es laeute nicht -
    und es laeutet doch. Deshalb muss er auffallen.
    """
    liste = {(k or "").strip().upper() for k in bekannte}
    liste.discard("")
    return [k for k in befund.kuerzel if k not in liste]
