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
from datetime import datetime

# ===== CONFIGURACIÓN =====
# IMPORTANTE: Modifica estos valores según tu instalación

# URL de tu instancia Odoo en CloudPepper
ODOO_URL = "https://223ivyj1eb1.cloudpepper.site"

# API Key (generar desde Odoo → Configuración → Báscula)
API_KEY = "TU_API_KEY_AQUI"

# Peso base a simular (kg)
PESO_BASE_MIN = 5000   # Peso mínimo (5 toneladas)
PESO_BASE_MAX = 35000  # Peso máximo (35 toneladas)

# Variación del peso (simula vibración de báscula)
VARIACION_PESO = 10  # +/- 10 kg

# Intervalo de actualización (en segundos)
INTERVALO_ACTUALIZACION = 1  # Actualizar cada 1 segundo

# Modo de simulación
MODO_SIMULACION = "aleatorio"  # "aleatorio" o "fijo"
PESO_FIJO = 28345.50  # Si modo = "fijo", usar este peso

# ===== FIN CONFIGURACIÓN =====

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bascula_simulador.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


class BasculaSimulador:
    """Simulador de báscula Prometálicos"""

    def __init__(self):
        self.pesaje_activo = None
        self.peso_actual = None
        self.peso_base = None

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
                    tipo = data.get('tipo_proceso', '')
                    logger.info(f"📋 Pesaje activo: ID {pesaje_id}, Placa: {placa}, Tipo: {tipo}")
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
        """Envía el peso simulado a Odoo"""
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
            logger.error("\n👉 Edita el archivo bascula_simulador.py y configura:")
            logger.error("   - ODOO_URL: URL de tu Odoo en CloudPepper")
            logger.error("   - API_KEY: Genera una en Odoo → Configuración → Báscula\n")
            return False

        return True

    def run(self):
        """Loop principal del simulador"""
        logger.info("=" * 70)
        logger.info("🎮 SIMULADOR DE BÁSCULA PROMETÁLICOS → ODOO CLOUDPEPPER")
        logger.info("=" * 70)
        logger.info(f"Odoo URL: {ODOO_URL}")
        logger.info(f"Modo: {MODO_SIMULACION.upper()}")
        if MODO_SIMULACION == "fijo":
            logger.info(f"Peso fijo: {PESO_FIJO} kg (± 2 kg)")
        else:
            logger.info(f"Rango de peso: {PESO_BASE_MIN} - {PESO_BASE_MAX} kg")
            logger.info(f"Variación: ± {VARIACION_PESO} kg")
        logger.info(f"Intervalo: {INTERVALO_ACTUALIZACION}s")
        logger.info("=" * 70)

        # Verificar configuración
        if not self.verificar_configuracion():
            return

        logger.info("\n✅ Simulador iniciado correctamente")
        logger.info("🔍 Esperando pesajes en Odoo...")
        logger.info("💡 Crea un pesaje en Odoo para empezar a ver datos\n")

        contador_actualizaciones = 0

        try:
            while True:
                # Obtener pesaje activo cada 5 actualizaciones
                if contador_actualizaciones % 5 == 0:
                    nuevo_pesaje = self.obtener_pesaje_activo()
                    if nuevo_pesaje != self.pesaje_activo:
                        self.pesaje_activo = nuevo_pesaje
                        if self.pesaje_activo:
                            logger.info(f"\n🎯 Nuevo pesaje activo: {self.pesaje_activo}")
                            logger.info("🔄 Iniciando envío de pesos simulados...\n")
                            # Resetear peso base para nuevo pesaje
                            self.peso_base = None

                # Generar y enviar peso
                if self.pesaje_activo:
                    peso = self.generar_peso()

                    # Mostrar con emojis de variación
                    if self.peso_actual:
                        if peso > self.peso_actual:
                            emoji = "📈"
                        elif peso < self.peso_actual:
                            emoji = "📉"
                        else:
                            emoji = "➡️"
                    else:
                        emoji = "⚖️"

                    logger.info(f"{emoji}  Peso simulado: {peso:,.2f} kg")

                    # Enviar a Odoo
                    if self.enviar_peso_odoo(self.pesaje_activo, peso):
                        logger.debug(f"✅ Peso enviado a Odoo")
                        self.peso_actual = peso
                    else:
                        logger.warning("⚠️  No se pudo enviar peso a Odoo")

                else:
                    # No hay pesaje activo
                    if contador_actualizaciones % 30 == 0:  # Cada 30 segundos
                        logger.info("⏳ Esperando pesaje activo en Odoo...")

                contador_actualizaciones += 1
                time.sleep(INTERVALO_ACTUALIZACION)

        except KeyboardInterrupt:
            logger.info("\n\n⏹️  Simulador detenido por el usuario")
            logger.info(f"📊 Total de actualizaciones enviadas: {contador_actualizaciones}")
        except Exception as e:
            logger.error(f"\n❌ Error fatal: {e}")
            import traceback
            traceback.print_exc()


def menu_interactivo():
    """Menú para configuración rápida"""
    print("\n" + "=" * 70)
    print("🎮 SIMULADOR DE BÁSCULA - CONFIGURACIÓN RÁPIDA")
    print("=" * 70)

    # Verificar configuración actual
    if "TU_API_KEY_AQUI" in API_KEY:
        print("\n⚠️  API KEY NO CONFIGURADA")
        print("👉 Edita el archivo y configura:")
        print(f"   ODOO_URL = '{ODOO_URL}'")
        print("   API_KEY = 'tu_api_key_aqui'")
        print("\nLuego ejecuta de nuevo el script.\n")
        return

    print(f"\n✅ Configuración actual:")
    print(f"   URL: {ODOO_URL}")
    print(f"   Modo: {MODO_SIMULACION}")
    if MODO_SIMULACION == "fijo":
        print(f"   Peso: {PESO_FIJO} kg")

    print("\n¿Qué deseas hacer?")
    print("1. Iniciar simulador")
    print("2. Cambiar a peso fijo")
    print("3. Cambiar a peso aleatorio")
    print("4. Salir")

    opcion = input("\nOpción (1-4): ").strip()

    if opcion == "1":
        return True
    elif opcion == "2":
        peso = input(f"Ingresa peso fijo (actual: {PESO_FIJO}): ").strip()
        if peso:
            print(f"\n📝 Para usar peso fijo de {peso} kg:")
            print(f"   Edita el script y cambia:")
            print(f"   MODO_SIMULACION = 'fijo'")
            print(f"   PESO_FIJO = {peso}")
    elif opcion == "3":
        print(f"\n📝 Para usar peso aleatorio:")
        print(f"   Edita el script y cambia:")
        print(f"   MODO_SIMULACION = 'aleatorio'")
    else:
        print("\n👋 ¡Hasta luego!")
        return False


if __name__ == "__main__":
    # Mostrar menú si no está configurado
    if len(sys.argv) > 1 and sys.argv[1] == "--menu":
        if not menu_interactivo():
            sys.exit(0)

    # Iniciar simulador
    simulador = BasculaSimulador()
    simulador.run()
