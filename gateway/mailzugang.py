"""
Den Zugang zum Postausgang merken - fuer den Fall, dass ChurchTools schweigt.

Die Zugangsdaten stehen in der Erweiterung, damit sie sich ohne Zugriff auf den
Server aendern lassen. Das hat eine Luecke, die genau im schlimmsten Fall
aufgeht: Kommt der Dienst beim Start gar nicht an ChurchTools heran - kein
Netz, abgelaufenes Token, fehlende Rechte -, dann kennt er auch den Postausgang
nicht. Er kann also nicht melden, dass er nicht laeuft. Beim Ausfall im
September 2026 stand die Automatik 32 Stunden still, ohne dass eine Mail kam;
im Protokoll auf dem Rechner der Gemeinde stand alles, nur sah dort niemand
nach.

Darum wird der zuletzt gelesene Zugang hier abgelegt und beim naechsten Start
benutzt, SOLANGE ChurchTools noch nicht geantwortet hat. Sobald eine Antwort da
ist, gilt wieder, was dort steht - die abgelegte Fassung wird dann aufgefrischt.

Was der Schutz leistet, und was nicht
-------------------------------------
In der Datei steht das Passwort des Postausgangs. Unter Windows wird sie mit
DPAPI verschluesselt und ist damit an das KONTO gebunden, unter dem der Dienst
laeuft: Ein anderer angemeldeter Benutzer kann sie nicht lesen, auch wenn er an
die Datei kommt. Wer am selben Rechner Administrator ist, kann sich allerdings
als Systemkonto ausgeben - gegen den schuetzt das nicht.

Ausserhalb von Windows gibt es DPAPI nicht. Dort bekommt die Datei die Rechte
0600 (nur der Eigentuemer) und der Inhalt bleibt lesbar. Das wird hier so
gesagt und nicht als Verschluesselung ausgegeben.

Wer den gemerkten Zugang loswerden will, loescht die Datei; der Pfad steht in
der Statusanzeige (Menuepunkt 3).
"""
from __future__ import annotations
import base64
import json
import logging
import os

import pfade

log = logging.getLogger("voco-gateway")

# Version des Dateiformats - falls sich spaeter etwas daran aendert.
FORMAT = 1


def pfad() -> str:
    return pfade.mailzugangsdatei()


# --- Windows: DPAPI ---------------------------------------------------------
def _dpapi(schuetzen: bool, roh: bytes) -> bytes | None:
    """CryptProtectData bzw. CryptUnprotectData. None, wenn es nicht geht."""
    try:
        import ctypes
        from ctypes import wintypes

        class BLOB(ctypes.Structure):
            _fields_ = [("cbData", wintypes.DWORD),
                        ("pbData", ctypes.POINTER(ctypes.c_char))]

        crypt = ctypes.WinDLL("crypt32", use_last_error=True)
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        rein = BLOB(len(roh), ctypes.cast(ctypes.create_string_buffer(roh),
                                          ctypes.POINTER(ctypes.c_char)))
        raus = BLOB()
        fn = crypt.CryptProtectData if schuetzen else crypt.CryptUnprotectData
        ok = fn(ctypes.byref(rein), None, None, None, None, 0, ctypes.byref(raus))
        if not ok:
            return None
        try:
            return ctypes.string_at(raus.pbData, raus.cbData)
        finally:
            kernel.LocalFree(raus.pbData)
    except Exception:
        return None


def _verpacken(daten: dict) -> dict:
    roh = json.dumps(daten).encode("utf-8")
    if os.name == "nt":
        blob = _dpapi(True, roh)
        if blob:
            return {"format": FORMAT, "art": "dpapi",
                    "daten": base64.b64encode(blob).decode("ascii")}
        # Lieber im Klartext merken als gar nicht: Ohne den gemerkten Zugang
        # bleibt die Stoerungsmail beim Anlauffehler ganz aus, und das ist der
        # Fall, fuer den es diese Datei gibt. Die Datei liegt im Arbeitsordner
        # des Dienstes, nicht im Netz.
        log.warning("Postausgang konnte nicht verschluesselt gemerkt werden - "
                    "er wird im Klartext abgelegt (%s).", pfad())
    return {"format": FORMAT, "art": "klartext", "daten": daten}


def _auspacken(huelle: dict) -> dict | None:
    art = huelle.get("art")
    if art == "klartext" and isinstance(huelle.get("daten"), dict):
        return huelle["daten"]
    if art == "dpapi" and isinstance(huelle.get("daten"), str):
        blob = base64.b64decode(huelle["daten"])
        roh = _dpapi(False, blob)
        if roh is None:
            # Haeufigster Grund: Die Datei wurde unter einem anderen Konto
            # geschrieben - etwa vom Dienst (Systemkonto), gelesen aber von
            # einem angemeldeten Benutzer beim Testlauf.
            log.info("Gemerkter Postausgang gehoert zu einem anderen Konto - "
                     "er wird uebergangen.")
            return None
        return json.loads(roh.decode("utf-8"))
    return None


# --- Nach aussen ------------------------------------------------------------
def _als_dict(cfg) -> dict:
    return {
        "host": cfg.host,
        "port": cfg.port,
        "user": cfg.user,
        "password": cfg.password,
        "from": cfg.mail_from,
        "to": cfg.mail_to,
        "security": cfg.security,
        "sendFeedback": cfg.send_feedback,
        "sendErrors": cfg.send_errors,
    }


def merken(cfg) -> None:
    """Zugang ablegen. Wirft nie - ein Merkzettel darf nichts anhalten."""
    if cfg is None or not getattr(cfg, "host", ""):
        return
    try:
        neu = _als_dict(cfg)
        if neu == holen(als_dict=True):
            return                      # unveraendert - nicht bei jedem Lauf schreiben
        huelle = _verpacken(neu)
        ziel = pfad()
        vorlaeufig = ziel + ".neu"
        with open(vorlaeufig, "w", encoding="utf-8") as f:
            json.dump(huelle, f)
        if os.name != "nt":
            os.chmod(vorlaeufig, 0o600)
        os.replace(vorlaeufig, ziel)    # atomar - keine halbe Datei
        log.info("Postausgang gemerkt (%s) - Stoerungsmails gehen auch raus, "
                 "wenn ChurchTools beim Start nicht erreichbar ist.", ziel)
    except Exception as e:
        log.warning("Postausgang konnte nicht gemerkt werden (%s).", e)


def holen(als_dict: bool = False):
    """Gemerkten Zugang lesen - als EmailConfig, oder None."""
    try:
        ziel = pfad()
        if not os.path.exists(ziel):
            return None
        with open(ziel, encoding="utf-8") as f:
            huelle = json.load(f)
        daten = _auspacken(huelle) if isinstance(huelle, dict) else None
        if not isinstance(daten, dict) or not daten.get("host"):
            return None
        if als_dict:
            return daten
        from config import EmailConfig
        return EmailConfig(
            host=str(daten.get("host") or ""),
            port=int(daten.get("port") or 587),
            user=str(daten.get("user") or ""),
            password=str(daten.get("password") or ""),
            mail_from=str(daten.get("from") or ""),
            mail_to=str(daten.get("to") or ""),
            security=str(daten.get("security") or "starttls"),
            send_feedback=bool(daten.get("sendFeedback", True)),
            send_errors=bool(daten.get("sendErrors", True)),
        )
    except Exception as e:
        log.warning("Gemerkter Postausgang nicht lesbar (%s).", e)
        return None


def beschreibung() -> str:
    """Eine Zeile fuer die Statusanzeige."""
    ziel = pfad()
    if not os.path.exists(ziel):
        return "(noch keiner gemerkt)"
    try:
        with open(ziel, encoding="utf-8") as f:
            art = json.load(f).get("art")
    except Exception:
        return f"{ziel} (nicht lesbar)"
    wie = "an das Dienstkonto gebunden" if art == "dpapi" else "im Klartext"
    return f"{ziel} ({wie})"
