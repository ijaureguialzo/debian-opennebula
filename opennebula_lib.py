#!/usr/bin/env python3
"""Librería común para gestión de recursos OpenNebula."""

import base64
import os
import ssl
import sys
import time
from datetime import datetime

import pyone
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

ENDPOINT = os.getenv("OPENNEBULA_ENDPOINT")
USERNAME = os.getenv("OPENNEBULA_USERNAME")
PASSWORD = os.getenv("OPENNEBULA_PASSWORD")
INSECURE = os.getenv("OPENNEBULA_INSECURE", "false").lower() == "true"
ID_RSA_PUB = os.getenv("ID_RSA_PUB")

# Nombre de la aplicación a buscar en el marketplace
APP_NAME = os.getenv("APP_NAME", "Debian 13")

# Sufijo que identifica los recursos temporales
SUFIJO_TEMP = os.getenv("SUFIJO_TEMP", "-temp")

# Datastore donde se descargará la imagen (1 = default)
DATASTORE_ID = int(os.getenv("DATASTORE_ID", "1"))

# Datastore de sistema que usará la VM al instanciarse (0 = sin preferencia explícita)
SYSTEM_DATASTORE_ID = int(os.getenv("SYSTEM_DATASTORE_ID", "0"))

# Configuración de la máquina virtual
VM_MEMORY_MB = int(os.getenv("VM_MEMORY_MB", "2048"))
VM_DISK_SIZE_MB = int(os.getenv("VM_DISK_SIZE_MB", "8192"))
VM_NETWORK_ID = int(os.getenv("VM_NETWORK_ID", "27"))

# Intervalos de comprobación (segundos)
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "5"))
IMAGE_POLL_TIMEOUT = int(os.getenv("IMAGE_POLL_TIMEOUT", "600"))
VM_POLL_TIMEOUT = int(os.getenv("VM_POLL_TIMEOUT", "300"))

# Mapa de IPs privadas a IPs públicas (formato: "ip_privada=ip_publica,...")
IP_PUBLICA = dict(
    par.split("=") for par in os.getenv("IP_PUBLICA", "").split(",") if "=" in par
)

# Mapa legible de estados de VM
VM_ESTADOS = {
    0: "INIT",
    1: "PENDING",
    2: "HOLD",
    3: "ACTIVE",
    4: "STOPPED",
    5: "SUSPENDED",
    6: "DONE",
    7: "FAILED",
    8: "POWEROFF",
}


# ---------------------------------------------------------------------------
# Conexión
# ---------------------------------------------------------------------------

def conectar():
    """Conectar al servidor OpenNebula mediante XML-RPC."""
    session = f"{USERNAME}:{PASSWORD}"

    if INSECURE:
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        one = pyone.OneServer(ENDPOINT, session=session, context=context)
    else:
        one = pyone.OneServer(ENDPOINT, session=session)

    return one


# ---------------------------------------------------------------------------
# Datastores
# ---------------------------------------------------------------------------

def seleccionar_datastore(one, tipo, etiqueta, default_id):
    """Mostrar los datastores de un tipo concreto y pedir al usuario que elija uno.

    Tipos de datastore en OpenNebula: 0=IMAGE, 1=SYSTEM, 2=FILE
    """
    pool = one.datastorepool.info()
    datastores = [ds for ds in pool.DATASTORE if ds.TYPE == tipo]

    if not datastores:
        print(f"  Advertencia: no se encontraron datastores de tipo {etiqueta}. Se usará el ID por defecto.")
        return default_id

    print(f"\nDatastores {etiqueta} disponibles:")
    for ds in datastores:
        print(f"  [{ds.ID}] {ds.NAME}")

    while True:
        respuesta = input(f"\n¿Qué datastore {etiqueta} utilizar? [por defecto: {default_id}]: ").strip()

        if respuesta == "":
            print(f"  Usando datastore {etiqueta} por defecto: {default_id}")
            return default_id

        if respuesta.isdigit():
            ds_id = int(respuesta)
            ids_validos = {ds.ID for ds in datastores}
            if ds_id in ids_validos:
                return ds_id
            else:
                print(f"  ID '{ds_id}' no válido. Elige uno de la lista.")
        else:
            print("  Entrada no válida. Introduce un número.")


# ---------------------------------------------------------------------------
# Imágenes
# ---------------------------------------------------------------------------

def esperar_imagen(one, image_id):
    """Esperar a que la imagen esté en estado READY."""
    # Estados de imagen en OpenNebula:
    # 0=INIT, 1=READY, 2=USED, 3=DISABLED, 4=LOCKED, 5=ERROR,
    # 6=CLONE, 7=DELETE, 8=USED_PERS, 9=LOCKED_USED, 10=LOCKED_USED_PERS
    READY = 1
    ERROR = 5

    print(f"\nEsperando a que la imagen (ID: {image_id}) esté lista...")

    inicio = time.time()
    while True:
        imagen = one.image.info(image_id)
        estado = imagen.STATE

        if estado == READY:
            print(f"  Imagen lista (estado: READY).")
            return imagen

        if estado == ERROR:
            print(f"  Error: La imagen ha entrado en estado ERROR.")
            sys.exit(1)

        transcurrido = time.time() - inicio
        if transcurrido > IMAGE_POLL_TIMEOUT:
            print(f"  Timeout: La imagen no se procesó en {IMAGE_POLL_TIMEOUT}s.")
            sys.exit(1)

        print(f"  Estado actual: {estado} - esperando {POLL_INTERVAL}s...")
        time.sleep(POLL_INTERVAL)


def esperar_imagen_liberada(one, image_id):
    """Esperar a que la imagen esté en estado READY (no USED) para poder borrarla."""
    READY = 1

    inicio = time.time()
    while True:
        imagen = one.image.info(image_id)
        estado = imagen.STATE

        if estado == READY:
            return

        transcurrido = time.time() - inicio
        if transcurrido > IMAGE_POLL_TIMEOUT:
            print(f"  Timeout esperando liberación de la imagen.")
            sys.exit(1)

        time.sleep(POLL_INTERVAL)


def borrar_imagen(one, image_id):
    """Eliminar una imagen."""
    print(f"  Eliminando imagen (ID: {image_id})...")
    one.image.delete(image_id)
    print(f"  Imagen eliminada.")


# ---------------------------------------------------------------------------
# Funciones específicas de crear.py
# ---------------------------------------------------------------------------

def pedir_nombre_app(default=APP_NAME):
    """Solicitar al usuario el nombre de la aplicación a descargar."""
    try:
        respuesta = input(f"Nombre de la aplicación a descargar [{default}]: ").strip()
    except (KeyboardInterrupt, EOFError):
        print("\nOperación cancelada por el usuario.")
        sys.exit(0)
    return respuesta if respuesta else default


def buscar_app(one, nombre, arquitectura="x86_64"):
    """Buscar una aplicación en el marketplace por nombre y arquitectura."""
    pool = one.marketapppool.info(-2, -1, -1)

    for app in pool.MARKETPLACEAPP:
        if app.NAME != nombre:
            continue

        arch_encontrada = False
        for campo in ("APPTEMPLATE64", "VMTEMPLATE64"):
            valor = app.TEMPLATE.get(campo, "")
            if valor:
                try:
                    contenido = base64.b64decode(valor).decode("utf-8", errors="ignore")
                    if arquitectura in contenido:
                        arch_encontrada = True
                        break
                except Exception:
                    pass

        if arch_encontrada:
            print(f"Aplicación encontrada: {app.NAME} (ID: {app.ID})")
            print(f"  - Marketplace ID: {app.MARKETPLACE_ID}")
            print(f"  - Tipo: {app.TYPE}")
            print(f"  - Arquitectura: {arquitectura}")
            print(f"  - Descripción: {app.TEMPLATE.get('DESCRIPTION', 'Sin descripción')}")
            return app

    return None


def generar_nombre_imagen(one, nombre_base):
    """Generar un nombre único para la imagen con formato 'Debian 13 - 2026030301'."""
    pool_img = one.imagepool.info(-2, -1, -1)
    nombres_existentes = set()
    for img in pool_img.IMAGE:
        nombres_existentes.add(img.NAME)

    pool_tmpl = one.templatepool.info(-2, -1, -1)
    for tmpl in pool_tmpl.VMTEMPLATE:
        nombres_existentes.add(tmpl.NAME)

    fecha = datetime.now().strftime("%Y%m%d")
    sufijo = 1

    while True:
        nombre = f"{nombre_base} - {fecha}{sufijo:02d}{SUFIJO_TEMP}"
        if nombre not in nombres_existentes:
            return nombre
        sufijo += 1


def descargar_app(one, app, nombre_imagen, datastore_id=DATASTORE_ID):
    """Exportar (descargar) una aplicación del marketplace al datastore local."""
    app_id = app.ID

    print(f"\nDescargando '{app.NAME}' como '{nombre_imagen}' al datastore {datastore_id}...")

    resultado = one.marketapp.export(app_id, datastore_id, nombre_imagen, nombre_imagen)

    print(f"Descarga iniciada correctamente.")
    print(f"  - ID de imagen creada: {resultado['image']}")
    print(f"  - ID de template creado: {resultado['vmtemplate']}")

    return resultado


def crear_vm(one, image_id, nombre_vm, system_datastore_id=SYSTEM_DATASTORE_ID):
    """Crear una máquina virtual con la imagen descargada."""
    sched_ds = ""
    if system_datastore_id > 0:
        sched_ds = f'\nSCHED_DS_REQUIREMENTS = "ID = {system_datastore_id}"'

    vm_template = f"""
NAME   = "{nombre_vm}"
CPU    = 1
VCPU   = 2
CPU_MODEL = [
    MODEL = "host-passthrough"
]
MEMORY = {VM_MEMORY_MB}
CONTEXT = [
  NETWORK = "YES",
  SSH_PUBLIC_KEY = "{ID_RSA_PUB}"
]
DISK   = [
  IMAGE_ID = {image_id},
  SIZE     = {VM_DISK_SIZE_MB}
]
NIC    = [
  NETWORK_ID = {VM_NETWORK_ID}
]
GRAPHICS = [
  TYPE   = "VNC",
  LISTEN = "0.0.0.0"
]{sched_ds}
"""

    print(f"\nCreando máquina virtual...")
    print(f"  - RAM: {VM_MEMORY_MB} MB")
    print(f"  - Disco: {VM_DISK_SIZE_MB} MB")
    print(f"  - Red ID: {VM_NETWORK_ID}")
    if system_datastore_id > 0:
        print(f"  - Datastore de sistema: {system_datastore_id}")

    vm_id = one.vm.allocate(vm_template, False)
    print(f"  Máquina virtual creada con ID: {vm_id}")

    return vm_id


def obtener_ip_vm(one, vm_id):
    """Consultar la IP asignada a la VM, esperando a que esté disponible."""
    print(f"\nEsperando a que la VM (ID: {vm_id}) tenga una IP asignada...")

    inicio = time.time()
    while True:
        vm = one.vm.info(vm_id)

        try:
            nics = vm.TEMPLATE.get("NIC", None)
            if nics:
                if isinstance(nics, dict):
                    nics = [nics]
                for nic in nics:
                    ip = nic.get("IP", "")
                    if ip:
                        print(f"  IP asignada: {ip}")
                        return ip
        except Exception:
            pass

        transcurrido = time.time() - inicio
        if transcurrido > VM_POLL_TIMEOUT:
            print(f"  Timeout: La VM no obtuvo IP en {VM_POLL_TIMEOUT}s.")
            sys.exit(1)

        print(f"  Sin IP todavía - esperando {POLL_INTERVAL}s...")
        time.sleep(POLL_INTERVAL)


def guardar_hosts_ini(ip_privada):
    """Guardar la IP (pública si existe, privada si no) en hosts.ini."""
    ip = IP_PUBLICA.get(ip_privada, ip_privada)

    if ip != ip_privada:
        print(f"\n  IP privada {ip_privada} → IP pública {ip}")
    else:
        print(f"\n  IP sin mapeo público, se usa directamente: {ip}")

    with open("hosts.ini", "w") as f:
        f.write(f"{ip}\n")

    print(f"  Fichero hosts.ini guardado con IP: {ip}")

    return ip


# ---------------------------------------------------------------------------
# Funciones específicas de guardar.py
# ---------------------------------------------------------------------------

def buscar_vm_temp(one):
    """Listar las VMs con sufijo -temp (excluyendo DONE) y pedir al usuario que elija una."""
    DONE = 6

    pool = one.vmpool.info(-2, -1, -1, -1)

    vms_temp = [
        vm for vm in pool.VM
        if vm.NAME.endswith(SUFIJO_TEMP) and vm.STATE != DONE
    ]

    if not vms_temp:
        return None

    print(f"Se encontraron {len(vms_temp)} VM(s) temporal(es):\n")
    for idx, vm in enumerate(vms_temp, start=1):
        estado_str = VM_ESTADOS.get(vm.STATE, str(vm.STATE))
        print(f"  [{idx}] {vm.NAME}  (ID: {vm.ID}, Estado: {estado_str})")

    print()
    while True:
        try:
            eleccion = input(f"Elige la VM a guardar [1-{len(vms_temp)}]: ").strip()
            num = int(eleccion)
            if 1 <= num <= len(vms_temp):
                return vms_temp[num - 1]
            print(f"  Por favor introduce un número entre 1 y {len(vms_temp)}.")
        except ValueError:
            print("  Entrada no válida. Introduce un número.")
        except (KeyboardInterrupt, EOFError):
            print("\nOperación cancelada por el usuario.")
            sys.exit(0)


def apagar_vm(one, vm_id):
    """Apagar la VM (poweroff). Si ya está apagada, no hace nada."""
    POWEROFF = 8

    vm = one.vm.info(vm_id)
    if vm.STATE == POWEROFF:
        print(f"\nLa VM (ID: {vm_id}) ya está apagada.")
        return

    print(f"\nApagando la VM (ID: {vm_id})...")
    one.vm.action("poweroff", vm_id)
    print(f"  Orden de apagado enviada.")


def esperar_vm_apagada(one, vm_id):
    """Esperar a que la VM esté en estado POWEROFF."""
    POWEROFF = 8

    print(f"\nEsperando a que la VM (ID: {vm_id}) se apague...")

    time.sleep(POLL_INTERVAL)

    inicio = time.time()
    while True:
        vm = one.vm.info(vm_id)
        estado = vm.STATE

        if estado == POWEROFF:
            print(f"  VM apagada (estado: POWEROFF).")
            return vm

        transcurrido = time.time() - inicio
        if transcurrido > VM_POLL_TIMEOUT:
            print(f"  Timeout: La VM no se apagó en {VM_POLL_TIMEOUT}s.")
            sys.exit(1)

        print(f"  Estado actual: {estado} - esperando {POLL_INTERVAL}s...")
        time.sleep(POLL_INTERVAL)


def guardar_disco_como_imagen(one, vm_id, nombre_definitivo):
    """Guardar el disco 0 de la VM como una nueva imagen."""
    print(f"\nGuardando disco de la VM como imagen '{nombre_definitivo}'...")

    # one.vm.disksaveas(vm_id, disk_id, nombre, tipo, snapshot_id)
    image_id = one.vm.disksaveas(vm_id, 0, nombre_definitivo, "", -1)

    print(f"  Imagen creada con ID: {image_id}")

    return image_id


def crear_template(one, image_id, nombre_definitivo):
    """Crear un nuevo VM template con la imagen guardada."""
    template = f"""
NAME   = "{nombre_definitivo}"
CPU    = 1
VCPU   = 2
CPU_MODEL = [
    MODEL = "host-passthrough"
]
MEMORY = {VM_MEMORY_MB}
CONTEXT = [
  NETWORK = "YES"
]
DISK   = [
  IMAGE_ID = {image_id},
  SIZE     = {VM_DISK_SIZE_MB}
]
GRAPHICS = [
  TYPE   = "VNC",
  LISTEN = "0.0.0.0"
]
"""

    print(f"\nCreando template '{nombre_definitivo}'...")
    template_id = one.template.allocate(template)
    print(f"  Template creado con ID: {template_id}")

    return template_id


def buscar_template_temp(one):
    """Buscar el template con sufijo -temp."""
    pool = one.templatepool.info(-2, -1, -1)

    for tmpl in pool.VMTEMPLATE:
        if tmpl.NAME.endswith(SUFIJO_TEMP):
            print(f"  Template temporal encontrado: {tmpl.NAME} (ID: {tmpl.ID})")
            return tmpl

    return None


def buscar_imagen_temp(one):
    """Buscar la imagen con sufijo -temp."""
    pool = one.imagepool.info(-2, -1, -1)

    for img in pool.IMAGE:
        if img.NAME.endswith(SUFIJO_TEMP):
            print(f"  Imagen temporal encontrada: {img.NAME} (ID: {img.ID})")
            return img

    return None


def borrar_vm(one, vm_id):
    """Eliminar la VM (terminate-hard)."""
    print(f"  Eliminando VM (ID: {vm_id})...")
    one.vm.action("terminate-hard", vm_id)
    print(f"  VM eliminada.")


def esperar_vm_eliminada(one, vm_id):
    """Esperar a que la VM esté en estado DONE."""
    DONE = 6

    inicio = time.time()
    while True:
        try:
            vm = one.vm.info(vm_id)
            estado = vm.STATE

            if estado == DONE:
                print(f"  VM en estado DONE.")
                return
        except Exception:
            print(f"  VM eliminada.")
            return

        transcurrido = time.time() - inicio
        if transcurrido > VM_POLL_TIMEOUT:
            print(f"  Timeout esperando eliminación de la VM.")
            sys.exit(1)

        time.sleep(POLL_INTERVAL)


def borrar_template(one, template_id):
    """Eliminar un template."""
    print(f"  Eliminando template (ID: {template_id})...")
    one.template.delete(template_id)
    print(f"  Template eliminado.")
