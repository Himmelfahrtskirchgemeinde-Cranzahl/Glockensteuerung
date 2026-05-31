#!/usr/bin/env bash
# Entdeckt offene Ports/Dienste der VOCO-futura ST5 im lokalen Netz.
# LOKAL auf dem Gateway-PC ausfuehren (gleiches Netz wie die ST5), nicht in der Cloud.
#
# Nutzung:   ./scan_st5.sh [IP]
# Beispiel:  ./scan_st5.sh 192.168.178.151
#
# Voraussetzung: nmap installiert (Linux: sudo apt install nmap | macOS: brew install nmap).
# Ausgabe komplett kopieren und im Chat einfuegen.

set -u
IP="${1:-192.168.178.151}"

echo "=================================================="
echo " VOCO-futura ST5 – Netzwerk-Discovery"
echo " Ziel-IP: $IP    Datum: $(date)"
echo "=================================================="

echo
echo "### 1) Erreichbarkeit (Ping) ###"
ping -c 3 "$IP"

echo
echo "### 2) Alle TCP-Ports + Dienst-/Versionserkennung ###"
echo "(Hinweis: 'sudo' liefert genauere Ergebnisse)"
nmap -p- -sV --reason -T4 "$IP"

echo
echo "### 3) Default-Skripte auf offenen Ports (Banner/Details) ###"
nmap -sV -sC "$IP"

echo
echo "### 4) Wichtigste UDP-Ports (inkl. mDNS 5353, SSDP 1900) ###"
echo "(braucht i.d.R. sudo)"
nmap -sU --top-ports 50 "$IP"

echo
echo "### 5) HTTP/HTTPS-Schnelltest auf gaengigen Web-Ports ###"
for p in 80 443 8080 8443; do
  echo "--- Port $p ---"
  curl -k -s -m 5 -i "http://$IP:$p/" 2>/dev/null | head -n 20
  [ "$p" = 443 -o "$p" = 8443 ] && curl -k -s -m 5 -i "https://$IP:$p/" 2>/dev/null | head -n 20
done

echo
echo "### 6) mDNS-Dienste im Netz (falls Tools vorhanden) ###"
command -v avahi-browse >/dev/null && timeout 8 avahi-browse -at 2>/dev/null
command -v dns-sd       >/dev/null && (dns-sd -B _services._dns-sd._udp local. & sleep 6; kill %1 2>/dev/null)

echo
echo "=================================================="
echo " Fertig. Bitte die GESAMTE Ausgabe oben kopieren."
echo "=================================================="
