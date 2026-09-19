"""
Lebenszeichen des Gateway-Dienstes.

Der Gateway schreibt regelmaessig einen Zeitstempel nach ChurchTools. Die
Extension liest ihn und warnt, wenn er zu alt ist oder fehlt - sonst merkt
niemand, dass die Automatik steht, bis ein Gottesdienst stumm bleibt.

Ablage: dasselbe Custom-Module wie die uebrige Konfiguration, Kategorie
'steuerung', Schluessel 'gatewayStatus'. Bewusst 'steuerung': Diese Kategorie
darf jeder lesen, der das Modul bedienen darf - die Warnung soll alle
erreichen, nicht nur Administratoren.
"""
from __future__ import annotations
import datetime as dt
import logging

import pfade
from kv import KV

log = logging.getLogger("voco-gateway")

SCHLUESSEL = "gatewayStatus"
KATEGORIE = "steuerung"


class Heartbeat:
    """Schreibt das Lebenszeichen."""

    def __init__(self, ct, ext_key: str):
        self.kv = KV(ct, ext_key, KATEGORIE)
        # Fehler nur beim Zustandswechsel melden, sonst floetet der Dienst alle
        # zwei Minuten dieselbe Zeile ins Log (und der Notifier mailt sie).
        self._failing = False

    def vorige_version(self) -> str:
        """Welche Fassung zuletzt ein Lebenszeichen geschrieben hat.

        Damit erkennt der Dienst beim Start, dass er nach einer
        Aktualisierung eine andere ist als zuvor - und kann es melden. Ein
        eigener Merkposten waere dafuer nicht noetig: Es steht ohnehin im
        Lebenszeichen.
        """
        try:
            daten = self.kv.lesen(SCHLUESSEL) or {}
            return str(daten.get("version") or "")
        except Exception:
            return ""

    def send(self, *, rules: int, simulation: bool, device: str, mail: bool = False,
             mail_fehler: bool = False,
             update_bis: dt.datetime | None = None,
             pause_bis: dt.datetime | None = None, grund: str = "") -> bool:
        """Schreibt einen Schlag. Gibt zurueck, ob es geklappt hat.

        Wirft NIE - ein fehlendes Lebenszeichen darf den Laeutebetrieb nicht
        anhalten. Genau dafuer ist es ja da.
        """
        payload = {
            "at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            # Welche Fassung gerade laeuft. Steht hier, damit es in der
            # Erweiterung ablesbar ist - und damit der Dienst beim naechsten
            # Start merkt, dass er eine andere ist als zuvor.
            "version": pfade.version(),
            "rules": rules,
            "simulation": simulation,
            "device": device,
            # Kann die Extension ihr Feedback per E-Mail schicken? Sie kann das
            # nicht selbst beantworten: Die Zugangsdaten liegen in der Kategorie
            # 'email', die normale Benutzer nicht lesen duerfen.
            "mail": mail,
            # Zweiter Schalter, getrennt vom ersten: Stoerungsmeldungen haengen
            # nicht am Feedback-Formular. Wer "Feedback per E-Mail" abschaltet,
            # aber "Stoerungen melden" anlaesst, bekam sonst keine - obwohl er
            # sie eingeschaltet hatte.
            "mailFehler": mail_fehler,
        }
        # Bis dahin ist Schweigen erwartet: Der Dienst startet gerade mit einer
        # neuen Fassung neu. Die Extension meldet in dieser Zeit keine Stoerung
        # - ein geplanter Neustart ist keiner.
        if update_bis is not None:
            payload["updateBis"] = update_bis.isoformat(timespec="seconds")
        # Der Dienst baut gerade neu auf. Auch das ist angekuendigtes Schweigen:
        # Er lebt, hat aber die Verbindung verloren und wartet auf den naechsten
        # Versuch. Ohne diese Angabe sah die Erweiterung nur, dass kein
        # Lebenszeichen mehr kommt, und meldete einen Ausfall - samt E-Mail -,
        # waehrend der Dienst laengst wieder hochkam.
        if pause_bis is not None:
            payload["pauseBis"] = pause_bis.isoformat(timespec="seconds")
            if grund:
                payload["grund"] = grund[:200]
        try:
            self.kv.schreiben(SCHLUESSEL, payload)
            if self._failing:
                log.info("Lebenszeichen wird wieder geschrieben.")
                self._failing = False
            return True
        except Exception as e:
            # Bewusst WARNING statt ERROR: Der Notifier verschickt ERROR per
            # Mail - bei anhaltender Stoerung alle zwei Minuten eine.
            if not self._failing:
                log.warning(
                    "Lebenszeichen konnte nicht geschrieben werden (%s). Die Extension "
                    "wird die Automatik als nicht erreichbar melden, gelaeutet wird "
                    "trotzdem weiter.", e
                )
                self._failing = True
            self.kv.vergessen()
            return False


def mask_serial(serial: str) -> str:
    """'VH-001085' -> 'VH-***085'. Die Seriennummer ist ein Geraete-Merkmal;
    fuer die blosse Anzeige „welches Geraet bedient der Dienst" reicht das."""
    s = (serial or "").strip()
    return s[:3] + "***" + s[-3:] if len(s) > 6 else ("***" if s else "")
