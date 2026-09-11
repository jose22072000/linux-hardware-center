# Centro

Panel de control para portátiles y sobremesas con Linux: temperaturas,
ventiladores, perfiles que cambian solos, batería y privacidad — en una
ventana y en un icono de la barra.

Nació para un MSI GF63, donde MSI Center no existe en Linux, pero **detecta el
hardware en vez de darlo por supuesto**: en un equipo sin controlador
embebido, sin batería o sin gráfica dedicada, esos controles simplemente no
aparecen. Nunca un botón que no hace nada.

> *A control panel for Linux laptops and desktops: temperatures, fan curves,
> automatic power profiles, battery care and privacy toggles. Spanish UI.*

## Qué hace

**Perfiles que cambian solos.** Detecta si estás jugando, trabajando o con el
equipo parado y ajusta el tope del procesador, la curva del ventilador y el
escenario del equipo. Se le dice qué programas cuentan como cada cosa
eligiéndolos de una lista.

| perfil | cuándo | qué hace |
|---|---|---|
| Juego | un juego abierto, o algo usando la gráfica dedicada | tope alto, mucho aire |
| Trabajo | un editor o IDE abierto | equilibrado |
| Estable | a mano | sin bandazos: el ventilador casi no cambia de velocidad |
| Reposo | ni lo uno ni lo otro | tope bajo, el equipo enfría |
| Fresco | a mano | alivio con calor: baja pantalla y apaga el teclado |

**Curva del ventilador que se arrastra.** Los seis puntos se mueven con el
ratón. No se puede guardar una curva inválida: cada punto se mueve solo entre
sus vecinos.

**Enfriado prolongado.** El ventilador sigue soplando después de que baje la
temperatura, porque el disipador sigue caliente. Se ajusta con un rango
*desde / hasta* y un tiempo mínimo.

**Cuidado de la batería.** Límite de carga (cargarla siempre al 100 % la
desgasta antes) y salud real frente a su capacidad original.

**Privacidad.** Apagar la cámara la desconecta de verdad: `/dev/video*`
desaparece del sistema.

**Herramientas.** Prueba de esfuerzo que dice si el procesador se frena por
calor, prueba de ventiladores, informe del equipo al portapapeles, registro.

**Widget de barra** para [Omarchy](https://omarchy.org/): temperatura de la
pieza más caliente siempre a la vista, y el panel con todo el detalle.

## Cómo está hecho

```
centrod   demonio. LO ÚNICO que corre como root.
centro    la ventana (GTK4 + libadwaita)
fresco    atajo de terminal
hw.py     capa de hardware: todo se detecta, nada se cablea
```

**Ni la ventana ni el widget piden contraseña.** Solo escriben
`~/.config/centro/centro.conf`, un fichero de texto tuyo. El demonio lo lee y
aplica. Toda la escritura privilegiada vive en un sitio.

**No se sondea la gráfica dedicada si está dormida.** El estado sale de
`sysfs`; a `nvidia-smi` solo se le pregunta si ya está despierta. Sondearla en
bucle la mantendría en vela y tiraría abajo su ahorro de energía.

## Instalar

Hace falta `python3`, `python-gobject` y `libadwaita`.

```bash
git clone <este-repo> centro
cd centro
sudo ./instalar.sh
```

En Omarchy, para el icono de la barra:

```bash
omarchy bar add centro.panel
```

Para quitarlo todo: `sudo ./instalar.sh desinstalar`. Tu configuración se
queda por si vuelves.

## Qué funciona en cada equipo

| | hace falta |
|---|---|
| Temperaturas, uso, discos, red, perfiles | nada: funciona en cualquier Linux |
| Tope del procesador | `intel_pstate` |
| Curva del ventilador, escenario, cámara, tecla Fn | controlador embebido compatible (`msi-ec`) |
| Límite de carga | que la batería exponga `charge_control_end_threshold` |
| Modo de gráfica | equipo híbrido con gráfica dedicada |
| Widget de barra | Omarchy |

En un sobremesa se ve todo lo de arriba salvo batería y controlador embebido.
**El control de ventiladores por `pwm` de `hwmon`, que es lo que usan los
sobremesas, todavía no está**: se ven las temperaturas pero no se gobiernan
los ventiladores.

## Licencia

MIT. Incluye `gpu-mode`, de Dima Panov, también MIT — ver
[TERCEROS.md](TERCEROS.md).
