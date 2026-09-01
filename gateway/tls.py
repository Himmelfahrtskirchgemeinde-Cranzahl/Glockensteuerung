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


# --- Fehlendes Zwischenzertifikat ------------------------------------------
#
# hew-voco.de sendet nur sein eigenes Zertifikat, nicht das der ausstellenden
# Zwischenstelle (Sectigo). Browser holen das fehlende Glied selbstaendig an der
# Adresse nach, die im Zertifikat steht ("caIssuers"); Python tut das nicht.
# Deshalb scheitert die Pruefung im Programm, waehrend im Browser alles laeuft.
#
# Der Dienst holt es jetzt ebenfalls - einmal, und legt es daneben ab. Beim
# naechsten Start reicht die Datei, es wird nichts mehr geladen. Die Pruefung
# bleibt vollstaendig: Das nachgeladene Zertifikat muss selbst von einer
# bekannten Stelle unterschrieben sein, sonst nuetzt es nichts.

ZWISCHEN_DATEI = "zwischenzertifikat.pem"

_kontexte: dict[tuple[str, int], ssl.SSLContext] = {}


def zwischenspeicher() -> str:
    """Ablage fuer das nachgeladene Zwischenzertifikat - neben den Modulen."""
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), ZWISCHEN_DATEI)


def _handschlag(ctx: ssl.SSLContext, host: str, port: int, timeout: float = 10.0) -> str:
    """Probeverbindung. Gibt 'ok', 'zertifikat' oder 'anderes' zurueck.

    Die Unterscheidung ist wichtig: Nachgeladen wird nur bei einem
    ZERTIFIKATSfehler. Ein Netzproblem oder ein Server, der an diesem Port gar
    kein TLS spricht (STARTTLS beginnt im Klartext), darf keinen Abruf ausloesen.
    Es wird nichts gesendet, nur verbunden.
    """
    import socket
    try:
        with socket.create_connection((host, port), timeout=timeout) as roh:
            with ctx.wrap_socket(roh, server_hostname=host):
                return "ok"
    except ssl.SSLCertVerificationError:
        return "zertifikat"
    except Exception:
        return "anderes"


def aussteller_urls(host: str, port: int, timeout: float = 10.0):
    """Adressen, unter denen das Zertifikat sein Ausstellerzertifikat verortet."""
    import socket
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    try:
        with socket.create_connection((host, port), timeout=timeout) as roh:
            with ctx.wrap_socket(roh, server_hostname=host) as s:
                kette = getattr(s, "get_unverified_chain", lambda: None)()
                if kette:
                    try:
                        return tuple(kette[0].get_info().get("caIssuers") or ()), len(kette)
                    except Exception:
                        pass
                info = _lies_zertifikat(s.getpeercert(binary_form=True) or b"")
                return tuple(info.get("caIssuers") or ()), (len(kette) if kette else None)
    except Exception:
        return (), None


def _lies_zertifikat(roh: bytes) -> dict:
    """DER-Zertifikat lesen. getpeercert() liefert ohne Pruefung nichts, und
    genau dann braucht man die Angaben."""
    if not roh:
        return {}
    import tempfile
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


def hole_aussteller(urls, timeout: float = 15.0) -> str | None:
    """Ausstellerzertifikat laden und als PEM zurueckgeben."""
    import urllib.request
    for url in urls or ():
        if not str(url).lower().startswith(("http://", "https://")):
            continue
        try:
            with urllib.request.urlopen(url, timeout=timeout) as antwort:
                daten = antwort.read(200_000)
        except Exception as e:
            log.warning("Ausstellerzertifikat unter %s nicht ladbar: %s", url, e)
            continue
        if not daten:
            continue
        if daten.lstrip().startswith(b"-----BEGIN"):
            return daten.decode("ascii", "ignore")
        try:
            return ssl.DER_cert_to_PEM_cert(daten)
        except Exception:
            continue
    return None


def context_fuer(host: str, port: int) -> ssl.SSLContext:
    """Kontext fuer genau diese Gegenstelle - notfalls mit nachgeladenem Glied.

    Reihenfolge, damit im Regelfall nichts Zusaetzliches passiert:
      1. Liegt die Datei schon da, wird sie geladen. Fertig, kein Netzverkehr.
      2. Sonst wird die Pruefung einmal vorab versucht. Gelingt sie, fertig.
      3. Erst wenn sie scheitert, wird das Ausstellerzertifikat geholt, geprueft
         und - wenn es hilft - abgelegt.
    Schlaegt etwas davon fehl, kommt der gewoehnliche Kontext zurueck: Dann
    scheitert der Verbindungsaufbau mit seiner eigenen, deutlichen Meldung.
    """
    schluessel = (host, int(port))
    fertig = _kontexte.get(schluessel)
    if fertig is not None:
        return fertig

    ctx = context()
    datei = zwischenspeicher()
    if os.path.exists(datei):
        try:
            ctx.load_verify_locations(cafile=datei)
            _kontexte[schluessel] = ctx
            return ctx
        except Exception as e:
            log.warning("Abgelegtes Zwischenzertifikat unbrauchbar (%s) - wird erneuert.", e)

    if _handschlag(ctx, host, port) != "zertifikat":
        # 'ok' - alles in Ordnung. 'anderes' - kein Zertifikatsproblem, dann
        # waere ein Abruf sinnlos; der Verbindungsaufbau meldet den Grund selbst.
        _kontexte[schluessel] = ctx
        return ctx

    urls, _ = aussteller_urls(host, port)
    pem = hole_aussteller(urls) if urls else None
    if pem:
        try:
            probe = context()
            probe.load_verify_locations(cadata=pem)
            if _handschlag(probe, host, port) == "ok":
                try:
                    with open(datei, "w", encoding="ascii") as f:
                        f.write(pem)
                    log.info("Fehlendes Zwischenzertifikat von %s geholt und unter "
                             "%s abgelegt.", host, datei)
                except Exception as e:
                    log.warning("Zwischenzertifikat konnte nicht abgelegt werden "
                                "(%s) - es wird bei jedem Start neu geholt.", e)
                _kontexte[schluessel] = probe
                return probe
        except Exception as e:
            log.warning("Nachgeladenes Zertifikat unbrauchbar: %s", e)

    _kontexte[schluessel] = ctx
    return ctx
