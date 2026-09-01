"""
Zertifikats-Diagnose: Warum scheitert die verschluesselte Verbindung?

Aufruf im gateway-Ordner (venv aktiv):

    python -m diagnose

Ausgegeben wird, gegen welche Zertifikatsquellen geprueft wird, wer das
Zertifikat des Brokers ausgestellt hat und ob die Pruefung damit gelingt.

Der Aussteller ist der entscheidende Hinweis. Steht dort eine oeffentliche
Zertifizierungsstelle (Let's Encrypt, DigiCert, Sectigo ...), ist die Leitung
unangetastet und es fehlen nur Wurzelzertifikate. Steht dort ein Virenscanner,
eine Firewall oder der eigene Arbeitgeber, wird die Verbindung aufgebrochen -
dann muss dessen Zertifikat in VOCO_CA_BUNDLE, sonst kann es nicht gelingen.

Es werden KEINE Zugangsdaten benutzt oder ausgegeben: Die Diagnose baut nur die
verschluesselte Verbindung auf und sieht sich das Zertifikat an. Angemeldet wird
sich nicht.
"""
from __future__ import annotations
import os
import socket
import ssl
import sys
from urllib.parse import urlparse

import config
import tls


def _ziel() -> tuple[str, int]:
    """Broker-Adresse aus der Umgebung - dieselbe Reihenfolge wie voco_mqtt."""
    url = os.environ.get("VOCO_BROKER_URL", "").strip()
    if url:
        u = urlparse(url)
        if u.hostname:
            return u.hostname, u.port or 8084
    return (os.environ.get("VOCO_BROKER_HOST", "hew-voco.de"),
            int(os.environ.get("VOCO_BROKER_PORT", "8084")))


def _name(paare) -> str:
    """('CN', 'x') aus der verschachtelten Form von getpeercert() herausziehen."""
    if not paare:
        return "(unbekannt)"
    flach = {k: v for gruppe in paare for (k, v) in gruppe}
    return flach.get("commonName") or flach.get("organizationName") or str(flach)


def _blattzertifikat(host: str, port: int):
    """Zertifikat holen, OHNE zu pruefen - sonst gaebe es bei Fehlern nichts zu sehen.

    Das ist hier unbedenklich: Es wird nichts gesendet und nichts geglaubt, nur
    angesehen. Die eigentliche Verbindung des Gateways prueft weiterhin streng.
    """
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    with socket.create_connection((host, port), timeout=10) as roh:
        with ctx.wrap_socket(roh, server_hostname=host) as s:
            # get_unverified_chain() gibt es erst in neueren Python-Fassungen.
            kette = getattr(s, "get_unverified_chain", lambda: None)()
            return s.getpeercert(binary_form=False) or _entschluesseln(s), kette


def _entschluesseln(s):
    """Rueckfall: ohne Pruefung liefert getpeercert() je nach Fassung ein leeres
    Ergebnis. Dann wenigstens die Rohdaten melden."""
    roh = s.getpeercert(binary_form=True)
    return {"_roh_bytes": len(roh or b"")}


def main() -> int:
    config.load_dotenv()
    host, port = _ziel()

    print("== Umgebung ==")
    print(f"Python           {sys.version.split()[0]} auf {sys.platform}")
    for q in tls.quellen():
        print(f"Zertifikatsquelle {q}")
    if not tls.certifi_bundle():
        print("HINWEIS: certifi ist nicht installiert - 'pip install certifi'.")
    try:
        print(f"Zertifikate im Speicher: {tls.context().cert_store_stats()['x509_ca']}")
    except Exception as e:
        print(f"Zertifikatsspeicher nicht lesbar: {e}")

    print(f"\n== Zertifikat von {host}:{port} ==")
    try:
        zert, kette = _blattzertifikat(host, port)
    except Exception as e:
        print(f"Verbindung nicht moeglich: {e}")
        print("Damit ist es kein Zertifikatsproblem, sondern die Leitung: Port "
              f"{port} wird vermutlich von einer Firewall gesperrt.")
        return 2

    print(f"ausgestellt fuer  {_name(zert.get('subject'))}")
    aussteller = _name(zert.get("issuer"))
    print(f"ausgestellt von   {aussteller}")
    if zert.get("notAfter"):
        print(f"gueltig bis       {zert['notAfter']}")
    if kette:
        print(f"mitgesendete Kette: {len(kette)} Zertifikat(e)")
        if len(kette) == 1:
            print("  Nur das eigene Zertifikat, kein Zwischenzertifikat. Wenn die "
                  "Pruefung unten scheitert, liegt es daran - dann kann nur der "
                  "Betreiber des Brokers es beheben.")

    print("\n== Pruefung mit den Einstellungen des Gateways ==")
    try:
        with socket.create_connection((host, port), timeout=10) as roh:
            with tls.context().wrap_socket(roh, server_hostname=host):
                print("Erfolgreich. Das Gateway kann sich verbinden.")
                return 0
    except ssl.SSLCertVerificationError as e:
        print(f"Fehlgeschlagen: {e}")
        print("\nWas jetzt zu tun ist:")
        print(f"  Der Aussteller lautet '{aussteller}'.")
        print("  - Ist das eine oeffentliche Zertifizierungsstelle (Let's Encrypt,")
        print("    DigiCert, Sectigo, GlobalSign ...): 'pip install --upgrade certifi'.")
        print("  - Ist das ein Virenscanner, eine Firewall oder die eigene Firma:")
        print("    Die Verbindung wird aufgebrochen. Deren Zertifikat exportieren")
        print("    (im Windows-Zertifikatsspeicher unter 'Vertrauenswuerdige")
        print("    Stammzertifizierungsstellen', Format Base-64/PEM) und den Pfad")
        print("    in die .env eintragen:  VOCO_CA_BUNDLE=C:\\Pfad\\zur\\datei.cer")
        return 1
    except Exception as e:
        print(f"Fehlgeschlagen: {e}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
