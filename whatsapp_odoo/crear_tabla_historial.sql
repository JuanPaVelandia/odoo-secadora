-- Historial de consultas del bot de WhatsApp.
--
-- Rol aparte del de lectura: `claude_lectura` debe seguir sin poder escribir
-- NADA. Este rol solo puede insertar en esta tabla, en su propio esquema.
--
-- Ejecutar en el VPS:
--   sudo -u postgres psql -d secadora_2 -f crear_tabla_historial.sql
--
-- ANTES: cambia la contraseña de la línea CREATE ROLE.

\set ON_ERROR_STOP on

-- Esquema propio: así el historial no se mezcla con las tablas de Odoo ni
-- aparece cuando el bot lista tablas del negocio.
CREATE SCHEMA IF NOT EXISTS bot;

CREATE TABLE IF NOT EXISTS bot.consultas (
    id           bigserial PRIMARY KEY,
    momento      timestamptz NOT NULL DEFAULT now(),
    numero       text        NOT NULL,
    pregunta     text        NOT NULL,
    respuesta    text,
    vueltas      integer,
    segundos     numeric(8,2),
    coste_usd    numeric(10,6),
    modelo       text,
    tokens_in    integer,
    tokens_cache integer,
    tokens_out   integer,
    con_adjunto  boolean     NOT NULL DEFAULT false,
    error        text
);

-- Consultas típicas: "lo de hoy", "lo de este número".
CREATE INDEX IF NOT EXISTS consultas_momento_idx
    ON bot.consultas (momento DESC);
CREATE INDEX IF NOT EXISTS consultas_numero_idx
    ON bot.consultas (numero, momento DESC);

-- Rol de escritura, solo para esta tabla.
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'claude_historial') THEN
    CREATE ROLE claude_historial
      LOGIN
      PASSWORD 'CAMBIA-ESTA-CONTRASENA'
      NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT
      CONNECTION LIMIT 5;
  END IF;
END
$$;

GRANT CONNECT ON DATABASE secadora_2 TO claude_historial;
GRANT USAGE ON SCHEMA bot TO claude_historial;
GRANT INSERT, SELECT ON bot.consultas TO claude_historial;
GRANT USAGE, SELECT ON SEQUENCE bot.consultas_id_seq TO claude_historial;

-- Que no pueda tocar nada más: ni el resto de la base, ni borrar lo escrito.
REVOKE UPDATE, DELETE, TRUNCATE ON bot.consultas FROM claude_historial;
REVOKE ALL ON SCHEMA public FROM claude_historial;
ALTER ROLE claude_historial SET statement_timeout = '10s';

-- El rol de consultas puede LEER el historial (para responder "cuántas
-- consultas hice esta semana"), pero no escribirlo.
GRANT USAGE ON SCHEMA bot TO claude_lectura;
GRANT SELECT ON bot.consultas TO claude_lectura;

SELECT 'Tabla bot.consultas creada. Roles:' AS info,
       (SELECT count(*) FROM information_schema.role_table_grants
        WHERE grantee = 'claude_historial' AND table_name = 'consultas') AS permisos_historial;
