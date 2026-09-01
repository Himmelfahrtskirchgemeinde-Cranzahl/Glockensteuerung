"""
Zugriff auf den Schluessel-Wert-Speicher der Extension.

Die Extension legt ihre Daten in ChurchTools-Custom-Modules ab: ein Modul, darin
Kategorien, darin Eintraege. Das Feld 'value' eines Eintrags ist ein
JSON-STRING der Form {"key": …, "data": {…}} - so schreibt es die Extension
(utils/kv-store.ts), und so muss der Dienst es auch schreiben.

Hier steht das Gemeinsame: IDs aufloesen, lesen, schreiben. Lebenszeichen und
Ereignisse benutzen es beide.
"""
from __future__ import annotations
import json
import logging

log = logging.getLogger("voco-gateway")


class KV:
    """Ein Kategoriezugriff. Merkt sich die IDs, loest sie bei Fehlern neu auf.

    Das Merken spart drei Zusatzabfragen je Zugriff. Das Verwerfen im Fehlerfall
    sorgt dafuer, dass ein geloeschtes und neu angelegtes Modul den Dienst nicht
    dauerhaft lahmlegt - beim naechsten Versuch wird alles neu gesucht.
    """

    def __init__(self, ct, ext_key: str, kategorie: str):
        self.ct = ct
        self.ext_key = ext_key
        self.kategorie = kategorie
        self._modul_id: int | None = None
        self._kategorie_id: int | None = None
        self._wert_ids: dict[str, int] = {}

    # --- IDs ---------------------------------------------------------------
    def _basis(self) -> str:
        if self._modul_id is None:
            for m in self.ct.get("/custommodules"):
                if m.get("shorty") == self.ext_key:
                    self._modul_id = m.get("id")
                    break
            if self._modul_id is None:
                raise RuntimeError(
                    f"Custom-Module '{self.ext_key}' nicht gefunden - die Extension "
                    "muss einmal von einer berechtigten Person geoeffnet worden "
                    "sein, damit es angelegt wird."
                )
        if self._kategorie_id is None:
            for c in self.ct.get(f"/custommodules/{self._modul_id}/customdatacategories"):
                if c.get("shorty") == self.kategorie:
                    self._kategorie_id = c.get("id")
                    break
            if self._kategorie_id is None:
                raise RuntimeError(f"Kategorie '{self.kategorie}' im Modul nicht gefunden.")
        return (f"/custommodules/{self._modul_id}"
                f"/customdatacategories/{self._kategorie_id}/customdatavalues")

    def vergessen(self) -> None:
        """IDs verwerfen - beim naechsten Zugriff wird neu gesucht."""
        self._modul_id = self._kategorie_id = None
        self._wert_ids = {}

    # --- Lesen und Schreiben ----------------------------------------------
    def lesen(self, key: str):
        """Daten zu einem Schluessel, oder None. Merkt sich nebenbei die Wert-ID."""
        basis = self._basis()
        for v in self.ct.get(basis):
            if schluessel_von(v) == key:
                if v.get("id"):
                    self._wert_ids[key] = v["id"]
                return daten_von(v)
        return None

    def schreiben(self, key: str, data) -> None:
        """Daten unter einem Schluessel ablegen - anlegen oder ueberschreiben."""
        basis = self._basis()
        if key not in self._wert_ids:
            # Vorhandenen Eintrag suchen, sonst entstuende bei jedem Schreiben
            # ein neuer und die Kategorie liefe voll.
            for v in self.ct.get(basis):
                if schluessel_von(v) == key and v.get("id"):
                    self._wert_ids[key] = v["id"]
                    break
        koerper = {"value": json.dumps({"key": key, "data": data})}
        if key in self._wert_ids:
            self.ct.put(f"{basis}/{self._wert_ids[key]}", koerper)
        else:
            neu = self.ct.post(basis, {"dataCategoryId": self._kategorie_id, **koerper})
            if isinstance(neu, dict) and neu.get("id"):
                self._wert_ids[key] = neu["id"]


def schluessel_von(v: dict) -> str:
    """Schluessel eines Eintrags - je nach API-Fassung flach oder in 'value'."""
    if v.get("key"):
        return str(v["key"])
    roh = v.get("value")
    if isinstance(roh, str):
        try:
            return str(json.loads(roh).get("key", ""))
        except Exception:
            return ""
    if isinstance(roh, dict):
        return str(roh.get("key", ""))
    return ""


def daten_von(v: dict):
    """Nutzdaten eines Eintrags."""
    if "data" in v and v.get("key"):
        return v["data"]
    roh = v.get("value")
    if isinstance(roh, str):
        try:
            return json.loads(roh).get("data")
        except Exception:
            return None
    if isinstance(roh, dict):
        return roh.get("data")
    return None
