#!/usr/bin/env python3
"""
Erzeugt eine ChurchTools-taugliche ZIP der gebauten Extension.

Wichtig: Eintraege werden als DOS/FAT-Host (create_system=0) ohne jegliche
Unix-Rechte-Bits geschrieben. Manche ChurchTools-Instanzen werten Unix-Mode-Bits
(die Standard-`zip` setzt) als "executable file" und lehnen den Upload ab
("ccm.files.zip.contains.executable.file"). Ausserdem: keine Verzeichnis-
Eintraege, volle Dateinamen bleiben erhalten.

Aufruf:  python3 make_zip.py <dist-Verzeichnis> <ziel.zip>
"""
import os
import sys
import zipfile


def main(dist_dir: str, out_path: str) -> None:
    if os.path.exists(out_path):
        os.remove(out_path)
    count = 0
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as z:
        for root, _dirs, files in os.walk(dist_dir):
            for name in sorted(files):
                if name == ".DS_Store" or name.endswith(".map"):
                    continue
                full = os.path.join(root, name)
                rel = os.path.relpath(full, dist_dir).replace(os.sep, "/")
                info = zipfile.ZipInfo(rel)
                info.create_system = 0        # 0 = DOS/FAT -> keine Unix-Rechte
                info.external_attr = 0         # keine (auch keine ausfuehrbaren) Attribute
                info.compress_type = zipfile.ZIP_DEFLATED
                with open(full, "rb") as fh:
                    z.writestr(info, fh.read())
                count += 1
    print(f"ZIP geschrieben: {out_path} ({count} Dateien, DOS-Host, keine x-Bits)")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("Aufruf: python3 make_zip.py <dist> <ziel.zip>")
    main(sys.argv[1], sys.argv[2])
