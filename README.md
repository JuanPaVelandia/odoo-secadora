# Odoo Secadora (Odoo 18 Enterprise)

Suite de módulos para operación de secadora de arroz con:

- Pesajes de báscula (entrada/salida)
- Órdenes de servicio
- Integración de inventario
- Calidad y laboratorio
- Facturación desde orden de servicio
- Bridge local para conectar báscula física por puerto serial (COM/USB)

## Módulos incluidos

- `bascula`
	- Núcleo del proceso de pesaje y órdenes de servicio.
	- API para recibir peso desde bridge externo.
	- Flujo de pesajes y facturación.

- `secadora_bascula`
	- Integración con inventarios (`stock`): pickings, ubicaciones y movimientos asociados.

- `secadora_calidad`
	- Análisis de laboratorio, descuentos y cálculo de peso comercial.

- `bridge`
	- Script Python para ejecutar en el PC conectado a la báscula.
	- Soporte por `.env`, Windows y Docker.

## Compatibilidad

- Objetivo: **Odoo 18 Enterprise**
- Dependencias principales:
	- `bascula`: `base`, `contacts`, `product`, `account`
	- `secadora_bascula`: `bascula`, `stock`
	- `secadora_calidad`: `bascula`, `mail`

## Flujo funcional (operación)

1. Crear orden de servicio.
2. Registrar pesajes (entrada/salida) con doble pesada:
	 - 1ª pesada
	 - 2ª pesada
	 - cálculo automático de peso neto.
3. Pasar orden a `listo_liquidar` / `liquidado`.
4. Generar factura desde la orden.
5. Revisar trazabilidad en chatter:
	 - creación de orden
	 - pesajes por usuario
	 - eventos de facturación.

## API de báscula (módulo `bascula`)

Endpoints principales:

- `POST /api/bascula/actualizar_peso`
- `POST /api/bascula/pesaje_activo`
- `POST /api/bascula/peso_actual_global`
- `GET /api/bascula/test`

Uso típico:

1. Bridge consulta pesaje activo.
2. Bridge envía peso periódico.
3. Odoo actualiza `peso_actual` en el pesaje en curso.

## Bridge de báscula (PC local)

Ubicación: `bridge/`

### Configuración por `.env`

Archivo ejemplo: `bridge/.env.example`

Variables clave:

- `BASCULA_ODOO_URL`
- `BASCULA_ODOO_DB`
- `BASCULA_ODOO_USER`
- `BASCULA_ODOO_PASSWORD`
- `BASCULA_API_KEY` (opcional)
- `BASCULA_PUERTO_SERIAL` (ejemplo: `COM3` o `/dev/ttyUSB0`)

### Ejecución en Windows

1. Instalar Python.
2. Instalar dependencias en `bridge/`:
	 - `pip install -r requirements.txt`
3. Configurar `.env`.
4. Ejecutar:
	 - `iniciar_bridge_windows.bat`

### Ejecución con Docker

En `bridge/`:

- `docker compose up -d --build`
- `docker compose logs -f bascula-bridge`

Nota: en Windows, para puertos COM físicos suele ser más estable ejecutar el bridge directamente con Python.

## Facturación

Desde la orden de servicio se puede:

- Generar factura (`account.move`).
- Ver factura generada.
- Bloquear cancelación de orden facturada.

## Trazabilidad y seguridad

- Bitácora de eventos en pesaje (`historial_seguridad`).
- Registro en chatter de:
	- pesajes realizados por usuario
	- creación de orden
	- generación de factura
- Captura de IP de origen en eventos API de báscula.

## Puesta en marcha / actualización

1. Actualizar código en servidor Odoo.
2. Apps → Actualizar lista de aplicaciones.
3. Actualizar módulos:
	 - `bascula`
	 - `secadora_bascula`
	 - `secadora_calidad`
4. Validar flujo completo en entorno de pruebas.

Si hay cambios estructurales y no importa conservar datos, revisar guía de reinstalación en `REINSTALAR.md`.

## Recomendación de validación (UAT)

- Crear orden
- Registrar 1ª/2ª pesada entrada y salida
- Confirmar liquidación
- Generar factura
- Verificar chatter y reportes
- Probar integración bridge ↔ API ↔ formulario de pesaje