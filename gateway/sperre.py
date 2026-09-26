"""
Nur ein Gateway darf laufen.

Zwei gleichzeitig laufende Dienste loesen dasselbe Gelaeut zweimal aus - und
das faellt nicht im Protokoll auf, sondern im Dorf. Der Fall ist nicht
konstruiert: Nach dem Umstieg auf die Programmdatei kann die alte Einrichtung
weiterlaufen (eine Aufgabe in der Aufgabenplanung, ein von Hand gestartetes
'python scheduler.py', ein zweites Fenster mit dem Testlauf).

Gesichert wird mit den Mitteln des Systems, nicht mit einer selbstgebauten
Datei voller Prozessnummern: Unter Windows ein benannter Mutex, sonst eine
Dateisperre. Beides verschwindet, wenn der Prozess endet - auch wenn er
abstuerzt. Eine Datei mit einer PID darin bliebe liegen und spraeche fuer
immer von einem Dienst, den es nicht mehr gibt.
"""
from __future__ import annotations
import logging
import os

log = logging.getLogger("voco-gateway")

# Der Name gilt rechnerweit ("Global\\"), damit auch ein Dienst (Sitzung 0) und
# ein angemeldeter Benutzer einander sehen. Genau diese Kombination ist der
# haeufige Fall: Der Dienst laeuft, und jemand startet zusaetzlich von Hand.
MUTEX_NAME = "Global\\Glockensteuerung-Gateway"
SPERRDATEI = "gateway.lock"

_halter = None          # haelt Mutex bzw. Datei offen, solange der Dienst laeuft


# Jeder darf den Mutex oeffnen. Ohne das legt der Dienst (als System) ein
# Objekt an, das ein angemeldeter Benutzer nicht einmal ansehen darf - sein
# CreateMutexW scheitert dann mit "Zugriff verweigert" statt mit "gibt es
# schon". Genau der Fall, den die Sperre erkennen soll, blieb so unerkannt.
_SDDL_JEDER = "D:(A;;GA;;;WD)"
ERROR_ACCESS_DENIED = 5
ERROR_FILE_NOT_FOUND = 2
ERROR_ALREADY_EXISTS = 183
SYNCHRONIZE = 0x00100000


def _sicherheit(ctypes, wintypes):
    """SECURITY_ATTRIBUTES, die jedem den Zugriff erlauben - oder None."""
    try:
        advapi = ctypes.WinDLL("advapi32", use_last_error=True)
        sd = ctypes.c_void_p()
        ok = advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW(
            ctypes.c_wchar_p(_SDDL_JEDER), 1, ctypes.byref(sd), None)
        if not ok:
            return None

        class SA(ctypes.Structure):
            _fields_ = [("nLength", wintypes.DWORD),
                        ("lpSecurityDescriptor", ctypes.c_void_p),
                        ("bInheritHandle", wintypes.BOOL)]

        return SA(ctypes.sizeof(SA), sd, False)
    except Exception:
        return None                      # dann eben mit den Standardrechten


def _laeuft_schon(ctypes, kernel32) -> bool:
    """Gibt es den Mutex, obwohl wir ihn nicht anlegen durften?

    Auf ein Objekt, das es nicht gibt, antwortet Windows mit "nicht gefunden".
    Kommt dagegen wieder "Zugriff verweigert", ist es da - und dann laeuft ein
    Gateway unter einem anderen Konto.
    """
    kernel32.OpenMutexW.restype = ctypes.c_void_p
    handle = kernel32.OpenMutexW(SYNCHRONIZE, False, MUTEX_NAME)
    if handle:
        kernel32.CloseHandle(ctypes.c_void_p(handle))
        return True
    return ctypes.get_last_error() != ERROR_FILE_NOT_FOUND


def _windows_sperren() -> bool:
    import ctypes
    from ctypes import wintypes
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.restype = wintypes.HANDLE
    kernel32.CreateMutexW.argtypes = [wintypes.LPCVOID, wintypes.BOOL, wintypes.LPCWSTR]
    sa = _sicherheit(ctypes, wintypes)
    handle = kernel32.CreateMutexW(ctypes.byref(sa) if sa else None, True, MUTEX_NAME)
    fehler = ctypes.get_last_error()
    if not handle:
        if fehler == ERROR_ACCESS_DENIED and _laeuft_schon(ctypes, kernel32):
            return False
        # Ohne Mutex lieber weiterlaufen als gar nicht laeuten.
        log.warning("Mehrfachstart-Sperre nicht moeglich (Fehler %s).", fehler)
        return True
    if fehler == ERROR_ALREADY_EXISTS:
        kernel32.CloseHandle(handle)
        return False
    global _halter
    _halter = handle
    return True


def _datei_sperren() -> bool:
    import fcntl
    import pfade
    pfad = os.path.join(pfade.arbeitsordner(), SPERRDATEI)
    try:
        f = open(pfad, "w", encoding="utf-8")
        fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return False
    except Exception as e:
        log.warning("Mehrfachstart-Sperre nicht moeglich (%s).", e)
        return True
    f.write(str(os.getpid()))
    f.flush()
    global _halter
    _halter = f
    return True


def belegen() -> bool:
    """Versucht, der einzige laufende Gateway zu werden.

    Gibt True zurueck, wenn das geklappt hat - dann darf gelaeutet werden.
    False heisst: Es laeuft bereits einer, dieser Start muss sich zurueckziehen.
    """
    if _halter is not None:
        return True
    try:
        return _windows_sperren() if os.name == "nt" else _datei_sperren()
    except Exception as e:
        log.warning("Mehrfachstart-Sperre nicht moeglich (%s).", e)
        return True


def freigeben() -> None:
    global _halter
    if _halter is None:
        return
    try:
        if os.name == "nt":
            import ctypes
            ctypes.WinDLL("kernel32").CloseHandle(_halter)
        else:
            _halter.close()
    except Exception:
        pass
    _halter = None
