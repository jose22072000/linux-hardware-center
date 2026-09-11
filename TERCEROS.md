# Código de terceros

## `lib/gpu-mode`

Viene del plugin de barra **nenadjokic.nvidia-hybrid**, de Dima Panov.
Licencia MIT, Copyright © 2026 Dima Panov. Se incorpora **sin cambios en su
lógica**.

Se incluye en vez de reescribirlo porque resuelve bien una parte delicada: al
volver al modo automático restaura el valor de OpenGL que tenía la sesión al
arrancar, en lugar de inventarse un valor por defecto. Una reimplementación
ingenua deja la sesión apuntando a la tarjeta equivocada.
