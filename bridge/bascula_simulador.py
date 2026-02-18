#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SIMULADOR de Báscula Prometálicos → Odoo CloudPepper
======================================================

Este script SIMULA una báscula sin necesidad de hardware físico.
Perfecto para hacer pruebas del sistema completo.

Genera pesos aleatorios que varían ligeramente para simular
un vehículo sobre la báscula.

Autor: Secadora La Gran Colombia S.A.S
Fecha: 2026-02
"""

import requests
import time
import logging
import sys
import random
import os
import secrets
import xmlrpc.client
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

# Peso base a simular (kg)
PESO_BASE_MIN = float(os.getenv("BASCULA_SIM_PESO_BASE_MIN", "5000"))   # Peso mínimo (5 toneladas)
PESO_BASE_MAX = float(os.getenv("BASCULA_SIM_PESO_BASE_MAX", "35000"))  # Peso máximo (35 toneladas)

# Variación del peso (simula vibración de báscula)
VARIACION_PESO = float(os.getenv("BASCULA_SIM_VARIACION_PESO", "10"))  # +/- 10 kg

# Intervalo de actualización (en segundos)
INTERVALO_ACTUALIZACION = float(os.getenv("BASCULA_SIM_INTERVALO", "1"))  # Actualizar cada 1 segundo

# Modo de simulación: "aleatorio", "fijo" o "manual"
# manual = escribir el peso desde la terminal
MODO_SIMULACION = os.getenv("BASCULA_SIM_MODO", "aleatorio").lower()
PESO_FIJO = float(os.getenv("BASCULA_SIM_PESO_FIJO", "28345.50"))  # Si modo = "fijo", usar este peso

log_level_name = os.getenv("BASCULA_LOG_LEVEL", "INFO").upper()
LOG_LEVEL = getattr(logging, log_level_name, logging.INFO)
LOG_FILE = os.getenv("BASCULA_SIM_LOG_FILE", "logs/bascula_simulador.log")
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
logger = logging.getLogger(__name__)

# Configurar encoding UTF-8 para stdout en Windows
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')


class BasculaSimulador:
    """Simulador de báscula Prometálicos"""

    def __init__(self):
        self.pesaje_activo = None
        self.peso_actual = None
        self.peso_base = None
        self.api_key = API_KEY
        self.ultimo_peso_global = None

    def _tiene_credenciales(self):
        return all([ODOO_DB, ODOO_USER, ODOO_PASSWORD])

    def _obtener_api_key_desde_credenciales(self):
        """Obtiene la API key guardada en Odoo usando credenciales admin."""
        try:
            common = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/common")
            uid = common.authenticate(ODOO_DB, ODOO_USER, ODOO_PASSWORD, {})
            if not uid:
                logger.error("[ERROR] No se pudo autenticar en Odoo con las credenciales suministradas")
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
                logger.info("[OK] API key obtenida desde Odoo con credenciales")
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
            logger.info("[OK] Se creó automáticamente 'bascula.api_key' en Odoo")
            return nueva_api_key
        except Exception as e:
            logger.error(f"[ERROR] No se pudo obtener API key desde credenciales: {e}")
            return None

    def generar_peso(self):
        """Genera un peso simulado"""
        if MODO_SIMULACION == "fijo":
            # Peso fijo con pequeña variación
            variacion = random.uniform(-2, 2)
            return round(PESO_FIJO + variacion, 2)
        else:
            # Peso aleatorio
            if self.peso_base is None or random.random() < 0.1:  # 10% chance de cambiar base
                # Generar nuevo peso base (simula nuevo vehículo)
                self.peso_base = random.uniform(PESO_BASE_MIN, PESO_BASE_MAX)

            # Agregar variación (simula vibración)
            variacion = random.uniform(-VARIACION_PESO, VARIACION_PESO)
            peso = self.peso_base + variacion

            # Redondear a 2 decimales
            return round(max(0, peso), 2)

    def obtener_pesaje_activo(self):
        """Obtiene el ID del pesaje activo desde Odoo"""
        try:
            url = f"{ODOO_URL}/api/bascula/pesaje_activo"
            payload = {"api_key": self.api_key}

            logger.debug(f"[DEBUG] Consultando: {url}")
            logger.debug(f"[DEBUG] Payload: {payload}")

            response = requests.post(
                url,
                json=payload,
                headers={'Content-Type': 'application/json'},
                timeout=5
            )

            logger.debug(f"[DEBUG] Status Code: {response.status_code}")
            logger.debug(f"[DEBUG] Response: {response.text}")

            if response.status_code == 200:
                data = response.json()
                logger.debug(f"[DEBUG] Data parsed: {data}")

                # Odoo usa JSON-RPC, la respuesta real está en 'result'
                result = data.get('result', data)

                if result.get('success'):
                    pesaje_id = result.get('pesaje_id')
                    placa = result.get('placa', '')
                    tipo = result.get('tipo_proceso', '')
                    logger.info(f"[PESAJE] Pesaje activo: ID {pesaje_id}, Placa: {placa}, Tipo: {tipo}")
                    return pesaje_id
                else:
                    logger.info(f"[INFO] No hay pesajes activos: {result.get('message')}")
                    return None
            else:
                logger.error(f"[ERROR] Error HTTP {response.status_code}: {response.text}")
                return None

        except requests.exceptions.Timeout:
            logger.error("[ERROR] Timeout conectando a Odoo")
            return None
        except requests.exceptions.ConnectionError:
            logger.error("[ERROR] No se puede conectar a Odoo. Verifica la URL y conexion a internet.")
            return None
        except Exception as e:
            logger.error(f"[ERROR] Error obteniendo pesaje activo: {e}")
            import traceback
            traceback.print_exc()
            return None

    def enviar_peso_odoo(self, pesaje_id, peso):
        """Envía el peso simulado a Odoo"""
        try:
            url = f"{ODOO_URL}/api/bascula/actualizar_peso"
            payload = {
                "pesaje_id": pesaje_id,
                "peso": peso,
                "api_key": self.api_key
            }

            response = requests.post(
                url,
                json=payload,
                headers={'Content-Type': 'application/json'},
                timeout=3
            )

            if response.status_code == 200:
                data = response.json()

                # Odoo usa JSON-RPC, la respuesta real está en 'result'
                result = data.get('result', data)

                if result.get('success'):
                    return True
                else:
                    logger.error(f"[ERROR] Error desde Odoo: {result.get('message')}")
                    return False
            else:
                logger.error(f"[ERROR] Error HTTP {response.status_code}")
                return False

        except Exception as e:
            logger.error(f"[ERROR] Error enviando peso: {e}")
            return False

    def enviar_peso_global_odoo(self, peso):
        """Envía el peso global a Odoo para formularios nuevos sin guardar."""
        try:
            url = f"{ODOO_URL}/api/bascula/actualizar_peso_global"
            payload = {
                "peso": peso,
                "api_key": self.api_key
            }

            response = requests.post(
                url,
                json=payload,
                headers={'Content-Type': 'application/json'},
                timeout=3
            )

            if response.status_code == 200:
                data = response.json()
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
                    errores.append("[ADVERTENCIA] No fue posible obtener API_KEY usando credenciales")
            else:
                errores.append("[ADVERTENCIA] Configura BASCULA_API_KEY o credenciales Odoo (DB/usuario/contraseña)")

        if "tu-instancia.cloudpepper.site" in ODOO_URL:
            errores.append("[ADVERTENCIA] Debes configurar el ODOO_URL en el script")

        if errores:
            logger.error("[ERROR] CONFIGURACION INCOMPLETA:")
            for error in errores:
                logger.error(f"   {error}")
            logger.error("\n[INSTRUCCIONES] Edita el archivo bascula_simulador.py y configura:")
            logger.error("   - ODOO_URL: URL de tu Odoo en CloudPepper")
            logger.error("   - API_KEY o credenciales Odoo (BASCULA_ODOO_DB, BASCULA_ODOO_USER, BASCULA_ODOO_PASSWORD)\n")
            return False

        return True

    def run(self):
        """Loop principal del simulador"""
        if MODO_SIMULACION == "manual":
            self.run_manual()
            return

        logger.info("=" * 70)
        logger.info("SIMULADOR DE BASCULA PROMETALICOS -> ODOO CLOUDPEPPER")
        logger.info("=" * 70)
        logger.info(f"Odoo URL: {ODOO_URL}")
        logger.info(f"Modo: {MODO_SIMULACION.upper()}")
        if MODO_SIMULACION == "fijo":
            logger.info(f"Peso fijo: {PESO_FIJO} kg (+/- 2 kg)")
        else:
            logger.info(f"Rango de peso: {PESO_BASE_MIN} - {PESO_BASE_MAX} kg")
            logger.info(f"Variacion: +/- {VARIACION_PESO} kg")
        logger.info(f"Intervalo: {INTERVALO_ACTUALIZACION}s")
        logger.info("=" * 70)

        # Verificar configuración
        if not self.verificar_configuracion():
            return

        logger.info("\n[OK] Simulador iniciado correctamente")
        logger.info("[INFO] Esperando pesajes en Odoo...")
        logger.info("[INFO] Crea un pesaje en Odoo para empezar a ver datos\n")

        contador_actualizaciones = 0

        try:
            while True:
                # Obtener pesaje activo cada 5 actualizaciones
                if contador_actualizaciones % 5 == 0:
                    nuevo_pesaje = self.obtener_pesaje_activo()
                    if nuevo_pesaje != self.pesaje_activo:
                        self.pesaje_activo = nuevo_pesaje
                        if self.pesaje_activo:
                            logger.info(f"\n[NUEVO] Nuevo pesaje activo: {self.pesaje_activo}")
                            logger.info("[INICIANDO] Iniciando envio de pesos simulados...\n")
                            # Resetear peso base para nuevo pesaje
                            self.peso_base = None

                # Generar y enviar peso
                peso = self.generar_peso()

                if peso is not None and peso != self.ultimo_peso_global:
                    self.enviar_peso_global_odoo(peso)
                    self.ultimo_peso_global = peso

                if self.pesaje_activo:

                    # Mostrar con indicadores de variación
                    if self.peso_actual:
                        if peso > self.peso_actual:
                            indicador = "[+]"
                        elif peso < self.peso_actual:
                            indicador = "[-]"
                        else:
                            indicador = "[=]"
                    else:
                        indicador = "[PESO]"

                    logger.info(f"{indicador} Peso simulado: {peso:,.2f} kg")

                    # Enviar a Odoo
                    if self.enviar_peso_odoo(self.pesaje_activo, peso):
                        logger.debug(f"[OK] Peso enviado a Odoo")
                        self.peso_actual = peso
                    else:
                        logger.warning("[ADVERTENCIA] No se pudo enviar peso a Odoo")

                else:
                    # No hay pesaje activo
                    if contador_actualizaciones % 30 == 0:  # Cada 30 segundos
                        logger.info("[ESPERANDO] Esperando pesaje activo en Odoo...")

                contador_actualizaciones += 1
                time.sleep(INTERVALO_ACTUALIZACION)

        except KeyboardInterrupt:
            logger.info("\n\n[DETENIDO] Simulador detenido por el usuario")
            logger.info(f"[ESTADISTICAS] Total de actualizaciones enviadas: {contador_actualizaciones}")
        except Exception as e:
            logger.error(f"\n[ERROR FATAL] Error fatal: {e}")
            import traceback
            traceback.print_exc()

    def run_manual(self):
        """Modo manual: escribir pesos desde la terminal"""
        print("=" * 70)
        print("SIMULADOR MANUAL DE BASCULA -> ODOO CLOUDPEPPER")
        print("=" * 70)
        print(f"Odoo URL: {ODOO_URL}")
        print("=" * 70)
        print()
        print("Escribe el peso en kg y presiona Enter para enviarlo.")
        print("Escribe 'q' para salir.")
        print()

        if not self.verificar_configuracion():
            return

        try:
            while True:
                # Buscar pesaje activo
                pesaje_id = self.obtener_pesaje_activo()
                if not pesaje_id:
                    input("[ESPERANDO] No hay pesaje activo. Crea uno en Odoo y presiona Enter...")
                    continue

                print(f"\n[PESAJE ACTIVO] ID: {pesaje_id}")
                print("-" * 40)

                while True:
                    entrada = input("Peso (kg): ").strip()

                    if entrada.lower() == 'q':
                        print("\nHasta luego!")
                        return

                    if entrada == '':
                        # Refrescar pesaje activo
                        nuevo = self.obtener_pesaje_activo()
                        if nuevo != pesaje_id:
                            pesaje_id = nuevo
                            if pesaje_id:
                                print(f"\n[PESAJE ACTIVO] ID: {pesaje_id}")
                            else:
                                print("[INFO] Ya no hay pesaje activo.")
                                break
                        continue

                    try:
                        peso = float(entrada.replace(',', ''))
                    except ValueError:
                        print("[ERROR] Escribe un numero valido. Ej: 15000")
                        continue

                    if peso < 0 or peso > 100000:
                        print("[ERROR] Peso fuera de rango (0 - 100,000 kg)")
                        continue

                    if self.enviar_peso_odoo(pesaje_id, peso):
                        print(f"[OK] {peso:,.2f} kg enviado a Odoo")
                    else:
                        print("[ERROR] No se pudo enviar el peso")

        except KeyboardInterrupt:
            print("\n\n[DETENIDO] Simulador detenido.")
        except Exception as e:
            print(f"\n[ERROR FATAL] {e}")


def menu_interactivo():
    """Menú para configuración rápida"""
    print("\n" + "=" * 70)
    print("SIMULADOR DE BASCULA - CONFIGURACION RAPIDA")
    print("=" * 70)

    # Verificar configuración actual
    if "TU_API_KEY_AQUI" in API_KEY:
        print("\n[ADVERTENCIA] API KEY NO CONFIGURADA")
        print("[INSTRUCCIONES] Edita el archivo y configura:")
        print(f"   ODOO_URL = '{ODOO_URL}'")
        print("   API_KEY = 'tu_api_key_aqui'")
        print("\nLuego ejecuta de nuevo el script.\n")
        return

    print(f"\n[OK] Configuracion actual:")
    print(f"   URL: {ODOO_URL}")
    print(f"   Modo: {MODO_SIMULACION}")
    if MODO_SIMULACION == "fijo":
        print(f"   Peso: {PESO_FIJO} kg")

    print("\nQue deseas hacer?")
    print("1. Iniciar simulador (automatico)")
    print("2. Modo manual (escribir pesos)")
    print("3. Salir")

    opcion = input("\nOpcion (1-3): ").strip()

    if opcion == "1":
        return "auto"
    elif opcion == "2":
        return "manual"
    else:
        print("\nHasta luego!")
        return False


if __name__ == "__main__":
    simulador = BasculaSimulador()

    # --manual: modo manual directo
    if len(sys.argv) > 1 and sys.argv[1] == "--manual":
        simulador.run_manual()
    # --menu: menú interactivo
    elif len(sys.argv) > 1 and sys.argv[1] == "--menu":
        resultado = menu_interactivo()
        if resultado == "manual":
            simulador.run_manual()
        elif resultado == "auto":
            simulador.run()
    else:
        # Modo por defecto segun MODO_SIMULACION
        simulador.run()
