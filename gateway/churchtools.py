"""
Minimaler ChurchTools-API-Client fuer den Gateway-Dienst.

Auth per Login-Token (ChurchTools: Einstellungen > ... > Login-Token eines
technischen Benutzers). Endpunkte/Felder ggf. gegen die Swagger-Doku der
eigenen Instanz pruefen: https://<gemeinde>.church.tools/api
"""
from __future__ import annotations
import datetime as dt
import logging
import time

import requests

log = logging.getLogger("voco-gateway")

# Wie oft eine Anfrage wiederholt wird, bevor sie als gescheitert gilt, und wie
# lange dazwischen gewartet wird. Kurz gehalten: Der Dienst prueft ohnehin alle
# 20 Sekunden erneut, er darf nur nicht minutenlang im Versuch haengen.
VERSUCHE = 3
PAUSE_S = 2


class ChurchTools:
    """Spricht mit ChurchTools - und bleibt dabei ueber Wochen ansprechbar.

    Die Anmeldung per Login-Token setzt ein Sitzungs-Cookie, und dieses Cookie
    laeuft ab. Genau daran scheiterte der Dienst bisher im laufenden Betrieb:
    Nach einigen Stunden beantwortete ChurchTools jede Anfrage mit 401. Sichtbar
    wurde das als "keine Verbindung" in der Erweiterung und als "0 Automationen
    geplant" im Fenster - die Regeln liessen sich schlicht nicht mehr lesen.
    Deshalb wird der Token hier behalten und die Sitzung bei 401 neu aufgebaut;
    die Anfrage laeuft danach weiter, als waere nichts gewesen.

    Genauso behandelt werden kurze Netzaussetzer: Ein Zeitabbruch beendet nicht
    mehr den Dienst, sondern wird ein paar Mal wiederholt.
    """

    def __init__(self, base_url: str, login_token: str, timeout: int = 15):
        self.base = base_url.rstrip("/")
        self.api = self.base + "/api"
        self.timeout = timeout
        self._token = login_token
        self.s = requests.Session()
        self.s.headers["Accept"] = "application/json"
        self.benutzer = ""
        # Traegt die Sitzung nicht, wird das Token jeder Anfrage beigelegt.
        # Siehe anmelden().
        self._token_mitsenden = False
        self.anmelden()

    def anmelden(self) -> None:
        """Sitzung per Login-Token (neu) aufbauen - setzt das Cookie.

        Haelt fest, WER dabei herauskommt. Das ist keine Spielerei: Auf ein
        Token, das zu dieser Instanz nicht passt, antwortet ChurchTools nicht
        mit 401, sondern mit einer Sitzung ohne angemeldete Person - HTTP 200.
        Der Dienst lief dann weiter, sah aber nichts und meldete nur, das
        Custom-Module sei "nicht gefunden". Mit dem Namen im Protokoll ist in
        einem Blick klar, ob das Token greift.
        """
        r = self.s.get(f"{self.api}/whoami", params={"login_token": self._token},
                       timeout=self.timeout)
        r.raise_for_status()
        self.benutzer = self._person(self._unwrap(r))
        if self.benutzer:
            log.info("Bei ChurchTools angemeldet als %s.", self.benutzer)
            self._sitzung_pruefen()
        else:
            # Kein Abbruch: Vielleicht liefert eine kuenftige Fassung die
            # Angaben anders. Gesagt werden muss es trotzdem - ohne diesen
            # Hinweis sucht man den Fehler bei den Rechten statt beim Token.
            log.warning("Bei ChurchTools angemeldet, aber ohne erkennbare Person - "
                        "das Login-Token gilt fuer %s vermutlich nicht. Der Dienst "
                        "sieht dann weder Modul noch Regeln.", self.base)

    @staticmethod
    def _person(daten) -> str:
        """'Vorname Nachname (ID n)' aus einer whoami-Antwort - oder leer.

        Wer nicht angemeldet ist, bekommt von ChurchTools keine Absage,
        sondern einen Platzhalter ohne Namen und mit einer Kennung von 0 oder
        -1. Der gilt hier als "niemand" - sonst haette der Dienst sich selbst
        bestaetigt, angemeldet zu sein.
        """
        if not isinstance(daten, dict):
            return ""
        name = " ".join(x for x in (daten.get("firstName"), daten.get("lastName")) if x)
        try:
            kennung = int(daten.get("id"))
        except (TypeError, ValueError):
            kennung = 0
        if kennung <= 0:
            return ""
        return f"{name} (ID {kennung})" if name else f"ID {kennung}"

    def _sitzung_pruefen(self) -> None:
        """Traegt die Anmeldung ueber den ersten Aufruf hinaus?

        Die Anmeldung setzt ein Sitzungs-Cookie, und jede weitere Anfrage lebt
        davon. Kommt das Cookie nicht an - etwa weil die Adresse weiterleitet
        und es bei der Zieladresse landet -, ist der Dienst ab dem zweiten
        Aufruf wieder anonym. ChurchTools weist ihn dann nicht ab, sondern
        antwortet mit leeren Listen: keine Module, keine Regeln, kein
        Lebenszeichen. Von aussen sah das aus wie fehlende Rechte.

        Deshalb hier ein zweiter whoami-Aufruf, diesmal OHNE Token. Erkennt er
        dieselbe Person, traegt die Sitzung. Sonst legt der Dienst das Token
        jeder Anfrage bei - der Weg, den ChurchTools fuer Server dieser Art
        ohnehin vorsieht.
        """
        self._token_mitsenden = False
        self.s.headers.pop("Authorization", None)
        if self._traegt():
            return
        # Zweiter Weg, und der bessere: das Token im Kopf der Anfrage statt in
        # der Adresse. So steht es in keiner Adresse, die irgendwo mitgeschrieben
        # wird - weder hier noch bei ChurchTools.
        self.s.headers["Authorization"] = f"Login {self._token}"
        if self._traegt():
            log.warning("Die Anmeldung traegt nicht ueber den ersten Aufruf hinaus - "
                        "es kommt kein gueltiges Sitzungs-Cookie an. Der Dienst weist "
                        "sich deshalb bei jeder Anfrage im Kopf der Anfrage aus.")
            return
        # Letzter Weg: in der Adresse. Aeltere Faelle koennen den Kopf nicht.
        self.s.headers.pop("Authorization", None)
        self._token_mitsenden = True
        log.warning("Die Anmeldung traegt nicht ueber den ersten Aufruf hinaus - "
                    "es kommt kein gueltiges Sitzungs-Cookie an. Der Dienst legt "
                    "das Login-Token deshalb jeder Anfrage bei.")

    def _traegt(self) -> bool:
        """Erkennt ChurchTools den Dienst bei einem Aufruf ohne Token wieder?"""
        try:
            return bool(self._person(self._unwrap(
                self.s.get(f"{self.api}/whoami", timeout=self.timeout))))
        except Exception as e:
            log.debug("Sitzungspruefung nicht moeglich: %s", e)
            return False

    def _anfrage(self, methode: str, path: str, *, params=None, json=None):
        if self._token_mitsenden:
            params = dict(params or {})
            params.setdefault("login_token", self._token)
        letzter: Exception | None = None
        neu_angemeldet = False
        for versuch in range(VERSUCHE):
            try:
                r = self.s.request(methode, self.api + path, params=params, json=json,
                                   timeout=self.timeout)
            except requests.RequestException as e:
                # Netz weg, Namensaufloesung, Zeitabbruch: gleich noch einmal.
                letzter = e
                if versuch + 1 < VERSUCHE:
                    time.sleep(PAUSE_S * (versuch + 1))
                continue

            # 401 heisst hier fast immer: Die Sitzung ist abgelaufen. Einmal neu
            # anmelden und dieselbe Anfrage wiederholen. Nur einmal - kommt
            # danach wieder 401, stimmt etwas mit dem Token nicht, und stures
            # Wiederholen machte es nur schlimmer.
            if r.status_code == 401 and not neu_angemeldet:
                neu_angemeldet = True
                log.info("ChurchTools-Sitzung abgelaufen - melde neu an.")
                try:
                    self.anmelden()
                    continue
                except Exception as e:
                    letzter = e
                    if versuch + 1 < VERSUCHE:
                        time.sleep(PAUSE_S * (versuch + 1))
                    continue

            r.raise_for_status()
            return self._unwrap(r)

        raise letzter if letzter else RuntimeError(f"{methode} {path} fehlgeschlagen")

    def get(self, path: str, **params):
        return self._anfrage("GET", path, params=params)

    def post(self, path: str, json: dict | None = None):
        return self._anfrage("POST", path, json=json)

    def put(self, path: str, json: dict | None = None):
        return self._anfrage("PUT", path, json=json)

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
        except Exception as sammel_fehler:
            # Fallback: pro Kalender einzeln
            raw = []
            fehler = []
            for cid in calendar_ids:
                try:
                    raw += self.get(f"/calendars/{cid}/appointments",
                                    **{"from": frm.isoformat(), "to": to.isoformat()})
                except Exception as e:
                    fehler.append(e)
            # Ist ALLES gescheitert, ist die Antwort nicht "keine Termine",
            # sondern "unbekannt". Der Unterschied ist entscheidend: Eine leere
            # Liste loescht im Dienst den Ausloeseplan, ein Fehler laesst den
            # bisherigen Plan stehen. Ein zweiminuetiger Aussetzer der API darf
            # kein Gelaeut ausfallen lassen.
            if fehler and not raw:
                raise RuntimeError(
                    f"Termine konnten nicht geladen werden ({sammel_fehler}; "
                    f"auch einzeln nicht: {fehler[0]})") from sammel_fehler
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
