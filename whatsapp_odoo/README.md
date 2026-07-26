# Consultar Odoo por WhatsApp

Bot que responde preguntas sobre los datos de la secadora desde cualquier
celular. Escribes por WhatsApp, el bot consulta Odoo y responde en español.

> Es **solo lectura** y solo atiende a los números que autorices.

## Cómo funciona

```
Tu celular → WhatsApp → Evolution API → webhook (este servicio)
                                              ↓
                                     API de Claude (opus-5)
                                              ↓
                                   Postgres de Odoo (solo lectura)
                                              ↓
                        respuesta ← Evolution API ← este servicio
```

Claude recibe la pregunta, escribe el SQL, lo ejecuta contra la base (por
nuestras herramientas, nunca directamente), y redacta la respuesta. Si una
consulta falla, ve el error y la corrige.

## Diferencias con el conector MCP (`../mcp_odoo/`)

| | MCP (Claude Desktop) | WhatsApp (esto) |
|---|---|---|
| Dónde funciona | Solo tu PC | Cualquier celular |
| Requiere túnel SSH | Sí | No (corre en el VPS) |
| Coste | Incluido en tu plan | API por uso |
| Quién puede usarlo | Tú | Los números autorizados |

Los dos comparten `pg_client.py` y el mismo rol `claude_lectura`.

## Coste

Cada consulta gasta tokens de la API de Claude ($5/millón entrada, $25/millón
salida). Una consulta típica ronda 3-8 mil tokens de entrada más la respuesta.
En la práctica, decenas de consultas diarias cuestan **unos pocos dólares al
mes**. El prompt del sistema va cacheado, así que las consultas seguidas salen
más baratas.

Si quieres abaratar más, cambia `CLAUDE_MODELO` a `claude-sonnet-5` — más
barato, algo menos hábil escribiendo SQL complejo.

## Requisitos previos

1. El rol `claude_lectura` creado en Postgres (ver `../mcp_odoo/README.md`, paso 1).
2. La instancia `jpv_bot` de Evolution API conectada.
3. Una API key de Anthropic en [console.anthropic.com](https://console.anthropic.com/settings/keys).

## Despliegue en el VPS (Easypanel)

El VPS ya usa Easypanel, que gestiona HTTPS y el proxy — es lo más sencillo.

### 1. Subir el código

```bash
ssh root@srv1360477.hstgr.cloud
cd /opt/odoo19/custom_addons/odoo-secadora && git pull origin secadora-19
```

### 2. Crear el servicio en Easypanel

En el panel: **+ Service → App**, y configura:

- **Source**: el repositorio, rama `secadora-19`
- **Build**: Dockerfile, ruta `whatsapp_odoo/Dockerfile`
- **Port**: 8080
- **Domain**: activa HTTPS y anota el dominio que te asigne

En **Environment**, pega las variables de `.env.ejemplo` con tus valores.

`PG_HOST` merece atención: dentro del contenedor, `127.0.0.1` es el contenedor
mismo, no el VPS. Usa la IP del host Docker (normalmente `172.17.0.1`) o el
nombre del servicio Postgres si lo gestiona Easypanel.

### 3. Comprobar que arrancó

```bash
curl https://TU-DOMINIO/salud
```

Debe responder:

```json
{"servicio":"ok","autorizados":2,"whatsapp":"open","odoo":"secadora_2"}
```

Si `whatsapp` no dice `open` o `odoo` no dice `secadora_2`, revisa las
variables antes de seguir.

### 4. Conectar el webhook

Este paso le dice a Evolution API dónde entregar los mensajes:

```bash
curl -X POST "https://whatsapp-facturas-evolution-api.h4syfu.easypanel.host/webhook/set/jpv_bot" \
  -H "apikey: TU_EVOLUTION_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "webhook": {
      "enabled": true,
      "url": "https://TU-DOMINIO/webhook",
      "events": ["MESSAGES_UPSERT"]
    }
  }'
```

Verifica:

```bash
curl -H "apikey: TU_EVOLUTION_API_KEY" \
  "https://whatsapp-facturas-evolution-api.h4syfu.easypanel.host/webhook/find/jpv_bot"
```

> ⚠️ **Esto afecta a la instancia compartida con el proyecto de facturas.**
> Ese proyecto lee por *polling*, no por webhook, así que añadir uno no debería
> romperlo. Aun así, después de configurarlo comprueba que la ingesta de
> facturas sigue procesando mensajes con normalidad.

### 5. Probar

Escribe al número del bot (**+57 320 986 0118**) desde un número autorizado:

> ayuda

Debe responder con ejemplos. Luego prueba algo real:

> ¿Cuántos contactos hay registrados?

## Qué se puede preguntar

- "¿Cuántas órdenes de secado hay abiertas?"
- "Peso total secado este mes por finca"
- "¿Qué facturas de compra están sin pagar y de cuánto?"
- "Compara los kilos embolsados de junio contra julio"
- "Los 10 clientes con más volumen este año"

Escribe `ayuda` para ver los ejemplos desde el celular.

## Quién puede usarlo

Solo los números en `NUMEROS_AUTORIZADOS` (con indicativo de país, sin `+`,
separados por comas). Los demás **no reciben respuesta** — ni un error, ni un
"no autorizado": el bot simplemente calla, para no revelar que existe.

Para añadir a alguien, edita la variable en Easypanel y reinicia el servicio.

**El bot ve las mismas 962 tablas que el rol `claude_lectura`**, incluida
nómina si existe. Autoriza solo a quien deba ver todo eso. Si más adelante
necesitas restringir, se hace con un rol de Postgres aparte.

## Seguridad

- **Solo lectura**, cuatro capas (las mismas que `mcp_odoo/`): rol Postgres sin
  permisos de escritura, sesión de solo lectura, conexión que lo fuerza otra
  vez, y validador de SQL.
- **Lista de números** en el webhook: un mensaje de un número no autorizado se
  descarta antes de llegar al modelo.
- **Deduplicación**: si Evolution reintenta, no se procesa dos veces.
- **Sin root** en el contenedor.
- Los grupos se ignoran: la autorización es por número individual.

Lo que este diseño **no** protege: si un número autorizado pierde el teléfono,
quien lo tenga puede consultar. Es el mismo riesgo que con WhatsApp Web.

## Diagnóstico

**El bot no responde** → mira `/salud`. Si `whatsapp` no está `open`, la
instancia se desvinculó del teléfono; reconéctala desde Evolution API.

**Responde "no pude generar una respuesta"** → normalmente es una pregunta
demasiado ambigua. Concreta el periodo o la entidad.

**Tarda mucho** → una consulta compleja puede encadenar varias vueltas. El
timeout de cada SQL es de 30 s y el bucle corta a las 12 vueltas.

**Ver los logs** → en Easypanel, pestaña Logs del servicio. Cada consulta
registra el número, el tiempo y la pregunta.
