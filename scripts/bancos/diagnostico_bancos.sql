-- Foto del estado de las cuentas bancarias. SOLO LECTURA.
--
-- Correr ANTES de empezar (guardar la salida) y DESPUES de cada paso.
-- El bloque 4 es el que importa: el saldo total del grupo 112005 por compañía
-- no puede cambiar en toda la migracion.
--
-- Uso:
--   sudo -u postgres psql -d secadora_2 -f diagnostico_bancos.sql
--
-- En Odoo 19 account_account NO tiene columnas code ni company_id: el codigo
-- vive en code_store (jsonb con el company_id como clave) y la relacion con
-- compañías en account_account_res_company_rel.

\echo ''
\echo '=== 1. Cuentas del grupo 112005 por compañía ==='
SELECT r.res_company_id AS cia,
       a.code_store->>(r.res_company_id::text) AS code,
       a.name->>'en_US' AS nombre,
       a.account_type,
       a.reconcile
FROM account_account a
JOIN account_account_res_company_rel r ON r.account_account_id = a.id
WHERE a.code_store->>(r.res_company_id::text) LIKE '112005%'
ORDER BY 1, 2;

\echo ''
\echo '=== 2. Diarios bancarios ==='
SELECT j.company_id AS cia, j.code, j.name->>'en_US' AS nombre,
       da.code_store->>(j.company_id::text) AS cuenta,
       sa.code_store->>(j.company_id::text) AS transitoria
FROM account_journal j
LEFT JOIN account_account da ON da.id = j.default_account_id
LEFT JOIN account_account sa ON sa.id = j.suspense_account_id
WHERE j.type = 'bank'
ORDER BY 1, 2;

\echo ''
\echo '=== 3. Lineas de metodo de pago sin cuenta (debe quedar en 0) ==='
SELECT count(*) AS sin_cuenta
FROM account_payment_method_line l
JOIN account_journal j ON j.id = l.journal_id
WHERE j.type = 'bank' AND l.payment_account_id IS NULL;

\echo ''
\echo '=== 4. INVARIANTE: saldo total del grupo 112005 por compañía ==='
\echo '    (no puede cambiar entre el antes y el despues)'
SELECT r.res_company_id AS cia,
       sum(l.balance) AS saldo,
       count(*) AS apuntes
FROM account_move_line l
JOIN account_account a ON a.id = l.account_id
JOIN account_account_res_company_rel r ON r.account_account_id = a.id
WHERE a.code_store->>(r.res_company_id::text) LIKE '112005%'
GROUP BY 1 ORDER BY 1;

\echo ''
\echo '=== 5. Detalle de los apuntes del grupo 112005 ==='
SELECT l.company_id AS cia,
       a.code_store->>(l.company_id::text) AS cuenta,
       j.code AS diario, l.name AS concepto,
       l.debit, l.credit, l.parent_state
FROM account_move_line l
JOIN account_account a ON a.id = l.account_id
JOIN account_journal j ON j.id = l.journal_id
WHERE a.code_store->>(l.company_id::text) LIKE '112005%'
ORDER BY 1, 2, l.date;

\echo ''
\echo '=== 6. INTEGRIDAD: code_store bajo una compañía que no es suya ==='
\echo '    (debe devolver 0 filas; detecta writes sin contexto de compañía)'
SELECT a.id, a.code_store
FROM account_account a
WHERE EXISTS (
    SELECT 1 FROM jsonb_object_keys(a.code_store) k
    WHERE NOT EXISTS (
        SELECT 1 FROM account_account_res_company_rel r
        WHERE r.account_account_id = a.id AND r.res_company_id = k::int));

\echo ''
\echo '=== 7. Codigos duplicados dentro de una misma compañía ==='
\echo '    (debe devolver 0 filas)'
SELECT r.res_company_id AS cia,
       a.code_store->>(r.res_company_id::text) AS code,
       count(*)
FROM account_account a
JOIN account_account_res_company_rel r ON r.account_account_id = a.id
WHERE a.code_store->>(r.res_company_id::text) LIKE '112%'
GROUP BY 1, 2 HAVING count(*) > 1;
