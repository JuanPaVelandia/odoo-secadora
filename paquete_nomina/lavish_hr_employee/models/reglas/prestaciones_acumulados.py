# -*- coding: utf-8 -*-

"""
PRESTACIONES SOCIALES - ACUMULADOS
==================================
Acumulados y contadores de reglas.
"""

from odoo import models


class HrSalaryRulePrestacionesAcumulados(models.AbstractModel):
    _inherit = 'hr.salary.rule.prestaciones'

    def _normalize_states(self, states, default_states):
        if states is None:
            return tuple(default_states)
        if isinstance(states, str):
            return (states,)
        return tuple(states) if states else tuple(default_states)

    def _get_prestacion_accumulated(self, localdict, date_from, date_to, code_regla, states=None):
        """
        Obtiene el valor acumulado de prestaciones de períodos anteriores
        Consulta líneas de nóminas procesadas anteriormente

        Este método es para PRESTACIONES (PRIMA, CESANTIAS, etc.)
        NO para provisiones (que usan _get_total_previous_provision)

        IMPORTANTE: Toma TODO EL MES COMPLETO (date_from hasta date_to)
        para incluir todas las liquidaciones del período.

        Args:
            localdict: Diccionario de contexto
            date_from: Fecha inicio del período (inicio del mes/semestre/año)
            date_to: Fecha fin del período (fin del mes/semestre/año)
            code_regla: Código de la regla (PRIMA, CESANTIAS, INTCESANTIAS, VACCONTRATO)
            states: Estados de nómina a incluir (default: ('done', 'paid'))

        Returns:
            tuple: (total_acumulado, lista_ids_lineas)
                - total_acumulado: float - Suma de totales de nóminas anteriores
                - lista_ids_lineas: list - IDs de hr.payslip.line encontradas
        """
        slip = localdict.get('slip')
        contract = localdict.get('contract')
        if not contract:
            return 0, []

        normalized_states = self._normalize_states(states, ('done', 'paid'))

        # Usar caché para evitar consultas repetidas
        cache = localdict.setdefault('_prestaciones_accumulated_cache', {})
        cache_key = (contract.id, date_from, date_to, normalized_states, code_regla)
        
        if cache_key not in cache:
            # Determinar tipo de prestación según código de regla
            tipo_map = {
                'PRIMA': 'prima',
                'CESANTIAS': 'cesantias',
                'VACCONTRATO': 'vacaciones',
                'VACACIONES': 'vacaciones',
                'INTCESANTIAS': 'intereses_cesantias',
            }
            tipo_prestacion = tipo_map.get(code_regla, 'all')

            # Usar servicio centralizado de consultas
            query_service = self.env['period.payslip.query.service']
            result = query_service.get_prestaciones_data(
                contract_id=contract.id,
                date_from=date_from,
                date_to=date_to,
                tipo_prestacion=tipo_prestacion,
                exclude_payslip_id=slip.id if slip else None,
                states=normalized_states,
            )

            # Filtrar por código de regla específico
            filtered_lines = [
                line for line in result.get('list', [])
                if line.get('rule_code') == code_regla
            ]

            total_acumulado = sum(line.get('total', 0.0) for line in filtered_lines)
            ids_lineas = [line['line_id'] for line in filtered_lines]

            cache[cache_key] = {
                'total': total_acumulado,
                'line_ids': ids_lineas,
            }
        else:
            cached_data = cache[cache_key]
            total_acumulado = cached_data['total']
            ids_lineas = cached_data['line_ids']

        if not ids_lineas:
            return 0, []

        localdict[f'{code_regla}_ACCUMULATED'] = {
            'total': total_acumulado,
            'line_ids': ids_lineas,
            'count': len(ids_lineas),
            'date_from': date_from,
            'date_to': date_to,
        }

        return total_acumulado, ids_lineas



    def _get_accumulated_payroll_records(self, localdict, date_from, date_to, code_regla):
        """
        Obtiene registros de hr.accumulated.payroll del período

        Consulta registros de acumulados guardados en hr.accumulated.payroll
        para incluirlos en el cálculo de prestaciones.

        Este método busca registros de:
        - Carga inicial (inception)
        - Novedades (novelty)
        - Ausencias (absence)
        - Ajustes manuales (adjustment)

        Args:
            localdict: Diccionario de contexto
            date_from: Fecha inicio del período
            date_to: Fecha fin del período
            code_regla: Código de la regla salarial

        Returns:
            tuple: (total_acumulado, lista_ids_acumulados)
                - total_acumulado: float - Suma de montos de acumulados
                - lista_ids_acumulados: list - IDs de hr.accumulated.payroll encontrados
        """
        slip = localdict['slip']
        contract = localdict['contract']
        employee = localdict['employee']

        HrSalaryRule = self.env['hr.salary.rule']
        salary_rule = HrSalaryRule.search([('code', '=', code_regla)], limit=1)

        if not salary_rule:
            return 0, []

        HrAccumulatedPayroll = self.env['hr.accumulated.payroll']

        cache = localdict.setdefault('_accumulated_payroll_cache', {})
        cache_key = (employee.id, contract.id, date_from, date_to)
        if cache_key not in cache:
            domain = [
                ('employee_id', '=', employee.id),
                ('date', '>=', date_from),
                ('date', '<=', date_to),
                ('contract_id', '=', contract.id),
            ]
            accumulated_rows = HrAccumulatedPayroll.search_read(
                domain=domain,
                fields=['id', 'amount', 'salary_rule_id', 'accumulated_type', 'date'],
                order='date asc'
            )
            aggregated = {}
            for record in accumulated_rows:
                rule_ref = record.get('salary_rule_id') or []
                rule_id = rule_ref[0] if rule_ref else None
                if not rule_id:
                    continue
                data = aggregated.setdefault(rule_id, {'total': 0.0, 'record_ids': []})
                data['total'] += record.get('amount', 0.0) or 0.0
                data['record_ids'].append(record['id'])
            cache[cache_key] = aggregated

        accumulated = cache.get(cache_key, {})
        rule_data = accumulated.get(salary_rule.id, {})
        total_acumulado = rule_data.get('total', 0.0)
        ids_acumulados = rule_data.get('record_ids', [])

        if not ids_acumulados:
            return 0, []

        localdict[f'{code_regla}_ACCUMULATED_PAYROLL'] = {
            'total': total_acumulado,
            'record_ids': ids_acumulados,
            'count': len(ids_acumulados),
            'date_from': date_from,
            'date_to': date_to,
        }

        return total_acumulado, ids_acumulados



    def _compute_prestaciones_counts(self):
        """Calcula el número de reglas marcadas para prima, cesantías y vacaciones"""
        for rule in self:
            # Obtener estructura asociada a la regla
            struct = rule.struct_id

            if struct:
                # Buscar todas las reglas de la misma estructura
                all_rules = self.search([('struct_id', '=', struct.id), ('active', '=', True)])

                # Contar reglas para cada concepto
                rule.prima_rules_count = len(all_rules.filtered('base_prima'))
                rule.cesantias_rules_count = len(all_rules.filtered('base_cesantias'))
                rule.vacaciones_rules_count = len(all_rules.filtered(lambda r: r.base_vacaciones or r.base_vacaciones_dinero))
                rule.intereses_cesantias_rules_count = len(all_rules.filtered('base_intereses_cesantias'))
            else:
                # Si no hay estructura, contar en toda la compañía
                all_rules = self.search([('company_id', '=', rule.company_id.id), ('active', '=', True)])

                rule.prima_rules_count = len(all_rules.filtered('base_prima'))
                rule.cesantias_rules_count = len(all_rules.filtered('base_cesantias'))
                rule.vacaciones_rules_count = len(all_rules.filtered(lambda r: r.base_vacaciones or r.base_vacaciones_dinero))
                rule.intereses_cesantias_rules_count = len(all_rules.filtered('base_intereses_cesantias'))
