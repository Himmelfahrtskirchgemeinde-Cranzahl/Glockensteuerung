"""
Lebenszeichen des Gateway-Dienstes.

Der Gateway schreibt regelmaessig einen Zeitstempel nach ChurchTools. Die
Extension liest ihn und warnt, wenn er zu alt ist oder fehlt – sonst merkt
niemand, dass die Automatik steht, bis ein Gottesdienst stumm bleibt.

Ablage: dasselbe Custom-Module wie die uebrige Konfiguration, Kategorie
'steuerung', Schluessel 'gatewayStatus'. Bewusst 'steuerung': Diese Kategorie
darf jeder lesen, der das Modul bedienen darf – die Warnung soll alle
erreichen, nicht nur Administratoren.

Das Format entspricht dem, was die Extension schreibt (utils/kv-store.ts):
Das Feld 'value' ist ein JSON-STRING der Form {"key": …, "data": {…}}.
"""
from __future__ import annotations
import datetime as dt
import json
import logging

log = logging.getLogger("voco-gateway")

VALUE_KEY = "gatewayStatus"
CATEGORY_SHORTY = "steuerung"


class Heartbeat:
    """Schreibt das Lebenszeichen; loest Modul-, Kategorie- und Wert-ID selbst auf.

    Die IDs werden gemerkt, damit nicht bei jedem Schlag drei Zusatzabfragen
    anfallen. Schlaegt das Schreiben fehl, werden sie verworfen und beim
    naechsten Versuch neu aufgeloest – so uebersteht der Dienst auch ein
    geloeschtes und neu angelegtes Modul, ohne Neustart.
    """

    def __init__(self, ct, ext_key: str):
        self.ct = ct
        self.ext_key = ext_key
        self._module_id: int | None = None
        self._category_id: int | None = None
        self._value_id: int | None = None
        # Fehler nur beim Zustandswechsel melden, sonst floetet der Dienst alle
        # zwei Minuten dieselbe Zeile ins Log (und der Notifier mailt sie).
        self._failing = False

    # --- IDs aufloesen -----------------------------------------------------
    def _resolve(self) -> None:
        if self._module_id is None:
            for m in self.ct.get("/custommodules"):
                if m.get("shorty") == self.ext_key:
                    self._module_id = m.get("id")
                    break
            if self._module_id is None:
                raise RuntimeError(
                    f"Custom-Module '{self.ext_key}' nicht gefunden – "
                    "die Extension muss einmal von einer berechtigten Person "
                    "geoeffnet worden sein, damit es angelegt wird."
                )

        if self._category_id is None:
            cats = self.ct.get(f"/custommodules/{self._module_id}/customdatacategories")
            for c in cats:
                if c.get("shorty") == CATEGORY_SHORTY:
                    self._category_id = c.get("id")
                    break
            if self._category_id is None:
                raise RuntimeError(f"Kategorie '{CATEGORY_SHORTY}' im Modul nicht gefunden.")

        if self._value_id is None:
            # Vorhandenen Eintrag suchen – sonst entsteht bei jedem Schlag ein
            # neuer und die Kategorie laeuft voll.
            vals = self.ct.get(
                f"/custommodules/{self._module_id}"
                f"/customdatacategories/{self._category_id}/customdatavalues"
            )
            for v in vals:
                if _key_of(v) == VALUE_KEY:
                    self._value_id = v.get("id")
                    break

    # --- Schreiben ---------------------------------------------------------
    def send(self, *, rules: int, simulation: bool, device: str) -> bool:
        """Schreibt einen Schlag. Gibt zurueck, ob es geklappt hat.

        Wirft NIE – ein fehlendes Lebenszeichen darf den Laeutebetrieb nicht
        anhalten. Genau dafuer ist es ja da.
        """
        payload = {
            "at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "rules": rules,
            "simulation": simulation,
            "device": device,
        }
        try:
            self._resolve()
            body = {"value": json.dumps({"key": VALUE_KEY, "data": payload})}
            base = (f"/custommodules/{self._module_id}"
                    f"/customdatacategories/{self._category_id}/customdatavalues")
            if self._value_id:
                self.ct.put(f"{base}/{self._value_id}", body)
            else:
                created = self.ct.post(base, {"dataCategoryId": self._category_id, **body})
                if isinstance(created, dict):
                    self._value_id = created.get("id")
            if self._failing:
                log.info("Lebenszeichen wird wieder geschrieben.")
                self._failing = False
            return True
        except Exception as e:
            # Bewusst WARNING statt ERROR: Der Notifier verschickt ERROR per
            # Mail – bei anhaltender Stoerung alle zwei Minuten eine.
            if not self._failing:
                log.warning(
                    "Lebenszeichen konnte nicht geschrieben werden (%s). Die Extension "
                    "wird die Automatik als nicht erreichbar melden, gelaeutet wird "
                    "trotzdem weiter.", e
                )
                self._failing = True
            # IDs verwerfen: Modul/Kategorie/Wert koennten geloescht worden sein.
            self._module_id = self._category_id = self._value_id = None
            return False


def _key_of(v: dict) -> str:
    """Schluessel eines KV-Eintrags – je nach API-Version flach oder in 'value'."""
    if v.get("key"):
        return str(v["key"])
    raw = v.get("value")
    if isinstance(raw, str):
        try:
            return str(json.loads(raw).get("key", ""))
        except Exception:
            return ""
    if isinstance(raw, dict):
        return str(raw.get("key", ""))
    return ""


def mask_serial(serial: str) -> str:
    """'VH-001085' -> 'VH-***085'. Die Seriennummer ist ein Geraete-Merkmal;
    fuer die blosse Anzeige „welches Geraet bedient der Dienst" reicht das."""
    s = (serial or "").strip()
    return s[:3] + "***" + s[-3:] if len(s) > 6 else ("***" if s else "")
