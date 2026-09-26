"""Das Protokoll monatsweise ablegen.

Bisher wurde nach Groesse umgebrochen: bei 1 MB, drei Staende aufgehoben.
Damit war die Datei zwar nie zu gross, aber was aelter war, fiel weg - und
wann es wegfiel, hing davon ab, wie gespraechig der Dienst gerade war. Wer im
Februar nachsehen wollte, was im Dezember geschah, fand nichts mehr.

Jetzt endet jeder Monat in einer eigenen Datei:

    gateway.log                        der laufende Monat
    protokolle/gateway-log-08_2026.log August 2026
    protokolle/gateway-log-09_2026.log September 2026

Die laufende Datei bleibt damit klein, und das Vergangene bleibt vollstaendig.
Zwei Faelle, die dabei leicht untergehen:

- **Der Dienst war ueber den Monatswechsel aus.** Dann stehen in gateway.log
  noch Zeilen aus dem alten Monat. Beim Start wird deshalb nicht die Uhr
  gefragt, sondern wann die Datei zuletzt beschrieben wurde.
- **Zu einem Monat gibt es schon eine Archivdatei.** Das passiert nach einem
  Neustart im selben Monat. Dann wird angehaengt, nicht ueberschrieben -
  sonst waere der erste Teil des Monats weg.

Damit eine Stoerung, die sich im Sekundentakt wiederholt, die Platte nicht
vollschreibt, gibt es zusaetzlich eine Obergrenze je Monat. Wird sie
erreicht, wandert der Stand als '-2', '-3' ... ins Archiv.
"""
from __future__ import annotations
import logging
import logging.handlers
import os
import shutil
import time

log = logging.getLogger("voco-gateway")

# So gross darf ein einzelner Monat hoechstens werden, bevor zwischendurch
# abgelegt wird. Im Normalbetrieb schreibt der Dienst rund 1 MB im Monat.
MAX_BYTES = 20 * 1024 * 1024


def _monat_von_datei(datei: str) -> tuple[int, int]:
    """(Jahr, Monat) der letzten Schreibung - oder jetzt, wenn es sie nicht gibt."""
    try:
        t = time.localtime(os.path.getmtime(datei))
    except OSError:
        t = time.localtime()
    return t.tm_year, t.tm_mon


class MonatsProtokoll(logging.handlers.BaseRotatingHandler):
    """Schreibt in eine laufende Datei und legt sie zum Monatswechsel ab."""

    def __init__(self, datei: str, ordner: str, encoding: str = "utf-8"):
        super().__init__(datei, "a", encoding=encoding, delay=False)
        self.ordner = ordner
        self._monat = _monat_von_datei(datei)
        # Der Monat der Zeile, die das Ablegen ausgeloest hat. Nach dem
        # Ablegen gilt er fuer die neue Datei - nicht die Systemuhr: Sonst
        # landete eine Zeile, die den Monatswechsel bringt, unter dem
        # falschen Monat, sobald Uhr und Zeitstempel auseinanderliegen.
        self._naechster = self._monat

    # --- wann wird abgelegt? ------------------------------------------------
    def shouldRollover(self, record: logging.LogRecord) -> int:   # noqa: N802
        t = time.localtime(record.created)
        self._naechster = (t.tm_year, t.tm_mon)
        if self._naechster != self._monat:
            return 1
        try:
            return 1 if os.path.getsize(self.baseFilename) >= MAX_BYTES else 0
        except OSError:
            return 0

    # --- wohin wird abgelegt? -----------------------------------------------
    def _zielname(self) -> str:
        jahr, monat = self._monat
        name = f"gateway-log-{monat:02d}_{jahr}.log"
        ziel = os.path.join(self.ordner, name)
        # Nur bei der Obergrenze entsteht ein zweiter Teil desselben Monats.
        # Nach einem Neustart im selben Monat wird dagegen angehaengt (siehe
        # doRollover) - sonst zerfiele ein Monat in beliebig viele Stuecke.
        return ziel

    def doRollover(self) -> None:                                 # noqa: N802
        if self.stream:
            self.stream.close()
            self.stream = None
        try:
            os.makedirs(self.ordner, exist_ok=True)
            ziel = self._zielname()
            if os.path.exists(ziel):
                if os.path.getsize(ziel) >= MAX_BYTES:
                    ziel = self._freier_teil(ziel)
                    os.replace(self.baseFilename, ziel)
                else:
                    self._anhaengen(self.baseFilename, ziel)
                    os.remove(self.baseFilename)
            else:
                os.replace(self.baseFilename, ziel)
        except Exception as e:
            # Ein misslungenes Ablegen darf den Dienst nicht anhalten: Er
            # schreibt dann eben weiter in dieselbe Datei.
            log.warning("Protokoll konnte nicht abgelegt werden (%s).", e)
        self._monat = self._naechster
        self.stream = self._open()

    @staticmethod
    def _anhaengen(quelle: str, ziel: str) -> None:
        with open(ziel, "a", encoding="utf-8") as z, \
             open(quelle, encoding="utf-8", errors="replace") as q:
            shutil.copyfileobj(q, z)

    @staticmethod
    def _freier_teil(ziel: str) -> str:
        """'...-08_2026.log' -> '...-08_2026-2.log', solange belegt."""
        stamm, endung = os.path.splitext(ziel)
        for teil in range(2, 1000):
            neu = f"{stamm}-{teil}{endung}"
            if not os.path.exists(neu):
                return neu
        return ziel
