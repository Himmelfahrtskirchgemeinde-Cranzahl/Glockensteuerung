"""
Wurzelzertifikate fuer verschluesselte Verbindungen.

Python bringt unter Windows KEINE Wurzelzertifikate mit und benutzt auch nicht
den Windows-Zertifikatsspeicher. Wer dort nur `ssl.CERT_REQUIRED` verlangt, ohne
ein Bundle anzugeben, bekommt beim Verbindungsaufbau:

    ssl.SSLCertVerificationError: [SSL: CERTIFICATE_VERIFY_FAILED]
    certificate verify failed: unable to get local issuer certificate

Das traf sowohl den MQTT-Broker (wss://hew-voco.de) als auch den Postausgang.

'certifi' pflegt genau dieses Bundle und ist ohnehin installiert - 'requests'
bringt es mit, und der ChurchTools-Client nutzt es laengst. Hier wird es
zusaetzlich fuer MQTT und SMTP herangezogen.

Die Pruefung wird dabei NICHT abgeschaltet. Wer hinter einem Firmen-Proxy mit
eigener Zertifizierungsstelle arbeitet, hinterlegt deren Bundle in
VOCO_CA_BUNDLE - das bleibt sicher, weil weiterhin geprueft wird, nur eben
gegen die eigene Stelle.
"""
from __future__ import annotations
import os
import ssl


def ca_bundle() -> str | None:
    """Pfad zum Bundle mit Wurzelzertifikaten, oder None fuer Pythons Standard.

    Reihenfolge: eigenes Bundle aus VOCO_CA_BUNDLE, sonst das von certifi,
    sonst der Standard (der auf Linux/macOS meist funktioniert).
    """
    eigenes = os.environ.get("VOCO_CA_BUNDLE", "").strip()
    if eigenes and os.path.exists(eigenes):
        return eigenes
    try:
        import certifi
        return certifi.where()
    except Exception:
        return None


def context() -> ssl.SSLContext:
    """SSL-Kontext mit den Wurzelzertifikaten aus `ca_bundle()`."""
    return ssl.create_default_context(cafile=ca_bundle())
