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
from serial.tools import list_ports
import requests
import time
import re
import logging
import sys
import os
import xmlrpc.client
import secrets
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# ===== CONFIGURACIÓN =====
# IMPORTANTE: Modifica estos valores según tu instalación

# URL de tu instancia Odoo
ODOO_URL = os.getenv("BASCULA_ODOO_URL", "https://tu-instancia.cloudpepper.site").rstrip('/')

# API Key (generar desde Odoo → Configuración → Báscula)
API_KEY = os.getenv("BASCULA_API_KEY", "TU_API_KEY_AQUI")
ODOO_DB = os.getenv("BASCULA_ODOO_DB", "")
ODOO_USER = os.getenv("BASCULA_ODOO_USER", "")
ODOO_PASSWORD = os.getenv("BASCULA_ODOO_PASSWORD", "")

# Puerto serial de la báscula (Windows: COM3, Linux: /dev/ttyUSB0)
# Usa "auto" para autodetección
PUERTO_SERIAL = os.getenv("BASCULA_PUERTO_SERIAL", "auto")

# Configuración serial para Prometálicos
BAUDRATE = int(os.getenv("BASCULA_BAUDRATE", "9600"))
DATA_BITS = int(os.getenv("BASCULA_DATA_BITS", "8"))
PARITY = os.getenv("BASCULA_PARITY", "N").upper()
STOP_BITS = float(os.getenv("BASCULA_STOP_BITS", "1"))
TIMEOUT = float(os.getenv("BASCULA_TIMEOUT", "1"))

DATA_BITS_MAP = {
    5: serial.FIVEBITS,
    6: serial.SIXBITS,
    7: serial.SEVENBITS,
    8: serial.EIGHTBITS,
}

PARITY_MAP = {
    'N': serial.PARITY_NONE,
    'E': serial.PARITY_EVEN,
    'O': serial.PARITY_ODD,
    'M': serial.PARITY_MARK,
    'S': serial.PARITY_SPACE,
}

STOP_BITS_MAP = {
    1.0: serial.STOPBITS_ONE,
    1.5: serial.STOPBITS_ONE_POINT_FIVE,
    2.0: serial.STOPBITS_TWO,
}

# Intervalo de lectura (en segundos)
INTERVALO_LECTURA = float(os.getenv("BASCULA_INTERVALO_LECTURA", "0.5"))  # Leer cada 500ms

# Nivel de logging
log_level_name = os.getenv("BASCULA_LOG_LEVEL", "INFO").upper()
LOG_LEVEL = getattr(logging, log_level_name, logging.INFO)
LOG_FILE = os.getenv("BASCULA_LOG_FILE", "logs/bascula_bridge.log")
os.makedirs(os.path.dirname(LOG_FILE) or '.', exist_ok=True)

# ===== FIN CONFIGURACIÓN =====

# Configurar logging (con encoding UTF-8 para Windows)
logging.basicConfig(
    level=LOG_LEVEL,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE, encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)

# Configurar encoding UTF-8 para stdout en Windows
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
logger = logging.getLogger(__name__)


class BasculaBridge:
    """Bridge entre báscula Prometálicos y Odoo"""

    # Reenviar peso cada N ciclos aunque no cambie (heartbeat)
    HEARTBEAT_CICLOS = 6  # ~3 segundos con intervalo 0.5s

    def __init__(self):
        self.serial_conn = None
        self.pesaje_activo = None
        self.ultimo_peso = None
        self.ultimo_peso_global = None
        self.ciclos_sin_envio = 0
        self.ciclos_sin_envio_global = 0
        self.conectado = False
        self.api_key = API_KEY
        self.puerto_serial = PUERTO_SERIAL

    def _es_puerto_candidato(self, port_info):
        texto = f"{port_info.device} {port_info.description} {port_info.hwid}".lower()
        patrones = [
            'usb', 'serial', 'ch340', 'cp210', 'ftdi', 'prolific',
            'ttyusb', 'ttyacm', 'com'
        ]
        return any(p in texto for p in patrones)

    def _detectar_puerto_bascula(self):
        """Retorna el puerto serial a usar. Si está en modo auto, intenta detectar."""
        if self.puerto_serial and self.puerto_serial.lower() not in ('auto', 'autodetect', 'detect'):
            return self.puerto_serial

        puertos = list(list_ports.comports())
        if not puertos:
            return None

        # Priorizar puertos típicos de convertidores serial USB
        candidatos = [p for p in puertos if self._es_puerto_candidato(p)]
        if not candidatos:
            candidatos = puertos

        elegido = candidatos[0].device
        logger.info(f"🔎 Puerto detectado automáticamente: {elegido}")
        return elegido

    def _tiene_credenciales(self):
        return all([ODOO_DB, ODOO_USER, ODOO_PASSWORD])

    def _obtener_api_key_desde_credenciales(self):
        """Obtiene (o crea) la API key de báscula desde Odoo usando credenciales."""
        try:
            common = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/common")
            uid = common.authenticate(ODOO_DB, ODOO_USER, ODOO_PASSWORD, {})
            if not uid:
                logger.error("❌ No se pudo autenticar en Odoo con las credenciales suministradas")
                return None

            models = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/object")
            api_key = models.execute_kw(
                ODOO_DB,
                uid,
                ODOO_PASSWORD,
                'ir.config_parameter',
                'get_param',
                ['bascula.api_key', '']
            )

            if api_key:
                logger.info("✅ API key obtenida desde Odoo con credenciales")
                return api_key

            nueva_api_key = secrets.token_urlsafe(32)
            models.execute_kw(
                ODOO_DB,
                uid,
                ODOO_PASSWORD,
                'ir.config_parameter',
                'set_param',
                ['bascula.api_key', nueva_api_key]
            )
            logger.info("✅ Se creó automáticamente 'bascula.api_key' en Odoo")
            return nueva_api_key
        except Exception as e:
            logger.error(f"❌ No se pudo obtener API key desde credenciales: {e}")
            return None

    def conectar_bascula(self):
        """Conecta al puerto serial de la báscula"""
        try:
            puerto = self._detectar_puerto_bascula()
            if not puerto:
                logger.error("❌ No se encontró ningún puerto serial. Configura BASCULA_PUERTO_SERIAL en .env")
                return False

            self.puerto_serial = puerto
            logger.info(f"Conectando a báscula en puerto {self.puerto_serial}...")
            bytesize = DATA_BITS_MAP.get(DATA_BITS, serial.EIGHTBITS)
            parity = PARITY_MAP.get(PARITY, serial.PARITY_NONE)
            stopbits = STOP_BITS_MAP.get(STOP_BITS, serial.STOPBITS_ONE)

            self.serial_conn = serial.Serial(
                port=self.puerto_serial,
                baudrate=BAUDRATE,
                bytesize=bytesize,
                parity=parity,
                stopbits=stopbits,
                timeout=TIMEOUT
            )
            self.conectado = True
            logger.info("✅ Conectado a báscula Prometálicos")
            return True
        except serial.SerialException as e:
            logger.error(f"❌ Error conectando a báscula: {e}")
            logger.error("Verifica que:")
            logger.error("  - El puerto COM es correcto (o usa BASCULA_PUERTO_SERIAL=auto)")
            logger.error("  - La báscula está encendida")
            logger.error("  - El cable está conectado")
            return False
        except Exception as e:
            logger.error(f"❌ Error inesperado: {e}")
            return False

    def leer_peso(self):
        """Lee el peso actual de la báscula (descarta datos viejos del buffer)"""
        try:
            if not self.serial_conn or not self.serial_conn.is_open:
                return None

            if self.serial_conn.in_waiting == 0:
                return None

            # Leer TODAS las líneas disponibles y quedarse con la última válida.
            # Esto evita que el buffer se llene con datos viejos.
            ultima_linea = None
            while self.serial_conn.in_waiting > 0:
                linea = self.serial_conn.readline().decode('ascii', errors='ignore').strip()
                if linea:
                    ultima_linea = linea

            if not ultima_linea:
                return None

            # Prometálicos típicamente envía:
            # "  12345.50 kg" o "  12345.50 Kg" o solo "12345.50"
            # Extraer solo el número usando regex
            match = re.search(r'([\d.]+)', ultima_linea)
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
            payload = {"api_key": self.api_key, "db": ODOO_DB}

            response = requests.post(
                url,
                json=payload,
                headers={'Content-Type': 'application/json'},
                timeout=5
            )

            if response.status_code == 200:
                data = response.json()
                # Odoo JSON-RPC envuelve la respuesta en {'result': {...}}
                result = data.get('result', data)
                if result.get('success'):
                    pesaje_id = result.get('pesaje_id')
                    placa = result.get('placa', '')
                    logger.info(f"📋 Pesaje activo: ID {pesaje_id}, Placa: {placa}")
                    return pesaje_id
                else:
                    logger.debug(f"No hay pesajes activos: {result.get('message')}")
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
                "api_key": self.api_key,
                "db": ODOO_DB,
            }

            response = requests.post(
                url,
                json=payload,
                headers={'Content-Type': 'application/json'},
                timeout=3
            )

            if response.status_code == 200:
                data = response.json()
                # Odoo JSON-RPC envuelve la respuesta en {'result': {...}}
                result = data.get('result', data)
                if result.get('success'):
                    return True
                else:
                    logger.error(f"❌ Error desde Odoo: {result.get('message')}")
                    return False
            else:
                logger.error(f"❌ Error HTTP {response.status_code}")
                return False

        except Exception as e:
            logger.error(f"❌ Error enviando peso: {e}")
            return False

    def enviar_peso_global_odoo(self, peso):
        """Envía el peso global a Odoo para formularios nuevos sin guardar."""
        try:
            url = f"{ODOO_URL}/api/bascula/actualizar_peso_global"
            payload = {
                "peso": peso,
                "api_key": self.api_key,
                "db": ODOO_DB,
            }

            response = requests.post(
                url,
                json=payload,
                headers={'Content-Type': 'application/json'},
                timeout=3
            )

            if response.status_code == 200:
                data = response.json()
                # Odoo JSON-RPC envuelve la respuesta en {'result': {...}}
                result = data.get('result', data)
                return bool(result.get('success'))

            return False
        except Exception:
            return False

    def verificar_configuracion(self):
        """Verifica que la configuración esté completa"""
        errores = []

        if (not self.api_key) or ("TU_API_KEY_AQUI" in self.api_key):
            if self._tiene_credenciales():
                api_key_obtenida = self._obtener_api_key_desde_credenciales()
                if api_key_obtenida:
                    self.api_key = api_key_obtenida
                else:
                    errores.append("⚠️  No fue posible obtener API_KEY usando credenciales")
            else:
                errores.append("⚠️  Configura BASCULA_API_KEY o credenciales Odoo (DB/usuario/contraseña)")

        if "tu-instancia.cloudpepper.site" in ODOO_URL:
            errores.append("⚠️  Debes configurar el ODOO_URL en el script")

        if errores:
            logger.error("❌ CONFIGURACIÓN INCOMPLETA:")
            for error in errores:
                logger.error(f"   {error}")
            logger.error("\n👉 Revisa el archivo .env y configura:")
            logger.error("   - BASCULA_ODOO_URL")
            logger.error("   - BASCULA_API_KEY o credenciales Odoo")
            logger.error("   - BASCULA_PUERTO_SERIAL\n")
            return False

        return True

    def run(self):
        """Loop principal del bridge"""
        logger.info("=" * 60)
        logger.info("🔌 BRIDGE BÁSCULA PROMETÁLICOS → ODOO CLOUDPEPPER")
        logger.info("=" * 60)
        logger.info(f"Odoo URL: {ODOO_URL}")
        logger.info(f"Puerto Serial (config): {PUERTO_SERIAL}")
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
                        # Resetear peso al cambiar de pesaje
                        self.ultimo_peso = None
                        self.ciclos_sin_envio = 0
                        self.pesaje_activo = nuevo_pesaje
                        if self.pesaje_activo:
                            logger.info(f"\n🎯 Nuevo pesaje activo: {self.pesaje_activo}")

                # Leer peso de báscula
                peso = self.leer_peso()

                # --- Peso global (para formularios nuevos sin guardar) ---
                if peso is not None:
                    self.ciclos_sin_envio_global += 1
                    cambio_global = peso != self.ultimo_peso_global
                    heartbeat_global = self.ciclos_sin_envio_global >= self.HEARTBEAT_CICLOS

                    if cambio_global or heartbeat_global:
                        self.enviar_peso_global_odoo(peso)
                        self.ultimo_peso_global = peso
                        self.ciclos_sin_envio_global = 0

                # --- Peso a pesaje específico ---
                if self.pesaje_activo and peso is not None:
                    self.ciclos_sin_envio += 1
                    cambio_peso = peso != self.ultimo_peso
                    heartbeat = self.ciclos_sin_envio >= self.HEARTBEAT_CICLOS

                    if cambio_peso or heartbeat:
                        if cambio_peso:
                            logger.info(f"⚖️  Peso leído: {peso:.2f} kg")

                        if self.enviar_peso_odoo(self.pesaje_activo, peso):
                            logger.debug(f"✅ Peso enviado a Odoo")
                            self.ultimo_peso = peso
                            self.ciclos_sin_envio = 0

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
