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
import os
import ssl
import sys
import time

try:
    import paho.mqtt.client as mqtt
except ImportError:
    sys.exit("Fehlt: paho-mqtt  ->  pip install paho-mqtt")

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
    def __init__(self):
        self.serial = _req("VOCO_SERIAL")
        self.devpw = _req("VOCO_DEVICE_PW")
        self.host = os.environ.get("VOCO_BROKER_HOST", "hew-voco.de")
        self.port = int(os.environ.get("VOCO_BROKER_PORT", "8084"))
        user = os.environ.get("VOCO_BROKER_USER", "hewWeb")
        pw = os.environ.get("VOCO_BROKER_PASS", "vocoWeb")
        ws_path = os.environ.get("VOCO_WS_PATH", "/mqtt")
        self.base = f"hew/voco/{self.serial}{self.devpw}"

        self.online = None
        self.play_raw = []      # rohe, startbare PGS-Namen
        self.stop_raw = []      # rohe, stoppbare PGS-Namen
        self._got_list = False

        cid = f"{self.serial}-web-ct"
        self.c = mqtt.Client(client_id=cid, transport="websockets",
                             clean_session=True)
        self.c.ws_set_options(path=ws_path)
        self.c.username_pw_set(user, pw)
        self.c.tls_set(cert_reqs=ssl.CERT_REQUIRED)
        self.c.on_connect = self._on_connect
        self.c.on_message = self._on_message

    def connect(self, timeout=10):
        self.c.connect(self.host, self.port, keepalive=600)
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
    def _on_connect(self, client, userdata, flags, rc, *a):
        client.subscribe(self.base + "/#")

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
