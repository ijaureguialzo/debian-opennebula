# AGENTS.md

## Resumen
Crea la imagen base Debian 13 en OpenNebula: descarga la app del marketplace,
provisiona una VM temporal, la actualiza con Ansible y la fija como imagen y
plantilla definitivas. Python 3.14 + Poetry (`package-mode = false`), Apache-2.0.
Flujo: `crear` → `actualizar` → `guardar`.

## Comandos
| Comando | Descripción |
|---|---|
| `make init` | `poetry install` (dependencias: pyone, python-dotenv) |
| `make crear` | Interactivo: elige app y datastores; crea VM `-temp` y genera `hosts.ini` |
| `make actualizar` | Ansible sobre `hosts.ini` como `root`: `apt dist-upgrade` + reinicio si procede |
| `make guardar` | Interactivo: guarda el disco como imagen + plantilla definitivas; borra los `-temp` |

- No hay suite de pruebas ni linter configurado.
- `ansible` **no** es dependencia del proyecto: debe estar instalado en el sistema.

## Preparación
1. `cp env-example .env` y rellenar credenciales. `.env` y `hosts.ini` están en
   `.gitignore`; nunca commitearlos (el `.env` real contiene credenciales en claro).
2. `ID_RSA_PUB` debe ser la clave pública de un par con acceso `root@<IP>` por SSH.
3. `actualizar` solo funciona si `crear` se ejecutó antes (genera `hosts.ini`).
   Con `IP_PUBLICA="privada=pública"`, `hosts.ini` contiene la IP pública.

## Arquitectura
- Scripts planos en la raíz, sin empaquetar; toda la configuración vive en `.env`.
- `opennebula_lib.py`: librería compartida. Carga el `.env`, crea la sesión `pyone`
  (XML-RPC) y concentra la lógica de datastores, imágenes, VMs y plantillas.
- `crear.py`: marketplace → imagen `-temp` → VM `-temp` → `hosts.ini`.
- `guardar.py`: apaga la VM → `disksaveas` → imagen + plantilla → borra temporales.
- `actualizar.yml`: único enlace con Ansible (lee `hosts.ini`).
- Los recursos temporales se identifican por el sufijo `SUFIJO_TEMP` (`-temp`);
  la limpieza y el renombrado se basan en él.

## Convenciones
- Todo lo configurable se lee como variable de entorno con `os.getenv(..., "default")`
  en `opennebula_lib.py`; no hardcodear valores.
- Comentarios, docstrings, mensajes `print` y mensajes de commit en español (imperativo).
- Estilo según `.editorconfig`: 4 espacios, LF, newline final.
- Los fallos se comunican con `sys.exit(1)` y mensaje; conservar el formato de salida.
- La operación es como `root`: nunca escribir secretos en código, docs ni logs.
