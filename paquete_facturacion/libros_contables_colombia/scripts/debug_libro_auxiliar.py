#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script para depurar el Libro Auxiliar usando Playwright.
Captura errores de consola y analiza problemas de expansión.
"""
import asyncio
import sys
from datetime import datetime

# Configuración
ODOO_URL = "http://localhost:3000"
DATABASE = "bohio"
USERNAME = "admin"
PASSWORD = "123456"

async def debug_libro_auxiliar():
    from playwright.async_api import async_playwright

    print("=" * 80)
    print("DEPURADOR DE LIBRO AUXILIAR - Odoo 18")
    print("=" * 80)
    print(f"Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"URL: {ODOO_URL}")
    print("-" * 80)

    console_errors = []
    console_warnings = []
    console_logs = []
    network_errors = []

    async with async_playwright() as p:
        # Iniciar navegador en modo headless
        browser = await p.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-setuid-sandbox']
        )

        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            ignore_https_errors=True
        )

        page = await context.new_page()

        # Capturar mensajes de consola
        def handle_console(msg):
            text = msg.text
            msg_type = msg.type
            if msg_type == 'error':
                console_errors.append(f"[ERROR] {text}")
                print(f"\033[91m[CONSOLE ERROR]\033[0m {text[:200]}")
            elif msg_type == 'warning':
                console_warnings.append(f"[WARNING] {text}")
                print(f"\033[93m[CONSOLE WARN]\033[0m {text[:200]}")
            elif 'error' in text.lower() or 'exception' in text.lower():
                console_logs.append(f"[LOG] {text}")
                print(f"\033[94m[CONSOLE LOG]\033[0m {text[:200]}")

        page.on('console', handle_console)

        # Capturar errores de red
        def handle_response(response):
            if response.status >= 400:
                network_errors.append(f"[{response.status}] {response.url}")
                print(f"\033[91m[NETWORK ERROR {response.status}]\033[0m {response.url[:100]}")

        page.on('response', handle_response)

        # Capturar errores de página
        def handle_pageerror(error):
            console_errors.append(f"[PAGE ERROR] {error}")
            print(f"\033[91m[PAGE ERROR]\033[0m {str(error)[:200]}")

        page.on('pageerror', handle_pageerror)

        try:
            # 1. Ir a la página de login
            print("\n[1] Navegando al Login de Odoo...")
            await page.goto(f"{ODOO_URL}/web/login", wait_until='domcontentloaded', timeout=60000)
            await asyncio.sleep(3)
            await page.screenshot(path='/tmp/odoo_01_login.png')
            print("    Screenshot: /tmp/odoo_01_login.png")

            # 2. Login
            print("\n[2] Iniciando sesión...")
            # Llenar el formulario de login usando ID específico
            await page.fill('#login', USERNAME)
            await page.fill('#password', PASSWORD)
            await page.screenshot(path='/tmp/odoo_02_form_filled.png')
            print("    Screenshot: /tmp/odoo_02_form_filled.png")

            # Click en el botón de submit
            await page.click('button[type="submit"]')
            await asyncio.sleep(10)  # Esperar carga después del login

            await page.screenshot(path='/tmp/odoo_02_post_login.png')
            print("    Screenshot: /tmp/odoo_02_post_login.png")
            print(f"    URL después del login: {page.url}")

            # Si redirige al portal, navegar explícitamente al backend
            if '/web' not in page.url or '/web/login' in page.url:
                print("    Redirigiendo al backend...")
                await page.goto(f"{ODOO_URL}/web#home", wait_until='domcontentloaded', timeout=30000)
                await asyncio.sleep(5)

            await page.screenshot(path='/tmp/odoo_02_dashboard.png')
            print("    Screenshot: /tmp/odoo_02_dashboard.png")
            print(f"    URL actual: {page.url}")

            # 3. Navegar al Libro Auxiliar
            print("\n[3] Navegando al Libro Auxiliar...")

            # Primero ir a Accounting
            await page.click('a:has-text("Accounting"), .o_app[data-menu-xmlid*="account"]')
            await asyncio.sleep(3)
            await page.screenshot(path='/tmp/odoo_03_accounting.png')
            print("    Screenshot: /tmp/odoo_03_accounting.png")

            # Luego navegar al Libro Auxiliar via menú Reportes > Colombia > Libro Auxiliar
            # O ir directo por URL
            await page.goto(
                f"{ODOO_URL}/web#action=libros_contables_colombia.action_co_auxiliary_book",
                wait_until='domcontentloaded',
                timeout=30000
            )
            await asyncio.sleep(5)  # Esperar carga de JS
            await page.screenshot(path='/tmp/odoo_03_libro_auxiliar.png')
            print("    Screenshot: /tmp/odoo_03_libro_auxiliar.png")

            # 4. Esperar que cargue el reporte
            print("\n[4] Esperando carga del reporte...")
            await asyncio.sleep(5)

            # Buscar líneas del reporte
            lines = await page.query_selector_all('.o_account_reports_level1, .o_account_report_line')
            print(f"    Líneas encontradas: {len(lines)}")

            # 5. Intentar expandir una línea
            print("\n[5] Buscando líneas expandibles...")
            expandable_lines = await page.query_selector_all('[data-expandable="true"], .o_account_reports_unfold_icon')
            print(f"    Líneas expandibles: {len(expandable_lines)}")

            if expandable_lines:
                print("\n[6] Intentando expandir primera línea...")
                try:
                    # Hacer clic en el primer ícono de expansión
                    first_expandable = expandable_lines[0]
                    await first_expandable.click()
                    await asyncio.sleep(3)
                    await page.screenshot(path='/tmp/odoo_04_expanded.png')
                    print("    Screenshot: /tmp/odoo_04_expanded.png")
                except Exception as e:
                    print(f"    Error al expandir: {e}")

            # 6. Verificar el filtro de ocultar cuentas
            print("\n[7] Buscando filtro 'Ocultar cuentas sin movimiento'...")

            # Buscar el menú de opciones
            options_menu = await page.query_selector('.o_filter_menu, .dropdown-toggle:has-text("Opciones")')
            if options_menu:
                await options_menu.click()
                await asyncio.sleep(1)
                await page.screenshot(path='/tmp/odoo_05_options_menu.png')
                print("    Screenshot: /tmp/odoo_05_options_menu.png")

                # Buscar el filtro específico
                hide_filter = await page.query_selector('text="Ocultar cuentas sin movimiento"')
                if hide_filter:
                    print("    ✓ Filtro encontrado!")
                else:
                    print("    ✗ Filtro NO encontrado")

            # 7. Capturar HTML del reporte para análisis
            print("\n[8] Capturando HTML del reporte...")
            report_container = await page.query_selector('.o_account_reports_page, .o_account_report_table, table')
            if report_container:
                html = await report_container.inner_html()
                with open('/tmp/odoo_report_html.html', 'w') as f:
                    f.write(html[:50000])  # Primeros 50KB
                print("    HTML guardado: /tmp/odoo_report_html.html")

            # 8. Ejecutar código JS para debug
            print("\n[9] Ejecutando diagnóstico JavaScript...")
            js_result = await page.evaluate('''() => {
                const result = {
                    owl_loaded: typeof owl !== 'undefined',
                    odoo_loaded: typeof odoo !== 'undefined',
                    report_component: null,
                    options: null,
                    filters: null,
                    errors: []
                };

                try {
                    // Buscar el componente del reporte
                    if (window.odoo && window.odoo.__DEBUG__) {
                        result.debug_available = true;
                    }

                    // Buscar en el DOM
                    const reportEl = document.querySelector('.o_account_reports_page');
                    if (reportEl) {
                        result.report_element = true;
                        result.report_classes = reportEl.className;
                    }

                    // Buscar líneas
                    const lines = document.querySelectorAll('.o_account_reports_level1');
                    result.level1_lines = lines.length;

                    const allLines = document.querySelectorAll('tr[data-line-id]');
                    result.total_lines = allLines.length;

                    // Verificar si hay errores en el DOM
                    const errorElements = document.querySelectorAll('.o_error, .alert-danger, .text-danger');
                    result.error_elements = errorElements.length;

                } catch (e) {
                    result.errors.push(e.toString());
                }

                return result;
            }''')

            print(f"    OWL cargado: {js_result.get('owl_loaded')}")
            print(f"    Odoo cargado: {js_result.get('odoo_loaded')}")
            print(f"    Líneas nivel 1: {js_result.get('level1_lines')}")
            print(f"    Total líneas: {js_result.get('total_lines')}")
            print(f"    Elementos error: {js_result.get('error_elements')}")

            await page.screenshot(path='/tmp/odoo_06_final.png', full_page=True)
            print("\n    Screenshot final: /tmp/odoo_06_final.png")

        except Exception as e:
            print(f"\n\033[91m[ERROR FATAL]\033[0m {e}")
            await page.screenshot(path='/tmp/odoo_error.png')
            import traceback
            traceback.print_exc()

        finally:
            await browser.close()

    # Resumen
    print("\n" + "=" * 80)
    print("RESUMEN DE ERRORES")
    print("=" * 80)

    if console_errors:
        print(f"\n\033[91mErrores de Consola ({len(console_errors)}):\033[0m")
        for err in console_errors[:20]:  # Primeros 20
            print(f"  • {err[:150]}")
    else:
        print("\n\033[92m✓ Sin errores de consola\033[0m")

    if console_warnings:
        print(f"\n\033[93mAdvertencias ({len(console_warnings)}):\033[0m")
        for warn in console_warnings[:10]:
            print(f"  • {warn[:150]}")

    if network_errors:
        print(f"\n\033[91mErrores de Red ({len(network_errors)}):\033[0m")
        for err in network_errors[:10]:
            print(f"  • {err}")
    else:
        print("\n\033[92m✓ Sin errores de red\033[0m")

    print("\n" + "=" * 80)
    print("Screenshots guardados en /tmp/odoo_*.png")
    print("=" * 80)

if __name__ == '__main__':
    asyncio.run(debug_libro_auxiliar())
