# -*- coding: utf-8 -*-
"""
Servicio de Acumulación de Nóminas
Maneja acumulación de categorías y conceptos de nóminas históricas
"""

import logging
from collections import defaultdict
from typing import Dict, List, Optional
from datetime import date
from odoo.addons.lavish_hr_employee.models.payroll.hr_slip_data_structures import CategoryCollection, CategoryData, RuleData

_logger = logging.getLogger(__name__)


class NominaAccumulationService:
    """
    Servicio para acumulación de nóminas históricas.
    
    Proporciona métodos para obtener:
    - Categorías acumuladas (por código de categoría)
    - Conceptos acumulados (por código de regla)
    - Líneas de nómina acumuladas
    """
    
    def __init__(self, env, batch_ctx=None):
        """
        Args:
            env: Odoo environment
            batch_ctx: PayrollBatchContext opcional
        """
        self.env = env
        self.batch_ctx = batch_ctx
        self._cr = env.cr

    def _normalize_states(self, states, default_states=None):
        if default_states is None:
            default_states = ['done', 'paid']
        if states is None:
            return list(default_states)
        if isinstance(states, str):
            return [states]
        return list(states) if states else list(default_states)

    def _get_category_ids(self, category_codes):
        if not category_codes:
            return []
        return self.env['hr.salary.rule.category'].search([
            ('code', 'in', category_codes)
        ]).ids

    def _get_rule_ids(self, concept_codes):
        if not concept_codes:
            return []
        return self.env['hr.salary.rule'].search([
            ('code', 'in', concept_codes)
        ]).ids

    def _build_payslip_line_domain(
        self,
        contract_id,
        date_from,
        date_to,
        company_id=None,
        exclude_payslip_id=None,
        states=None,
        category_ids=None,
        rule_ids=None,
        group_by_period=True,
    ):
        """
        Construye dominio para líneas de nómina.
        
        Args:
            group_by_period: Si es True, solo incluye nóminas de períodos completos
        """
        domain = [
            ('contract_id', '=', contract_id),
            ('state_slip', 'in', self._normalize_states(states)),
        ]
        
        date_domain = [
            ('date_from', '>=', date_from),
            ('date_from', '<=', date_to),
        ]
        
        domain += date_domain
            
        if company_id:
            domain.append(('company_id', '=', company_id))
        if exclude_payslip_id:
            domain.append(('slip_id', '!=', exclude_payslip_id))
        if category_ids:
            domain.append(('category_id', 'in', category_ids))
        if rule_ids:
            domain.append(('salary_rule_id', 'in', rule_ids))

        return domain

    def _get_category_line_map(self, domain):
        line_rows = self.env['hr.payslip.line'].search_read(
            domain,
            ['id', 'contract_id', 'category_id', 'salary_rule_id', 'leave_id']
        )

        leave_ids = {
            row['leave_id'][0]
            for row in line_rows
            if row.get('leave_id')
        }
        leave_map = {
            leave.id: leave
            for leave in self.env['hr.leave'].browse(leave_ids)
        }

        line_map = defaultdict(
            lambda: {
                'line_ids': [],
                'leave_ids': set(),
                'leave_novelty': set(),
                'leave_liquidacion_value': set(),
            }
        )

        for row in line_rows:
            contract_ref = row.get('contract_id')
            category_ref = row.get('category_id')
            rule_ref = row.get('salary_rule_id')
            if not contract_ref or not category_ref or not rule_ref:
                continue

            key = (contract_ref[0], category_ref[0], rule_ref[0])
            info = line_map[key]
            info['line_ids'].append(row['id'])

            leave_ref = row.get('leave_id')
            if not leave_ref:
                continue
            leave = leave_map.get(leave_ref[0])
            if not leave or not leave.holiday_status_id:
                continue

            info['leave_ids'].add(leave.id)
            novelty = leave.holiday_status_id.novelty or ''
            if novelty:
                info['leave_novelty'].add(novelty)
            liquidacion_value = leave.holiday_status_id.liquidacion_value or ''
            if liquidacion_value:
                info['leave_liquidacion_value'].add(liquidacion_value)

        return line_map

    def _get_concept_line_map(self, domain):
        line_rows = self.env['hr.payslip.line'].search_read(
            domain,
            ['id', 'contract_id', 'salary_rule_id']
        )

        line_map = defaultdict(list)
        for row in line_rows:
            contract_ref = row.get('contract_id')
            rule_ref = row.get('salary_rule_id')
            if not contract_ref or not rule_ref:
                continue
            line_map[(contract_ref[0], rule_ref[0])].append(row['id'])

        return line_map
    
    def get_categories_accumulated(
        self,
        contract_id: int,
        date_from: date,
        date_to: date,
        company_id: Optional[int] = None,
        category_codes: Optional[List[str]] = None,
        exclude_payslip_id: Optional[int] = None,
        states: Optional[List[str]] = None
    ) -> CategoryCollection:
        """
        Obtiene categorías acumuladas usando SQL objects.
        
        Args:
            contract_id: ID del contrato
            date_from: Fecha inicial
            date_to: Fecha final
            company_id: ID de compañía (opcional)
            category_codes: Códigos de categorías a filtrar (opcional)
            exclude_payslip_id: ID de nómina a excluir (opcional)
            states: Estados de nómina (default: ['done', 'paid'])
        
        Returns:
            CategoryCollection con CategoryData y RuleData
        """
        if not contract_id:
            _logger.warning("Contrato no definido para consultar categorías acumuladas")
            return CategoryCollection()
        
        category_ids = self._get_category_ids(category_codes)
        if category_codes and not category_ids:
            _logger.warning("No se encontraron categorías para acumulación")
            return CategoryCollection()

        domain = self._build_payslip_line_domain(
            contract_id=contract_id,
            date_from=date_from,
            date_to=date_to,
            company_id=company_id,
            exclude_payslip_id=exclude_payslip_id,
            states=states,
            category_ids=category_ids,
            group_by_period=True,
        )

        # Agrupar por mes completo o período completo usando SQL
        # IMPORTANTE: Solo incluir nóminas de períodos completos (con period_id)
        # Esto asegura que solo se acumulen nóminas que pertenezcan a un período
        # completo (mes completo o período definido), evitando acumular nóminas
        # parciales o fuera de período.
        query = """
            SELECT 
                HPL.contract_id,
                HPL.category_id,
                HPL.salary_rule_id,
                SUM(HPL.total) as total_sum,
                SUM(HPL.amount) as amount_sum,
                SUM(HPL.quantity) as quantity_sum,
                AVG(HPL.rate) as rate_avg,
                ARRAY_AGG(DISTINCT HPL.id) as line_ids
            FROM hr_payslip_line HPL
            INNER JOIN hr_payslip HP ON HP.id = HPL.slip_id
            WHERE 
                HPL.contract_id = %(contract_id)s
                AND HP.period_id IS NOT NULL
                AND HPL.date_from >= %(date_from)s
                AND HPL.date_from <= %(date_to)s
                AND HP.state IN %(states)s
        """
        
        params = {
            'contract_id': contract_id,
            'date_from': date_from,
            'date_to': date_to,
            'states': tuple(self._normalize_states(states)),
        }
        
        if company_id:
            query += " AND HP.company_id = %(company_id)s"
            params['company_id'] = company_id
            
        if exclude_payslip_id:
            query += " AND HP.id != %(exclude_payslip_id)s"
            params['exclude_payslip_id'] = exclude_payslip_id
            
        if category_ids:
            query += " AND HPL.category_id = ANY(%(category_ids)s)"
            params['category_ids'] = category_ids
            
        query += """
            GROUP BY HPL.contract_id, HPL.category_id, HPL.salary_rule_id
        """
        
        self._cr.execute(query, params)
        grouped = self._cr.dictfetchall()
        
        # Convertir a formato compatible con read_group
        grouped_formatted = []
        for row in grouped:
            grouped_formatted.append({
                'contract_id': (row['contract_id'], ''),
                'category_id': (row['category_id'], ''),
                'salary_rule_id': (row['salary_rule_id'], ''),
                'total': row['total_sum'],
                'amount': row['amount_sum'],
                'quantity': row['quantity_sum'],
                'rate': row['rate_avg'],
                'line_ids': row['line_ids'],
            })
        
        grouped = grouped_formatted

        category_ids_found = {
            row['category_id'][0]
            for row in grouped
            if row.get('category_id')
        }
        rule_ids_found = {
            row['salary_rule_id'][0]
            for row in grouped
            if row.get('salary_rule_id')
        }

        category_map = {
            category.id: category.code
            for category in self.env['hr.salary.rule.category'].browse(category_ids_found)
        }
        rule_map = {
            rule.id: rule.code
            for rule in self.env['hr.salary.rule'].browse(rule_ids_found)
        }

        # Reconstruir domain para line_map (sin group_by_period para obtener todas las líneas)
        domain_for_map = self._build_payslip_line_domain(
            contract_id=contract_id,
            date_from=date_from,
            date_to=date_to,
            company_id=company_id,
            exclude_payslip_id=exclude_payslip_id,
            states=states,
            category_ids=category_ids,
            group_by_period=False,  # Para obtener todas las líneas del período
        )
        line_map = self._get_category_line_map(domain_for_map)

        accumulated = CategoryCollection()
        categories_dict = {}

        for row in grouped:
            contract_ref = row.get('contract_id')
            category_ref = row.get('category_id')
            rule_ref = row.get('salary_rule_id')
            if not contract_ref or not category_ref or not rule_ref:
                continue

            cat_code = category_map.get(category_ref[0])
            rule_code = rule_map.get(rule_ref[0])
            if not cat_code or not rule_code:
                continue

            if cat_code not in categories_dict:
                categories_dict[cat_code] = CategoryData(code=cat_code)

            info = line_map.get((contract_ref[0], category_ref[0], rule_ref[0]), {})
            line_ids = info.get('line_ids', [])
            leave_ids = info.get('leave_ids', set())
            leave_novelty = max(info.get('leave_novelty', set()) or [''], default='')
            leave_liquidacion_value = max(info.get('leave_liquidacion_value', set()) or [''], default='')

            rate_value = row.get('rate')
            rule_data = RuleData(
                code=rule_code,
                total=float(row.get('total') or 0.0),
                amount=float(row.get('amount') or 0.0),
                quantity=float(row.get('quantity') or 0.0),
                rate=float(rate_value) if rate_value else 100.0,
                category_code=cat_code,
                rule_id=rule_ref[0],
                has_leave=bool(leave_ids),
                leave_id=max(leave_ids) if leave_ids else 0,
                leave_novelty=leave_novelty or '',
                leave_liquidacion_value=leave_liquidacion_value or '',
                line_ids=line_ids or []
            )

            categories_dict[cat_code].add_rule(rule_data)

        for category in categories_dict.values():
            accumulated.add_category(category)
        
        _logger.info(
            f"Categorías acumuladas: {len(categories_dict)} categorías, "
            f"período {date_from} - {date_to}, contrato {contract_id}"
        )
        
        return accumulated
    
    def get_concepts_accumulated(
        self,
        contract_id: int,
        date_from: date,
        date_to: date,
        company_id: Optional[int] = None,
        concept_codes: Optional[List[str]] = None,
        exclude_payslip_id: Optional[int] = None,
        states: Optional[List[str]] = None
    ) -> Dict[str, Dict]:
        """
        Obtiene conceptos acumulados por código de regla.
        
        Args:
            contract_id: ID del contrato
            date_from: Fecha inicial
            date_to: Fecha final
            company_id: ID de compañía (opcional)
            concept_codes: Códigos de conceptos a filtrar (opcional)
            exclude_payslip_id: ID de nómina a excluir (opcional)
            states: Estados de nómina (default: ['done', 'paid'])
        
        Returns:
            dict: {
                'concept_code': {
                    'total': float,
                    'line_ids': [int, ...]
                }
            }
        """
        if not contract_id:
            _logger.warning("Contrato no definido para consultar conceptos acumulados")
            return {}
        
        rule_ids = self._get_rule_ids(concept_codes)
        if concept_codes and not rule_ids:
            _logger.warning("No se encontraron conceptos para acumulación")
            return {}

        domain = self._build_payslip_line_domain(
            contract_id=contract_id,
            date_from=date_from,
            date_to=date_to,
            company_id=company_id,
            exclude_payslip_id=exclude_payslip_id,
            states=states,
            rule_ids=rule_ids,
            group_by_period=True,
        )

        # Agrupar por mes completo o período completo usando SQL
        # IMPORTANTE: Solo incluir nóminas de períodos completos (con period_id)
        # Esto asegura que solo se acumulen nóminas que pertenezcan a un período
        # completo (mes completo o período definido), evitando acumular nóminas
        # parciales o fuera de período.
        query = """
            SELECT 
                HPL.contract_id,
                HPL.salary_rule_id,
                SUM(HPL.total) as total_sum,
                ARRAY_AGG(DISTINCT HPL.id) as line_ids
            FROM hr_payslip_line HPL
            INNER JOIN hr_payslip HP ON HP.id = HPL.slip_id
            WHERE 
                HPL.contract_id = %(contract_id)s
                AND HP.period_id IS NOT NULL
                AND HPL.date_from >= %(date_from)s
                AND HPL.date_from <= %(date_to)s
                AND HP.state IN %(states)s
        """
        
        params = {
            'contract_id': contract_id,
            'date_from': date_from,
            'date_to': date_to,
            'states': tuple(self._normalize_states(states)),
        }
        
        if company_id:
            query += " AND HP.company_id = %(company_id)s"
            params['company_id'] = company_id
            
        if exclude_payslip_id:
            query += " AND HP.id != %(exclude_payslip_id)s"
            params['exclude_payslip_id'] = exclude_payslip_id
            
        if rule_ids:
            query += " AND HPL.salary_rule_id = ANY(%(rule_ids)s)"
            params['rule_ids'] = rule_ids
            
        query += """
            GROUP BY HPL.contract_id, HPL.salary_rule_id
        """
        
        self._cr.execute(query, params)
        grouped = self._cr.dictfetchall()
        
        # Convertir a formato compatible con read_group
        grouped_formatted = []
        for row in grouped:
            grouped_formatted.append({
                'contract_id': (row['contract_id'], ''),
                'salary_rule_id': (row['salary_rule_id'], ''),
                'total': row['total_sum'],
                'line_ids': row['line_ids'],
            })
        
        grouped = grouped_formatted

        rule_ids_found = {
            row['salary_rule_id'][0]
            for row in grouped
            if row.get('salary_rule_id')
        }
        rule_map = {
            rule.id: rule.code
            for rule in self.env['hr.salary.rule'].browse(rule_ids_found)
        }

        # Reconstruir domain para line_map (sin group_by_period para obtener todas las líneas)
        domain_for_map = self._build_payslip_line_domain(
            contract_id=contract_id,
            date_from=date_from,
            date_to=date_to,
            company_id=company_id,
            exclude_payslip_id=exclude_payslip_id,
            states=states,
            rule_ids=rule_ids,
            group_by_period=False,  # Para obtener todas las líneas del período
        )
        line_map = self._get_concept_line_map(domain_for_map)

        accumulated = {}
        for row in grouped:
            contract_ref = row.get('contract_id')
            rule_ref = row.get('salary_rule_id')
            if not contract_ref or not rule_ref:
                continue

            concept_code = rule_map.get(rule_ref[0])
            if not concept_code:
                continue

            line_ids = line_map.get((contract_ref[0], rule_ref[0]), [])
            accumulated[concept_code] = {
                'total': float(row.get('total') or 0.0),
                'line_ids': line_ids or []
            }
        
        _logger.info(
            f"Conceptos acumulados: {len(accumulated)} conceptos, "
            f"período {date_from} - {date_to}, contrato {contract_id}"
        )
        
        return accumulated
