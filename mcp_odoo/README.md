# Consultar Odoo desde Claude (MCP)

Conector de **solo lectura** que deja preguntarle a Claude por los datos de la
secadora en lenguaje natural: *"¿cuántas toneladas se secaron en julio?"*,
*"¿qué órdenes de secado siguen abiertas?"*, *"¿cuánto le compramos a cada finca?"*.

Claude traduce la pregunta a SQL, encadena varias consultas si hace falta y
resume la respuesta.

> ⚠️ Apunta a **producción** (`secadora_2`). Por eso el conector solo lee.

## Dos modos, y por qué el de por defecto es Postgres

| | **postgres** (por defecto) | **xmlrpc** |
|---|---|---|
| Coste | **Gratis** — no consume licencia | Gasta un usuario interno de pago |
| Permisos | Los del rol Postgres (los defines tú) | Los de Odoo, con record rules |
| Potencia | SQL completo: JOINs, agregados | Limitado a la API del ORM |
| Campos calculados no almacenados | No los ve | Sí |

Odoo Enterprise cobra por usuario interno, así que crear un usuario solo para
consultas puede salir caro. El modo **postgres** habla directo con la base de
datos y no pasa por la capa de usuarios de Odoo, así que **no consume licencia**.

A cambio, las reglas de acceso de Odoo no aplican: lo que controla qué se puede
ver son los permisos que le des al rol de Postgres en el paso 1.

> Si tu contrato de Odoo restringe accesos programáticos a la base fuera de los
> usuarios licenciados, consúltalo con tu partner antes de usar este modo.

## 1. Crear el rol de solo lectura en el VPS

Copia `crear_usuario_lectura.sql` al servidor y **cambia la contraseña** de la
línea `PASSWORD 'CAMBIA-ESTA-CONTRASENA'` por una larga y única:

```bash
scp mcp_odoo/crear_usuario_lectura.sql root@srv1360477.hstgr.cloud:/tmp/
ssh root@srv1360477.hstgr.cloud
nano /tmp/crear_usuario_lectura.sql          # pon la contraseña
sudo -u postgres psql -d secadora_2 -f /tmp/crear_usuario_lectura.sql
rm /tmp/crear_usuario_lectura.sql            # no dejes la clave ahí
```

El script crea el rol `claude_lectura` con:

- Solo `SELECT`, nunca `INSERT`/`UPDATE`/`DELETE`.
- `default_transaction_read_only = on`: aunque algo intentara escribir, Postgres aborta.
- Sin acceso a `res_users`, `ir_config_parameter`, `res_users_apikeys`,
  `ir_logging` ni `ir_mail_server`. Para datos de usuario hay una vista
  `v_usuarios_basico` sin contraseñas.
- `statement_timeout = 30s` y máximo 5 conexiones, para que una consulta pesada
  no afecte a la operación.

## 2. Instalar

Necesitas Python 3.10+ y [uv](https://docs.astral.sh/uv/):

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Desde esta carpeta:

```bash
uv sync
```

## 3. Abrir el túnel SSH

**No expongas el puerto 5432 a internet.** En vez de eso, un túnel SSH:

```bash
ssh -N -L 15432:localhost:5432 root@srv1360477.hstgr.cloud
```

Eso hace que el Postgres del VPS aparezca en tu `localhost:15432`. Déjalo
abierto mientras uses el conector.

Para que sea permanente en Windows, crea un acceso directo con:

```
ssh -N -L 15432:localhost:5432 root@srv1360477.hstgr.cloud
```

o instala [autossh](https://www.harding.motd.ca/autossh/) para que se
reconecte solo.

## 4. Configurar credenciales

Copia `.env.ejemplo` a `.env` y pon la contraseña del paso 1. `.env` está
ignorado por git.

Comprueba que todo funciona:

```bash
uv run probar_conexion.py
```

Debe decir `Conectado`, listar tablas y confirmar que **no puede escribir**.

## 5a. Conectar con Claude Desktop

Edita `%AppData%\Claude\claude_desktop_config.json` (créalo si no existe):

```json
{
  "mcpServers": {
    "odoo-secadora": {
      "command": "uv",
      "args": [
        "--directory",
        "C:\\Users\\Usuario\\Desktop\\DOCUMENTO5\\Odoo\\Odoo_SGC\\odoo-secadora-main\\mcp_odoo",
        "run",
        "server.py"
      ],
      "env": {
        "MODO_CONEXION": "postgres",
        "PG_HOST": "127.0.0.1",
        "PG_PORT": "15432",
        "PG_DB": "secadora_2",
        "PG_USER": "claude_lectura",
        "PG_PASSWORD": "la-contrasena-del-paso-1"
      }
    }
  }
}
```

Si `uv` no está en el PATH, pon la ruta completa
(`C:\\Users\\Usuario\\AppData\\Local\\Programs\\uv\\uv.exe`).

**Reinicia Claude Desktop.** Aparecerá un icono de herramientas con `odoo-secadora`.

## 5b. Conectar con Claude Code

```bash
claude mcp add odoo-secadora uv \
  --args "--directory" --args "/mnt/c/Users/Usuario/Desktop/DOCUMENTO5/Odoo/Odoo_SGC/odoo-secadora-main/mcp_odoo" \
  --args "run" --args "server.py" \
  --env "MODO_CONEXION=postgres" \
  --env "PG_HOST=127.0.0.1" --env "PG_PORT=15432" \
  --env "PG_DB=secadora_2" --env "PG_USER=claude_lectura" \
  --env "PG_PASSWORD=la-contrasena-del-paso-1"
```

## Qué se puede preguntar

Claude descubre el esquema solo, así que no necesitas saber nombres de tablas:

- "¿Cuántas órdenes de secado hay abiertas?"
- "Dame el peso total secado por finca este mes."
- "¿Qué facturas de compra están sin pagar y de cuánto?"
- "Compara los kilos embolsados de junio contra julio."
- "¿Cuáles son los 10 clientes con más volumen este año?"

## Herramientas expuestas

| Herramienta | Para qué |
|---|---|
| `odoo_sql` | Consulta SELECT libre — la más potente (solo modo postgres) |
| `odoo_listar_modelos` | Descubrir qué tablas hay |
| `odoo_describir_modelo` | Ver las columnas de una tabla |
| `odoo_buscar` | Traer registros de una tabla |
| `odoo_contar` | Contar filas |
| `odoo_agrupar` | Totales por cliente, mes, estado… |
| `odoo_estado_conexion` | Diagnosticar la conexión |

## Notas sobre el esquema de Odoo

- Los modelos usan punto, las tablas guión bajo: `sale.order` → `sale_order`.
- Los Many2one son columnas `<campo>_id`.
- En v19 los campos traducibles son `jsonb`: extrae con `->>'es_CO'`.
- Casi todas las tablas tienen `create_date`, `write_date`, `create_uid`.

## Seguridad

Cuatro capas, de la más importante a la menos:

1. **El rol de Postgres** solo tiene `SELECT`. Es la barrera real.
2. **La sesión** es `default_transaction_read_only`.
3. **La conexión** fuerza solo-lectura y timeout de 30 s.
4. **El validador** rechaza todo lo que no sea un `SELECT` limpio: SQL apilado,
   CTEs con `DELETE ... RETURNING`, comentarios que esconden payload.

La capa 4 es defensa en profundidad, no la principal: un regex siempre se puede
sortear con suficiente ingenio. Por eso importan las capas 1-3.

Los datos que consultes viajan a Claude para poder responderte: el mismo
criterio que aplicarías al pegar un informe en el chat.

## WhatsApp

Este conector es la base. Para exponerlo por WhatsApp hace falta además: número
de WhatsApp Business API (Meta Cloud API), un webhook público en el VPS y
llamadas a la API de Claude (facturadas por uso). La capa de consulta se
reaprovecha tal cual.
