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

en_casa() { "$PY" "$AQUI/bin/centro-en-casa" "$USUARIO" "$@"; }

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

  info "librerias -> /usr/local/lib/centro"
  "$INSTALL" -d -m 755 /usr/local/lib/centro
  "$INSTALL" -m 644 "$AQUI/lib/hw.py" "$AQUI/lib/widgets.py" \
                    "$AQUI/lib/seguro.py" /usr/local/lib/centro/
  "$INSTALL" -m 755 "$AQUI/lib/gpu-mode" "$AQUI/bin/centro-en-casa" \
                    /usr/local/lib/centro/

  info "demonio -> /usr/local/bin/centrod"
  "$INSTALL" -m 755 "$AQUI/bin/centrod" /usr/local/bin/centrod

  info "ventana y atajo -> $CASA/.local/bin"
  en_casa copiar "$AQUI/bin/centro"  .local/bin/centro  755
  en_casa copiar "$AQUI/bin/fresco"  .local/bin/fresco  755

  info "lanzador"
  en_casa copiar "$AQUI/org.centro.Centro.desktop" \
          .local/share/applications/org.centro.Centro.desktop 644

  # La configuracion NO se sobreescribe: es del usuario y puede llevar horas
  # de ajustes. El ayudante devuelve 3 si ya estaba.
  local r=0
  en_casa copiar-si-falta "$AQUI/docs/centro.conf.ejemplo" \
          .config/centro/centro.conf 644 || r=$?
  case $r in
    0) info "configuracion nueva en $CONF/centro.conf" ;;
    3) info "configuracion ya existente: se respeta" ;;
    *) rojo "no pude dejar la configuracion"; exit 1 ;;
  esac

  # El widget de barra es solo para Omarchy; en otro escritorio se salta.
  #
  # Dos caminos posibles y los dos tienen que funcionar:
  #   `omarchy plugin add <url>`  ya dejo el repo EN la carpeta de plugins, y
  #                               entonces no hay nada que copiar
  #   `git clone` a mano          hay que copiar el widget a su sitio
  if en_casa hay-carpeta .config/omarchy/plugins; then
    DESTINO="$(en_casa ruta .config/omarchy/plugins/centro.panel)"
    if [[ -d $DESTINO && $AQUI -ef $DESTINO ]]; then
      info "widget de barra: ya esta en su sitio"
    else
      info "widget de barra (Omarchy)"
      # Que un destino trucado no tumbe el resto: lo demas ya esta puesto.
      local base=.config/omarchy/plugins/centro.panel
      if ! { en_casa copiar "$AQUI/manifest.json"  "$base/manifest.json"  644 &&
             en_casa copiar "$AQUI/Panel.qml"      "$base/Panel.qml"      644 &&
             en_casa copiar "$AQUI/centro-stats"   "$base/centro-stats"   755; }
      then
        rojo "  no pude dejar el widget en su sitio; el resto si quedo instalado"
      fi
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
  "$INSTALL" -m 644 "$AQUI/systemd/centrod.service" /etc/systemd/system/
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
  "$RM" -rf /usr/local/lib/centro
  "$RM" -f /usr/local/bin/centrod
  en_casa borrar .local/bin/centro
  en_casa borrar .local/bin/fresco
  en_casa borrar .local/share/applications/org.centro.Centro.desktop
  en_casa borrar .config/omarchy/plugins/centro.panel
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
