#!/usr/bin/env python3
"""Guarda la VM temporal como plantilla definitiva y limpia los recursos temporales."""

import sys

from opennebula_lib import (
    ENDPOINT,
    INSECURE,
    SUFIJO_TEMP,
    USERNAME,
    apagar_vm,
    borrar_imagen,
    borrar_template,
    borrar_vm,
    buscar_imagen_temp,
    buscar_template_temp,
    buscar_vm_temp,
    conectar,
    crear_template,
    esperar_imagen,
    esperar_imagen_liberada,
    esperar_vm_apagada,
    esperar_vm_eliminada,
    guardar_disco_como_imagen,
)


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

    # Buscar y seleccionar la VM temporal
    vm = buscar_vm_temp(one)
    if vm is None:
        print(f"Error: No se encontró ninguna VM con sufijo '{SUFIJO_TEMP}'.")
        sys.exit(1)

    vm_id = vm.ID
    nombre_temp = vm.NAME
    nombre_definitivo = nombre_temp.replace(SUFIJO_TEMP, "")
    print(f"\n  VM seleccionada:  {nombre_temp} (ID: {vm_id})")
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
