#!/usr/bin/env python3
"""Descarga la imagen Debian 13 desde el Marketplace de OpenNebula."""

import base64
import os
import ssl
import sys

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


def descargar_app(one, app):
    """Exportar (descargar) una aplicación del marketplace al datastore local."""
    app_id = app.ID
    app_name = app.NAME

    print(f"\nDescargando '{app_name}' (ID: {app_id}) al datastore {DATASTORE_ID}...")

    # Exportar la aplicación del marketplace
    # Firma posicional: marketapp.export(appid, dsid, name, vmtemplate_name)
    resultado = one.marketapp.export(app_id, DATASTORE_ID, app_name)

    print(f"Descarga iniciada correctamente.")
    print(f"  - ID de imagen creada: {resultado['image']}")
    print(f"  - ID de template creado: {resultado['vmtemplate']}")

    return resultado


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
    print(f"Buscando '{APP_NAME}' para AMD64 en el marketplace...")
    app = buscar_app(one, APP_NAME)

    if app is None:
        print(f"\nError: No se encontró la aplicación '{APP_NAME}' para AMD64.")
        print("Aplicaciones disponibles con 'Debian' en el nombre:")

        pool = one.marketapppool.info(-2, -1, -1)
        for a in pool.MARKETPLACEAPP:
            if "debian" in a.NAME.lower():
                print(f"  - {a.NAME} (ID: {a.ID})")

        sys.exit(1)

    # Descargar la aplicación
    descargar_app(one, app)

    print("\n¡Proceso completado con éxito!")


if __name__ == "__main__":
    main()
