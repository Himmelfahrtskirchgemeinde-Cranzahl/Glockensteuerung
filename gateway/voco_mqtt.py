#!/usr/bin/env python3
"""
VOCO-futura ST5 – Steuerung über MQTT (app.hew-voco.de).

Belegt aus dem Web-App-Quelltext, siehe docs/VOCO-MQTT-Protokoll.md.
Auf einem Gerät MIT Internet ausfuehren (Gateway-PC). Benoetigt: paho-mqtt
    pip install paho-mqtt

Konfiguration ueber Umgebungsvariablen / .env (NICHT committen):
    VOCO_SERIAL, VOCO_DEVICE_PW  (Pflicht, GEHEIM)
    VOCO_BROKER_HOST=hew-voco.de  VOCO_BROKER_PORT=8084
    VOCO_BROKER_USER=hewWeb        VOCO_BROKER_PASS=vocoWeb
    VOCO_WS_PATH=/mqtt

Sicherheit: 'start' loest ECHTES Laeuten aus -> nur mit --yes.

Beispiele:
    python voco_mqtt.py list
    python voco_mqtt.py status
    python voco_mqtt.py start "Gottesdienstgeläut" --yes
    python voco_mqtt.py stop ALL --yes
"""
import argparse
import logging
import os
import ssl

import tls
import sys
import time

try:
    import paho.mqtt.client as mqtt
except ImportError:
    sys.exit("Fehlt: paho-mqtt  ->  pip install paho-mqtt")

log = logging.getLogger("voco-gateway")

# Optionales .env-Laden (ohne Zusatzpaket)
def load_dotenv(path=".env"):
    if os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

load_dotenv()

# Sonderzeichen-Mapping (Steuerbyte -> Zeichen), nur fuer die ANZEIGE
DECODE = {0x24: ":", 0x25: "ß", 0x26: "Ä", 0x27: "Ö",
          0x28: "Ü", 0x29: "ä", 0x30: "ö", 0x31: "ü"}

def decode_name(raw: str) -> str:
    return "".join(DECODE.get(ord(c), c) for c in raw)


class Voco:
    def __init__(self, serial=None, device_pw=None, broker_url=None,
                 host=None, port=None, ws_path=None, user=None, password=None):
        self.serial = serial or _req("VOCO_SERIAL")
        self.devpw = device_pw or _req("VOCO_DEVICE_PW")
        # Broker-URL (wss://host:port/pfad) hat Vorrang, sonst Einzelwerte/ENV
        if broker_url:
            from urllib.parse import urlparse
            u = urlparse(broker_url)
            host = host or u.hostname
            port = port or u.port
            ws_path = ws_path or (u.path or "/mqtt")
        self.host = host or os.environ.get("VOCO_BROKER_HOST", "hew-voco.de")
        self.port = int(port or os.environ.get("VOCO_BROKER_PORT", "8084"))
        user = user or os.environ.get("VOCO_BROKER_USER", "hewWeb")
        pw = password or os.environ.get("VOCO_BROKER_PASS", "vocoWeb")
        ws_path = ws_path or os.environ.get("VOCO_WS_PATH", "/mqtt")
        self.base = f"hew/voco/{self.serial}{self.devpw}"

        self.online = None
        self.play_raw = []      # rohe, startbare PGS-Namen
        self.stop_raw = []      # rohe, stoppbare PGS-Namen
        self._got_list = False

        cid = f"{self.serial}-web-ct"
        # Callback-API Version 2 (paho-mqtt 2.x). Version 1 warnt bei jedem
        # Start, dass sie veraltet ist. Die Rueckrufe hier vertragen beide:
        # _on_connect faengt das zusaetzliche Argument mit *a ab, und weder der
        # Rueckgabecode noch die Flags werden ausgewertet. Aeltere
        # paho-Fassungen kennen den Parameter nicht - dann eben ohne.
        try:
            self.c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=cid,
                                 transport="websockets", clean_session=True)
        except (AttributeError, TypeError):
            self.c = mqtt.Client(client_id=cid, transport="websockets",
                                 clean_session=True)
        self.c.ws_set_options(path=ws_path)
        self.c.username_pw_set(user, pw)
        # Fertigen Kontext uebergeben statt eines einzelnen Bundle-Pfades:
        # 'tls_set(ca_certs=...)' laedt NUR diese eine Datei und schliesst den
        # Zertifikatsspeicher des Systems aus - dann scheitert der Aufbau, sobald
        # ein Virenscanner oder Firmen-Proxy die Verbindung aufbricht. Siehe
        # tls.py.
        self.c.tls_set_context(tls.context_fuer(self.host, self.port))
        self.c.on_connect = self._on_connect
        self.c.on_disconnect = self._on_disconnect
        self.c.on_message = self._on_message
        # Wird vom Dienst gesetzt, um Verbindungswechsel zu protokollieren.
        # Standardmaessig passiert nichts - das Kommandozeilenwerkzeug braucht
        # kein Protokoll in ChurchTools.
        self.on_zustand = None

    def connect(self, timeout=10):
        try:
            self.c.connect(self.host, self.port, keepalive=600)
        except ssl.SSLCertVerificationError as e:
            # Haeufigster Stolperstein unter Windows - die blosse
            # OpenSSL-Meldung hilft dabei niemandem weiter.
            raise RuntimeError(
                f"Das Zertifikat von {self.host} konnte nicht geprueft werden ({e}).\n"
                f"Geprueft wurde gegen: {', '.join(tls.quellen())}.\n"
                "Ein fehlendes Zwischenzertifikat wurde bereits vergeblich "
                "nachzuladen versucht.\n"
                "Was jetzt hilft, der Reihe nach:\n"
                "  1. 'python -m diagnose' im gateway-Ordner ausfuehren - das sagt, "
                "wer das Zertifikat ausgestellt hat.\n"
                "  2. Nennt die Ausgabe einen Virenscanner, eine Firewall oder die "
                "eigene Firma als Aussteller, wird die Verbindung aufgebrochen. Dann "
                "deren Zertifikat als Datei exportieren und den Pfad in "
                "VOCO_CA_BUNDLE eintragen.\n"
                "  3. 'pip install --upgrade certifi' bringt die oeffentlichen "
                "Wurzelzertifikate auf den neuesten Stand."
            ) from e
        self.c.loop_start()
        t0 = time.time()
        while self.c.is_connected() is False and time.time() - t0 < timeout:
            time.sleep(0.1)
        if not self.c.is_connected():
            raise SystemExit("Verbindung zum Broker fehlgeschlagen")

    def close(self):
        try:
            self.c.loop_stop(); self.c.disconnect()
        except Exception:
            pass

    # --- MQTT-Callbacks ---
    # Signatur passt fuer beide Callback-Fassungen: Version 2 reicht zusaetzlich
    # 'properties' herein, was *a auffaengt. rc und flags werden nicht benutzt.
    def _on_connect(self, client, userdata, flags, rc, *a):
        client.subscribe(self.base + "/#")
        self._melde_zustand(True)

    # Auch hier passt die Signatur fuer beide Callback-Fassungen: Version 2
    # reicht zusaetzlich Flags und Properties herein, die *a auffaengt.
    def _on_disconnect(self, client, userdata, rc, *a):
        self._melde_zustand(False)

    def _melde_zustand(self, verbunden: bool) -> None:
        """Verbindungswechsel weitermelden - ohne den MQTT-Faden zu gefaehrden.

        Der Rueckruf laeuft im Netzwerk-Faden von paho. Eine Ausnahme darin
        wuerde dort landen, wo sie niemand faengt; im schlimmsten Fall steht
        danach die Verbindung still. Deshalb hier abgefangen.
        """
        if not self.on_zustand:
            return
        try:
            self.on_zustand(verbunden)
        except Exception as e:
            log.warning("Zustandsmeldung fehlgeschlagen: %s", e)

    def _on_message(self, client, userdata, msg):
        topic = msg.topic[len(self.base):]  # fuehrendes Basis-Topic abschneiden
        payload = msg.payload.decode("latin1", "replace")
        if topic == "/connection":
            self.online = (payload == "1")
        elif topic == "/sendpgsD":
            self._parse_pgs_list(payload)
            self._got_list = True

    # --- Befehle ---
    def _pub(self, subtopic, payload):
        self.c.publish(self.base + subtopic, payload, qos=0, retain=False)

    def request_list(self, wait=4):
        self._got_list = False
        self._pub("/fetchinfo", "EN")
        self._pub("/playpgsD", "list")
        t0 = time.time()
        while not self._got_list and time.time() - t0 < wait:
            time.sleep(0.1)
        return self.play_raw

    def start(self, name_raw, when="INSTANT"):
        self._pub("/playpgsD", f"START:{name_raw}:{when}")

    def stop(self, name_raw):
        self._pub("/playpgsD", f"STOP:{name_raw}")

    def schlagwerk(self, on):   self._pub("/swD", "EN" if on else "DIS")
    def automatik(self, on):    self._pub("/autoD", "EN" if on else "DIS")

    # --- Parser fuer /sendpgsD (laengenpraefix-Format LL_<name>X) ---
    def _parse_pgs_list(self, payload):
        i = payload.find(":")
        if i < 0:
            return
        part_play, part_stop = payload[:i], payload[i + 1:]
        self.play_raw = _parse_lenprefixed(part_play)
        self.stop_raw = _parse_lenprefixed(part_stop)

    def resolve(self, user_name):
        """Findet den rohen Namen anhand des (dekodierten) Anzeigenamens."""
        for raw in self.play_raw:
            if decode_name(raw) == user_name or raw == user_name:
                return raw
        return None


def _parse_lenprefixed(s):
    """Format je Eintrag: 2-stellige Laenge + '_' + Name + 1 Trennzeichen."""
    out, idx = [], 0
    # optionaler Prefix wie "PGS: " kann vorne stehen -> erst ab erster Ziffernfolge
    while idx < len(s):
        # Prefixe ueberspringen
        for pre in ("Sofort PGS: ", "Uhrschlag: ", "Melodie: ", "PGS: "):
            if s[idx:idx + len(pre)] == pre:
                idx += len(pre)
                break
        if idx + 3 > len(s):
            break
        ln_str = s[idx:idx + 2]
        if not ln_str.isdigit():
            break
        ln = int(ln_str)
        name = s[idx + 3: idx + 3 + ln]
        out.append(name)
        idx += ln + 4
    return out


def _req(key):
    v = os.environ.get(key)
    if not v or v.startswith(("X", "x")) and set(v) <= set("Xx"):
        sys.exit(f"Umgebungsvariable {key} fehlt (siehe .env / .env.example)")
    return v


def main():
    ap = argparse.ArgumentParser(description="VOCO-futura ST5 MQTT-Client")
    ap.add_argument("command", choices=["list", "status", "start", "stop"])
    ap.add_argument("name", nargs="?", help="PGS-Name (fuer start/stop; stop ALL moeglich)")
    ap.add_argument("--yes", action="store_true", help="Bestaetigt start/stop (loest Laeuten aus)")
    ap.add_argument("--when", default="INSTANT", help="'INSTANT' oder Sekunden seit 0 Uhr")
    args = ap.parse_args()

    v = Voco()
    v.connect()
    try:
        # kurz auf Online-Status warten
        t0 = time.time()
        while v.online is None and time.time() - t0 < 3:
            time.sleep(0.1)

        if args.command == "status":
            print("Gerät online:", v.online)
            names = v.request_list()
            print("Startbare PGS:")
            for raw in names:
                print("  -", decode_name(raw))

        elif args.command == "list":
            names = v.request_list()
            if not names:
                print("(keine startbaren PGS empfangen – Gerät online?)")
            for raw in names:
                print("  -", decode_name(raw))

        elif args.command in ("start", "stop"):
            if not args.name:
                ap.error(f"'{args.command}' braucht einen PGS-Namen")
            if not args.yes:
                ap.error("ACHTUNG: loest echtes Laeuten aus. Mit --yes bestaetigen.")
            if args.command == "stop":
                target = "ALL" if args.name.upper() == "ALL" else args.name
                v.stop(target)
                print(f"STOP gesendet: {target}")
            else:
                v.request_list()
                raw = v.resolve(args.name) or args.name
                v.start(raw, args.when)
                print(f"START gesendet: {decode_name(raw)} ({args.when})")
            time.sleep(1)  # Nachricht rausschicken lassen
    finally:
        v.close()


if __name__ == "__main__":
    main()
