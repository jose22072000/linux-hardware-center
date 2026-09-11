# Centro

**English** · [Español](README.es.md)

A control panel for Linux laptops and desktops: temperatures, fan curves,
power profiles that switch themselves, battery care, hybrid graphics and
privacy toggles — in one window and one bar icon.

It started on an MSI GF63, where MSI Center doesn't exist for Linux. But it
**detects your hardware instead of assuming it**: on a machine with no embedded
controller, no battery or no discrete GPU, those controls simply don't appear.

> Note: the user interface is currently in Spanish. Translations are very
> welcome — every string lives in a single file, `bin/centro`.

![Panel](docs/img/panel.png)

## What it does

**Profiles that switch themselves.** It notices whether you're gaming, working
or idle and adjusts the CPU ceiling, the fan curve and the machine's own
performance scenario. You pick which programs count as what from a list of
what's running.

| profile | when | what it does |
|---|---|---|
| Game | a game is open, or something is using the discrete GPU | high ceiling, lots of air |
| Work | an editor or IDE is open | balanced |
| Steady | manual | no swings: the fan barely changes speed |
| Idle | neither | low ceiling, the machine cools down |
| Cool | manual | heat relief: dims the screen, turns off the keyboard light |

**A fan curve you drag.** Six points, moved with the mouse. You can't save an
invalid curve: each point only moves between its neighbours.

![Profiles](docs/img/perfiles.png)

**Extended cooling.** The fan keeps running after the temperature drops,
because the heatsink is still hot. Configured as a range — *from* / *until* —
plus a minimum time.

**Battery care.** Charge limit (always charging to 100% wears it out faster)
and real health against its original capacity.

**Privacy.** Turning the camera off really disconnects it: `/dev/video*`
disappears from the system, and the key's indicator light goes off with it.

**Automatic keyboard backlight.** On at dusk, off in the morning. Time-based,
because most laptops have no ambient light sensor; if yours has no backlit
keyboard, the control doesn't appear.

**Every sensor.** Frequency and temperature per thread, disks with their
temperature, memory, network, and what's using the machine right now.

![Sensors](docs/img/sensores.png)

**Tools.** A stress test that tells you whether the CPU had to throttle from
heat, a fan test, a machine report copied to the clipboard, and the log.

![Tools](docs/img/util.png)

**Bar widget** for [Omarchy](https://omarchy.org/): the hottest component's
temperature always visible, and the full detail plus profile and GPU buttons
when you open it.

It's **one project, not two**: the window and the widget write the same
configuration and the daemon applies it, so whichever you change, the other
one knows.

![Bar widget](docs/img/barra.png)

## It looks at what you have, then decides what to show

Nothing is assumed. Before drawing a single control, `hw.py` looks for:

| | how it's found |
|---|---|
| Embedded controller | by driver (`msi-ec`, `asus-nb-wmi`, `thinkpad_acpi`, `hp-wmi`, `ideapad_laptop`) |
| Fan curve | only if that controller's register map is known |
| CPU ceiling | `intel_pstate` or `amd_pstate` if present, otherwise by frequency |
| Sensors | by family (`coretemp`, `k10temp`, `iwlwifi`, `ath*`, `nvme`, `amdgpu`…), and anything not in the table shows under its own name |
| Graphics | by PCI class and vendor, not a fixed path |
| Battery, backlight, keyboard light | looked for, not assumed |

**What your machine doesn't have doesn't show up.** No dead buttons, no fields
stuck at `—`. And if the embedded controller isn't one with a known register
map, everything else still works but the fan curve isn't offered: writing
blindly into someone else's laptop controller is the quick way to break it.

**The Fn keys win.** If you turn the camera off with Fn+F6, or raise the
keyboard light with its key, the program adopts that instead of undoing it. A
key press is the user talking.

## How it's built

```
centrod   the daemon. The ONLY thing running as root.
centro    the window (GTK4 + libadwaita)
fresco    terminal shortcut
hw.py     hardware layer: everything is detected, nothing is hardcoded
```

**Neither the window nor the widget ever asks for a password.** They only write
`~/.config/centro/centro.conf`, a plain text file that belongs to you. The
daemon reads it and applies it. All privileged writing lives in one place.

**The discrete GPU is never polled while it sleeps.** Its state comes from
`sysfs`; `nvidia-smi` is only asked if it's already awake. Polling it in a loop
would keep it awake and undo its own power saving.

## Install

Needs `python3`, `python-gobject` and `libadwaita`.

### On Omarchy

```bash
omarchy plugin add https://github.com/jose22072000/linux-hardware-center.git --enable
```

That puts the widget in the bar. For the profiles and the fan curve to
actually work you also need the service, which requires permissions:

```bash
sudo ~/.config/omarchy/plugins/centro.panel/instalar.sh
```

Two steps on purpose: the widget only reads, but changing the fan curve or the
CPU ceiling writes into the machine's controller and that needs root. If you
stop after the first step, the widget says so instead of showing you buttons
that would do nothing.

### On any other desktop

```bash
git clone https://github.com/jose22072000/linux-hardware-center.git
cd linux-hardware-center
sudo ./instalar.sh
```

You get the window and the service; the bar widget is Omarchy-only and is
skipped automatically.

To remove everything: `sudo ./instalar.sh desinstalar`. Your configuration
stays, in case you come back.

## What works on which machine

| | needs |
|---|---|
| Temperatures, usage, disks, network, profiles | nothing: works on any Linux |
| CPU ceiling | `intel_pstate`, `amd_pstate`, or plain `cpufreq` |
| Fan curve, scenario, camera, Fn key | a supported embedded controller |
| Charge limit | a battery exposing `charge_control_end_threshold` |
| GPU mode | a hybrid machine with a discrete GPU |
| Bar widget | Omarchy |

On a desktop you get everything above except battery and embedded controller.
**Fan control through `hwmon`'s `pwm`, which is what desktops use, isn't there
yet**: you'll see temperatures but won't be able to drive the fans.

## Dependencies and permissions

**Dependencies:** `python3`, `python-gobject` and `libadwaita` for the window.
The bar widget needs nothing beyond what Omarchy already ships.

**Permissions:** the widget and the window **never ask for a password** — they
only read sensors and write a text file of yours in `~/.config/centro/`.

The `centrod` service does run as root, because changing the fan curve, the CPU
ceiling or the charge limit writes into the machine's controller. It's installed
separately and deliberately, with `instalar.sh`. All privileged writing lives
there and nowhere else.

**Your configuration is never overwritten.** If `~/.config/centro/centro.conf`
already exists, the installer leaves it alone and tells you. Uninstalling
leaves it in place.

**What the installer touches:** `/usr/local/lib/centro/`,
`/usr/local/bin/centrod`, `/etc/systemd/system/centrod.service`,
`/etc/modules-load.d/drivetemp.conf` (so SATA disks report their temperature),
and in your home `~/.local/bin/`, `~/.local/share/applications/` and
`~/.config/centro/`. `sudo ./instalar.sh desinstalar` removes all of it.

## Help and bugs

If something doesn't work on your machine, **open an issue** with the output of
*Tools → Copy machine report*: it carries the CPU model, which sensors were
detected and what controls your machine has. That's enough to add support for
hardware I don't have in front of me.

What helps most right now:

- trying it on laptops from other brands (Lenovo, ASUS, HP…) and saying what
  gets detected and what doesn't
- trying it on a desktop: it should show sensors and profiles, but it doesn't
  drive fans through `pwm` yet
- translations: the interface is in Spanish and every string sits in one place,
  `bin/centro`

## License

MIT. Includes `gpu-mode` by Dima Panov, also MIT — see [TERCEROS.md](TERCEROS.md).
