#!/usr/bin/bash
# Instalador de Centro.
#
#   ./instalar.sh             instala
#   ./instalar.sh desinstalar quita todo y deja el equipo como estaba
#
# Que toca y por que:
#   /usr/local/lib/centro   la capa de hardware y los dibujos
#   /usr/local/bin/centrod  el demonio (lo UNICO que corre como root)
#   ~/.local/bin            la ventana y el atajo de terminal
#   ~/.config/centro        tu configuracion (no se borra al desinstalar)
#
# Esto corre como root, asi que no se fia de nada que venga de fuera:
#
#   * el entorno se tira entero y se rehace (PATH fijo); un `XDG_CONFIG_HOME`
#     heredado bastaba para que root creara carpetas tuyas donde el atacante
#     quisiera, asi que ya no se mira: la casa sale del passwd y punto;
#   * cada programa privilegiado se resuelve y se comprueba con `seguro.py`
#     antes de usarlo, nunca por nombre suelto;
#   * lo que se escribe dentro de tu casa NO lo hace `install`, que sigue
#     enlaces, sino `bin/centro-en-casa`, que valida cada componente del
#     camino por descriptor.
set -euo pipefail

# ── Entorno limpio ──────────────────────────────────────────────────────────
if [[ "${CENTRO_ENTORNO:-}" != limpio ]]; then
  _yo="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/$(basename "${BASH_SOURCE[0]}")"
  exec /usr/bin/env -i \
    CENTRO_ENTORNO=limpio \
    PATH=/usr/bin \
    LC_ALL=C.UTF-8 \
    TERM="${TERM:-dumb}" \
    SUDO_USER="${SUDO_USER:-}" \
    USUARIO_ORIGINAL="${USER:-}" \
    /usr/bin/bash "$_yo" "$@"
fi

AQUI="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

rojo()  { printf '\033[31m%s\033[0m\n' "$*"; }
verde() { printf '\033[32m%s\033[0m\n' "$*"; }
info()  { printf '  %s\n' "$*"; }

# ── Programas, resueltos y comprobados ──────────────────────────────────────
PY=/usr/bin/python3
if [[ ! -x $PY ]]; then
  rojo "No encuentro /usr/bin/python3."
  exit 1
fi

eval "$(CENTRO_LIB="$AQUI/lib" "$PY" - getent cut install lsmod grep modprobe \
                                       systemctl rm <<'FIN'
import os, sys
sys.path.insert(0, os.environ["CENTRO_LIB"])
import seguro
faltan = []
for n in sys.argv[1:]:
    ruta = seguro.programa(n)
    if ruta:
        print(f"{n.upper()}={ruta}")
    else:
        faltan.append(n)
print("FALTAN=%r" % " ".join(faltan))
FIN
)"
if [[ -n $FALTAN ]]; then
  rojo "No puedo verificar estos programas: $FALTAN"
  echo "  Tienen que estar en una carpeta del sistema, ser de root y no"
  echo "  ser escribibles por grupo ni por otros."
  exit 1
fi

# ── Quien es el usuario, y donde vive ───────────────────────────────────────
# Del passwd, nunca de HOME ni de XDG_CONFIG_HOME: los elige quien llama.
USUARIO="${SUDO_USER:-${USUARIO_ORIGINAL:-}}"
if [[ -z $USUARIO || $USUARIO == root ]]; then
  rojo "No se para que usuario instalar."
  echo "Ejecuta:  sudo ./instalar.sh"
  exit 1
fi
CASA="$("$GETENT" passwd "$USUARIO" | "$CUT" -d: -f6)"
if [[ -z $CASA ]]; then
  rojo "El usuario $USUARIO no tiene casa en el passwd."
  exit 1
fi
CONF="$CASA/.config/centro"

# El ayudante que hace TODAS las copias. Se usa el instalado en
# /usr/local/lib/centro —de root— en cuanto existe; el del arbol de trabajo
# solo para ponerlo ahi, que es el unico momento en que no hay otra cosa.
AYUDANTE_ROOT=/usr/local/lib/centro/centro-copiar
copiar() { "$PY" "${1:-$AYUDANTE_ROOT}" "$AQUI" "$USUARIO" "${@:2}"; }

necesita_root() {
  if [[ $EUID -ne 0 ]]; then
    rojo "Hace falta root para instalar el servicio."
    echo "Ejecuta:  sudo $0 ${1:-}"
    exit 1
  fi
}

comprobar() {
  local faltan=()
  "$PY" -c 'import gi' 2>/dev/null || faltan+=("python-gobject")
  "$PY" -c 'import gi; gi.require_version("Adw","1")' 2>/dev/null || faltan+=("libadwaita")
  if (( ${#faltan[@]} )); then
    rojo "Faltan dependencias: ${faltan[*]}"
    echo "  Arch:   sudo pacman -S python-gobject libadwaita"
    echo "  Fedora: sudo dnf install python3-gobject libadwaita"
    echo "  Debian: sudo apt install python3-gi gir1.2-adw-1"
    exit 1
  fi
}

instalar() {
  necesita_root
  comprobar

  # Fase 1: el ayudante y su libreria, puestos con el ayudante del arbol de
  # trabajo. Es la unica vez que root ejecuta algo de ahi, y es inevitable:
  # es el mismo arbol del que ya se esta ejecutando este guion.
  info "librerias -> /usr/local/lib/centro"
  copiar "$AQUI/bin/centro-copiar" plan <<'PLAN'
sistema lib/seguro.py     /usr/local/lib/centro/seguro.py      644
sistema bin/centro-copiar /usr/local/lib/centro/centro-copiar  755
PLAN

  # Fase 2: de aqui en adelante solo el de root, que ya nadie puede cambiar.
  if [[ ! -x $AYUDANTE_ROOT ]]; then
    rojo "no se pudo instalar el ayudante privilegiado"
    exit 1
  fi

  info "demonio -> /usr/local/bin/centrod"
  info "ventana y atajo -> $CASA/.local/bin"
  info "lanzador"
  copiar "" plan <<'PLAN'
sistema lib/hw.py               /usr/local/lib/centro/hw.py            644
sistema lib/widgets.py          /usr/local/lib/centro/widgets.py       644
sistema lib/gpu-mode            /usr/local/lib/centro/gpu-mode         755
sistema bin/centrod             /usr/local/bin/centrod                 755
sistema systemd/centrod.service /etc/systemd/system/centrod.service    644
casa bin/centro                    .local/bin/centro                             755
casa bin/fresco                    .local/bin/fresco                             755
casa org.centro.Centro.desktop     .local/share/applications/org.centro.Centro.desktop 644
casa-si-falta docs/centro.conf.ejemplo .config/centro/centro.conf                644
PLAN

  # El widget de barra es solo para Omarchy; en otro escritorio se salta.
  #
  # Dos caminos posibles y los dos tienen que funcionar:
  #   `omarchy plugin add <url>`  ya dejo el repo EN la carpeta de plugins, y
  #                               entonces no hay nada que copiar
  #   `git clone` a mano          hay que copiar el widget a su sitio
  if copiar "" hay-carpeta .config/omarchy/plugins; then
    DESTINO="$(copiar "" ruta .config/omarchy/plugins/centro.panel)"
    if [[ -d $DESTINO && $AQUI -ef $DESTINO ]]; then
      info "widget de barra: ya esta en su sitio"
    else
      # Que un destino trucado no tumbe el resto: lo demas ya esta puesto.
      info "widget de barra (Omarchy)"
      copiar "" plan <<'PLAN' || rojo "  el resto si quedo instalado"
casa manifest.json .config/omarchy/plugins/centro.panel/manifest.json 644 opcional
casa Panel.qml     .config/omarchy/plugins/centro.panel/Panel.qml     644 opcional
casa centro-stats  .config/omarchy/plugins/centro.panel/centro-stats  755 opcional
PLAN
    fi
    echo "     para verlo en la barra:  omarchy plugin enable centro.panel"
  fi

  # Los discos SATA no publican temperatura sin este modulo, y no se carga solo.
  if ! "$LSMOD" | "$GREP" -q '^drivetemp'; then
    "$MODPROBE" drivetemp 2>/dev/null && info "modulo drivetemp cargado" || true
  fi
  "$INSTALL" -d -m 755 /etc/modules-load.d
  printf 'drivetemp\n' > /etc/modules-load.d/drivetemp.conf

  info "servicio"
  "$SYSTEMCTL" daemon-reload
  "$SYSTEMCTL" enable --now centrod

  echo
  verde "Instalado. / Installed."
  echo "  Abre «Centro» desde el lanzador, o escribe: centro"
  echo "  Open \"Centro\" from your launcher, or run: centro"
  echo "  Estado del servicio / service status:  systemctl status centrod"
}

desinstalar() {
  necesita_root
  "$SYSTEMCTL" disable --now centrod 2>/dev/null || true
  "$RM" -f /etc/systemd/system/centrod.service /etc/modules-load.d/drivetemp.conf
  "$SYSTEMCTL" daemon-reload
  # Con el ayudante de root si esta; si ya no, con el del arbol de trabajo.
  local ayudante="$AYUDANTE_ROOT"
  [[ -x $ayudante ]] || ayudante="$AQUI/bin/centro-copiar"
  copiar "$ayudante" plan <<'PLAN' || true
borrar-casa - .local/bin/centro
borrar-casa - .local/bin/fresco
borrar-casa - .local/share/applications/org.centro.Centro.desktop
borrar-casa - .config/omarchy/plugins/centro.panel
PLAN
  "$RM" -rf /usr/local/lib/centro
  "$RM" -f /usr/local/bin/centrod
  echo
  verde "Desinstalado."
  echo "  Tu configuracion sigue en $CONF por si vuelves."
  echo "  La curva del ventilador se queda como estuviera: si quieres la de"
  echo "  fabrica, ponla desde Herramientas ANTES de desinstalar."
}

case "${1:-instalar}" in
  instalar|"")   instalar ;;
  desinstalar)   desinstalar ;;
  *) echo "uso: $0 [instalar|desinstalar]"; exit 1 ;;
esac
