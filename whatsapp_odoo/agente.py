"""Traduce una pregunta en español a consultas SQL sobre Odoo y responde.

Usa el bucle de herramientas de la API de Claude: el modelo pide consultas,
nosotros las ejecutamos contra Postgres (solo lectura) y le devolvemos los
resultados hasta que tenga la respuesta.
"""

from __future__ import annotations

import json
import logging
import os

import anthropic

from adjuntos import AdjuntoError
from adjuntos import leer as leer_adjunto

# Copia del cliente de mcp_odoo/, para que este servicio se despliegue solo.
from pg_client import PgError, PgReadOnlyClient

log = logging.getLogger(__name__)

# Opus 5 por defecto: en producción resolvió en 3 vueltas frente a las 4 de
# Sonnet, y la calidad de las respuestas es mejor. Con el caché de la
# conversación cuesta ~$0,08/consulta. Cambiable con CLAUDE_MODELO.
MODELO = os.environ.get("CLAUDE_MODELO", "claude-opus-5")

# Tope de vueltas del bucle. Cada vuelta reenvía todo el contexto acumulado,
# así que el coste crece rápido: en producción se midieron 8 vueltas por
# $0,24. Con 4, una consulta normal cabe de sobra y una que se atasca se
# rinde barato. Configurable por si alguna consulta legítima necesita más.
MAX_VUELTAS = int(os.environ.get("MAX_VUELTAS", "4"))

SISTEMA = """Eres el asistente de consultas de una secadora de arroz colombiana.
Respondes por WhatsApp a preguntas sobre los datos de su Odoo 19.

Tienes acceso de SOLO LECTURA a la base PostgreSQL de Odoo. Para responder,
usa la herramienta `consultar_sql` cuantas veces necesites.

## Cómo trabajar
1. **Escribe el SQL directamente**: abajo tienes las tablas principales. Cada
   llamada a `listar_tablas` o `describir_tabla` cuesta dinero y tiempo, así
   que úsalas solo si de verdad no sabes dónde buscar.
2. Ejecuta y responde con los datos reales.
3. Si una consulta falla, lee el error y corrígela. No inventes datos jamás.
4. Si no encuentras la información, dilo claramente en vez de aproximar.
5. Resuelve en la MENOR cantidad de consultas posible. Si necesitas datos de
   varias tablas, usa JOIN en una sola consulta en vez de encadenar varias.

## Tablas con datos reales (verificado, con nº de filas aprox.)
Esta base está en migración: muchas tablas existen pero están VACÍAS.
Estas son las que tienen datos:

**Mantenimiento — es donde hay más información:**
- `maintenance_equipment_cost_line` (5.861) — costes de repuestos y servicios
- `maintenance_request` (1.164) — órdenes de trabajo
- `maintenance_horometro_reading` (833) — lecturas de horómetro
- `maintenance_equipment_location_history` (406) — movimientos de máquinas
- `maintenance_equipment` (270) — máquinas y componentes
- `maintenance_task_plan_line` (42) — planes de mantenimiento

**Contabilidad y contactos:**
- `res_partner` (549) — clientes, proveedores, fincas
- `account_move_line` (268) — apuntes contables
- `account_account` (1.043) — plan de cuentas
- `account_journal` (57), `account_asset` (128)

**Secadora — ojo con estas dos, se confunden fácil:**
- `secadora_pesaje` — **AQUÍ están los pesos reales de báscula**:
  `peso_bruto`, `peso_tara`, `peso_neto` (numeric), más `fecha`, `name`
  (ej. PES-05960), `state`, `tipo_proceso`, `humedad`, `grano_partido`,
  `impurezas`, `bultos`, `tercero_id` (→ res_partner), `producto_id`,
  `variedad_id`, `origen_id`, `destino_id`, `vehiculo_id`, `placa_texto`.
  **Para "cuánto arroz entró/salió" usa SIEMPRE esta tabla.**
- `secadora_movimiento_arroz` (83) — movimientos internos entre sitios.
  Solo tiene `peso_kg` (no bruto/tara/neto), `pesaje_id` (→ secadora_pesaje),
  `tipo`, `sitio_origen_id`, `sitio_destino_id`, `posicion_id`.

  ⚠️ **Un mismo pesaje genera VARIOS movimientos** y muchos son
  reorganizaciones internas, no ingresos nuevos. Los valores de `tipo` son:
  `movimiento`, `combinacion`, `creacion`, `division`, `despacho`.
  Sumar `peso_kg` de todos **infla enormemente el total**: hoy los 104
  movimientos suman 4,2 millones de kg cuando solo hay 23 pesajes reales.
  **Para totales de arroz ingresado usa `secadora_pesaje.peso_neto`.**

**Reglas al contar arroz (importante):**
- Filtra `secadora_pesaje.state = 'completado'`: hay pesajes cancelados que
  no deben sumar.
- `tipo_proceso` distingue `'entrada'` (recepción) de `'salida'` (despacho).
  Si preguntan "cuánto entró", filtra por `'entrada'`.
- Da el neto, y si te piden detalle acompáñalo de bruto y tara.
- Usa `name` (ej. PES-05960) para identificar cada pesaje en la respuesta.

- `secadora_analisis_lab` (10) — análisis de calidad
- `secadora_descuento_calidad` (6)

**Adjuntos:** `ir_attachment` — metadatos de fotos y documentos.

⚠️ **Vacías o casi vacías** (NO las consultes esperando datos):
`sale_order`, `sale_order_line`, `account_move` (5 filas), `stock_picking`,
`secadora_liquidacion`, `secadora_flete`, `secadora_embolsado_*`,
`secadora_cuadrilla_*`, `secadora_despacho_bultos`.
Si te preguntan por ventas, liquidaciones, fletes o embolsado, di
directamente que esos datos aún no están cargados en el sistema — no
gastes consultas buscándolos.

Si necesitas una tabla que no está en la lista, usa `listar_tablas` con un
filtro. Pero antes pregúntate si el dato existe: esta base está en
migración y muchos módulos aún no tienen información.

## Ahorra consultas (importante)
- Si dos consultas seguidas no devuelven filas, **para y dilo**. No sigas
  probando variantes: cada intento cuesta dinero y el usuario prefiere un
  "no encuentro eso" rápido a esperar 50 segundos por lo mismo.
- Antes de escribir SQL, comprueba en la lista de arriba que la tabla tiene
  datos. Consultar una tabla vacía es tiempo perdido.
- No uses `describir_tabla` salvo que una consulta falle por una columna
  que no existe.

## Esquema de Odoo (importante)
- Los modelos usan punto, las tablas guión bajo: `sale.order` -> `sale_order`.
- Los Many2one son columnas `<campo>_id` que apuntan al id de otra tabla.
- En Odoo 19 los campos traducibles son jsonb: extrae con ->>'es_CO'.
  Ej: `SELECT name->>'es_CO' FROM product_template`.
  Si devuelve NULL, prueba ->>'en_US'.
- Casi todas las tablas tienen create_date, write_date, create_uid.
- Los importes suelen ser `numeric`. Las cantidades pueden venir en kg.
- La tabla res_users está vetada: para usuarios usa la vista v_usuarios_basico.
- Filtra por `active = true` cuando la tabla tenga esa columna, salvo que
  pregunten explícitamente por archivados.

## Formato de respuesta (es WhatsApp, no un informe)
- Responde en español, directo y breve. Dos o tres frases si basta.
- Cifras con separador de miles y sin decimales innecesarios: 1.234.567 kg.
- Para listas usa viñetas con "-", máximo 10 elementos. Si hay más, di cuántos
  faltan.
- Nada de tablas markdown ni encabezados: WhatsApp no los renderiza.
- Usa *negrita de WhatsApp* (un asterisco) para destacar la cifra clave.
- No expliques el SQL que usaste salvo que te lo pidan.

## Enviar archivos guardados en Odoo
Si te piden una foto o un documento ("mándame la foto del pesaje de ayer",
"la foto del arroz del análisis X"):
1. Búscalo en `ir_attachment`: columnas `res_model`, `res_id`, `name`,
   `mimetype`, `file_size`. Cruza `res_id` con la tabla del modelo para
   filtrar por fecha, número de documento o lo que te pidan.
2. Llama a `enviar_adjunto` con el `id` de la fila.
3. **Envía UN archivo por respuesta.** Si hay varios candidatos, descríbelos
   brevemente (fecha, a qué pertenecen) y pregunta cuál quiere. Solo manda
   varios si el usuario los pidió explícitamente ("mándame todas las fotos
   del pesaje X"). Un "sí" a tu pregunta no significa "mándalas todas".
4. Solo puedo enviar adjuntos de modelos de negocio (pesajes, análisis,
   equipos, facturas, contactos). Los iconos y recursos internos de Odoo
   están bloqueados: no los ofrezcas.
5. Las facturas en PDF con la plantilla de Odoo NO están guardadas en la
   base: se generan al vuelo. Si te piden una, explica que puedes dar los
   datos de la factura pero no el PDF con formato.

## Cotizaciones de repuestos (PDF o foto)
Cuando te manden una cotización y pregunten si los precios tienen sentido:

1. Extrae los ítems del documento: descripción, cantidad y precio unitario.
2. Busca cada uno en `maintenance_equipment_cost_line`. **Ahí está el
   histórico de compras de repuestos, NO en purchase_order_line**, que está
   vacía en esta base. Son ~5.800 líneas migradas del sistema anterior.
   - `name` = descripción del repuesto, `code` = código del proveedor antiguo
   - `unit_cost` = precio unitario pagado, `date` = cuándo
   - `partner_id` → res_partner, o `source_name` (texto libre) si no hay
   - `origin`: 'invoice' (con factura), 'historic' (migrado), 'manual'
3. El matching es POR TEXTO: `product_id` está vacío en el histórico migrado.
   Usa ILIKE con las palabras clave del repuesto, no con la frase completa.
   Ej: para "RODAMIENTO SKF 6205 2RS" busca '%RODAMIENTO%6205%' y también
   '%6205%' por separado. Prueba varias combinaciones antes de rendirte.
4. **Si no encuentras histórico de un ítem, dilo. NUNCA estimes un precio
   de mercado ni inventes una referencia.** Es preferible "no tengo con qué
   comparar este" a dar una cifra inventada.
5. **Siempre indica la fecha del precio histórico y cuánto hace de eso.**
   En Colombia la inflación importa: un precio de 2023 no es comparable sin
   contexto. Di "lo compraste a $X en marzo de 2024 (hace ~2 años)".
6. Cierra con una recomendación corta: qué ítems piden revisión y cuáles
   están en línea.
"""

HERRAMIENTAS = [
    {
        "name": "consultar_sql",
        "description": (
            "Ejecuta una consulta SELECT sobre la base de datos de Odoo y "
            "devuelve las filas. Solo lectura: cualquier otra cosa se rechaza. "
            "Una sola sentencia por llamada, sin ';' intermedios."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "consulta": {
                    "type": "string",
                    "description": "La sentencia SELECT (o WITH ... SELECT).",
                },
                "limite": {
                    "type": "integer",
                    "description": "Máximo de filas a devolver (por defecto 50).",
                },
            },
            "required": ["consulta"],
        },
    },
    {
        "name": "listar_tablas",
        "description": (
            "Lista las tablas disponibles en la base de Odoo. Úsala para "
            "descubrir dónde vive un dato cuando no conozcas el esquema."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "filtro": {
                    "type": "string",
                    "description": "Texto a buscar en el nombre, ej. 'sale' o 'secadora'.",
                }
            },
        },
    },
    {
        "name": "describir_tabla",
        "description": "Muestra las columnas de una tabla con su tipo.",
        "input_schema": {
            "type": "object",
            "properties": {
                "tabla": {
                    "type": "string",
                    "description": "Nombre de la tabla, ej. 'sale_order'.",
                }
            },
            "required": ["tabla"],
        },
    },
    {
        "name": "enviar_adjunto",
        "description": (
            "Envía al usuario por WhatsApp un archivo que está guardado en "
            "Odoo (foto de un pesaje, de un análisis, un documento adjunto). "
            "Primero busca el adjunto en la tabla ir_attachment con "
            "consultar_sql para obtener su id, luego llama a esta herramienta. "
            "Si hay varios candidatos, pregúntale al usuario cuál quiere en "
            "vez de mandarlos todos."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "attachment_id": {
                    "type": "integer",
                    "description": "El id de la fila en ir_attachment.",
                },
                "mensaje": {
                    "type": "string",
                    "description": (
                        "Texto breve que acompaña al archivo, ej. 'Foto del "
                        "pesaje PS-0042 del 23 de julio'."
                    ),
                },
            },
            "required": ["attachment_id"],
        },
    },
]


def _con_cache(mensajes: list[dict]) -> list[dict]:
    """Marca el último mensaje como cacheable.

    Sin esto solo se cachea el prompt del sistema, y todo lo que crece —los
    resultados de las consultas— se reenvía a precio completo en cada vuelta.
    Con la marca, las vueltas siguientes leen ese contexto al 10%.
    """
    if not mensajes:
        return mensajes

    salida = list(mensajes)
    ultimo = dict(salida[-1])
    contenido = ultimo.get("content")

    if isinstance(contenido, str):
        ultimo["content"] = [
            {
                "type": "text",
                "text": contenido,
                "cache_control": {"type": "ephemeral"},
            }
        ]
    elif isinstance(contenido, list) and contenido:
        bloques = [dict(b) if isinstance(b, dict) else b for b in contenido]
        if isinstance(bloques[-1], dict):
            bloques[-1]["cache_control"] = {"type": "ephemeral"}
        ultimo["content"] = bloques
    else:
        return salida

    salida[-1] = ultimo
    return salida


def _contenido(pregunta: str, documento: tuple[str, str] | None):
    """Arma el contenido del mensaje, con el adjunto delante si lo hay.

    El documento va primero porque el modelo lee mejor cuando ve el material
    antes que la instrucción sobre él.
    """
    if not documento:
        return pregunta

    mime, b64 = documento
    if mime == "application/pdf":
        bloque = {
            "type": "document",
            "source": {"type": "base64", "media_type": mime, "data": b64},
        }
    else:
        bloque = {
            "type": "image",
            "source": {"type": "base64", "media_type": mime, "data": b64},
        }
    return [bloque, {"type": "text", "text": pregunta}]


class Agente:
    """Mantiene el cliente de Claude y el de Postgres entre preguntas."""

    def __init__(self) -> None:
        self.claude = anthropic.Anthropic()
        self._pg: PgReadOnlyClient | None = None
        # Lo fija responder(): depende de a quién estemos atendiendo.
        self._enviar_archivo = None

    @property
    def pg(self) -> PgReadOnlyClient:
        if self._pg is None:
            self._pg = PgReadOnlyClient()
        return self._pg

    def _ejecutar_herramienta(self, nombre: str, entrada: dict) -> tuple[str, bool]:
        """Devuelve (resultado_en_texto, hubo_error)."""
        try:
            if nombre == "consultar_sql":
                filas = self.pg.consultar(
                    entrada["consulta"], int(entrada.get("limite", 50))
                )
                if not filas:
                    return "La consulta no devolvió ninguna fila.", False
                return json.dumps(filas, ensure_ascii=False, default=str), False

            if nombre == "listar_tablas":
                filtro = (entrada.get("filtro") or "").strip()
                if not filtro:
                    return (
                        "Necesitas un filtro: la base tiene ~960 tablas y "
                        "listarlas todas malgasta contexto. Prueba con una "
                        "palabra clave ('pesaje', 'secado', 'invoice', "
                        "'maintenance'), o mira el esquema del prompt.",
                        True,
                    )
                tablas = self.pg.listar_tablas(filtro)
                nombres = [t["tabla"] for t in tablas]
                if len(nombres) > 40:
                    return (
                        json.dumps(nombres[:40], ensure_ascii=False)
                        + f"\n(y {len(nombres) - 40} mas; afina el filtro)",
                        False,
                    )
                return json.dumps(nombres, ensure_ascii=False), False

            if nombre == "describir_tabla":
                cols = self.pg.describir_tabla(entrada["tabla"])
                return json.dumps(cols, ensure_ascii=False, default=str), False

            if nombre == "enviar_adjunto":
                return self._enviar_adjunto(entrada)

            return f"Herramienta desconocida: {nombre}", True

        except AdjuntoError as exc:
            return f"ERROR: {exc}", True
        except PgError as exc:
            # El error vuelve al modelo para que corrija la consulta.
            return f"ERROR: {exc}", True
        except Exception as exc:
            log.exception("fallo inesperado en la herramienta %s", nombre)
            return f"ERROR inesperado: {exc}", True

    def _enviar_adjunto(self, entrada: dict) -> tuple[str, bool]:
        """Busca el adjunto, lo lee del filestore y lo manda por WhatsApp."""
        if self._enviar_archivo is None:
            return "ERROR: no puedo enviar archivos en este contexto.", True

        try:
            att_id = int(entrada["attachment_id"])
        except (KeyError, TypeError, ValueError):
            return "ERROR: attachment_id debe ser un número entero.", True

        filas = self.pg.consultar(
            "SELECT id, name, res_model, mimetype, file_size, store_fname "
            f"FROM ir_attachment WHERE id = {att_id}",
            1,
        )
        if not filas:
            return f"ERROR: no existe el adjunto {att_id}.", True

        a = filas[0]
        b64 = leer_adjunto(
            a.get("store_fname") or "",
            a.get("res_model") or "",
            int(a.get("file_size") or 0),
            a.get("mimetype") or "",
        )
        nombre = a.get("name") or f"adjunto-{att_id}"
        self._enviar_archivo(
            b64, nombre, a["mimetype"], entrada.get("mensaje", "")
        )
        # El modelo necesita saber que ya salió, para no volver a mandarlo ni
        # anunciar en su respuesta que "lo enviará".
        return (
            f"Archivo '{nombre}' enviado al usuario correctamente. "
            "Ya lo tiene; no lo anuncies como pendiente.",
            False,
        )

    def responder(
        self,
        pregunta: str,
        historial: list[dict] | None = None,
        documento: tuple[str, str] | None = None,
        enviar_archivo=None,
    ) -> tuple[str, list[dict]]:
        """Responde una pregunta y devuelve (respuesta, historial_actualizado).

        El historial permite preguntas de seguimiento ("¿y el mes pasado?").
        `documento` es (mime, base64) de un PDF o imagen adjunto.
        """
        self._enviar_archivo = enviar_archivo
        mensajes: list[dict] = list(historial or [])
        mensajes.append(
            {"role": "user", "content": _contenido(pregunta, documento)}
        )
        # Acumulamos para saber qué cuesta cada consulta: sin esto el gasto
        # solo se ve agregado en la consola de Anthropic, cuando ya es tarde.
        gasto = {"entrada": 0, "salida": 0, "cache_lectura": 0, "cache_escritura": 0}

        for vuelta in range(MAX_VUELTAS):
            respuesta = self.claude.messages.create(
                model=MODELO,
                max_tokens=4096,
                system=[
                    {
                        "type": "text",
                        "text": SISTEMA,
                        # El prompt es estable: cachearlo abarata cada consulta.
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                tools=HERRAMIENTAS,
                messages=_con_cache(mensajes),
            )

            u = respuesta.usage
            gasto["entrada"] += u.input_tokens
            gasto["salida"] += u.output_tokens
            gasto["cache_lectura"] += getattr(u, "cache_read_input_tokens", 0) or 0
            gasto["cache_escritura"] += (
                getattr(u, "cache_creation_input_tokens", 0) or 0
            )

            if respuesta.stop_reason == "refusal":
                # No guardamos el rechazo: dejarlo envenenaría el hilo.
                return (
                    "No puedo responder eso. Si es una consulta legítima de la "
                    "operación, reformúlala de otra manera.",
                    list(historial or []),
                )

            # Avisamos con dos vueltas de margen: con una sola, a veces no
            # da tiempo a cerrar una consulta que necesita un último cruce.
            restantes = MAX_VUELTAS - 1 - vuelta
            if restantes in (1, 2):
                mensajes.append(
                    {
                        "role": "user",
                        "content": (
                            f"[Aviso del sistema: te quedan {restantes} "
                            "consulta(s). Ve cerrando: responde con lo que "
                            "tengas y di claramente qué no pudiste verificar. "
                            "Es preferible un dato parcial bien explicado a "
                            "quedarte sin margen.]"
                        ),
                    }
                )

            if respuesta.stop_reason != "tool_use":
                texto = (
                    "".join(
                        b.text for b in respuesta.content if b.type == "text"
                    ).strip()
                    or "No pude generar una respuesta."
                )
                # Guardamos solo pregunta y respuesta final: los resultados de
                # SQL intermedios pueden ser enormes y no aportan al seguimiento.
                # El adjunto NO se guarda: reenviar el PDF en cada turno
                # posterior multiplicaría el coste sin aportar nada.
                _log_gasto(gasto, vuelta + 1)
                marca = (
                    f"[adjuntó un documento] {pregunta}" if documento else pregunta
                )
                nuevo_historial = list(historial or []) + [
                    {"role": "user", "content": marca},
                    {"role": "assistant", "content": texto},
                ]
                return texto, nuevo_historial

            mensajes.append({"role": "assistant", "content": respuesta.content})

            resultados = []
            for bloque in respuesta.content:
                if bloque.type != "tool_use":
                    continue
                salida, hubo_error = self._ejecutar_herramienta(
                    bloque.name, bloque.input
                )
                if hubo_error:
                    log.warning(
                        "vuelta %d: %s FALLÓ -> %s | entrada: %s",
                        vuelta + 1,
                        bloque.name,
                        salida[:300],
                        json.dumps(bloque.input, ensure_ascii=False)[:400],
                    )
                else:
                    log.info(
                        "vuelta %d: %s -> %s chars",
                        vuelta + 1,
                        bloque.name,
                        len(salida),
                    )
                resultados.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": bloque.id,
                        "content": salida,
                        "is_error": hubo_error,
                    }
                )
            mensajes.append({"role": "user", "content": resultados})

        _log_gasto(gasto, MAX_VUELTAS)
        return (
            "No di con esos datos. Puede que no estén cargados todavía en el "
            "sistema, o que la pregunta necesite más contexto: prueba con un "
            "nombre, una fecha o un número de documento concreto.",
            list(historial or []),
        )


# Precios por millón de tokens, según el modelo configurado.
# La lectura de caché cuesta ~10% de la entrada; la escritura ~125%.
PRECIO_ENTRADA = 3.0 if "sonnet" in MODELO else 5.0
PRECIO_SALIDA = 15.0 if "sonnet" in MODELO else 25.0


def _log_gasto(gasto: dict, vueltas: int) -> None:
    """Registra el coste estimado de la consulta, para poder diagnosticarlo."""
    usd = (
        gasto["entrada"] * PRECIO_ENTRADA
        + gasto["cache_escritura"] * PRECIO_ENTRADA * 1.25
        + gasto["cache_lectura"] * PRECIO_ENTRADA * 0.1
        + gasto["salida"] * PRECIO_SALIDA
    ) / 1_000_000
    log.info(
        "COSTE ~$%.4f | %d vueltas | entrada %d, cache_r %d, cache_w %d, salida %d",
        usd,
        vueltas,
        gasto["entrada"],
        gasto["cache_lectura"],
        gasto["cache_escritura"],
        gasto["salida"],
    )
