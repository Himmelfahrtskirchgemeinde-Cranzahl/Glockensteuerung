"""
Minimaler ChurchTools-API-Client fuer den Gateway-Dienst.

Auth per Login-Token (ChurchTools: Einstellungen > ... > Login-Token eines
technischen Benutzers). Endpunkte/Felder ggf. gegen die Swagger-Doku der
eigenen Instanz pruefen: https://<gemeinde>.church.tools/api
"""
from __future__ import annotations
import datetime as dt
import requests


class ChurchTools:
    def __init__(self, base_url: str, login_token: str, timeout: int = 15):
        self.base = base_url.rstrip("/")
        self.api = self.base + "/api"
        self.timeout = timeout
        self.s = requests.Session()
        self.s.headers["Accept"] = "application/json"
        # Session per Login-Token etablieren (setzt Cookie)
        r = self.s.get(f"{self.api}/whoami", params={"login_token": login_token}, timeout=timeout)
        r.raise_for_status()

    def get(self, path: str, **params):
        r = self.s.get(self.api + path, params=params, timeout=self.timeout)
        r.raise_for_status()
        return self._unwrap(r)

    def post(self, path: str, json: dict | None = None):
        r = self.s.post(self.api + path, json=json, timeout=self.timeout)
        r.raise_for_status()
        return self._unwrap(r)

    def put(self, path: str, json: dict | None = None):
        r = self.s.put(self.api + path, json=json, timeout=self.timeout)
        r.raise_for_status()
        return self._unwrap(r)

    @staticmethod
    def _unwrap(r):
        """ChurchTools verpackt Nutzdaten in {"data": …} – auspacken, wenn da."""
        try:
            j = r.json()
        except ValueError:
            return None          # z. B. 204 ohne Inhalt
        return j.get("data", j) if isinstance(j, dict) else j

    # --- Kalender / Termine ---
    def calendars(self):
        return self.get("/calendars")

    def appointments(self, calendar_ids: list[int], frm: dt.date, to: dt.date):
        """Termine (Kalender-Appointments) im Zeitraum. Rueckgabe: normalisierte Liste."""
        if not calendar_ids:
            return []
        params = {"from": frm.isoformat(), "to": to.isoformat()}
        # ChurchTools erlaubt Sammelabruf ueber calendar_ids[]
        for i, cid in enumerate(calendar_ids):
            params[f"calendar_ids[{i}]"] = cid
        try:
            raw = self.get("/calendars/appointments", **params)
        except Exception:
            # Fallback: pro Kalender einzeln
            raw = []
            for cid in calendar_ids:
                try:
                    raw += self.get(f"/calendars/{cid}/appointments", **{"from": frm.isoformat(), "to": to.isoformat()})
                except Exception:
                    pass
        return [_norm_appointment(a) for a in raw if a]


def _parse_dt(s):
    if not s:
        return None
    try:
        return dt.datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except Exception:
        return None


def _norm_appointment(a: dict) -> dict:
    """Normalisiert EIN Termin-Vorkommen aus /calendars/appointments.

    Die API liefert je Vorkommen {"appointment": {"base": …, "calculated": …}}.
    Aeltere/abweichende Antworten sind flach oder haben "base" direkt – alle
    drei Formen werden hier abgedeckt (die Extension tut dasselbe).
    """
    inner = a.get("appointment") if isinstance(a.get("appointment"), dict) else a
    base = inner.get("base") if isinstance(inner.get("base"), dict) else inner
    calc = inner.get("calculated") if isinstance(inner.get("calculated"), dict) else {}
    cal = base.get("calendar") or a.get("calendar") or {}
    # Bei SERIENTERMINEN traegt base.startDate den Beginn der SERIE (oft Jahre
    # her) – das Datum dieses Vorkommens steht in calculated.startDate. Erst
    # dort nachsehen, sonst faellt jeder Serientermin aus dem Zeitfenster und
    # wird nie ausgeloest.
    start = _parse_dt(calc.get("startDate") or base.get("startDate"))
    return {
        "kind": "appointment",
        "id": str(base.get("id") or a.get("id") or ""),
        "title": (base.get("title") or base.get("caption") or "").strip(),
        "start": start,
        "calendarId": (cal.get("id") if isinstance(cal, dict) else cal),
    }
