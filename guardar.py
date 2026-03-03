#!/usr/bin/env python3
"""Guarda la VM temporal como plantilla definitiva y limpia los recursos temporales."""

import os
import ssl
import sys
import time

import pyone
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

ENDPOINT = os.getenv("OPENNEBULA_ENDPOINT")
USERNAME = os.getenv("OPENNEBULA_USERNAME")
PASSWORD = os.getenv("OPENNEBULA_PASSWORD")
INSECURE = os.getenv("OPENNEBULA_INSECURE", "false").lower() == "true"
ID_RSA_PUB = os.getenv("ID_RSA_PUB")

# Sufijo que identifica los recursos temporales
SUFIJO_TEMP = "-temp"

# Configuración de la máquina virtual (misma que en crear.py)
VM_MEMORY_MB = 2048
VM_DISK_SIZE_MB = 8192
VM_NETWORK_ID = 27

# Intervalos de comprobación (segundos)
POLL_INTERVAL = 5
VM_POLL_TIMEOUT = 300  # 5 minutos
IMAGE_POLL_TIMEOUT = 600  # 10 minutos


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


def buscar_vm_temp(one):
    """Buscar la VM con sufijo -temp."""
    pool = one.vmpool.info(-2, -1, -1, -1)

    for vm in pool.VM:
        if vm.NAME.endswith(SUFIJO_TEMP):
            print(f"VM temporal encontrada: {vm.NAME} (ID: {vm.ID}, Estado: {vm.STATE})")
            return vm

    return None


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
    # VM_STATE: 0=INIT, 1=PENDING, 2=HOLD, 3=ACTIVE, 4=STOPPED,
    #           5=SUSPENDED, 6=DONE, 7=FAILED, 8=POWEROFF
    POWEROFF = 8

    print(f"\nEsperando a que la VM (ID: {vm_id}) se apague...")

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
    # disk_id = 0 (primer disco), tipo = "" (mismo tipo), snapshot_id = -1 (sin snapshot)
    image_id = one.vm.disksaveas(vm_id, 0, nombre_definitivo, "", -1)

    print(f"  Imagen creada con ID: {image_id}")

    return image_id


def esperar_imagen(one, image_id):
    """Esperar a que la imagen esté en estado READY."""
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
            print(f"  Timeout: La imagen no se guardó en {IMAGE_POLL_TIMEOUT}s.")
            sys.exit(1)

        print(f"  Estado actual: {estado} - esperando {POLL_INTERVAL}s...")
        time.sleep(POLL_INTERVAL)


def crear_template(one, image_id, nombre_definitivo):
    """Crear un nuevo VM template con la imagen guardada."""
    template = f"""
NAME   = "{nombre_definitivo}"
CPU    = 1
VCPU   = 1
MEMORY = {VM_MEMORY_MB}
CONTEXT = [
  NETWORK = "YES"
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
    """Eliminar la VM (terminate)."""
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
            # La VM ya no existe
            print(f"  VM eliminada.")
            return

        transcurrido = time.time() - inicio
        if transcurrido > VM_POLL_TIMEOUT:
            print(f"  Timeout esperando eliminación de la VM.")
            sys.exit(1)

        time.sleep(POLL_INTERVAL)


def esperar_imagen_liberada(one, image_id):
    """Esperar a que la imagen temporal esté en estado READY (no USED) para poder borrarla."""
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


def borrar_template(one, template_id):
    """Eliminar un template."""
    print(f"  Eliminando template (ID: {template_id})...")
    one.template.delete(template_id)
    print(f"  Template eliminado.")


def borrar_imagen(one, image_id):
    """Eliminar una imagen."""
    print(f"  Eliminando imagen (ID: {image_id})...")
    one.image.delete(image_id)
    print(f"  Imagen eliminada.")


def main():
    """Programa principal."""
    print("=" * 60)
    print("Guardar VM temporal como plantilla definitiva")
    print("=" * 60)
    print(f"\nEndpoint: {ENDPOINT}")
    print(f"Usuario: {USERNAME}")
    print(f"SSL inseguro: {INSECURE}\n")

    # Conectar a OpenNebula
    print("Conectando a OpenNebula...")
    one = conectar()

    version = one.system.version()
    print(f"Conectado. Versión de OpenNebula: {version}\n")

    # Buscar la VM temporal
    vm = buscar_vm_temp(one)
    if vm is None:
        print("Error: No se encontró ninguna VM con sufijo '-temp'.")
        sys.exit(1)

    vm_id = vm.ID
    nombre_temp = vm.NAME
    nombre_definitivo = nombre_temp.replace(SUFIJO_TEMP, "")
    print(f"  Nombre temporal: {nombre_temp}")
    print(f"  Nombre definitivo: {nombre_definitivo}")

    # Apagar la VM
    apagar_vm(one, vm_id)
    esperar_vm_apagada(one, vm_id)

    # Guardar el disco como imagen nueva (sin -temp)
    image_id = guardar_disco_como_imagen(one, vm_id, nombre_definitivo)
    esperar_imagen(one, image_id)

    # Crear el template definitivo con la nueva imagen
    crear_template(one, image_id, nombre_definitivo)

    # Limpiar recursos temporales
    print(f"\nLimpiando recursos temporales...")

    # 1. Eliminar la VM temporal
    borrar_vm(one, vm_id)
    esperar_vm_eliminada(one, vm_id)

    # 2. Eliminar el template temporal
    tmpl_temp = buscar_template_temp(one)
    if tmpl_temp:
        borrar_template(one, tmpl_temp.ID)

    # 3. Eliminar la imagen temporal (esperar a que esté libre)
    img_temp = buscar_imagen_temp(one)
    if img_temp:
        esperar_imagen_liberada(one, img_temp.ID)
        borrar_imagen(one, img_temp.ID)

    print("\n¡Proceso completado con éxito!")


if __name__ == "__main__":
    main()
