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
import tempfile
import urllib.request
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


def _entschluesseln(roh: bytes) -> dict:
    """DER-Zertifikat in dieselbe Form bringen, die getpeercert() liefert.

    Noetig, weil getpeercert() ein LEERES Ergebnis liefert, solange nicht
    geprueft wurde - und genau dann will man ja wissen, wer da ausgestellt hat.
    Python bringt keinen oeffentlichen Zertifikatsleser mit; die interne
    Hilfsfunktion tut es seit Langem und wird hier abgesichert benutzt.
    """
    try:
        pem = ssl.DER_cert_to_PEM_cert(roh)
        with tempfile.NamedTemporaryFile("w", suffix=".pem", delete=False) as f:
            f.write(pem)
            pfad = f.name
        try:
            return ssl._ssl._test_decode_cert(pfad)  # type: ignore[attr-defined]
        finally:
            os.unlink(pfad)
    except Exception:
        return {}


def _blattzertifikat(host: str, port: int):
    """Zertifikat und Kette holen, OHNE zu pruefen.

    Ohne diesen Schritt gaebe es bei einem Fehler nichts zu sehen - und der
    Aussteller ist genau die Angabe, die weiterhilft. Unbedenklich: Es wird
    nichts gesendet und nichts geglaubt, nur angesehen. Die eigentliche
    Verbindung des Gateways prueft weiterhin streng.
    """
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    with socket.create_connection((host, port), timeout=10) as roh:
        with ctx.wrap_socket(roh, server_hostname=host) as s:
            # Ab Python 3.13 gibt es die ungepruefte Kette samt Angaben.
            kette = getattr(s, "get_unverified_chain", lambda: None)()
            laenge = len(kette) if kette else None
            zert = {}
            if kette:
                try:
                    zert = kette[0].get_info()
                except Exception:
                    zert = {}
            if not zert:
                zert = _entschluesseln(s.getpeercert(binary_form=True) or b"")
            return zert, laenge


def _hole_aussteller(urls) -> bytes | None:
    """Das fehlende Zwischenzertifikat unter der im Zertifikat genannten
    Adresse laden. Genau das tun Browser von sich aus; Python nicht."""
    for url in urls or ():
        if not str(url).lower().startswith(("http://", "https://")):
            continue
        try:
            with urllib.request.urlopen(url, timeout=15) as antwort:
                daten = antwort.read(200_000)
            if daten:
                return daten
        except Exception as e:
            print(f"  {url} nicht ladbar: {e}")
    return None


def _als_pem(daten: bytes) -> str | None:
    """Geladenes Zertifikat in PEM umwandeln - egal ob es als PEM oder DER kam."""
    if daten.lstrip().startswith(b"-----BEGIN"):
        return daten.decode("ascii", "ignore")
    try:
        return ssl.DER_cert_to_PEM_cert(daten)
    except Exception:
        return None


def _prueft_mit(pem_zusatz: str | None, host: str, port: int) -> bool:
    """Gelingt die Pruefung, wenn das nachgeladene Zertifikat dazukommt?"""
    ctx = tls.context()
    if pem_zusatz:
        try:
            ctx.load_verify_locations(cadata=pem_zusatz)
        except Exception:
            return False
    try:
        with socket.create_connection((host, port), timeout=10) as roh:
            with ctx.wrap_socket(roh, server_hostname=host):
                return True
    except Exception:
        return False


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
    if kette is not None:
        print(f"mitgesendete Kette: {kette} Zertifikat(e)")

    print("\n== Pruefung mit den Einstellungen des Gateways ==")
    if _prueft_mit(None, host, port):
        print("Erfolgreich. Das Gateway kann sich verbinden.")
        return 0
    print("Fehlgeschlagen: das Zertifikat laesst sich nicht auf eine bekannte "
          "Stelle zurueckfuehren.")

    # Fehlt das Zwischenzertifikat, nennt das Zertifikat selbst die Adresse,
    # unter der es liegt ("caIssuers"). Browser laden es dort nach, Python
    # nicht - das ist der haeufigste Grund, warum eine Seite im Browser
    # funktioniert und derselbe Server im Programm scheitert.
    urls = zert.get("caIssuers")
    if urls:
        print("\n== Fehlendes Zwischenzertifikat ==")
        if kette == 1:
            print("Der Broker sendet nur sein eigenes Zertifikat.")
        print("Das Zwischenzertifikat wird jetzt an der im Zertifikat genannten")
        print("Adresse geholt und die Pruefung damit wiederholt.")
        daten = _hole_aussteller(urls)
        pem = _als_pem(daten) if daten else None
        if pem and _prueft_mit(pem, host, port):
            ziel = os.path.abspath("zwischenzertifikat.pem")
            # Ein bereits eingetragenes eigenes Bundle mit hineinschreiben:
            # VOCO_CA_BUNDLE nennt EINE Datei, und wer dort schon die eigene
            # Zertifizierungsstelle stehen hat, verloere sie sonst beim Wechsel
            # auf die neue Datei.
            vorher = tls.eigenes_bundle()
            with open(ziel, "w", encoding="ascii") as f:
                if vorher and os.path.abspath(vorher) != ziel:
                    try:
                        f.write(open(vorher, encoding="ascii", errors="ignore").read())
                        f.write("\n")
                        print(f"  Das bisherige Bundle ({vorher}) wurde uebernommen.")
                    except Exception as e:
                        print(f"  Achtung: bisheriges Bundle nicht lesbar ({e}) - "
                              "bitte von Hand anhaengen.")
                f.write(pem)
            print("\nDAS WAR ES. Mit dem nachgeladenen Zwischenzertifikat gelingt")
            print("die Pruefung. Es wurde gespeichert unter:")
            print(f"  {ziel}")
            print("\nDiese Zeile in die .env eintragen, dann laeuft das Gateway:")
            print(f"  VOCO_CA_BUNDLE={ziel}")
            print("\nGeprueft wird weiterhin vollstaendig: Das Zwischenzertifikat")
            print("muss selbst von einer bekannten Stelle unterschrieben sein,")
            print("sonst haette auch dieser Versuch nicht funktioniert.")
            return 0
        print("\nDas Nachladen hat nicht geholfen.")

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


if __name__ == "__main__":
    raise SystemExit(main())
