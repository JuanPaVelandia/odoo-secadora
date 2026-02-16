#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Bridge para Báscula Prometálicos → Odoo CloudPepper
===================================================

Este script se ejecuta en el PC local conectado a la báscula
y envía los pesos en tiempo real a Odoo en la nube.

Autor: Secadora La Gran Colombia S.A.S
Fecha: 2026-02
"""

import serial
import requests
import time
import re
import logging
import sys
from datetime import datetime

# ===== CONFIGURACIÓN =====
# IMPORTANTE: Modifica estos valores según tu instalación

# URL de tu instancia Odoo en CloudPepper
ODOO_URL = "https://tu-instancia.cloudpepper.site"

# API Key (generar desde Odoo → Configuración → Báscula)
API_KEY = "TU_API_KEY_AQUI"

# Puerto serial de la báscula (ver en Administrador de Dispositivos de Windows)
PUERTO_SERIAL = "COM3"  # Cambiar según tu PC (COM1, COM2, COM3, etc.)

# Configuración serial para Prometálicos
BAUDRATE = 9600
DATA_BITS = 8
PARITY = 'N'  # None
STOP_BITS = 1
TIMEOUT = 1

# Intervalo de lectura (en segundos)
INTERVALO_LECTURA = 0.5  # Leer cada 500ms

# Nivel de logging
LOG_LEVEL = logging.INFO  # Cambiar a DEBUG para más detalles

# ===== FIN CONFIGURACIÓN =====

# Configurar logging
logging.basicConfig(
    level=LOG_LEVEL,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bascula_bridge.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


class BasculaBridge:
    """Bridge entre báscula Prometálicos y Odoo"""

    def __init__(self):
        self.serial_conn = None
        self.pesaje_activo = None
        self.ultimo_peso = None
        self.conectado = False

    def conectar_bascula(self):
        """Conecta al puerto serial de la báscula"""
        try:
            logger.info(f"Conectando a báscula en puerto {PUERTO_SERIAL}...")
            self.serial_conn = serial.Serial(
                port=PUERTO_SERIAL,
                baudrate=BAUDRATE,
                bytesize=DATA_BITS,
                parity=PARITY,
                stopbits=STOP_BITS,
                timeout=TIMEOUT
            )
            self.conectado = True
            logger.info("✅ Conectado a báscula Prometálicos")
            return True
        except serial.SerialException as e:
            logger.error(f"❌ Error conectando a báscula: {e}")
            logger.error("Verifica que:")
            logger.error("  - El puerto COM es correcto (ver Administrador de Dispositivos)")
            logger.error("  - La báscula está encendida")
            logger.error("  - El cable está conectado")
            return False
        except Exception as e:
            logger.error(f"❌ Error inesperado: {e}")
            return False

    def leer_peso(self):
        """Lee el peso actual de la báscula"""
        try:
            if not self.serial_conn or not self.serial_conn.is_open:
                return None

            if self.serial_conn.in_waiting > 0:
                # Leer línea del puerto serial
                linea = self.serial_conn.readline().decode('ascii', errors='ignore').strip()

                if not linea:
                    return None

                # Prometálicos típicamente envía:
                # "  12345.50 kg" o "  12345.50 Kg" o solo "12345.50"
                # Extraer solo el número usando regex
                match = re.search(r'([\d.]+)', linea)
                if match:
                    peso_str = match.group(1)
                    peso = float(peso_str)

                    # Validar que el peso sea razonable (entre 0 y 100,000 kg)
                    if 0 <= peso <= 100000:
                        return peso
                    else:
                        logger.warning(f"Peso fuera de rango: {peso} kg")
                        return None

        except ValueError as e:
            logger.debug(f"Error parseando peso: {e}")
            return None
        except Exception as e:
            logger.error(f"Error leyendo báscula: {e}")
            return None

    def obtener_pesaje_activo(self):
        """Obtiene el ID del pesaje activo desde Odoo"""
        try:
            url = f"{ODOO_URL}/api/bascula/pesaje_activo"
            payload = {"api_key": API_KEY}

            response = requests.post(
                url,
                json=payload,
                headers={'Content-Type': 'application/json'},
                timeout=5
            )

            if response.status_code == 200:
                data = response.json()
                if data.get('success'):
                    pesaje_id = data.get('pesaje_id')
                    placa = data.get('placa', '')
                    logger.info(f"📋 Pesaje activo: ID {pesaje_id}, Placa: {placa}")
                    return pesaje_id
                else:
                    logger.debug(f"No hay pesajes activos: {data.get('message')}")
                    return None
            else:
                logger.error(f"❌ Error HTTP {response.status_code}: {response.text}")
                return None

        except requests.exceptions.Timeout:
            logger.error("❌ Timeout conectando a Odoo")
            return None
        except requests.exceptions.ConnectionError:
            logger.error("❌ No se puede conectar a Odoo. Verifica la URL y conexión a internet.")
            return None
        except Exception as e:
            logger.error(f"❌ Error obteniendo pesaje activo: {e}")
            return None

    def enviar_peso_odoo(self, pesaje_id, peso):
        """Envía el peso actual a Odoo"""
        try:
            url = f"{ODOO_URL}/api/bascula/actualizar_peso"
            payload = {
                "pesaje_id": pesaje_id,
                "peso": peso,
                "api_key": API_KEY
            }

            response = requests.post(
                url,
                json=payload,
                headers={'Content-Type': 'application/json'},
                timeout=3
            )

            if response.status_code == 200:
                data = response.json()
                if data.get('success'):
                    return True
                else:
                    logger.error(f"❌ Error desde Odoo: {data.get('message')}")
                    return False
            else:
                logger.error(f"❌ Error HTTP {response.status_code}")
                return False

        except Exception as e:
            logger.error(f"❌ Error enviando peso: {e}")
            return False

    def verificar_configuracion(self):
        """Verifica que la configuración esté completa"""
        errores = []

        if "TU_API_KEY_AQUI" in API_KEY:
            errores.append("⚠️  Debes configurar el API_KEY en el script")

        if "tu-instancia.cloudpepper.site" in ODOO_URL:
            errores.append("⚠️  Debes configurar el ODOO_URL en el script")

        if errores:
            logger.error("❌ CONFIGURACIÓN INCOMPLETA:")
            for error in errores:
                logger.error(f"   {error}")
            logger.error("\n👉 Edita el archivo bascula_bridge.py y configura:")
            logger.error("   - ODOO_URL: URL de tu Odoo en CloudPepper")
            logger.error("   - API_KEY: Genera una en Odoo → Configuración → Báscula")
            logger.error("   - PUERTO_SERIAL: Puerto COM de tu báscula\n")
            return False

        return True

    def run(self):
        """Loop principal del bridge"""
        logger.info("=" * 60)
        logger.info("🔌 BRIDGE BÁSCULA PROMETÁLICOS → ODOO CLOUDPEPPER")
        logger.info("=" * 60)
        logger.info(f"Odoo URL: {ODOO_URL}")
        logger.info(f"Puerto Serial: {PUERTO_SERIAL}")
        logger.info(f"Intervalo: {INTERVALO_LECTURA}s")
        logger.info("=" * 60)

        # Verificar configuración
        if not self.verificar_configuracion():
            return

        # Conectar a báscula
        if not self.conectar_bascula():
            logger.error("No se pudo conectar a la báscula. Abortando.")
            return

        logger.info("\n✅ Bridge iniciado correctamente")
        logger.info("🔍 Esperando pesajes en Odoo...\n")

        contador_lecturas = 0

        try:
            while True:
                # Obtener pesaje activo cada 10 lecturas (cada ~5 segundos)
                if contador_lecturas % 10 == 0:
                    nuevo_pesaje = self.obtener_pesaje_activo()
                    if nuevo_pesaje != self.pesaje_activo:
                        self.pesaje_activo = nuevo_pesaje
                        if self.pesaje_activo:
                            logger.info(f"\n🎯 Nuevo pesaje activo: {self.pesaje_activo}")

                # Leer peso de báscula
                if self.pesaje_activo:
                    peso = self.leer_peso()

                    if peso is not None and peso != self.ultimo_peso:
                        logger.info(f"⚖️  Peso leído: {peso:.2f} kg")

                        # Enviar a Odoo
                        if self.enviar_peso_odoo(self.pesaje_activo, peso):
                            logger.debug(f"✅ Peso enviado a Odoo")
                            self.ultimo_peso = peso

                contador_lecturas += 1
                time.sleep(INTERVALO_LECTURA)

        except KeyboardInterrupt:
            logger.info("\n\n⏹️  Bridge detenido por el usuario")
        except Exception as e:
            logger.error(f"\n❌ Error fatal: {e}")
        finally:
            if self.serial_conn and self.serial_conn.is_open:
                self.serial_conn.close()
                logger.info("🔌 Conexión serial cerrada")


if __name__ == "__main__":
    bridge = BasculaBridge()
    bridge.run()
