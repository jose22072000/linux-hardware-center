# El cerco de privilegios

De este proyecto solo una cosa corre como root: `bin/centrod`. La ventana y el
widget de la barra no piden contraseña nunca, y no la piden porque no escriben
en el hardware: dejan pares `clave=valor` en un fichero de texto suyo y el
demonio los lee y decide.

Esa comodidad es justo lo que hay que vigilar. El fichero vive en
`~/.config/centro/centro.conf`, o sea **en una carpeta donde el usuario
escribe**, y lo lee un proceso que es root.

## La regla

> El demonio abre la carpeta **una sola vez**, validando la ruta componente a
> componente, y a partir de ahi trabaja **siempre contra ese descriptor** y
> sin seguir enlaces. Nunca vuelve a abrir nada por su nombre.

Todo eso esta en un unico sitio, `lib/seguro.py`, para que se pueda revisar de
una sentada. `bin/centrod` no abre por nombre ningun fichero del usuario.

## Que se comprueba, y contra que

| Comprobacion | Que ataque corta |
|---|---|
| Cada componente con `O_NOFOLLOW\|O_DIRECTORY`, desde `/` | cambiar `.config` por un enlace a `/etc` |
| Dueño root o el propio usuario en cada componente | que un tercero mande sobre el camino |
| Se rechaza escribible por todos sin bit pegajoso | sustituir el contenido de la carpeta |
| El fichero se abre con `O_NOFOLLOW` y se exige regular | `centro.conf -> /etc/shadow` |
| `st_nlink == 1` | enlace duro a un fichero ajeno |
| Tope de tamaño | hacer que root se trague un fichero enorme |
| Temporal con nombre aleatorio, `O_CREAT\|O_EXCL\|O_NOFOLLOW` | el viejo `centro.conf.tmp`, que era predecible |
| `fchown`/`fchmod` **sobre el descriptor** y antes del renombrado | cambiar el fichero por un enlace entre el `rename` y el `chown` |
| `os.replace` con `src_dir_fd`/`dst_dir_fd` | mover la carpeta a media escritura |

El descriptor apunta al inodo, no al nombre: aunque renombren la carpeta o
dejen un enlace en su sitio, se sigue escribiendo donde se abrio.

## Lo que lanza root

Nada por nombre suelto. `lib/seguro.programa()` resuelve contra `/usr/bin`,
`/bin`, `/usr/sbin` y `/sbin`, y exige que el binario sea de root y no
escribible por otros. La unidad fija ademas su propio `PATH`, que si no se
hereda.

- `pgrep` — ruta absoluta resuelta al arrancar.
- `sync` — ya no se lanza: es `os.sync()`.
- `sh` — ya no se lanza: la prueba de esfuerzo usa el propio interprete.

## La unidad

`ProtectSystem=strict` con `ReadWritePaths=/run /home /root`,
`NoNewPrivileges`, `PrivateNetwork` (no habla con la red por ningun sitio),
`PrivateTmp`, `RestrictNamespaces`, `RestrictSUIDSGID`, `RestrictRealtime`,
`LockPersonality`, `ProtectClock`, `ProtectHostname`, `ProtectKernelModules`,
`ProtectControlGroups` y `SystemCallArchitectures=native`.

No se pone `ProtectKernelTunables` a proposito: la accion «liberar memoria»
escribe en `/proc/sys/vm/drop_caches`.

`CapabilityBoundingSet` se dejo en tres, y las tres estan **medidas en
maquina**, no elegidas a ojo: se ejecuto cada operacion privilegiada del
demonio bajo distintos conjuntos hasta dar con el minimo en el que todo sigue
funcionando.

| Capacidad | Para que | Si se quita |
|---|---|---|
| `CAP_DAC_OVERRIDE` | crear la configuracion en la carpeta del usuario, que es suya | no puede escribirla |
| `CAP_CHOWN` | devolverle el fichero al usuario | la ventana ya no podria guardar |
| `CAP_SYS_PTRACE` | leer `/proc/<pid>/fd` ajenos, que es como se ve quien usa la grafica | el perfil de juego no se detecta solo |

`CAP_FOWNER` no hace falta a proposito: `seguro.py` pone el modo **antes** que
el dueño. `CAP_DAC_READ_SEARCH` tampoco: se probo y no aporta nada.

Escribir en sysfs y en el EC no necesita ninguna: esos ficheros son de root y
tienen su bit de escritura.

El interprete no se elige por `PATH`: la unidad lo fija
(`ExecStart=/usr/bin/python3 …`) y el shebang es `#!/usr/bin/python3`. Un
shebang con `env` es el `PATH` decidiendo quien corre como root.

Nota de `systemd-analyze security`: **9.4 UNSAFE antes, 4.1 OK ahora**.

## El instalador

`instalar.sh` tambien corre como root, y tiene los mismos dos problemas que el
demonio: de donde salen los programas y donde acaban las escrituras.

**El entorno se tira entero.** El script se vuelve a lanzar con `env -i` y un
`PATH` fijo. Lo que se hereda no decide nada, y en particular
`XDG_CONFIG_HOME` **ya ni se mira**: con el puesto, un
`sudo XDG_CONFIG_HOME=/etc ./instalar.sh` hacia que root creara `/etc/centro` a
nombre del usuario. La casa sale del `passwd`, por `getent`, y de ningun otro
sitio.

**Los programas se verifican antes de usarse.** `getent`, `cut`, `install`,
`lsmod`, `grep`, `modprobe`, `systemctl` y `rm` pasan por `seguro.programa()`;
si alguno no se puede verificar, el instalador se para y lo dice. El shebang es
`#!/usr/bin/bash`, no `env bash`.

**Lo que va dentro de tu casa no lo escribe `install`.** `install -o usuario`
sigue enlaces: basta con que `~/.local/bin` apunte a otro sitio para que la
copia —o el cambio de dueño— acabe donde el atacante quiera. Esas escrituras
las hace `bin/centro-en-casa`, que abre cada componente del destino validado y
por descriptor, crea lo que falte a nombre del usuario y deja el fichero con
`escribir_en()`. El origen tambien se abre con `O_NOFOLLOW`: si no, un enlace
dentro del repo haria que root copiara a tu casa un fichero que solo root
puede leer.

Comprobado con la trampa puesta: con `~/.config/omarchy/plugins/centro.panel`
convertido en un enlace a una carpeta de `/root`, la instalacion **se niega,
lo explica y no toca la victima**, y el resto queda instalado igual.

Un detalle que costo un intento: `programa()` devuelve **la ruta pedida**, no
el final de la cadena de enlaces. `lsmod` y `modprobe` son enlaces a `kmod`,
que mira su propio `argv[0]`; llamandolo `/usr/bin/kmod` se quedaba escupiendo
la ayuda. Lo que importa es haber comprobado a donde lleva el enlace, no
llamar por el otro nombre.

## Las pruebas

`pruebas/prueba_seguro.py` monta los ataques y comprueba que ninguno pasa:
enlace simbolico en el sitio del fichero, enlace en el sitio del temporal,
enlace en un componente del camino, y enlace duro ajeno.
