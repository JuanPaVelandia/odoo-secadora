# -*- coding: utf-8 -*-
"""
PRESTACIONES - CARGADOR DE PROVISIONES ACUMULADAS
==================================================
Servicio para consultar provisiones y pagos acumulados desde la base de datos.

Usado por liquidaciones para calcular ajustes (total adeudado - ya provisionado/pagado).
"""
from odoo import models, api
from datetime import date
import logging

_logger = logging.getLogger(__name__)


class PrestacionesProvisionLoader(models.AbstractModel):
    """
    Servicio para cargar provisiones y pagos acumulados de prestaciones.

    Métodos principales:
    - load_provisions(): Carga provisiones acumuladas
    - load_payments(): Carga pagos realizados
    - load_total_accumulated(): Carga total (provisiones + pagos)
    """
    _name = 'hr.salary.rule.prestaciones.provision.loader'
    _description = 'Cargador de Provisiones de Prestaciones'

    # =========================================================================
    # MAPEO DE TIPOS A CÓDIGOS DE REGLAS
    # =========================================================================

    PROVISION_CODES = {
        'prima': 'PRV_PRIM',
        'cesantias': 'PRV_CES',
        'intereses': 'PRV_ICES',
        'vacaciones': 'PRV_VAC',
    }

    PAYMENT_CODES = {
        'prima': ['PRIMA', 'PRIMANOVA'],
        'cesantias': ['CESANTIAS', 'CESANOVA'],
        'intereses': ['INTCESANTIAS', 'INTCESANOVA'],
        'vacaciones': ['VACCONTRATO', 'VACANOVE'],
    }

    # =========================================================================
    # MÉTODOS PRINCIPALES
    # =========================================================================

    def load_provisions(self, contract_id, tipo_prestacion, date_from, date_to, exclude_slip_id=None):
        """
        Carga provisiones acumuladas de un tipo de prestación.

        Args:
            contract_id: ID del contrato
            tipo_prestacion: 'prima', 'cesantias', 'intereses', 'vacaciones'
            date_from: Fecha inicio del período
            date_to: Fecha fin del período
            exclude_slip_id: ID de nómina a excluir (opcional)

        Returns:
            dict: {
                'total': float,
                'count': int,
                'detalle': list[dict],
                'periodo': {'date_from': date, 'date_to': date}
            }
        """
        rule_code = self.PROVISION_CODES.get(tipo_prestacion)
        if not rule_code:
            _logger.warning(f"Tipo prestación desconocido: {tipo_prestacion}")
            return {'total': 0, 'count': 0, 'detalle': [], 'periodo': {}}

        return self._query_payslip_lines(
            contract_id, rule_code, date_from, date_to,
            exclude_slip_id, tipo_linea='provision'
        )

    def load_payments(self, contract_id, tipo_prestacion, date_from, date_to, exclude_slip_id=None):
        """
        Carga pagos realizados de un tipo de prestación.

        Args:
            contract_id: ID del contrato
            tipo_prestacion: 'prima', 'cesantias', 'intereses', 'vacaciones'
            date_from: Fecha inicio del período
            date_to: Fecha fin del período
            exclude_slip_id: ID de nómina a excluir (opcional)

        Returns:
            dict: Mismo formato que load_provisions()
        """
        rule_codes = self.PAYMENT_CODES.get(tipo_prestacion, [])
        if not rule_codes:
            _logger.warning(f"Tipo prestación desconocido: {tipo_prestacion}")
            return {'total': 0, 'count': 0, 'detalle': [], 'periodo': {}}

        return self._query_payslip_lines(
            contract_id, rule_codes, date_from, date_to,
            exclude_slip_id, tipo_linea='pago'
        )

    def load_total_accumulated(self, contract_id, tipo_prestacion, date_from, date_to, exclude_slip_id=None):
        """
        Carga total acumulado (provisiones + pagos) de un tipo de prestación.

        Útil para liquidaciones que necesitan restar todo lo ya contabilizado.

        Returns:
            dict: {
                'total': float,
                'provisiones': dict (resultado de load_provisions),
                'pagos': dict (resultado de load_payments),
                'periodo': dict
            }
        """
        provisiones = self.load_provisions(contract_id, tipo_prestacion, date_from, date_to, exclude_slip_id)
        pagos = self.load_payments(contract_id, tipo_prestacion, date_from, date_to, exclude_slip_id)

        total = provisiones['total'] + pagos['total']

        return {
            'total': total,
            'provisiones': provisiones,
            'pagos': pagos,
            'periodo': {
                'date_from': date_from,
                'date_to': date_to,
            }
        }

    # =========================================================================
    # MÉTODOS AUXILIARES - SQL QUERIES
    # =========================================================================

    def _query_payslip_lines(self, contract_id, rule_codes, date_from, date_to,
                             exclude_slip_id=None, tipo_linea='provision'):
        """
        Query genérico para consultar líneas de nómina.

        Args:
            rule_codes: str o list[str] - Código(s) de regla salarial
            tipo_linea: 'provision' | 'pago' (para logging)

        Returns:
            dict: {total, count, detalle, periodo}
        """
        if isinstance(rule_codes, str):
            rule_codes = [rule_codes]

        # Buscar IDs de reglas salariales
        rules = self.env['hr.salary.rule'].search([('code', 'in', rule_codes)])
        if not rules:
            _logger.warning(f"No se encontraron reglas con códigos: {rule_codes}")
            return {
                'total': 0,
                'count': 0,
                'detalle': [],
                'periodo': {'date_from': date_from, 'date_to': date_to}
            }

        rule_ids = rules.ids

        # Construir query SQL
        query = """
            SELECT
                hsl.salary_rule_id,
                hsr.code AS rule_code,
                hsr.name AS rule_name,
                hp.date_from,
                hp.date_to,
                SUM(hsl.total) AS total,
                COUNT(hsl.id) AS count_lines,
                COUNT(DISTINCT hp.id) AS count_payslips
            FROM hr_payslip_line hsl
            INNER JOIN hr_payslip hp ON hsl.slip_id = hp.id
            INNER JOIN hr_salary_rule hsr ON hsl.salary_rule_id = hsr.id
            WHERE hp.contract_id = %s
              AND hsl.salary_rule_id IN %s
              AND hp.state IN ('done', 'paid')
              AND hp.date_to >= %s
              AND hp.date_to <= %s
        """

        params = [contract_id, tuple(rule_ids), date_from, date_to]

        if exclude_slip_id:
            query += " AND hp.id != %s"
            params.append(exclude_slip_id)

        query += """
            GROUP BY hsl.salary_rule_id, hsr.code, hsr.name, hp.date_from, hp.date_to
            ORDER BY hp.date_to DESC
        """

        # Ejecutar query
        cr = self.env.cr
        cr.execute(query, params)
        rows = cr.fetchall()

        # Procesar resultados
        total_acumulado = 0.0
        count_total = 0
        detalle = []

        for row in rows:
            rule_id, rule_code, rule_name, slip_date_from, slip_date_to, total, count_lines, count_slips = row
            total_float = float(total or 0)
            total_acumulado += total_float
            count_total += int(count_lines or 0)

            detalle.append({
                'rule_id': rule_id,
                'rule_code': rule_code,
                'rule_name': rule_name,
                'date_from': slip_date_from,
                'date_to': slip_date_to,
                'total': total_float,
                'count_lines': int(count_lines or 0),
                'count_payslips': int(count_slips or 0),
            })

        return {
            'total': total_acumulado,
            'count': count_total,
            'detalle': detalle,
            'periodo': {
                'date_from': date_from,
                'date_to': date_to,
            }
        }

    # =========================================================================
    # MÉTODOS ESPECIALIZADOS POR TIPO
    # =========================================================================

    def load_prima_acumulada(self, contract_id, semestre_start, semestre_end, exclude_slip_id=None):
        """
        Carga prima acumulada (provisiones + pagos) del semestre.

        Args:
            contract_id: ID del contrato
            semestre_start: Fecha inicio semestre (1 enero o 1 julio)
            semestre_end: Fecha fin semestre (30 junio o 31 diciembre)
            exclude_slip_id: ID de nómina a excluir

        Returns:
            dict: {total, provisiones, pagos}
        """
        return self.load_total_accumulated(
            contract_id, 'prima', semestre_start, semestre_end, exclude_slip_id
        )

    def load_cesantias_acumuladas(self, contract_id, year_start, year_end, exclude_slip_id=None):
        """
        Carga cesantías acumuladas (provisiones + pagos) del año.

        Args:
            year_start: Fecha inicio año (1 enero)
            year_end: Fecha fin año o fecha actual

        Returns:
            dict: {total, provisiones, pagos}
        """
        return self.load_total_accumulated(
            contract_id, 'cesantias', year_start, year_end, exclude_slip_id
        )

    def load_intereses_acumulados(self, contract_id, year_start, year_end, exclude_slip_id=None):
        """
        Carga intereses acumulados (provisiones + pagos) del año.

        Returns:
            dict: {total, provisiones, pagos}
        """
        return self.load_total_accumulated(
            contract_id, 'intereses', year_start, year_end, exclude_slip_id
        )

    def load_vacaciones_acumuladas(self, contract_id, date_from, date_to, exclude_slip_id=None):
        """
        Carga vacaciones acumuladas (provisiones + pagos) desde última fecha de corte.

        Returns:
            dict: {total, provisiones, pagos}
        """
        return self.load_total_accumulated(
            contract_id, 'vacaciones', date_from, date_to, exclude_slip_id
        )
