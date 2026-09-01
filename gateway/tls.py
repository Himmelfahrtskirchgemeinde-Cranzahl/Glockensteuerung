"""
Wurzelzertifikate fuer verschluesselte Verbindungen.

Zwei Stolpersteine, die beide zur selben Meldung fuehren
("certificate verify failed: unable to get local issuer certificate"):

1. Python bringt unter Windows KEINE Wurzelzertifikate mit. Wer dort nur
   `ssl.CERT_REQUIRED` verlangt, ohne ein Bundle anzugeben, scheitert schon an
   ganz gewoehnlichen Zertifikaten. Dagegen hilft 'certifi', das genau dieses
   Bundle pflegt.

2. Umgekehrt reicht certifi ALLEIN oft auch nicht. Virenscanner, Firmen-Proxys
   und manche Router brechen die Verschluesselung auf und stellen im laufenden
   Betrieb eigene Zertifikate aus. Deren Zertifizierungsstelle steht im
   Windows-Zertifikatsspeicher - der Browser kennt sie also, certifi nicht.
   Genau dann bleibt der Fehler bestehen, obwohl certifi installiert ist.

Deshalb wird BEIDES geladen: der Zertifikatsspeicher des Systems (unter Windows
liest Python ihn ueber `load_default_certs`) und zusaetzlich das Bundle von
certifi. Wer eine eigene Zertifizierungsstelle betreibt, legt ihr Bundle in
VOCO_CA_BUNDLE - es kommt dann obendrauf.

Die Pruefung wird an keiner Stelle abgeschaltet. Ein Gateway, das jedes
Zertifikat annimmt, laesst sich mit einem untergeschobenen Broker fernsteuern -
bei einer Anlage, die Glocken laeutet, ist das keine theoretische Sorge.
"""
from __future__ import annotations
import logging
import os
import ssl

log = logging.getLogger("voco-gateway")


def eigenes_bundle() -> str | None:
    """Pfad aus VOCO_CA_BUNDLE, sofern gesetzt und vorhanden."""
    p = os.environ.get("VOCO_CA_BUNDLE", "").strip()
    return p if p and os.path.exists(p) else None


def certifi_bundle() -> str | None:
    """Pfad zum Bundle von certifi, sofern das Paket installiert ist."""
    try:
        import certifi
        p = certifi.where()
        return p if os.path.exists(p) else None
    except Exception:
        return None


def ca_bundle() -> str | None:
    """Ein einzelner Bundle-Pfad - fuer Schnittstellen, die nur einen annehmen.

    Reihenfolge: eigenes Bundle, sonst certifi, sonst None (Pythons Standard).
    Wo es geht, ist `context()` vorzuziehen: Der Kontext kennt zusaetzlich den
    Zertifikatsspeicher des Systems, ein einzelner Pfad schliesst ihn aus.
    """
    return eigenes_bundle() or certifi_bundle()


def context() -> ssl.SSLContext:
    """SSL-Kontext, der Systemspeicher, certifi und ein eigenes Bundle kennt.

    `ssl.create_default_context()` OHNE Dateiangabe laedt den Speicher des
    Systems; wird dagegen `cafile=` uebergeben, laedt es NUR diese Datei. Genau
    daran scheitert die Verbindung, wenn ein Virenscanner dazwischensitzt: Seine
    Zertifizierungsstelle steht im Systemspeicher, nicht in certifi. Also erst
    den Standard laden und die Bundles danach dazulegen.
    """
    ctx = ssl.create_default_context()
    for pfad in (certifi_bundle(), eigenes_bundle()):
        if not pfad:
            continue
        try:
            ctx.load_verify_locations(cafile=pfad)
        except Exception as e:
            # Kein Abbruch: Der Systemspeicher allein genuegt oft schon.
            log.warning("Zertifikatsbundle '%s' konnte nicht geladen werden: %s", pfad, e)
    return ctx


def quellen() -> list[str]:
    """Beschreibung der benutzten Quellen - fuer Logausgabe und Diagnose."""
    raus = ["Zertifikatsspeicher des Systems"]
    if certifi_bundle():
        raus.append(f"certifi ({certifi_bundle()})")
    if eigenes_bundle():
        raus.append(f"VOCO_CA_BUNDLE ({eigenes_bundle()})")
    return raus
