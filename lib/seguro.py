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
    try:
        fd = os.open(nombre, _ABRIR | os.O_DIRECTORY, dir_fd=dfd)
    except OSError as e:
        # Con O_NOFOLLOW un enlace da ELOOP, y si ademas se pidio O_DIRECTORY,
        # ENOTDIR. Merece un mensaje que se entienda: es EL ataque.
        if e.errno in (errno.ELOOP, errno.ENOTDIR):
            try:
                if stat.S_ISLNK(os.lstat(nombre, dir_fd=dfd).st_mode):
                    raise Inseguro(
                        f"«{nombre}» es un enlace simbolico; no se escribe a "
                        f"traves de enlaces. Quitalo y vuelve a intentarlo.")
            except OSError:
                pass
        raise
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
        return escribir_en(self.dfd, self.nombre, texto.encode(),
                           0o644, self.uid, self.gid)


def escribir_en(dfd, nombre, datos, modo, uid, gid):
    """Deja `datos` como `nombre` dentro de una carpeta YA validada.

    De forma atomica: temporal con nombre imprevisible, creado en exclusiva y
    sin seguir enlaces, con permisos y dueño puestos **sobre el descriptor y
    antes del renombrado** —asi no hay carrera que aprovechar ni hace falta
    CAP_FOWNER— y encima del destino sin soltar la carpeta.
    """
    tmp = f".{nombre}.{secrets.token_hex(8)}"
    try:
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL
                     | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600, dir_fd=dfd)
    except OSError:
        return False
    try:
        os.write(fd, datos)
        os.fchmod(fd, modo)
        os.fchown(fd, uid, gid)
        os.fsync(fd)
        os.close(fd)
        fd = None
        os.replace(tmp, nombre, src_dir_fd=dfd, dst_dir_fd=dfd)
        os.fsync(dfd)
        return True
    except OSError:
        try:
            os.unlink(tmp, dir_fd=dfd)
        except OSError:
            pass
        return False
    finally:
        if fd is not None:
            os.close(fd)


def existe_en(dfd, nombre):
    try:
        os.lstat(nombre, dir_fd=dfd)
        return True
    except OSError:
        return False


def borrar_en(dfd, nombre):
    """Quita `nombre` de una carpeta ya validada. Si es un enlace se borra el
    enlace, nunca lo que apunte: `unlink` no sigue enlaces."""
    try:
        st = os.lstat(nombre, dir_fd=dfd)
    except OSError:
        return False
    try:
        if stat.S_ISDIR(st.st_mode):
            hijo = os.open(nombre, _ABRIR | os.O_DIRECTORY, dir_fd=dfd)
            try:
                for n in os.listdir(hijo):
                    borrar_en(hijo, n)
            finally:
                os.close(hijo)
            os.rmdir(nombre, dir_fd=dfd)
        else:
            os.unlink(nombre, dir_fd=dfd)
        return True
    except OSError:
        return False


# ── Programas que lanza root ────────────────────────────────────────────────
# Por nombre suelto los busca el PATH, y el PATH se hereda. Se resuelven una
# vez, sin seguir enlaces a ciegas: cada carpeta del camino tiene que ser de
# root y no escribible ni por grupo ni por otros, y un enlace solo vale si es
# de root y apunta a un vecino de su misma carpeta ya validada.

_FIABLES = ("/usr/bin", "/usr/sbin", "/bin", "/sbin")
_MAX_SALTOS = 8

# Entorno minimo para lo que lanza root: nada heredado.
ENTORNO = {"PATH": "/usr/bin", "LC_ALL": "C.UTF-8"}


def _escribible_por_otros(st):
    return bool(st.st_mode & (stat.S_IWGRP | stat.S_IWOTH))


def _abrir_dir_del_sistema(ruta):
    """Descriptor de una carpeta del sistema, validando todo el camino desde
    la raiz. No se siguen enlaces: si un componente lo es, se rechaza."""
    dfd = os.open("/", _ABRIR | os.O_DIRECTORY)
    try:
        st = os.fstat(dfd)
        if st.st_uid != 0 or _escribible_por_otros(st):
            raise Inseguro("la raiz no es de root o es escribible")
        for parte in ruta.strip("/").split("/"):
            nuevo = os.open(parte, _ABRIR | os.O_DIRECTORY, dir_fd=dfd)
            os.close(dfd)
            dfd = nuevo
            st = os.fstat(dfd)
            if not stat.S_ISDIR(st.st_mode):
                raise Inseguro(f"{parte} no es carpeta")
            if st.st_uid != 0:
                raise Inseguro(f"{parte} no es de root")
            if _escribible_por_otros(st):
                raise Inseguro(f"{parte} es escribible por grupo u otros")
    except Exception:
        os.close(dfd)
        raise
    return dfd


def _resolver(dfd, carpeta, nombre, saltos=0):
    """Nombre final, ya sin enlaces, dentro de `carpeta`."""
    if saltos > _MAX_SALTOS:
        raise Inseguro("demasiados enlaces")
    st = os.lstat(nombre, dir_fd=dfd)
    if stat.S_ISLNK(st.st_mode):
        # Un enlace de root dentro de una carpeta que solo root escribe es
        # tan de fiar como el fichero; de cualquier otro, no.
        if st.st_uid != 0:
            raise Inseguro(f"{nombre} es un enlace que no es de root")
        destino = os.readlink(nombre, dir_fd=dfd)
        if "/" in destino:
            # Saltar de carpeta obligaria a revalidar otro camino entero;
            # aqui no hace falta y no se admite.
            raise Inseguro(f"{nombre} apunta fuera de {carpeta}")
        return _resolver(dfd, carpeta, destino, saltos + 1)
    return nombre


def programa(nombre):
    """Ruta absoluta de un programa de confianza, o None.

    De confianza quiere decir: en una carpeta del sistema cuyo camino entero
    es de root y no escribible por grupo ni por otros, y el fichero mismo
    —siguiendo la cadena de enlaces a mano, uno a uno y exigiendo que cada
    enlace sea de root— regular, de root, no escribible por grupo ni por
    otros, y ejecutable.

    Se devuelve **la ruta pedida**, no el final de la cadena. Es a proposito:
    `lsmod` y `modprobe` son enlaces a `kmod`, que mira su propio `argv[0]`
    para saber que es. Devolviendo `/usr/bin/kmod` se quedaba escupiendo la
    ayuda. Lo que importa es haber comprobado a donde lleva el enlace, no
    llamar por el otro nombre.
    """
    for carpeta in _FIABLES:
        try:
            dfd = _abrir_dir_del_sistema(carpeta)
        except (OSError, Inseguro):
            continue                      # p.ej. /bin, que aqui es un enlace
        try:
            real = _resolver(dfd, carpeta, nombre)
            fd = os.open(real, _ABRIR, dir_fd=dfd)
            try:
                st = os.fstat(fd)
                if (stat.S_ISREG(st.st_mode) and st.st_uid == 0
                        and not _escribible_por_otros(st)
                        and st.st_mode & stat.S_IXUSR):
                    return os.path.join(carpeta, nombre)
            finally:
                os.close(fd)
        except (OSError, Inseguro):
            continue
        finally:
            os.close(dfd)
    return None
