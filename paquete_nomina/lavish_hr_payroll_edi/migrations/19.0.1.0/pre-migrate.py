# -*- coding: utf-8 -*-
"""Migración 19.0.1.0: adaptación al nuevo modelo hr.version de Odoo 19.

En Odoo 19 el modelo hr.contract fue eliminado y reemplazado por hr.version.
Este script migra las columnas contract_id → version_id en las tablas del módulo.

Mapeo de columnas:
  hr_payslip_edi.contract_id           → version_id  (Many2one hr.version)
  hr_payslip_edi_line.contract_id      → version_id  (Many2one hr.version)
  hr_payslip_edi_worked_days.contract_id → version_id (relatedcomputed, sin columna física)

Mapeo de datos:
  hr.contract.id → hr.version.id
  En Odoo 19, la migración del núcleo crea registros hr.version por cada hr.contract
  anterior. La tabla hr_version tendrá los mismos ids si la migración oficial de
  Odoo se ejecutó antes. Validamos la existencia de la tabla antes de operar.
"""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return

    # Verificar que la tabla hr_version existe (migración de Odoo 19 ya ejecutada)
    cr.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables
            WHERE table_name = 'hr_version'
        )
    """)
    if not cr.fetchone()[0]:
        _logger.warning(
            "lavish_hr_payroll_edi 19.0.1.0: tabla hr_version no existe aún. "
            "Asegúrese de que la migración del módulo hr de Odoo 19 se ejecutó primero."
        )
        return

    # ── hr_payslip_edi ──────────────────────────────────────────────────────
    # Renombrar columna contract_id → version_id si aún no se hizo
    cr.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.columns
            WHERE table_name = 'hr_payslip_edi' AND column_name = 'contract_id'
        )
    """)
    if cr.fetchone()[0]:
        _logger.info("lavish_hr_payroll_edi: renombrando hr_payslip_edi.contract_id → version_id")
        cr.execute("""
            ALTER TABLE hr_payslip_edi
            RENAME COLUMN contract_id TO version_id
        """)

    # ── hr_payslip_edi_line ─────────────────────────────────────────────────
    cr.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.columns
            WHERE table_name = 'hr_payslip_edi_line' AND column_name = 'contract_id'
        )
    """)
    if cr.fetchone()[0]:
        _logger.info("lavish_hr_payroll_edi: renombrando hr_payslip_edi_line.contract_id → version_id")
        cr.execute("""
            ALTER TABLE hr_payslip_edi_line
            RENAME COLUMN contract_id TO version_id
        """)
