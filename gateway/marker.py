"""
Marker im Kalendertitel: einzelne Laeutungen abschalten, ohne eine Regel
anzufassen.

Im Titel eines Termins steht hinter einem Pluszeichen, was NICHT laeuten soll:

    Gottesdienst +AUSA           alles aus - fuer diesen Termin laeutet nichts
    Gottesdienst +AUSVL          nur die Regel mit dem Kuerzel "VL" faellt aus
    Gottesdienst +AUSVL +AUSNL   mehrere auf einmal

Kurzform: statt "AUS" genuegt ein "A" - "+AVL" wirkt wie "+AUSVL", "+AA" wie
"+AUSA". Gross- und Kleinschreibung ist egal, und ein Doppelpunkt darf
dazwischen stehen (`+AUS:VL`).

Ein Kuerzel gehoert IMMER dazu - entweder das einer Regel oder "A" fuer alle.
"+AUS" oder "+A" allein bewirkt nichts: Dort fehlt die Angabe, was abgeschaltet
werden soll, und ein halber Befehl soll nicht das ganze Gelaeut abstellen.

Die Kurzform greift NUR mit einem Kuerzel, das es wirklich gibt. Sonst risse
sie Loecher in gewoehnliche Titel: Aus "Konzert +Anmeldung erforderlich" wuerde
"Konzert erforderlich", und "nmeldung" galte als Kuerzel. "+AUS" ist dagegen
eindeutig genug, um immer zu wirken - auch mit einem Kuerzel, das es nicht gibt
(das ist ein Tippfehler, und der soll auffallen).

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

# Das Pluszeichen ist der Indikator, "AUS" (oder kurz "A") das Steuerwort.
# Beides zusammen kommt in einem Termin-Titel sonst nicht vor - anders als ein
# "+" allein. Die Reihenfolge in der Alternative ist wichtig: "AUS" wird zuerst
# versucht, sonst laese sich "+AUSVL" auch als "A" + Kuerzel "USVL".
_MUSTER = re.compile(
    r"\+(AUS|A)(?::?([A-Za-zÄÖÜäöüß0-9_-]+))?",
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
    # Stand "+AUS" ohne Kuerzel da? Das bewirkt nichts und ist fast immer ein
    # vergessenes "A".
    ohne_kuerzel: bool = False


def lesen(roh: str | None, bekannte=()) -> Befund:
    """Titel zerlegen: was bleibt, und was soll ausfallen?

    `bekannte` sind die Kuerzel aller Regeln. Sie entscheiden allein ueber die
    Kurzform "+A<Kuerzel>"; ohne sie wirkt nur das eindeutige "+AUS...".
    """
    text = (roh or "").strip()
    befund = Befund(titel=text)
    if "+" not in text:
        return befund                    # haeufigster Fall, ohne Regex

    bekannt = {(k or "").strip().upper() for k in bekannte}
    bekannt.discard("")
    gesehen: set[str] = set()

    def ersetzen(treffer: re.Match) -> str:
        wort = (treffer.group(1) or "").upper()
        k = (treffer.group(2) or "").upper()
        if not k:
            # Ohne Kuerzel fehlt die Angabe, was abgeschaltet werden soll.
            # Bei der langen Form ist die Absicht aber erkennbar - das gehoert
            # gemeldet, sonst laeutet es und niemand weiss, warum.
            if wort != ALLE:
                befund.ohne_kuerzel = True
            return treffer.group(0)      # kein Marker: Text unangetastet
        # Kurzform nur bei einem Kuerzel, das es gibt - sonst bliebe von
        # "+Anmeldung" ein Loch im Titel zurueck.
        if wort == ALLE and k != ALLE and k not in bekannt:
            return treffer.group(0)
        befund.gefunden = True
        if k == ALLE:
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
