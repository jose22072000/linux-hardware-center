"""hw — capa de hardware de Centro.

Todo lo que este proyecto sabe del equipo vive aqui. La regla es una sola:
NADA de rutas fijas. Cada cosa se busca por nombre o por identificador, porque
los numeros de `hwmon`, el nodo de la grafica y el del retroiluminado cambian
entre arranques y entre equipos.

Si una pieza no existe (otro portatil, otro fabricante), su funcion devuelve
None y la interfaz simplemente no enseña ese control. Nunca un boton que no
hace nada.
"""
import os, re, glob, time, subprocess

# ── Utilidades ──────────────────────────────────────────────────────────────

def _leer(ruta, defecto=None):
    try:
        with open(ruta) as f:
            return f.read().strip()
    except (OSError, TypeError):
        return defecto

def _int(ruta, defecto=None, div=1):
    v = _leer(ruta)
    try:
        return int(v) // div
    except (TypeError, ValueError):
        return defecto

def escribir(ruta, valor):
    """Escribe en sysfs. Solo la usa el demonio, que corre como root."""
    try:
        with open(ruta, "w") as f:
            f.write(str(valor))
        return True
    except OSError:
        return False

# ── Donde vive la configuracion ─────────────────────────────────────────────

def dir_config(home=None):
    base = os.environ.get("XDG_CONFIG_HOME") if home is None else None
    if not base:
        base = os.path.join(home or os.path.expanduser("~"), ".config")
    return os.path.join(base, "centro")

def usuario_grafico():
    """El usuario con sesion, para que el demonio (root) encuentre su config.

    Sin esto habria que cablear /home/<alguien>, que es justo lo que impide
    que esto sirva en otro equipo.
    """
    for d in sorted(glob.glob("/run/user/*")):
        try:
            uid = int(os.path.basename(d))
        except ValueError:
            continue
        if uid < 1000:
            continue
        try:
            import pwd
            return pwd.getpwuid(uid)
        except (KeyError, ImportError):
            continue
    return None

# ── Sensores ────────────────────────────────────────────────────────────────
_cache_hwmon = {}

def _hwmon():
    """Mapa nombre -> ruta. Se rehace si un nodo desaparecio."""
    if _cache_hwmon and all(os.path.exists(p) for p in _cache_hwmon.values()):
        return _cache_hwmon
    _cache_hwmon.clear()
    for d in glob.glob("/sys/class/hwmon/hwmon*"):
        n = _leer(os.path.join(d, "name"))
        if n:
            _cache_hwmon.setdefault(n, d)
    return _cache_hwmon

def temp_cpu():
    """Temperatura del paquete. Se busca por etiqueta, nunca por indice."""
    for nombre in ("coretemp", "k10temp", "zenpower"):
        d = _hwmon().get(nombre)
        if not d:
            continue
        for lbl in glob.glob(os.path.join(d, "temp*_label")):
            t = _leer(lbl, "")
            if t.startswith("Package") or t in ("Tctl", "Tdie"):
                return _int(lbl.replace("_label", "_input"), div=1000)
        return _int(os.path.join(d, "temp1_input"), div=1000)
    return None

def temp_por_nombre(prefijo):
    for n, d in _hwmon().items():
        if n.startswith(prefijo):
            return _int(os.path.join(d, "temp1_input"), div=1000)
    return None

def ventiladores():
    """[(etiqueta, rpm)] de todos los ventiladores que reporten algo."""
    out = []
    for n, d in _hwmon().items():
        for f in sorted(glob.glob(os.path.join(d, "fan*_input"))):
            rpm = _int(f)
            if rpm is None:
                continue
            lbl = _leer(f.replace("_input", "_label")) or os.path.basename(f).split("_")[0]
            out.append((lbl, rpm))
    return out

# ── Grafica dedicada ────────────────────────────────────────────────────────
_cache_gpu = []

def gpu_discreta():
    """Ruta PCI de la GPU dedicada, buscada por clase y fabricante.

    Cablear 0000:01:00.0 funcionaba en este equipo y en ninguno mas.
    """
    if _cache_gpu:
        return _cache_gpu[0]
    for d in glob.glob("/sys/bus/pci/devices/*"):
        clase = _leer(os.path.join(d, "class"), "")
        if not clase.startswith("0x03"):       # 0x03 = controlador de video
            continue
        vend = _leer(os.path.join(d, "vendor"), "")
        if vend in ("0x10de", "0x1002"):       # NVIDIA, AMD
            if os.path.exists(os.path.join(d, "power/runtime_status")):
                _cache_gpu.append(d)
                return d
    return None

def gpu_estado():
    """(estado, temperatura, vatios, clientes).

    La temperatura solo se pregunta si la tarjeta YA esta despierta: sondear
    nvidia-smi en bucle la despertaria y tumbaria el ahorro RTD3.
    """
    d = gpu_discreta()
    if not d:
        return (None, None, None, 0)
    est = _leer(os.path.join(d, "power/runtime_status"), "?")
    clientes = len(glob.glob("/proc/[0-9]*/fd/*")) and _clientes_gpu()
    if est == "suspended":
        return ("dormida", None, None, 0)
    t = w = None
    try:
        r = subprocess.run(["nvidia-smi",
                            "--query-gpu=temperature.gpu,power.draw",
                            "--format=csv,noheader,nounits"],
                           capture_output=True, text=True, timeout=3)
        if r.returncode == 0 and r.stdout.strip():
            p = [x.strip() for x in r.stdout.strip().split(",")]
            t, w = int(float(p[0])), float(p[1])
    except Exception:
        pass
    return ("despierta", t, w, clientes)

def _clientes_gpu():
    n = 0
    for fd in glob.glob("/proc/[0-9]*/fd/*"):
        try:
            if "/dev/nvidia" in os.readlink(fd):
                n += 1
        except OSError:
            pass
    return n

# ── Controlador embebido (MSI y equivalentes) ───────────────────────────────
EC = "/sys/devices/platform/msi-ec"

def ec_disponible():
    return os.path.isdir(EC)

def ec_get(clave):
    return _leer(os.path.join(EC, clave))

def ec_opciones(clave):
    v = _leer(os.path.join(EC, f"available_{clave}s"))
    return v.split() if v else []

# ── Bateria ─────────────────────────────────────────────────────────────────

def bateria():
    for b in sorted(glob.glob("/sys/class/power_supply/BAT*")):
        d = {"ruta": b,
             "capacidad": _int(os.path.join(b, "capacity")),
             "estado": _leer(os.path.join(b, "status")),
             "ciclos": _int(os.path.join(b, "cycle_count")),
             "limite": _int(os.path.join(b, "charge_control_end_threshold"))}
        plena = _int(os.path.join(b, "energy_full")) or _int(os.path.join(b, "charge_full"))
        diseno = (_int(os.path.join(b, "energy_full_design"))
                  or _int(os.path.join(b, "charge_full_design")))
        d["salud"] = round(100 * plena / diseno) if plena and diseno else None
        return d
    return None

# ── Pantalla y teclado ──────────────────────────────────────────────────────

def retroiluminado():
    for d in sorted(glob.glob("/sys/class/backlight/*")):
        return d
    return None

def brillo_pct():
    d = retroiluminado()
    if not d:
        return None
    act, mx = _int(os.path.join(d, "brightness")), _int(os.path.join(d, "max_brightness"))
    return round(100 * act / mx) if act is not None and mx else None

def led_teclado():
    for d in glob.glob("/sys/class/leds/*kbd_backlight*"):
        return d
    return None

# ── Procesador ──────────────────────────────────────────────────────────────
PSTATE = "/sys/devices/system/cpu/intel_pstate"

def techo_turbo():
    return _int(os.path.join(PSTATE, "max_perf_pct"))

def cpu_modelo():
    for l in _leer("/proc/cpuinfo", "").split("\n"):
        if l.startswith("model name"):
            return l.split(":", 1)[1].strip()
    return "?"

def cpu_uso(_prev={}):
    """% de uso desde la llamada anterior. Sin sleep: se guarda el contador."""
    try:
        c = open("/proc/stat").readline().split()[1:]
        v = [int(x) for x in c]
    except (OSError, ValueError):
        return None
    idle, total = v[3] + v[4], sum(v)
    p = _prev.get("v")
    _prev["v"] = (idle, total)
    if not p:
        return None
    di, dt = idle - p[0], total - p[1]
    return max(0, min(100, round(100 * (dt - di) / dt))) if dt > 0 else None

def memoria():
    d = {}
    for l in _leer("/proc/meminfo", "").split("\n"):
        p = l.split()
        if len(p) >= 2 and p[0].rstrip(":") in ("MemTotal", "MemAvailable"):
            d[p[0].rstrip(":")] = int(p[1])
    t, a = d.get("MemTotal"), d.get("MemAvailable")
    if not t:
        return None
    return {"total_gb": t / 1048576, "usada_gb": (t - a) / 1048576,
            "pct": round(100 * (t - a) / t)}


# ── Detalle para la pestaña de sensores ─────────────────────────────────────

def nucleos():
    """[(nombre, MHz, °C)] por nucleo. La temperatura solo la dan algunos
    chips; cuando no la hay va None y la interfaz no la enseña."""
    temps = {}
    for nombre in ("coretemp", "k10temp"):
        d = _hwmon().get(nombre)
        if not d:
            continue
        for lbl in glob.glob(os.path.join(d, "temp*_label")):
            t = _leer(lbl, "")
            if t.startswith("Core "):
                try:
                    temps[int(t.split()[1])] = _int(lbl.replace("_label", "_input"), div=1000)
                except ValueError:
                    pass
    def _num(ruta):
        m = re.search(r"/cpu(\d+)/", ruta)
        return int(m.group(1)) if m else -1

    # En un chip con hyperthreading hay el doble de hilos que de nucleos con
    # sensor: los hilos 0 y 1 comparten el sensor del nucleo 0.
    por_nucleo = 2 if temps and len(temps) * 2 <= _nproc() else 1
    out = []
    for f in sorted(glob.glob("/sys/devices/system/cpu/cpu[0-9]*/cpufreq/scaling_cur_freq"),
                    key=_num):
        n = _num(f)
        if n < 0:
            continue
        out.append((n, _int(f, div=1000), temps.get(n // por_nucleo)))
    return out


def _nproc():
    return len(glob.glob("/sys/devices/system/cpu/cpu[0-9]*/cpufreq"))


def discos():
    """[(nombre, usado_gb, total_gb, pct, temp)] por DISPOSITIVO.

    Se agrupa por dispositivo, no por punto de montaje: con btrfs y
    subvolumenes, `/`, `/home` y `/var/log` son el mismo disco y salian cuatro
    veces con los mismos numeros.
    """
    temps = {}
    for n, d in _hwmon().items():
        if n in ("nvme", "drivetemp"):
            t = _int(os.path.join(d, "temp1_input"), div=1000)
            # Hay que saber a CUAL de los discos pertenece la temperatura, y
            # cada tipo lo cuelga en un sitio distinto:
            #   NVMe  el bloque esta directo bajo device/  (device/nvme0n1)
            #   SATA  cuelga de device/block/sdX
            for patron in ("device/nvme*n*", "device/block/*", "../block/*"):
                for blk in glob.glob(os.path.join(d, patron)):
                    temps[os.path.basename(blk)] = t

    def fisico(b, saltos=0):
        """Del nombre de bloque al disco fisico que hay debajo.

        Hace falta porque una raiz cifrada se monta desde /dev/mapper/root,
        que es `dm-0` y no se parece en nada a `nvme0n1`. El kernel deja la
        cadena en /sys/block/<x>/slaves, y puede tener varios eslabones
        (LUKS sobre LVM, por ejemplo), asi que se sigue hasta el final.
        """
        if not b.startswith("dm-") or saltos > 5:
            return b
        esclavos = glob.glob(f"/sys/block/{b}/slaves/*")
        return fisico(os.path.basename(esclavos[0]), saltos + 1) if esclavos else b

    def disco_de(dev):
        b = fisico(os.path.basename(os.path.realpath(dev)))
        for nombre in temps:
            if b.startswith(nombre):
                return nombre
        return re.sub(r"(p?\d+)$", "", b)

    por_dev = {}
    try:
        for l in open("/proc/mounts"):
            p = l.split()
            if len(p) < 3 or not p[0].startswith("/dev/"):
                continue
            if p[2] in ("squashfs", "iso9660"):
                continue
            try:
                st = os.statvfs(p[1])
            except OSError:
                continue
            tot = st.f_blocks * st.f_frsize / 1073741824
            if tot < 1:
                continue
            d = disco_de(p[0])
            if d in por_dev:
                continue                      # ya contado: es otro subvolumen
            libre = st.f_bavail * st.f_frsize / 1073741824
            por_dev[d] = (p[1], tot - libre, tot,
                          round(100 * (tot - libre) / tot), temps.get(d))
    except OSError:
        pass
    return sorted(por_dev.values(), key=lambda x: -x[2])[:4]


def red(_prev={}):
    """(bajada_kbs, subida_kbs) sumando las interfaces reales."""
    rx = tx = 0
    for d in glob.glob("/sys/class/net/*"):
        n = os.path.basename(d)
        if n == "lo" or n.startswith(("veth", "docker", "br-", "virbr")):
            continue
        rx += _int(os.path.join(d, "statistics/rx_bytes"), 0)
        tx += _int(os.path.join(d, "statistics/tx_bytes"), 0)
    ahora = time.time()
    p = _prev.get("v")
    _prev["v"] = (rx, tx, ahora)
    if not p:
        return (0, 0)
    dt = ahora - p[2]
    if dt <= 0:
        return (0, 0)
    return (max(0, (rx - p[0]) / dt / 1024), max(0, (tx - p[1]) / dt / 1024))


def top_procesos(n=5):
    """Los que mas CPU consumen, para saber quien esta calentando el equipo."""
    try:
        out = subprocess.run(
            ["ps", "-eo", "pcpu=,pmem=,comm=", "--sort=-pcpu"],
            capture_output=True, text=True, timeout=4).stdout
    except Exception:
        return []
    r = []
    for l in out.strip().split("\n")[:n]:
        p = l.split(None, 2)
        if len(p) == 3:
            try:
                r.append((p[2].strip(), float(p[0]), float(p[1])))
            except ValueError:
                pass
    return r

