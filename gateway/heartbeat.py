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

    def send(self, *, rules: int, simulation: bool, device: str, mail: bool = False) -> bool:
        """Schreibt einen Schlag. Gibt zurueck, ob es geklappt hat.

        Wirft NIE - ein fehlendes Lebenszeichen darf den Laeutebetrieb nicht
        anhalten. Genau dafuer ist es ja da.
        """
        payload = {
            "at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "rules": rules,
            "simulation": simulation,
            "device": device,
            # Kann die Extension ihr Feedback per E-Mail schicken? Sie kann das
            # nicht selbst beantworten: Die Zugangsdaten liegen in der Kategorie
            # 'email', die normale Benutzer nicht lesen duerfen.
            "mail": mail,
        }
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
