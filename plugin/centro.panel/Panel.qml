import QtQuick
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Ui

// Centro — el unico widget de hardware de esta barra.
//
// Nacio de fusionar un widget de hardware y otro de grafica hibrida:
// tener el estado termico en un sitio y la NVIDIA en otro obligaba a mirar dos
// paneles para entender una sola cosa. Ahora salen juntos, PERO cada tarjeta
// con su cifra propia y etiquetada, que era el motivo real de separarlos:
// la pastilla (CPU + GPU Intel, un solo sensor) y la RTX, que es otra cosa.
//
// Todo sale de /proc y /sys via `centro-stats`, sin root. La RTX se consulta
// por sysfs; solo se le pregunta la temperatura a nvidia-smi si YA esta
// despierta, para no tumbar el ahorro RTD3 sondeandola cada pocos segundos.
Panel {
  id: root
  moduleName: "centro.panel"
  ipcTarget: "centro.panel"

  property var stats: ({})
  readonly property bool showLabel: setting("showLabel", true) === true

  // El script se invoca por bash para resolver $HOME sin cablear la ruta.
  readonly property string statsCmd: "exec \"$HOME/.config/omarchy/plugins/centro.panel/centro-stats\""

  function num(key, fallback) {
    var v = parseFloat(stats[key])
    return isFinite(v) ? v : (fallback === undefined ? 0 : fallback)
  }

  function str(key, fallback) {
    var v = stats[key]
    return (v === undefined || v === "") ? (fallback === undefined ? "—" : fallback) : String(v)
  }

  readonly property int cpuTemp: num("cpu_temp", 0)
  readonly property int cpuPct: num("cpu_pct", 0)
  readonly property bool hot: root.tempMax >= 85

  // La GPU Intel no tiene sensor propio: va dentro del mismo encapsulado que la
  // CPU y comparte con ella el disipador, asi que coretemp mide las dos a la vez.
  // Esa unica cifra es la que manda en el titular.
  readonly property int dieTemp: cpuTemp

  // Calor del equipo entero: la pieza mas caliente, sea cual sea.
  readonly property int tempMax: num("temp_max", 0)
  readonly property string tempMaxQue: str("temp_max_que", "")

  // ── RTX 3050 ──
  readonly property string nvEstado: root.str("nv_estado", "?")
  readonly property bool nvDormida: nvEstado === "suspended"
  readonly property int nvClientes: num("nv_clientes", 0)
  // Despierta y con cero clientes = esta calentando para nada. Es exactamente
  // el fallo que se cazo el 11/09/2026 (3h42 despierta sin que nadie la usara).
  readonly property bool nvDesperdicio: !nvDormida && nvClientes === 0
  readonly property string gpuModo: root.str("gpu_modo", "?")

  // ── Perfil termico ──
  readonly property string perfil: root.str("perfil", "?")
  readonly property bool perfilForzado: root.str("perfil_modo", "auto") !== "auto"

  // Se delega en el script del plugin nenadjokic, que sabe restaurar el valor
  // original de la sesion. Si no esta instalado, `gpu_modo` llega vacio y los
  // botones no se enseñan: nunca un boton que no hace nada.
  readonly property string gpuModeSh:
    "\"/usr/local/lib/centro/gpu-mode\""
  readonly property bool hayModoGpu: root.gpuModo !== "?" && root.gpuModo !== ""
  readonly property string frescoSh: "\"$HOME/.local/bin/fresco\"" 

  readonly property string healthText: {
    if (dieTemp <= 0) return "Leyendo"
    if (dieTemp < 60) return "Frio"
    if (dieTemp < 75) return "Templado"
    if (dieTemp < 85) return "Caliente"
    return "Muy caliente"
  }

  readonly property color warnColor: hot ? (bar ? bar.urgent : Color.urgent)
                                         : (bar ? bar.foreground : Color.foreground)

  function parseStats(raw) {
    var next = {}
    var lines = String(raw || "").split("\n")
    for (var i = 0; i < lines.length; i++) {
      var line = lines[i].trim()
      if (line === "") continue
      var eq = line.indexOf("=")
      if (eq <= 0) continue
      next[line.substring(0, eq)] = line.substring(eq + 1)
    }
    // Un refresco vacio (script interrumpido al cerrar el panel) no debe
    // vaciar el panel: se conserva la ultima lectura buena.
    if (Object.keys(next).length === 0) return
    root.stats = next
  }

  function refresh() {
    if (statsProc.running) return
    statsProc.command = ["bash", "-c", statsCmd + (root.opened ? " full" : " bar")]
    statsProc.running = true
  }

  Process {
    id: statsProc
    stdout: StdioCollector { waitForEnd: true; onStreamFinished: root.parseStats(text) }
  }

  // Refresco lento para la etiqueta de la barra, rapido mientras el panel esta
  // abierto y alguien lo esta mirando.
  Timer {
    interval: root.opened ? 1500 : 4000
    running: true
    repeat: true
    triggeredOnStart: true
    onTriggered: root.refresh()
  }

  onOpenedChanged: if (opened) refresh()

  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight

  BarIconButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    // Temperatura siempre a la vista, que es lo que se quiere vigilar de un
    // portatil. Si la grafica dedicada esta despierta sale tambien la suya:
    // dormida no se enseña porque no tiene ninguna, y un "—" solo es ruido.
    // La cifra es la de la pieza MAS caliente del equipo, no la del
    // procesador: mirar solo la CPU engaña, porque aqui el chipset llega a
    // estar mas caliente que ella y no tiene ventilador que lo enfrie.
    text: {
      if (!root.showLabel || vertical) return "󰔏"
      return "󰔏 " + (root.tempMax > 0 ? root.tempMax + "°" : "—")
    }
    foreground: root.warnColor
    tooltipText: root.tempMax > 0
      ? "Lo mas caliente: " + root.tempMaxQue + " a " + root.tempMax + "°C"
      : ""
    slotSize: Style.bar.iconSlot * (root.showLabel && !vertical ? 2 : 1)
    tooltipText: ""
    onPressed: function(b) {
      if (b === Qt.RightButton) root.bar.run("omarchy-launch-or-focus-tui btop")
      else root.toggle()
    }
  }

  KeyboardPanel {
    id: panel
    anchorItem: button
    owner: root
    bar: root.bar
    open: root.opened
    focusTarget: keyCatcher
    contentWidth: panel.fittedContentWidth(Style.space(400))
    contentHeight: panel.fittedContentHeight(column.implicitHeight)

    PanelKeyCatcher {
      id: keyCatcher
      anchors.fill: parent
      onCloseRequested: root.close()
      onTabRequested: function(direction) { root.switchPanel(direction) }

      Column {
        id: column
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        spacing: Style.space(14)

        // ---------- Titular: temperatura de la pastilla (CPU + GPU Intel) ----------
        Item {
          width: parent.width
          implicitHeight: Math.max(heroIcon.implicitHeight, heroLabels.implicitHeight, heroTemp.implicitHeight)

          Text {
            id: heroIcon
            textFormat: Text.PlainText
            text: "󰘚"
            color: root.warnColor
            font.family: root.bar.fontFamily
            font.pixelSize: Style.font.display
            anchors.left: parent.left
            anchors.verticalCenter: parent.verticalCenter
            Behavior on color { ColorAnimation { duration: 200 } }
          }

          Column {
            id: heroLabels
            anchors.left: heroIcon.right
            anchors.leftMargin: Style.space(14)
            anchors.right: heroTemp.left
            anchors.rightMargin: Style.space(10)
            anchors.verticalCenter: parent.verticalCenter
            spacing: Style.space(2)

            Text {
              text: "Centro"
              color: root.bar.foreground
              font.family: root.bar.fontFamily
              font.pixelSize: Style.font.title
              font.bold: true
              elide: Text.ElideRight
              width: parent.width
            }

            Text {
              textFormat: Text.PlainText
              text: root.healthText.toUpperCase() + " · " + root.perfil.toUpperCase()
                    + (root.perfilForzado ? " (FIJO)" : "") + " · TECHO " + root.num("techo") + "%"
              color: Qt.darker(root.bar.foreground, 1.4)
              font.family: root.bar.fontFamily
              font.pixelSize: Style.font.caption
              font.bold: true
              font.letterSpacing: 1.2
              elide: Text.ElideRight
              width: parent.width
            }
          }

          Text {
            id: heroTemp
            textFormat: Text.PlainText
            text: root.dieTemp > 0 ? root.dieTemp + "°" : "—"
            color: root.warnColor
            font.family: root.bar.fontFamily
            font.pixelSize: Style.font.displayLarge
            font.bold: true
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            Behavior on color { ColorAnimation { duration: 200 } }
          }
        }

        // ---------- Barras de uso ----------
        Column {
          width: parent.width
          spacing: Style.space(10)

          MetricBar {
            label: "CPU"
            fraction: root.num("cpu_pct") / 100
            value: root.num("cpu_pct") + "%  ·  " + (root.cpuTemp > 0 ? root.cpuTemp + "°C" : "—")
          }

          // El i915 no publica un porcentaje de uso; lo que se mide es el hueco
          // que deja el RC6, el estado de reposo del motor grafico. Es actividad
          // real, no una estimacion: si la barra sube, la Intel esta dibujando.
          MetricBar {
            label: "GPU Intel"
            fraction: root.num("igpu_pct") / 100
            value: root.num("igpu_pct") + "%  ·  " + root.num("igpu_freq") + " MHz"
                   + (root.dieTemp > 0 ? "  ·  " + root.dieTemp + "°C" : "")
          }

          MetricBar {
            label: "Memoria"
            fraction: root.num("mem_pct") / 100
            value: root.str("mem_used") + " / " + root.str("mem_total") + " GB"
          }

          MetricBar {
            label: "Disco"
            fraction: root.num("disk_pct") / 100
            value: root.str("disk_used") + " / " + root.str("disk_total") + " GB"
                   + (root.num("disk_temp") > 0 ? "  ·  " + root.num("disk_temp") + "°C" : "")
          }
        }

        PanelSeparator { foreground: root.bar.foreground }

        // ---------- Detalles ----------
        Column {
          width: parent.width
          spacing: Style.space(10)

          PanelSectionHeader {
            text: "DETALLES"
            foreground: root.bar.foreground
            fontFamily: root.bar.fontFamily
          }

          Row {
            width: parent.width
            spacing: Style.space(20)

            Column {
              width: (parent.width - parent.spacing) / 2
              spacing: Style.spacing.labelGap
              InfoPair {
                label: "Ventilador"
                value: root.num("fan_rpm") > 0 ? root.num("fan_rpm") + " rpm" : "Parado"
              }
              InfoPair { label: "Carga (1m)"; value: root.str("load1") }
              // Se repite la temperatura a proposito: es la misma para la CPU y
              // para la GPU Intel, y verlo escrito evita buscar una segunda cifra
              // que este chip nunca va a dar.
              InfoPair {
                label: "Pastilla"
                value: root.dieTemp > 0 ? root.dieTemp + "°C · CPU + GPU" : "—"
              }
              InfoPair {
                label: "Techo GPU"
                value: root.num("igpu_freq_max") > 0 ? root.num("igpu_freq_max") + " MHz" : "—"
              }
            }

            Column {
              width: (parent.width - parent.spacing) / 2
              spacing: Style.spacing.labelGap
              InfoPair {
                label: "Bateria"
                value: root.str("bat_pct") + "%"
                       + (root.num("bat_watts") > 0 ? " · " + root.str("bat_watts") + " W" : "")
              }
              InfoPair {
                label: "Swap"
                value: root.num("swap_total") > 0
                       ? root.str("swap_used") + " / " + root.str("swap_total") + " GB"
                       : "Sin swap"
              }
              InfoPair {
                label: "Encendido"
                value: {
                  var s = root.num("uptime")
                  if (s <= 0) return "—"
                  var h = Math.floor(s / 3600)
                  var m = Math.floor((s % 3600) / 60)
                  return h > 0 ? h + "h " + m + "m" : m + "m"
                }
              }
            }
          }
        }

        PanelSeparator { foreground: root.bar.foreground }

        // ---------- Temperatura de cada pieza ----------
        Column {
          width: parent.width
          spacing: Style.space(10)

          PanelSectionHeader {
            text: "CALOR DEL EQUIPO"
            foreground: root.bar.foreground
            fontFamily: root.bar.fontFamily
          }

          Repeater {
            model: ["Procesador", "Grafica", "Chipset", "Disco", "Placa"]
            InfoPair {
              required property var modelData
              visible: modelData === "Grafica"
                       ? (!root.nvDormida && root.num("nv_temp") > 0)
                       : root.num("t_" + modelData) > 0
              label: modelData === "Placa" ? "Placa base" : modelData
              value: (modelData === "Grafica"
                        ? root.num("nv_temp")
                        : root.num("t_" + modelData)) + " °C"
                     + ((modelData === root.tempMaxQue) ? "   ← lo mas caliente" : "")
            }
          }
        }

        PanelSeparator { foreground: root.bar.foreground }

        // ---------- RTX 3050 ----------
        // Separada de la pastilla a proposito: son dos tarjetas y dos sensores.
        // Mezclar las cifras era lo que impedia saber cual estaba caliente.
        Column {
          width: parent.width
          spacing: Style.space(10)

          PanelSectionHeader {
            text: "RTX 3050"
            foreground: root.bar.foreground
            fontFamily: root.bar.fontFamily
          }

          InfoPair {
            label: "Estado"
            value: root.nvDormida
                   ? "Dormida · no gasta"
                   : (root.num("nv_temp") > 0
                      ? root.num("nv_temp") + "°C · " + root.str("nv_watts") + " W"
                      : "Despierta")
          }

          // El aviso que importa: despierta sin que nadie la use es calor
          // regalado bajo el teclado.
          InfoPair {
            label: "En uso por"
            value: root.nvDesperdicio
                   ? "NADIE — despierta para nada"
                   : (root.nvDormida ? "—" : root.nvClientes + " proceso(s)")
          }

          InfoPair {
            visible: root.hayModoGpu
            label: "Apps nuevas van a"
            value: root.gpuModo === "intel"  ? "Intel (ahorro)"
                 : root.gpuModo === "nvidia" ? "RTX (forzado)"
                 : root.gpuModo === "auto"   ? "Auto — para jugar"
                 : root.gpuModo
          }

          Row {
            visible: root.hayModoGpu
            width: parent.width
            spacing: Style.space(8)

            Repeater {
              model: [
                { m: "intel",  t: "Intel",  i: "󰢮" },
                { m: "auto",   t: "Auto",   i: "󰾆" },
                { m: "nvidia", t: "RTX",    i: "󰾲" }
              ]
              Button {
                required property var modelData
                width: (parent.width - parent.spacing * 2) / 3
                iconText: modelData.i
                iconSize: Style.font.body
                text: modelData.t
                fontSize: Style.font.bodySmall
                foreground: root.bar.foreground
                fontFamily: root.bar.fontFamily
                horizontalPadding: Style.spacing.controlPaddingX
                verticalPadding: Style.spacing.controlPaddingY
                bordered: true
                opacity: root.gpuModo === modelData.m ? 1.0 : 0.55
                onClicked: root.bar.run(root.gpuModeSh + " " + modelData.m)
              }
            }
          }
        }

        PanelSeparator { foreground: root.bar.foreground }

        // ---------- Perfil termico ----------
        Column {
          width: parent.width
          spacing: Style.space(10)

          PanelSectionHeader {
            text: "PERFIL TERMICO"
            foreground: root.bar.foreground
            fontFamily: root.bar.fontFamily
          }

          InfoPair {
            label: "Ahora"
            value: root.perfil + (root.perfilForzado ? " · fijado a mano" : " · automatico")
          }

          Row {
            width: parent.width
            spacing: Style.space(8)

            Repeater {
              // Juego y Trabajo no van aqui: los elige la maquina sola segun
              // lo que este abierto. Estos son los que se fijan a mano.
              model: [
                { m: "auto",    t: "Auto" },
                { m: "estable", t: "Estable" },
                { m: "reposo",  t: "Reposo" },
                { m: "fresco",  t: "Fresco" }
              ]
              Button {
                required property var modelData
                width: (parent.width - parent.spacing * 3) / 4
                text: modelData.t
                fontSize: Style.font.bodySmall
                foreground: root.bar.foreground
                fontFamily: root.bar.fontFamily
                horizontalPadding: Style.spacing.controlPaddingX
                verticalPadding: Style.spacing.controlPaddingY
                bordered: true
                onClicked: root.bar.run(root.frescoSh + " " + modelData.m)
              }
            }
          }
        }

        PanelSeparator { foreground: root.bar.foreground }

        // ---------- Quien consume ----------
        Column {
          width: parent.width
          spacing: Style.space(10)

          PanelSectionHeader {
            text: "QUIEN MAS CONSUME"
            foreground: root.bar.foreground
            fontFamily: root.bar.fontFamily
          }

          Row {
            width: parent.width
            spacing: Style.space(20)

            Column {
              width: (parent.width - parent.spacing) / 2
              spacing: Style.spacing.labelGap
              InfoLabel { text: "CPU"; opacity: 0.45 }
              Repeater {
                model: ["top_cpu_1", "top_cpu_2", "top_cpu_3"]
                InfoValue {
                  required property var modelData
                  text: root.str(modelData, "—")
                  elide: Text.ElideRight
                  width: parent.width
                }
              }
            }

            Column {
              width: (parent.width - parent.spacing) / 2
              spacing: Style.spacing.labelGap
              InfoLabel { text: "Memoria"; opacity: 0.45 }
              Repeater {
                model: ["top_mem_1", "top_mem_2", "top_mem_3"]
                InfoValue {
                  required property var modelData
                  text: root.str(modelData, "—")
                  elide: Text.ElideRight
                  width: parent.width
                }
              }
            }
          }
        }

        // ---------- Accion ----------
        Row {
          width: parent.width
          spacing: Style.space(8)

          Button {
            width: (parent.width - parent.spacing) / 2
            iconText: "󰒓"
            iconSize: Style.font.title
            text: "Centro"
            fontSize: Style.font.bodySmall
            foreground: root.bar.foreground
            fontFamily: root.bar.fontFamily
            horizontalPadding: Style.spacing.controlPaddingX
            verticalPadding: Style.spacing.controlPaddingY + Style.space(2)
            bordered: true
            onClicked: {
              root.bar.run("\"$HOME/.local/bin/centro\"")
              root.close()
            }
          }

          Button {
            width: (parent.width - parent.spacing) / 2
            iconText: "󰜚"
            iconSize: Style.font.title
            text: "btop"
            fontSize: Style.font.bodySmall
            foreground: root.bar.foreground
            fontFamily: root.bar.fontFamily
            horizontalPadding: Style.spacing.controlPaddingX
            verticalPadding: Style.spacing.controlPaddingY + Style.space(2)
            bordered: true
            onClicked: {
              root.bar.run("omarchy-launch-or-focus-tui btop")
              root.close()
            }
          }
        }
      }
    }
  }

  // Etiqueta a la izquierda, cifra a la derecha y una barra fina debajo.
  component MetricBar: Column {
    property string label: ""
    property string value: ""
    property real fraction: 0

    width: parent.width
    spacing: Style.space(5)

    Item {
      width: parent.width
      implicitHeight: Math.max(barLabel.implicitHeight, barValue.implicitHeight)

      Text {
        id: barLabel
        textFormat: Text.PlainText
        text: label
        color: root.bar.foreground
        opacity: 0.6
        font.family: root.bar.fontFamily
        font.pixelSize: Style.font.bodySmall
        elide: Text.ElideRight
        anchors.left: parent.left
        anchors.right: barValue.left
        anchors.rightMargin: Style.space(8)
        anchors.verticalCenter: parent.verticalCenter
      }

      Text {
        id: barValue
        textFormat: Text.PlainText
        text: value
        color: root.bar.foreground
        font.family: root.bar.fontFamily
        font.pixelSize: Style.font.bodySmall
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
      }
    }

    Item {
      width: parent.width
      implicitHeight: Style.space(6)

      Rectangle {
        id: track
        anchors.fill: parent
        radius: height / 2
        color: Qt.rgba(root.bar.foreground.r, root.bar.foreground.g, root.bar.foreground.b, 0.12)
      }

      Rectangle {
        anchors.left: track.left
        anchors.verticalCenter: track.verticalCenter
        height: track.height
        radius: track.radius
        // Se pinta en rojo solo cuando el recurso esta realmente apretado.
        color: fraction >= 0.9 ? (root.bar.urgent || root.bar.foreground) : root.bar.foreground
        width: Math.max(track.height, track.width * Math.max(0, Math.min(1, fraction)))
        Behavior on width { NumberAnimation { duration: 320; easing.type: Easing.OutCubic } }
        Behavior on color { ColorAnimation { duration: 220 } }
      }
    }
  }

  component InfoPair: Row {
    property string label: ""
    property string value: ""

    width: parent.width
    spacing: Style.space(8)

    InfoLabel { text: label }
    Item {
      width: Math.max(0, parent.width - parent.children[0].implicitWidth - parent.children[2].implicitWidth - parent.spacing * 2)
      height: 1
    }
    InfoValue { text: value }
  }

  component InfoLabel: Text {
    textFormat: Text.PlainText
    color: root.bar.foreground
    opacity: 0.6
    font.family: root.bar.fontFamily
    font.pixelSize: Style.font.bodySmall
  }

  component InfoValue: Text {
    textFormat: Text.PlainText
    color: root.bar.foreground
    font.family: root.bar.fontFamily
    font.pixelSize: Style.font.bodySmall
  }
}
