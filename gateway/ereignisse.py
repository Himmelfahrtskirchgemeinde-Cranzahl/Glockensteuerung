"""
Ereignisse des Gateway-Dienstes fuer das Ereignis-Log der Extension.

Das Ereignis-Log in der Extension lebt bisher nur im Browser: Es zeigt, was seit
dem Oeffnen der Seite geschah. Ob der Dienst um drei Uhr nachts die Verbindung
verloren und um vier wiederbekommen hat, sah dort niemand.

Der Dienst haelt solche Ereignisse deshalb selbst fest - in derselben Kategorie
wie das Lebenszeichen ('steuerung', lesbar fuer jeden, der das Modul bedienen
darf), unter dem Schluessel 'gatewayEvents'.

Bewusst nur ZUSTANDSWECHSEL, nicht jeder Durchlauf: Ein Dienst, der stuendlich
"laeuft noch" meldet, verstopft das Log, und die eine Zeile, auf die es ankommt,
geht darin unter. Das Lebenszeichen beantwortet "laeuft er?" ohnehin besser.
"""
from __future__ import annotations
import datetime as dt
import logging

from kv import KV

log = logging.getLogger("voco-gateway")

SCHLUESSEL = "gatewayEvents"
KATEGORIE = "steuerung"

# Wie viele Ereignisse aufgehoben werden. Genug, um eine unruhige Nacht
# nachzuvollziehen; wenig genug, dass der Eintrag klein bleibt - er wird bei
# jedem Seitenaufruf mitgeladen.
MAX = 50


class Ereignisse:
    """Schreibt Ereignisse. Wirft nie - ein Protokoll darf nichts anhalten."""

    def __init__(self, ct, ext_key: str):
        self.kv = KV(ct, ext_key, KATEGORIE)
        self._letzter_fehler = False

    def melde(self, art: str, text: str) -> bool:
        """Ein Ereignis anhaengen. 'art' ist 'an', 'aus' oder 'info'."""
        eintrag = {
            "at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "art": art,
            "text": text,
        }
        try:
            bisher = self.kv.lesen(SCHLUESSEL)
            liste = bisher if isinstance(bisher, list) else []
            # Neueste zuerst - so liest die Extension es auch.
            liste = [eintrag] + [e for e in liste if isinstance(e, dict)][: MAX - 1]
            self.kv.schreiben(SCHLUESSEL, liste)
            if self._letzter_fehler:
                log.info("Ereignisse werden wieder geschrieben.")
                self._letzter_fehler = False
            return True
        except Exception as e:
            # WARNING, nicht ERROR: Der Notifier verschickt ERROR per Mail, und
            # eine anhaltende Stoerung ergaebe eine Mail je Ereignis.
            if not self._letzter_fehler:
                log.warning("Ereignis konnte nicht protokolliert werden (%s). "
                            "Gelaeutet wird trotzdem weiter.", e)
                self._letzter_fehler = True
            self.kv.vergessen()
            return False


class Zustandswaechter:
    """Meldet nur, wenn sich etwas aendert.

    Ohne das schriebe jeder Wiederverbindungsversuch eine Zeile. paho meldet
    beim Verbindungsaufbau mehrfach 'verbunden', und ein flatterndes Netz
    erzeugte binnen Minuten Dutzende Eintraege.
    """

    def __init__(self, ereignisse: Ereignisse):
        self.ereignisse = ereignisse
        self._verbunden: bool | None = None

    def setze(self, verbunden: bool) -> None:
        if self._verbunden == verbunden:
            return
        erster = self._verbunden is None
        self._verbunden = verbunden
        if verbunden:
            self.ereignisse.melde("an", "Mit der Anlage verbunden."
                                  if erster else "Verbindung zur Anlage wiederhergestellt.")
        else:
            self.ereignisse.melde("aus", "Verbindung zur Anlage verloren.")
