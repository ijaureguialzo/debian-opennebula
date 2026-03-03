#!/usr/bin/env python3
"""Descarga la imagen Debian 13 desde el Marketplace de OpenNebula."""

import base64
from datetime import datetime
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

# Nombre de la aplicación a buscar en el marketplace
APP_NAME = "Debian 13"

# Datastore donde se descargará la imagen (1 = default)
DATASTORE_ID = 1

# Configuración de la máquina virtual
VM_MEMORY_MB = 2048  # 2 GB de RAM
VM_DISK_SIZE_MB = 8192  # 8 GB de disco
VM_NETWORK_ID = 27

# Intervalo de comprobación del estado de la imagen (segundos)
IMAGE_POLL_INTERVAL = 5
IMAGE_POLL_TIMEOUT = 600  # 10 minutos máximo


def conectar():
    """Conectar al servidor OpenNebula mediante XML-RPC."""
    session = f"{USERNAME}:{PASSWORD}"

    # Si el certificado no es válido, desactivar la verificación SSL
    if INSECURE:
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        one = pyone.OneServer(ENDPOINT, session=session, context=context)
    else:
        one = pyone.OneServer(ENDPOINT, session=session)

    return one


def buscar_app(one, nombre, arquitectura="x86_64"):
    """Buscar una aplicación en el marketplace por nombre y arquitectura."""
    # Listar todas las aplicaciones del marketplace
    # Parámetros: filtro (-2 = todas), rango inicio, rango fin (-1 = sin límite)
    pool = one.marketapppool.info(-2, -1, -1)

    for app in pool.MARKETPLACEAPP:
        if app.NAME != nombre:
            continue

        # Comprobar la arquitectura en los templates embebidos (base64)
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
    # Obtener las imágenes existentes para comprobar nombres
    pool_img = one.imagepool.info(-2, -1, -1)
    nombres_existentes = set()
    for img in pool_img.IMAGE:
        nombres_existentes.add(img.NAME)

    # Obtener los templates existentes para comprobar nombres
    pool_tmpl = one.templatepool.info(-2, -1, -1)
    for tmpl in pool_tmpl.VMTEMPLATE:
        nombres_existentes.add(tmpl.NAME)

    # Generar nombre con la fecha actual y sufijo incremental
    fecha = datetime.now().strftime("%Y%m%d")
    sufijo = 1

    while True:
        nombre = f"{nombre_base} - {fecha}{sufijo:02d}"
        if nombre not in nombres_existentes:
            return nombre
        sufijo += 1


def descargar_app(one, app, nombre_imagen):
    """Exportar (descargar) una aplicación del marketplace al datastore local."""
    app_id = app.ID

    print(f"\nDescargando '{app.NAME}' como '{nombre_imagen}' al datastore {DATASTORE_ID}...")

    # Exportar la aplicación del marketplace
    # Firma posicional: marketapp.export(appid, dsid, name, vmtemplate_name)
    resultado = one.marketapp.export(app_id, DATASTORE_ID, nombre_imagen, nombre_imagen)

    print(f"Descarga iniciada correctamente.")
    print(f"  - ID de imagen creada: {resultado['image']}")
    print(f"  - ID de template creado: {resultado['vmtemplate']}")

    return resultado


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
            print(f"  Timeout: La imagen no se descargó en {IMAGE_POLL_TIMEOUT}s.")
            sys.exit(1)

        print(f"  Estado actual: {estado} - esperando {IMAGE_POLL_INTERVAL}s...")
        time.sleep(IMAGE_POLL_INTERVAL)


def crear_vm(one, image_id, nombre_vm):
    """Crear una máquina virtual con la imagen descargada."""
    vm_template = f"""
NAME   = "{nombre_vm}"
CPU    = 1
VCPU   = 1
MEMORY = {VM_MEMORY_MB}
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

    print(f"\nCreando máquina virtual...")
    print(f"  - RAM: {VM_MEMORY_MB} MB")
    print(f"  - Disco: {VM_DISK_SIZE_MB} MB")
    print(f"  - Red ID: {VM_NETWORK_ID}")

    # one.vm.allocate(template, pending=False) → crea e inicia la VM
    vm_id = one.vm.allocate(vm_template, False)

    print(f"  Máquina virtual creada con ID: {vm_id}")

    return vm_id


def main():
    """Programa principal."""
    print("=" * 60)
    print("Descarga de imagen Debian 13 desde el Marketplace")
    print("=" * 60)
    print(f"\nEndpoint: {ENDPOINT}")
    print(f"Usuario: {USERNAME}")
    print(f"SSL inseguro: {INSECURE}\n")

    # Conectar a OpenNebula
    print("Conectando a OpenNebula...")
    one = conectar()

    # Verificar la conexión
    version = one.system.version()
    print(f"Conectado. Versión de OpenNebula: {version}\n")

    # Buscar la aplicación en el marketplace
    print(f"Buscando '{APP_NAME}' para x86_64 en el marketplace...")
    app = buscar_app(one, APP_NAME)

    if app is None:
        print(f"\nError: No se encontró la aplicación '{APP_NAME}' para x86_64.")
        print("Aplicaciones disponibles con 'Debian' en el nombre:")

        pool = one.marketapppool.info(-2, -1, -1)
        for a in pool.MARKETPLACEAPP:
            if "debian" in a.NAME.lower():
                print(f"  - {a.NAME} (ID: {a.ID})")

        sys.exit(1)

    # Generar un nombre único para la imagen
    nombre_imagen = generar_nombre_imagen(one, APP_NAME)
    print(f"Nombre de la imagen: {nombre_imagen}")

    # Descargar la aplicación
    resultado = descargar_app(one, app, nombre_imagen)
    image_id = resultado['image']

    # Esperar a que la imagen esté lista
    esperar_imagen(one, image_id)

    # Crear la máquina virtual
    crear_vm(one, image_id, nombre_imagen)

    print("\n¡Proceso completado con éxito!")


if __name__ == "__main__":
    main()
