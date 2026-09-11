import os, sys, tempfile, stat
sys.path.insert(0, "/mnt/datos/Work/centro/lib")
import seguro

uid, gid = os.getuid(), os.getgid()
base = tempfile.mkdtemp(prefix="centro-prueba-")
conf = os.path.join(base, ".config", "centro")
victima = os.path.join(base, "VICTIMA")
open(victima, "w").write("contenido de root que NO se debe tocar\n")

ok = lambda t: print(f"  ok   {t}")
mal = lambda t: (print(f"  MAL  {t}"), globals().__setitem__("fallos", fallos + 1))
fallos = 0

# 1 — uso normal
dfd = seguro.abrir_carpeta(conf, uid, gid, crear=True)
f = seguro.Fichero(dfd, "centro.conf", uid, gid)
f.escribir_texto("modo=juego\n")
print("1. uso normal")
ok("escribe y lee") if f.leer_texto() == "modo=juego\n" else mal("no lee lo escrito")
st = os.stat(os.path.join(conf, "centro.conf"))
ok("el fichero queda del usuario") if st.st_uid == uid else mal("dueño mal")
ok("no quedan temporales") if os.listdir(conf) == ["centro.conf"] else mal(f"sobra: {os.listdir(conf)}")

# 2 — el ataque del correo: centro.conf es un enlace a otro fichero
print("2. centro.conf sustituido por un enlace simbolico")
os.unlink(os.path.join(conf, "centro.conf"))
os.symlink(victima, os.path.join(conf, "centro.conf"))
ok("no lee a traves del enlace") if f.leer_texto() == "" else mal("LEYO la victima")
f.escribir_texto("modo=reposo\n")
cont = open(victima).read()
ok("la victima sigue intacta") if "NO se debe tocar" in cont else mal("VICTIMA MACHACADA")
ok("el enlace fue reemplazado por un fichero real") if not os.path.islink(os.path.join(conf, "centro.conf")) else mal("sigue siendo enlace")

# 3 — el temporal predecible ya no existe
print("3. temporal predecible")
os.symlink(victima, os.path.join(conf, "centro.conf.tmp"))
f.escribir_texto("modo=trabajo\n")
ok("no usa centro.conf.tmp") if "NO se debe tocar" in open(victima).read() else mal("VICTIMA MACHACADA por el .tmp")
os.unlink(os.path.join(conf, "centro.conf.tmp"))

# 4 — un componente de la ruta es un enlace
print("4. una carpeta del camino es un enlace")
base2 = tempfile.mkdtemp(prefix="centro-prueba2-")
os.symlink("/etc", os.path.join(base2, ".config"))
try:
    seguro.abrir_carpeta(os.path.join(base2, ".config", "centro"), uid, gid, crear=True)
    mal("acepto un enlace en el camino")
except (OSError, seguro.Inseguro) as e:
    ok(f"rechazado: {type(e).__name__}")

# 5 — enlace duro a un fichero de otro dueño
print("5. enlace duro")
try:
    os.link("/etc/hostname", os.path.join(conf, "centro.conf.duro"))
    g = seguro.Fichero(dfd, "centro.conf.duro", uid, gid)
    ok("no lee un enlace duro ajeno") if g.leer_texto() == "" else mal("LEYO el enlace duro")
except OSError as e:
    ok(f"el kernel ya lo impide ({e.strerror})")

# 6 — programas por ruta absoluta
print("6. programas")
p = seguro.programa("pgrep")
ok(f"pgrep -> {p}") if p and p.startswith("/") else mal("no resuelve pgrep")
ok("no inventa programas") if seguro.programa("no-existe-esto") is None else mal("invento uno")

print(f"\n{'TODO BIEN' if fallos == 0 else str(fallos) + ' FALLOS'}")
sys.exit(1 if fallos else 0)
