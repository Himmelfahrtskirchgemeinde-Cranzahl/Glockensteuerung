"""Haelt Zugangsdaten aus dem Protokoll heraus.

Seit der Dienst das Login-Token einer Anfrage beilegen kann, steht es unter
Umstaenden in der Adresse - und damit in jeder Fehlermeldung, die die
HTTP-Bibliothek daraus baut. Solche Meldungen landen im Protokoll, im
Ereignis-Log der Gemeinde und bei einer Stoerung sogar per E-Mail. Ein Token
in einer Rundmail waere schlimmer als der Fehler, der sie ausgeloest hat.

Deshalb wird der Wert ersetzt, bevor eine Zeile irgendwohin geschrieben wird.
Das haengt am Protokoll selbst, nicht an den einzelnen Aufrufern: Es soll auch
dann greifen, wenn eine kuenftige Stelle daran nicht denkt.
"""
from __future__ import annotations
import logging
import re

# Das Token endet am ersten Zeichen, das in einer Adresse nicht mehr dazu
# gehoert - oder am Zeilenende.
_MUSTER = re.compile(r"(login_token=)[^&\s\"'>)]+", re.IGNORECASE)


def ohne_geheimnisse(text: str) -> str:
    """Ersetzt den Wert eines Login-Tokens durch Sternchen."""
    return _MUSTER.sub(r"\1***", text)


class Filter(logging.Filter):
    """Maskiert jede Zeile, die durch einen Handler geht."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            text = record.getMessage()
        except Exception:
            return True                      # lieber unveraendert als gar nicht
        sauber = ohne_geheimnisse(text)
        if sauber != text:
            record.msg = sauber
            record.args = ()
        return True


def schuetzen(handler: logging.Handler) -> logging.Handler:
    """Haengt den Filter an einen Handler und gibt ihn zurueck."""
    handler.addFilter(Filter())
    return handler
