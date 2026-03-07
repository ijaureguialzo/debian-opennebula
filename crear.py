#!/usr/bin/env python3
"""Descarga la imagen Debian 13 desde el Marketplace de OpenNebula."""

import sys

from opennebula_lib import (
    DATASTORE_ID,
    ENDPOINT,
    INSECURE,
    SYSTEM_DATASTORE_ID,
    USERNAME,
    buscar_app,
    conectar,
    crear_vm,
    descargar_app,
    esperar_imagen,
    generar_nombre_imagen,
    guardar_hosts_ini,
    obtener_ip_vm,
    pedir_nombre_app,
    seleccionar_datastore,
)


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

    version = one.system.version()
    print(f"Conectado. Versión de OpenNebula: {version}\n")

    # Pedir el nombre de la aplicación a descargar
    nombre_app = pedir_nombre_app()

    # Buscar la aplicación en el marketplace
    print(f"\nBuscando '{nombre_app}' para x86_64 en el marketplace...")
    app = buscar_app(one, nombre_app)

    if app is None:
        print(f"\nError: No se encontró la aplicación '{nombre_app}' para x86_64.")
        print("Aplicaciones disponibles con 'Debian' en el nombre:")

        pool = one.marketapppool.info(-2, -1, -1)
        for a in pool.MARKETPLACEAPP:
            if "debian" in a.NAME.lower():
                print(f"  - {a.NAME} (ID: {a.ID})")

        sys.exit(1)

    # Generar un nombre único para la imagen
    nombre_imagen = generar_nombre_imagen(one, nombre_app)
    print(f"Nombre de la imagen: {nombre_imagen}")

    # Seleccionar el datastore donde se descargará la imagen
    datastore_id = seleccionar_datastore(one, tipo=0, etiqueta="IMAGE", default_id=DATASTORE_ID)

    # Seleccionar el datastore de sistema que usará la VM al instanciarse
    system_datastore_id = seleccionar_datastore(one, tipo=1, etiqueta="SYSTEM", default_id=SYSTEM_DATASTORE_ID)

    # Descargar la aplicación
    resultado = descargar_app(one, app, nombre_imagen, datastore_id)
    image_id = resultado['image']

    # Esperar a que la imagen esté lista
    esperar_imagen(one, image_id)

    # Crear la máquina virtual
    vm_id = crear_vm(one, image_id, nombre_imagen, system_datastore_id)

    # Obtener la IP de la VM
    ip_privada = obtener_ip_vm(one, vm_id)

    # Guardar la IP en hosts.ini
    guardar_hosts_ini(ip_privada)

    print("\n¡Proceso completado con éxito!")


if __name__ == "__main__":
    main()
