"""Acceso privilegiado a ficheros que viven en carpetas del usuario.

`centrod` corre como root y su configuracion esta en el HOME del usuario, es
decir dentro de una carpeta donde ese usuario escribe. Abrir esa ruta por su
nombre —`open("/home/x/.config/centro/centro.conf")`— deja que el usuario
ponga ahi un enlace simbolico y consiga que root lea, trunque o cambie de
dueño cualquier fichero del sistema. Es una escalada de privilegios local, no
un detalle de estilo.

La regla de esta casa: **la carpeta se abre UNA vez, comprobando componente a
componente, y a partir de ahi todo se hace relativo a ese descriptor y sin
seguir enlaces.** Un descriptor apunta al inodo, no al nombre: aunque despues
renombren la carpeta o dejen un enlace en su sitio, seguimos escribiendo donde
abrimos, y nunca en otro lado.
"""
import os, stat, errno, secrets

# Un fichero de configuracion son cuatro lineas. Si hay mas de esto, alguien
# esta intentando que root se trague algo raro.
TOPE_BYTES = 256 * 1024

_ABRIR = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC


class Inseguro(Exception):
    """La ruta no cumple lo que se le exige; no se toca y punto."""


def _comprobar(st, uid, quiero_dir):
    if quiero_dir and not stat.S_ISDIR(st.st_mode):
        raise Inseguro("no es una carpeta")
    if not quiero_dir and not stat.S_ISREG(st.st_mode):
        raise Inseguro("no es un fichero normal")
    # De root o del propio usuario. Cualquier otro dueño en el camino
    # significa que un tercero manda sobre lo que vamos a abrir.
    if st.st_uid not in (0, uid):
        raise Inseguro(f"dueño inesperado (uid {st.st_uid})")
    # Escribible por todo el mundo y sin el bit pegajoso: cualquiera podria
    # sustituir lo que hay dentro.
    if st.st_mode & stat.S_IWOTH and not st.st_mode & stat.S_ISVTX:
        raise Inseguro("carpeta escribible por cualquiera")


def _abrir_hijo(dfd, nombre, uid):
    fd = os.open(nombre, _ABRIR | os.O_DIRECTORY, dir_fd=dfd)
    try:
        _comprobar(os.fstat(fd), uid, quiero_dir=True)
    except Exception:
        os.close(fd)
        raise
    return fd


def abrir_carpeta(ruta, uid, gid=None, crear=False):
    """Devuelve el descriptor de `ruta`, recorrida desde la raiz y validando
    cada componente. `crear` fabrica los que falten, del usuario y con 755."""
    dfd = os.open("/", _ABRIR | os.O_DIRECTORY)
    try:
        for parte in ruta.strip("/").split("/"):
            try:
                nuevo = _abrir_hijo(dfd, parte, uid)
            except FileNotFoundError:
                if not crear:
                    raise
                os.mkdir(parte, 0o755, dir_fd=dfd)
                nuevo = _abrir_hijo(dfd, parte, uid)
                if gid is not None:
                    os.fchown(nuevo, uid, gid)
            os.close(dfd)
            dfd = nuevo
    except Exception:
        os.close(dfd)
        raise
    return dfd


class Fichero:
    """Un fichero del usuario, anclado al descriptor de su carpeta."""

    def __init__(self, dfd, nombre, uid, gid):
        self.dfd, self.nombre, self.uid, self.gid = dfd, nombre, uid, gid

    # La carpeta por la que puede preguntar inotify. El enlace magico de
    # /proc apunta al inodo que ya validamos, no a la ruta por su nombre.
    @property
    def carpeta_vigilable(self):
        return f"/proc/self/fd/{self.dfd}"

    def leer_texto(self, defecto=""):
        try:
            fd = os.open(self.nombre, _ABRIR, dir_fd=self.dfd)
        except OSError:
            return defecto
        try:
            st = os.fstat(fd)
            _comprobar(st, self.uid, quiero_dir=False)
            # Un enlace duro a un fichero de root pasaria el O_NOFOLLOW; no
            # pasa esto.
            if st.st_nlink != 1:
                raise Inseguro("el fichero tiene mas de un nombre")
            if st.st_size > TOPE_BYTES:
                raise Inseguro("demasiado grande")
            return os.read(fd, TOPE_BYTES).decode("utf-8", "replace")
        except (OSError, Inseguro):
            return defecto
        finally:
            os.close(fd)

    def escribir_texto(self, texto):
        """Guarda de forma atomica: temporal con nombre imprevisible, creado
        en exclusiva y sin seguir enlaces, con su dueño puesto por descriptor
        —antes del renombrado, para que no haya carrera que aprovechar— y
        encima del destino sin soltar la carpeta."""
        tmp = f".{self.nombre}.{secrets.token_hex(8)}"
        try:
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL
                         | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600, dir_fd=self.dfd)
        except OSError:
            return False
        try:
            os.write(fd, texto.encode())
            # Los permisos ANTES del dueño: en cuanto el fichero es del
            # usuario, root ya no puede cambiarle el modo sin CAP_FOWNER, y
            # el objetivo es que el demonio no necesite esa capacidad.
            os.fchmod(fd, 0o644)
            os.fchown(fd, self.uid, self.gid)
            os.fsync(fd)
            os.close(fd)
            fd = None
            os.replace(tmp, self.nombre, src_dir_fd=self.dfd, dst_dir_fd=self.dfd)
            os.fsync(self.dfd)
            return True
        except OSError:
            try:
                os.unlink(tmp, dir_fd=self.dfd)
            except OSError:
                pass
            return False
        finally:
            if fd is not None:
                os.close(fd)


# ── Programas que lanza root ────────────────────────────────────────────────
# Por nombre suelto los buscaria el PATH, y el PATH se hereda. Se resuelven
# una vez contra carpetas del sistema y se comprueba que son de root.

_FIABLES = ("/usr/bin", "/bin", "/usr/sbin", "/sbin")


def programa(nombre):
    """Ruta absoluta de confianza, o None si no aparece."""
    for d in _FIABLES:
        p = os.path.join(d, nombre)
        try:
            st = os.stat(p)
        except OSError:
            continue
        if (stat.S_ISREG(st.st_mode) and st.st_uid == 0
                and not st.st_mode & stat.S_IWOTH
                and st.st_mode & stat.S_IXUSR):
            return p
    return None
