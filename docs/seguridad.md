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

Nota de `systemd-analyze security`: **9.4 UNSAFE antes, 4.1 OK ahora**.

## Las pruebas

`pruebas/prueba_seguro.py` monta los ataques y comprueba que ninguno pasa:
enlace simbolico en el sitio del fichero, enlace en el sitio del temporal,
enlace en un componente del camino, y enlace duro ajeno.
