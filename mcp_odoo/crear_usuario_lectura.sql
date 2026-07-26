-- Usuario de PostgreSQL de SOLO LECTURA para el conector MCP.
-- No consume licencia de Odoo: no pasa por la capa de usuarios de Odoo.
--
-- Ejecutar en el VPS como root:
--   sudo -u postgres psql -d secadora_2 -f crear_usuario_lectura.sql
--
-- ANTES: cambia la contraseña de la línea CREATE ROLE por una larga y única.

\set ON_ERROR_STOP on

-- 1. El rol. NOSUPERUSER/NOCREATEDB/NOCREATEROLE: no puede escalar privilegios.
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'claude_lectura') THEN
    CREATE ROLE claude_lectura
      LOGIN
      PASSWORD 'CAMBIA-ESTA-CONTRASENA'
      NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT
      CONNECTION LIMIT 5;
  END IF;
END
$$;

-- 2. Conectar a la base y leer el esquema público.
GRANT CONNECT ON DATABASE secadora_2 TO claude_lectura;
GRANT USAGE ON SCHEMA public TO claude_lectura;

-- 3. SELECT sobre las tablas actuales...
GRANT SELECT ON ALL TABLES IN SCHEMA public TO claude_lectura;

-- 4. ...y sobre las que Odoo cree después (módulos nuevos, updates).
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT SELECT ON TABLES TO claude_lectura;

-- 5. Quitar explícitamente todo lo que no sea lectura, por si algún GRANT
--    previo o el rol PUBLIC concedió de más.
REVOKE INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER
  ON ALL TABLES IN SCHEMA public FROM claude_lectura;
REVOKE CREATE ON SCHEMA public FROM claude_lectura;

-- IMPRESCINDIBLE: en PostgreSQL 15 y anteriores, el rol PUBLIC tiene CREATE
-- sobre el esquema public por defecto, y claude_lectura lo hereda. Sin este
-- REVOKE el rol PUEDE crear tablas aunque le quitemos el permiso directo.
-- Verificado en producción (Odoo 19 sobre PG 15): sin esto, CREATE TABLE pasa.
REVOKE CREATE ON SCHEMA public FROM PUBLIC;

-- NOTA: no tocamos los permisos de PUBLIC sobre la BASE (solo sobre el
-- esquema). Revocar CONNECT a PUBLIC dejaría fuera a otros servicios.
-- El usuario de Odoo es dueño de sus tablas, así que no le afecta.

-- 6. res_users se necesita para saber "quién creó qué", pero contiene el hash
--    de la contraseña y el secreto TOTP. Exponemos solo lo inocuo por una
--    vista. Se crea ANTES de revocar, porque la vista la ejecuta su dueño
--    (postgres), no quien la consulta.
CREATE OR REPLACE VIEW v_usuarios_basico AS
  SELECT u.id, p.name AS nombre, u.login, u.active
  FROM res_users u
  JOIN res_partner p ON p.id = u.partner_id;
GRANT SELECT ON v_usuarios_basico TO claude_lectura;

-- 7. Tablas con credenciales y datos sensibles: ni siquiera lectura.
--    Si alguna no existe en esta base, comenta la línea y vuelve a ejecutar.
REVOKE ALL ON ir_config_parameter    FROM claude_lectura;
REVOKE ALL ON res_users              FROM claude_lectura;
REVOKE ALL ON res_users_apikeys      FROM claude_lectura;
REVOKE ALL ON ir_logging             FROM claude_lectura;
REVOKE ALL ON ir_mail_server         FROM claude_lectura;
-- ir_attachment: quita el comentario si no quieres exponer adjuntos.
-- REVOKE ALL ON ir_attachment       FROM claude_lectura;

-- 8. Forzar solo-lectura a nivel de sesión: aunque el código intentara
--    escribir, Postgres aborta la transacción.
ALTER ROLE claude_lectura SET default_transaction_read_only = on;
ALTER ROLE claude_lectura SET statement_timeout = '30s';
ALTER ROLE claude_lectura SET idle_in_transaction_session_timeout = '60s';

-- 9. Comprobación.
SELECT 'Rol creado. Tablas legibles:' AS info,
       count(*) AS total
FROM information_schema.table_privileges
WHERE grantee = 'claude_lectura' AND privilege_type = 'SELECT';
