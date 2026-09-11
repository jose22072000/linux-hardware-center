#!/usr/bin/env bash
# Instalador de Centro.
#
#   ./instalar.sh            instala
#   ./instalar.sh desinstalar quita todo y deja el equipo como estaba
#
# Que toca y por que:
#   /usr/local/lib/centro   la capa de hardware y los dibujos
#   /usr/local/bin/centrod  el demonio (lo UNICO que corre como root)
#   ~/.local/bin            la ventana y el atajo de terminal
#   ~/.config/centro        tu configuracion (no se borra al desinstalar)
set -euo pipefail

AQUI="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
USUARIO="${SUDO_USER:-$USER}"
CASA="$(getent passwd "$USUARIO" | cut -d: -f6)"
CONF="${XDG_CONFIG_HOME:-$CASA/.config}/centro"
PLUGINS="$CASA/.config/omarchy/plugins"

rojo()  { printf '\033[31m%s\033[0m\n' "$*"; }
verde() { printf '\033[32m%s\033[0m\n' "$*"; }
info()  { printf '  %s\n' "$*"; }

necesita_root() {
  if [[ $EUID -ne 0 ]]; then
    rojo "Hace falta root para instalar el servicio."
    echo "Ejecuta:  sudo $0 ${1:-}"
    exit 1
  fi
}

comprobar() {
  local faltan=()
  command -v python3 >/dev/null || faltan+=("python3")
  python3 -c 'import gi' 2>/dev/null || faltan+=("python-gobject")
  python3 -c 'import gi; gi.require_version("Adw","1")' 2>/dev/null || faltan+=("libadwaita")
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
  install -d -m 755 /usr/local/lib/centro
  install -m 644 "$AQUI/lib/hw.py" "$AQUI/lib/widgets.py" /usr/local/lib/centro/
  install -m 755 "$AQUI/lib/gpu-mode" /usr/local/lib/centro/

  info "demonio -> /usr/local/bin/centrod"
  install -m 755 "$AQUI/bin/centrod" /usr/local/bin/centrod

  info "ventana y atajo -> $CASA/.local/bin"
  install -d -o "$USUARIO" -m 755 "$CASA/.local/bin"
  install -o "$USUARIO" -m 755 "$AQUI/bin/centro" "$AQUI/bin/fresco" "$CASA/.local/bin/"

  info "lanzador"
  install -d -o "$USUARIO" -m 755 "$CASA/.local/share/applications"
  install -o "$USUARIO" -m 644 "$AQUI/org.centro.Centro.desktop" \
          "$CASA/.local/share/applications/"

  # La configuracion NO se sobreescribe: es del usuario y puede llevar horas
  # de ajustes.
  install -d -o "$USUARIO" -m 755 "$CONF"
  if [[ -f "$CONF/centro.conf" ]]; then
    info "configuracion ya existente: se respeta"
  else
    install -o "$USUARIO" -m 644 "$AQUI/docs/centro.conf.ejemplo" "$CONF/centro.conf"
    info "configuracion nueva en $CONF/centro.conf"
  fi

  # El widget de barra es solo para Omarchy; en otro escritorio se salta.
  #
  # Dos caminos posibles y los dos tienen que funcionar:
  #   `omarchy plugin add <url>`  ya dejo el repo EN la carpeta de plugins, y
  #                               entonces no hay nada que copiar
  #   `git clone` a mano          hay que copiar el widget a su sitio
  if [[ -d "$PLUGINS" ]]; then
    DESTINO="$PLUGINS/centro.panel"
    if [[ "$AQUI" -ef "$DESTINO" ]]; then
      info "widget de barra: ya esta en su sitio"
    else
      info "widget de barra (Omarchy)"
      install -d -o "$USUARIO" -m 755 "$DESTINO"
      install -o "$USUARIO" -m 644 "$AQUI/manifest.json" "$AQUI/Panel.qml" "$DESTINO/"
      install -o "$USUARIO" -m 755 "$AQUI/centro-stats" "$DESTINO/"
    fi
    echo "     para verlo en la barra:  omarchy plugin enable centro.panel"
  fi

  # Los discos SATA no publican temperatura sin este modulo, y no se carga solo.
  if ! lsmod | grep -q '^drivetemp'; then
    modprobe drivetemp 2>/dev/null && info "modulo drivetemp cargado" || true
  fi
  echo drivetemp > /etc/modules-load.d/drivetemp.conf

  info "servicio"
  install -m 644 "$AQUI/systemd/centrod.service" /etc/systemd/system/
  systemctl daemon-reload
  systemctl enable --now centrod

  echo
  verde "Instalado."
  echo "  Abre «Centro» desde el lanzador, o escribe: centro"
  echo "  Estado del servicio:  systemctl status centrod"
}

desinstalar() {
  necesita_root
  systemctl disable --now centrod 2>/dev/null || true
  rm -f /etc/systemd/system/centrod.service /etc/modules-load.d/drivetemp.conf
  systemctl daemon-reload
  rm -rf /usr/local/lib/centro
  rm -f /usr/local/bin/centrod
  rm -f "$CASA/.local/bin/centro" "$CASA/.local/bin/fresco"
  rm -f "$CASA/.local/share/applications/org.centro.Centro.desktop"
  rm -rf "$PLUGINS/centro.panel"
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
