# -*- coding: utf-8 -*-
"""
Servicio de Consultas Consolidadas por Período
==============================================

Este servicio centraliza todas las consultas repetitivas a hr.payslip y hr.payslip.line
en consultas SQL únicas y optimizadas.

IMPORTANTE: Dos consultas separadas:
1. get_period_payslip_data() - Solo nómina (hr.payslip.line)
2. get_period_leave_data() - Solo ausencias (hr.leave.line)

Después se procesan los resultados según el tipo de cálculo.
"""

from odoo import models, api
from odoo.exceptions import ValidationError


class PeriodPayslipQueryService(models.AbstractModel):
    """
    Servicio centralizado para consultas de nómina agrupadas por período.
    
    Consolida múltiples consultas repetitivas en consultas SQL únicas
    que agrupan datos por período (mes, semestre, año) para mejorar rendimiento.
    
    Soporta:
    - IBD (Ingreso Base de Cotización)
    - RETENCIONES (Retención en la fuente)
    - PRESTACIONES (Prestaciones sociales)
    """
    _name = 'period.payslip.query.service'
    _description = 'Servicio de consultas consolidadas por período'

    def get_period_payslip_data(
        self,
        contract_id,
        date_from,  # date_from de la nómina a liquidar (inicio del período de acumulación)
        date_to,    # date_to de la nómina a liquidar (fin del período de acumulación)
        calculation_type,  # 'ibd', 'retenciones', 'prestaciones'
        exclude_payslip_id=None,
        states=('done', 'paid'),
        # Parámetros específicos según calculation_type
        tipo_prestacion=None,  # Para 'prestaciones': 'prima', 'cesantias', 'vacaciones', 'all'
        contexto_base='liquidacion',  # Para 'prestaciones': 'provision' o 'liquidacion'
        exclude_codes=None,  # Para 'retenciones': códigos a excluir
        include_categories=None,  # Para 'retenciones': categorías a incluir
        excluded_categories=None,  # Para 'prestaciones': categorías a excluir
    ):
        """
        Consulta SQL única para obtener datos de NÓMINA por período.
        
        IMPORTANTE: 
        - date_from: Es el inicio del período de la nómina a liquidar (inicio del período de acumulación)
        - date_to: Es el fin del período de la nómina a liquidar (fin del período de acumulación)
        - La consulta busca nóminas anteriores que estén dentro del rango [date_from, date_to]
        - Se excluye la nómina actual (exclude_payslip_id) del cálculo
        
        Args:
            contract_id: ID del contrato
            date_from: Fecha inicio del período de la nómina a liquidar
            date_to: Fecha fin del período de la nómina a liquidar
            calculation_type: Tipo de cálculo ('ibd', 'retenciones', 'prestaciones')
            exclude_payslip_id: ID de nómina a excluir
            states: Estados de nómina a incluir
            tipo_prestacion: Para 'prestaciones': 'prima', 'cesantias', 'vacaciones', 'intereses_cesantias', 'all'
            contexto_base: Para 'prestaciones': 'provision' o 'liquidacion'
            exclude_codes: Para 'retenciones': Lista de códigos de reglas a excluir
            include_categories: Para 'retenciones': Lista de categorías a incluir
            excluded_categories: Para 'prestaciones': Lista de categorías a excluir
        
        Returns:
            dict: {
                'total': float,
                'totals_by_type': {...},
                'list': [...],
                'by_period': {...},
                'by_category': {...},  # Solo para 'retenciones'
                'by_base_field': {...},  # Solo para 'prestaciones'
            }
        """
        # Preparar parámetros base
        # Convertir states a lista para PostgreSQL array
        if states is None:
            states_list = ['done', 'paid']
        elif isinstance(states, tuple):
            states_list = list(states)
        elif isinstance(states, list):
            states_list = states
        else:
            states_list = [states]  # Si es un string único
        
        params = {
            'contract_id': contract_id,
            'date_from': date_from,
            'date_to': date_to,
            'exclude_payslip_id': exclude_payslip_id or 0,
            'states': tuple(states_list) if states_list else ('done', 'paid'),
        }
        
        # Construir filtros WHERE dinámicos según calculation_type
        where_filters = []
        select_extra_fields = []
        
        if calculation_type == 'ibd':
            where_filters.append("""
                hsr.base_seguridad_social = TRUE
                AND (hsr.excluir_seguridad_social = FALSE OR hsr.excluir_seguridad_social IS NULL)
                AND (hsrc.code != 'AUX' AND (hsrc_parent.code IS NULL OR hsrc_parent.code != 'AUX'))
            """)
            select_extra_fields.append("""
                CASE 
                    WHEN hsrc.code = 'DEV_NO_SALARIAL' OR hsrc_parent.code = 'DEV_NO_SALARIAL'
                    THEN 'no_salary'
                    ELSE 'salary'
                END AS data_type
            """)
            
        elif calculation_type == 'retenciones':
            exclude_codes = exclude_codes or []
            include_categories = include_categories or ['BASIC', 'DEV_SALARIAL', 'DEV_NO_SALARIAL', 'HEYREC', 'COMISIONES']
            
            # Construir filtro de códigos excluidos (solo si hay códigos a excluir)
            exclude_filter = ""
            if exclude_codes:
                exclude_codes_tuple = tuple(exclude_codes)
                params['exclude_codes'] = exclude_codes_tuple
                exclude_filter = "AND hsr.code NOT IN %(exclude_codes)s"
            
            # Convertir a tupla para PostgreSQL IN
            include_categories_tuple = tuple(include_categories) if include_categories else ('',)
            params['include_categories'] = include_categories_tuple
            
            where_filters.append(f"""
                (hsr.excluir_ret = FALSE OR hsr.excluir_ret IS NULL)
                {exclude_filter}
                AND (hsrc.code IN %(include_categories)s
                     OR hsrc_parent.code IN %(include_categories)s)
            """)
            select_extra_fields.append("""
                CASE 
                    WHEN hsrc.code = 'BASIC' THEN 'basic'
                    WHEN hsrc.code IN ('DEV_SALARIAL', 'HEYREC', 'COMISIONES') THEN 'devengos'
                    WHEN hsrc.code = 'DEV_NO_SALARIAL' THEN 'dev_no_salarial'
                    ELSE 'other'
                END AS data_type
            """)
            
        elif calculation_type == 'prestaciones':
            excluded_categories = excluded_categories or ['BASIC', 'DED', 'PROV', 'SSOCIAL', 'PRESTACIONES_SOCIALES', 'NET']
            tipo_prestacion = tipo_prestacion or 'all'
            contexto_base = contexto_base or 'liquidacion'
            if contexto_base not in ('provision', 'liquidacion'):
                contexto_base = 'liquidacion'
            
            # Construir filtro de campo base según tipo_prestacion
            base_field_map = {
                'prima': f'base_prima_{contexto_base}',
                'cesantias': f'base_cesantias_{contexto_base}',
                'vacaciones': f'base_vacaciones_{contexto_base}',
                'vacaciones_dinero': f'base_vacaciones_dinero_{contexto_base}',
                'intereses_cesantias': f'base_intereses_cesantias_{contexto_base}',
            }
            
            if tipo_prestacion == 'all':
                base_filter = f"""
                    (hsr.base_prima_{contexto_base} = TRUE OR hsr.base_cesantias_{contexto_base} = TRUE
                     OR hsr.base_vacaciones_{contexto_base} = TRUE OR hsr.base_vacaciones_dinero_{contexto_base} = TRUE
                     OR hsr.base_intereses_cesantias_{contexto_base} = TRUE)
                """
            else:
                base_field = base_field_map.get(tipo_prestacion, f'base_prima_{contexto_base}')
                base_filter = f"hsr.{base_field} = TRUE"
            
            # Construir filtro de categorías excluidas (solo si hay categorías a excluir)
            excluded_filter = ""
            if excluded_categories:
                excluded_categories_tuple = tuple(excluded_categories)
                params['excluded_categories'] = excluded_categories_tuple
                excluded_filter = "AND hsrc.code NOT IN %(excluded_categories)s"
            
            where_filters.append(f"""
                {base_filter}
                {excluded_filter}
            """)


            select_extra_fields.append(f"""
                CASE 
                    WHEN hsr.base_prima_{contexto_base} THEN 'base_prima_{contexto_base}'
                    WHEN hsr.base_cesantias_{contexto_base} THEN 'base_cesantias_{contexto_base}'
                    WHEN hsr.base_vacaciones_{contexto_base} THEN 'base_vacaciones_{contexto_base}'
                    WHEN hsr.base_vacaciones_dinero_{contexto_base} THEN 'base_vacaciones_dinero_{contexto_base}'
                    WHEN hsr.base_intereses_cesantias_{contexto_base} THEN 'base_intereses_cesantias_{contexto_base}'
                    ELSE NULL
                END AS base_field,
                CASE 
                    WHEN hsrc.code = 'BASIC' THEN 'basic'
                    ELSE 'variable'
                END AS data_type
            """)
        
        # Construir consulta SQL completa
        extra_select = ', ' + ', '.join(select_extra_fields) if select_extra_fields else ', NULL AS data_type'
        extra_where = ' AND ' + ' AND '.join(where_filters) if where_filters else ''
        # Nota: base_field ya está incluido en extra_select para 'prestaciones', no se necesita agregar separadamente
        
        # Agregar parámetro para estados de ausencia (para el CTE de ausencias)
        # Convertir a tupla para PostgreSQL IN
        if 'leave_states' not in params:
            params['leave_states'] = ('paid', 'validate', 'validated')
        else:
            if isinstance(params['leave_states'], list):
                params['leave_states'] = tuple(params['leave_states'])
            elif not isinstance(params['leave_states'], tuple):
                params['leave_states'] = (params['leave_states'],)
        
        # CONSULTA SQL ÚNICA PARA NÓMINA (incluye IDs de ausencias del período)
        query = f"""
        WITH
        -- CTE 1: Nóminas del período de acumulación
        payslips_by_period AS (
            SELECT
                hp.id AS payslip_id,
                hp.number AS payslip_number,
                hp.date_from,
                hp.date_to,
                TO_CHAR(hp.date_from, 'YYYY-MM') AS period_key,
                EXTRACT(YEAR FROM hp.date_from) AS year,
                EXTRACT(MONTH FROM hp.date_from) AS month
            FROM hr_payslip hp
            WHERE hp.contract_id = %(contract_id)s
              AND hp.state IN %(states)s
              AND hp.date_from >= %(date_from)s
              AND hp.date_to <= %(date_to)s
              AND (hp.id != %(exclude_payslip_id)s OR %(exclude_payslip_id)s = 0)
        ),
        -- CTE 2: Ausencias del período actual (para incluir sus IDs en la consulta de nómina)
        leaves_current_period AS (
            SELECT
                hll.id AS leave_line_id,
                hll.leave_id,
                hll.date,
                TO_CHAR(hll.date, 'YYYY-MM') AS period_key,
                hl.contract_id
            FROM hr_leave_line hll
            INNER JOIN hr_leave hl ON hl.id = hll.leave_id
            WHERE hl.contract_id = %(contract_id)s
              AND hl.state = 'validate'
              AND hll.state IN %(leave_states)s
              AND hll.date BETWEEN %(date_from)s AND %(date_to)s
        ),
        -- CTE 3: Agrupar ausencias por período
        leaves_by_period_agg AS (
            SELECT
                period_key,
                ARRAY_AGG(leave_line_id) AS leave_line_ids,
                ARRAY_AGG(DISTINCT leave_id) AS leave_ids
            FROM leaves_current_period
            GROUP BY period_key
        )
        -- SELECT final: Lista detallada de líneas de nómina (con IDs de ausencias del período)
        SELECT
            hpl.id AS line_id,
            hpl.slip_id AS payslip_id,
            pbp.payslip_number,
            hpl.date_from,
            hpl.date_to,
            hsr.code AS rule_code_full,
            COALESCE(hsr.name->>'es_CO', hsr.name->>'en_US', hsr.code) AS rule_name,
            hsrc.code AS category_code,
            COALESCE(hsrc.name->>'es_CO', hsrc.name->>'en_US', hsrc.code) AS category_name,
            hpl.total,
            hpl.amount,
            hpl.quantity,
            pbp.period_key,
            pbp.year,
            pbp.month,
            'payslip' AS source_type,
            COALESCE(lpa.leave_line_ids, ARRAY[]::int[]) AS leave_line_ids,
            COALESCE(lpa.leave_ids, ARRAY[]::int[]) AS leave_ids
            {extra_select}
        FROM hr_payslip_line hpl
        INNER JOIN payslips_by_period pbp ON pbp.payslip_id = hpl.slip_id
        INNER JOIN hr_salary_rule hsr ON hsr.id = hpl.salary_rule_id
        -- Odoo 19: hr.payslip.line.category_id es related (no columna fisica). Usar hsr.category_id.
        INNER JOIN hr_salary_rule_category hsrc ON hsrc.id = hsr.category_id
        LEFT JOIN hr_salary_rule_category hsrc_parent ON hsrc.parent_id = hsrc_parent.id
        LEFT JOIN leaves_by_period_agg lpa ON lpa.period_key = pbp.period_key
        WHERE hpl.total > 0
          {extra_where}
        ORDER BY pbp.period_key, hpl.date_from, hsrc.code, hsr.code
        """
        
        # Ejecutar consulta
        self._cr.execute(query, params)
        rows = self._cr.dictfetchall()

        # Procesar resultados
        return self._process_payslip_results(rows, calculation_type)

    def get_period_leave_data(
        self,
        contract_id,
        date_from,  # date_from de la nómina a liquidar (inicio del período de acumulación)
        date_to,    # date_to de la nómina a liquidar (fin del período de acumulación)
        calculation_type,  # 'ibd', 'retenciones', 'prestaciones'
        leave_states=None,  # Estados de ausencia ('paid', 'validate', 'validated')
    ):
        """
        Consulta SQL única para obtener datos de AUSENCIAS por período.
        
        IMPORTANTE: 
        - date_from: Es el inicio del período de la nómina a liquidar (inicio del período de acumulación)
        - date_to: Es el fin del período de la nómina a liquidar (fin del período de acumulación)
        - La consulta busca ausencias que intersecten con el rango [date_from, date_to]
        
        Args:
            contract_id: ID del contrato
            date_from: Fecha inicio del período de la nómina a liquidar
            date_to: Fecha fin del período de la nómina a liquidar
            calculation_type: Tipo de cálculo ('ibd', 'retenciones', 'prestaciones')
            leave_states: Estados de ausencia a incluir
        
        Returns:
            dict: {
                'total': float,
                'totals_by_type': {...},
                'list': [...],
                'by_period': {...},
                'by_category': {...},  # Solo para 'retenciones'
                'by_base_field': {...},  # Solo para 'prestaciones'
            }
        """
        # Preparar parámetros base
        # Convertir leave_states a tupla para PostgreSQL IN
        if leave_states is None:
            leave_states = ('paid', 'validate', 'validated')
        elif isinstance(leave_states, list):
            leave_states = tuple(leave_states)
        elif not isinstance(leave_states, tuple):
            leave_states = (leave_states,)
        
        params = {
            'contract_id': contract_id,
            'date_from': date_from,
            'date_to': date_to,
            'leave_states': leave_states,
        }
        
        # Para ausencias, los filtros son más simples (no tienen salary_rule)
        # Mapeamos leave_type a categorías según el tipo de cálculo
        select_extra_fields = []
        
        if calculation_type == 'ibd':
            # Para IBD, las ausencias pagadas pueden ser parte del cálculo
            select_extra_fields.append("""
                CASE 
                    WHEN HLT.unpaid_absences THEN 'no_salary'
                    ELSE 'salary'
                END AS data_type
            """)
        elif calculation_type == 'retenciones':
            # Para retenciones, clasificamos por tipo de ausencia
            select_extra_fields.append("""
                CASE 
                    WHEN HLT.unpaid_absences THEN 'dev_no_salarial'
                    ELSE 'devengos'
                END AS data_type
            """)
        elif calculation_type == 'prestaciones':
            # Para prestaciones, las ausencias pueden afectar la base
            select_extra_fields.append("""
                NULL AS base_field,
                CASE 
                    WHEN HLT.unpaid_absences THEN 'variable'
                    ELSE 'basic'
                END AS data_type
            """)
        else:
            select_extra_fields.append("NULL AS data_type")
        
        extra_select = ', ' + ', '.join(select_extra_fields) if select_extra_fields else ', NULL AS data_type'
        base_field_select = ', base_field' if calculation_type == 'prestaciones' else ''
        
        # CONSULTA SQL ÚNICA PARA AUSENCIAS
        query = f"""
        WITH
        -- CTE 1: Ausencias del período de acumulación
        leaves_by_period AS (
            SELECT
                hl.id AS leave_id,
                hl.contract_id,
                hl.date_from,
                hl.date_to,
                TO_CHAR(hl.date_from, 'YYYY-MM') AS period_key,
                EXTRACT(YEAR FROM hl.date_from) AS year,
                EXTRACT(MONTH FROM hl.date_from) AS month
            FROM hr_leave hl
            WHERE hl.contract_id = %(contract_id)s
              AND hl.state = 'validate'
              AND hl.date_from <= %(date_to)s
              AND hl.date_to >= %(date_from)s
        )
        -- SELECT final: Lista detallada de líneas de ausencia
        SELECT
            hll.id AS line_id,
            NULL::int AS payslip_id,
            NULL::varchar AS payslip_number,
            hll.date AS date_from,
            hll.date AS date_to,
            HLT.code AS rule_code_full,
            COALESCE(HLT.name->>'es_CO', HLT.name->>'en_US', HLT.code) AS rule_name,
            CASE
                WHEN HLT.unpaid_absences THEN 'DED'
                ELSE 'DEV_SALARIAL'
            END AS category_code,
            COALESCE(HLT.name->>'es_CO', HLT.name->>'en_US', HLT.code) AS category_name,
            COALESCE(hll.amount, 0) AS total,
            COALESCE(hll.amount, 0) AS amount,
            COALESCE(hll.days_payslip, 0) AS quantity,
            lbp.period_key,
            lbp.year,
            lbp.month,
            'leave' AS source_type
            {extra_select}
            {base_field_select}
        FROM hr_leave_line hll
        INNER JOIN leaves_by_period lbp ON lbp.leave_id = hll.leave_id
        INNER JOIN hr_leave hl ON hl.id = hll.leave_id
        INNER JOIN hr_leave_type HLT ON HLT.id = hl.holiday_status_id
        WHERE hll.state IN %(leave_states)s
          AND hll.date BETWEEN %(date_from)s AND %(date_to)s
        ORDER BY lbp.period_key, hll.date, HLT.code
        """
        
        # Ejecutar consulta
        self._cr.execute(query, params)
        rows = self._cr.dictfetchall()
        
        # Procesar resultados
        return self._process_leave_results(rows, calculation_type)

    def get_period_data_combined(
        self,
        contract_id,
        date_from,
        date_to,
        calculation_type,
        exclude_payslip_id=None,
        states=('done', 'paid'),
        leave_states=None,
        # Parámetros específicos
        tipo_prestacion=None,
        exclude_codes=None,
        include_categories=None,
        excluded_categories=None,
    ):
        """
        Obtiene datos combinados de nómina Y ausencias, procesando ambas consultas.
        
        Ejecuta las dos consultas separadas y combina los resultados.
        
        Returns:
            dict: Resultado combinado con source_type en cada línea
        """
        # Ejecutar ambas consultas
        payslip_data = self.get_period_payslip_data(
            contract_id=contract_id,
            date_from=date_from,
            date_to=date_to,
            calculation_type=calculation_type,
            exclude_payslip_id=exclude_payslip_id,
            states=states,
            tipo_prestacion=tipo_prestacion,
            exclude_codes=exclude_codes,
            include_categories=include_categories,
            excluded_categories=excluded_categories,
        )
        
        leave_data = self.get_period_leave_data(
            contract_id=contract_id,
            date_from=date_from,
            date_to=date_to,
            calculation_type=calculation_type,
            leave_states=leave_states,
        )
        
        # Combinar resultados
        return self._combine_results(payslip_data, leave_data, calculation_type)

    def _process_payslip_results(self, rows, calculation_type):
        """Procesa resultados de la consulta de nómina."""
        return self._process_results(rows, calculation_type, 'payslip')

    def _process_leave_results(self, rows, calculation_type):
        """Procesa resultados de la consulta de ausencias."""
        return self._process_results(rows, calculation_type, 'leave')

    def _process_results(self, rows, calculation_type, source_type='payslip'):
        """
        Procesa los resultados de la consulta según el tipo de cálculo.
        """
        total = 0.0
        list_detail = []
        by_period = {}
        totals_by_type = {}
        
        # Inicializar totales según tipo
        if calculation_type == 'ibd':
            totals_by_type = {'total_salary': 0.0, 'total_no_salary': 0.0}
        elif calculation_type == 'retenciones':
            totals_by_type = {
                'total_basic': 0.0,
                'total_devengos': 0.0,
                'total_dev_no_salarial': 0.0,
            }
            by_category = {}
        elif calculation_type == 'prestaciones':
            totals_by_type = {'total_basic': 0.0, 'total_variables': 0.0}
            by_base_field = {}
        
        # Procesar cada fila
        for row in rows:
            total += row['total']
            data_type = row.get('data_type', 'other')
            
            # Construir detalle de línea
            line_detail = {
                'line_id': row['line_id'],
                'payslip_id': row['payslip_id'],
                'payslip_number': row['payslip_number'],
                'date_from': row['date_from'],
                'date_to': row['date_to'],
                'rule_code': row['rule_code_full'],
                'rule_name': row['rule_name'],
                'category_code': row['category_code'],
                'category_name': row['category_name'],
                'total': row['total'],
                'amount': row['amount'],
                'quantity': row['quantity'],
                'period_key': row['period_key'],
                'source_type': source_type,
            }
            
            # Agregar IDs de ausencias del período (si existen)
            if 'leave_line_ids' in row and row['leave_line_ids']:
                line_detail['leave_line_ids'] = row['leave_line_ids']
            if 'leave_ids' in row and row['leave_ids']:
                line_detail['leave_ids'] = row['leave_ids']
            
            if calculation_type == 'prestaciones':
                line_detail['base_field'] = row.get('base_field')
            
            list_detail.append(line_detail)
            
            # Agrupar por período
            period_key = row['period_key']
            if period_key not in by_period:
                by_period[period_key] = {
                    'total': 0.0,
                    'line_ids': [],
                    **{k: 0.0 for k in totals_by_type.keys()}
                }
            
            by_period[period_key]['total'] += row['total']
            by_period[period_key]['line_ids'].append(row['line_id'])
            
            # Acumular totales por tipo según calculation_type
            if calculation_type == 'ibd':
                if data_type == 'salary':
                    totals_by_type['total_salary'] += row['total']
                    by_period[period_key]['total_salary'] += row['total']
                elif data_type == 'no_salary':
                    totals_by_type['total_no_salary'] += row['total']
                    by_period[period_key]['total_no_salary'] += row['total']
                    
            elif calculation_type == 'retenciones':
                if data_type == 'basic':
                    totals_by_type['total_basic'] += row['total']
                    by_period[period_key]['total_basic'] += row['total']
                elif data_type == 'devengos':
                    totals_by_type['total_devengos'] += row['total']
                    by_period[period_key]['total_devengos'] += row['total']
                elif data_type == 'dev_no_salarial':
                    totals_by_type['total_dev_no_salarial'] += row['total']
                    by_period[period_key]['total_dev_no_salarial'] += row['total']
                
                # Agrupar por categoría
                cat_code = row['category_code']
                if cat_code not in by_category:
                    by_category[cat_code] = {'total': 0.0, 'line_ids': []}
                by_category[cat_code]['total'] += row['total']
                by_category[cat_code]['line_ids'].append(row['line_id'])
                
            elif calculation_type == 'prestaciones':
                if data_type == 'basic':
                    totals_by_type['total_basic'] += row['total']
                    by_period[period_key]['total_basic'] += row['total']
                else:
                    totals_by_type['total_variables'] += row['total']
                    by_period[period_key]['total_variables'] += row['total']
                
                # Agrupar por campo base
                base_field = row.get('base_field')
                if base_field:
                    if base_field not in by_base_field:
                        by_base_field[base_field] = {'total': 0.0, 'line_ids': []}
                    by_base_field[base_field]['total'] += row['total']
                    by_base_field[base_field]['line_ids'].append(row['line_id'])
        
        # Agregar IDs de ausencias del período al resultado (consolidado por período)
        # Solo para consultas de nómina (source_type='payslip')
        leave_ids_by_period = {}
        leave_line_ids_by_period = {}
        
        if source_type == 'payslip':
            for row in rows:
                period_key = row['period_key']
                
                # Agregar leave_ids
                if 'leave_ids' in row and row['leave_ids']:
                    if period_key not in leave_ids_by_period:
                        leave_ids_by_period[period_key] = set()
                    # row['leave_ids'] puede ser un array de PostgreSQL
                    if isinstance(row['leave_ids'], list):
                        leave_ids_by_period[period_key].update(row['leave_ids'])
                    elif row['leave_ids']:
                        leave_ids_by_period[period_key].add(row['leave_ids'])
                
                # Agregar leave_line_ids
                if 'leave_line_ids' in row and row['leave_line_ids']:
                    if period_key not in leave_line_ids_by_period:
                        leave_line_ids_by_period[period_key] = set()
                    # row['leave_line_ids'] puede ser un array de PostgreSQL
                    if isinstance(row['leave_line_ids'], list):
                        leave_line_ids_by_period[period_key].update(row['leave_line_ids'])
                    elif row['leave_line_ids']:
                        leave_line_ids_by_period[period_key].add(row['leave_line_ids'])
            
            # Convertir sets a listas
            leave_ids_by_period = {k: list(v) for k, v in leave_ids_by_period.items()}
            leave_line_ids_by_period = {k: list(v) for k, v in leave_line_ids_by_period.items()}
        
        # Construir resultado
        result = {
            'total': total,
            'totals_by_type': totals_by_type,
            'list': list_detail,
            'by_period': by_period,
        }
        
        # Agregar IDs de ausencias al resultado (solo para nómina)
        if source_type == 'payslip':
            if leave_ids_by_period:
                result['leave_ids_by_period'] = leave_ids_by_period
            if leave_line_ids_by_period:
                result['leave_line_ids_by_period'] = leave_line_ids_by_period
        
        if calculation_type == 'retenciones':
            result['by_category'] = by_category
        elif calculation_type == 'prestaciones':
            result['by_base_field'] = by_base_field
        
        return result

    def get_devengos_tope_auxilio(
        self,
        contract_id,
        date_from,
        date_to,
        exclude_payslip_id=None,
        states=('done', 'paid'),
        solo_marcadas=False,
    ):
        """
        Obtiene los devengos que hacen base para el tope de auxilio de transporte.

        Logica de inclusion:
        1. DEV_SALARIAL: Se incluye por DEFECTO (categoria padre o directa)
        2. base_auxtransporte_tope=True: Para OTRAS reglas que quieran agregarse
        3. excluir_auxtransporte_tope=True: EXCLUYE (tiene PRIORIDAD sobre todo)
        4. Excluye BASIC (ya se cuenta en salario contrato)

        Args:
            contract_id: ID del contrato
            date_from: Fecha inicio del periodo
            date_to: Fecha fin del periodo
            exclude_payslip_id: ID de nomina a excluir
            states: Estados de nomina a incluir

        Returns:
            dict: {
                'total': float,
                'list': [...],
                'by_period': {...}
            }
        """
        if states is None:
            states_list = ['done', 'paid']
        elif isinstance(states, tuple):
            states_list = list(states)
        elif isinstance(states, list):
            states_list = states
        else:
            states_list = [states]

        params = {
            'contract_id': contract_id,
            'date_from': date_from,
            'date_to': date_to,
            'exclude_payslip_id': exclude_payslip_id or 0,
            'states': tuple(states_list) if states_list else ('done', 'paid'),
        }

        include_clause = (
            "hsr.base_auxtransporte_tope = TRUE"
            if solo_marcadas
            else """(
              -- DEV_SALARIAL por defecto (categoria directa o padre)
              hsrc.code = 'DEV_SALARIAL'
              OR hsrc_parent.code = 'DEV_SALARIAL'
              -- O tiene base_auxtransporte_tope=True
              OR hsr.base_auxtransporte_tope = TRUE
          )"""
        )

        query = f"""
        WITH payslips_by_period AS (
            SELECT
                hp.id AS payslip_id,
                hp.number AS payslip_number,
                hp.date_from,
                hp.date_to,
                TO_CHAR(hp.date_from, 'YYYY-MM') AS period_key
            FROM hr_payslip hp
            WHERE hp.contract_id = %(contract_id)s
              AND hp.state IN %(states)s
              AND hp.date_from >= %(date_from)s
              AND hp.date_to <= %(date_to)s
              AND (hp.id != %(exclude_payslip_id)s OR %(exclude_payslip_id)s = 0)
        )
        SELECT
            hpl.id AS line_id,
            hpl.slip_id AS payslip_id,
            pbp.payslip_number,
            hpl.date_from,
            hpl.date_to,
            hsr.code AS rule_code,
            COALESCE(hsr.name->>'es_CO', hsr.name->>'en_US', hsr.code) AS rule_name,
            hsrc.code AS category_code,
            hpl.total,
            pbp.period_key
        FROM hr_payslip_line hpl
        INNER JOIN payslips_by_period pbp ON pbp.payslip_id = hpl.slip_id
        INNER JOIN hr_salary_rule hsr ON hsr.id = hpl.salary_rule_id
        -- Odoo 19: hr.payslip.line.category_id es related (no columna fisica). Usar hsr.category_id.
        INNER JOIN hr_salary_rule_category hsrc ON hsrc.id = hsr.category_id
        LEFT JOIN hr_salary_rule_category hsrc_parent ON hsrc.parent_id = hsrc_parent.id
        WHERE hpl.total > 0
          AND hsr.code != 'BASIC'
          AND (hsr.excluir_auxtransporte_tope = FALSE OR hsr.excluir_auxtransporte_tope IS NULL)
          AND {include_clause}
        ORDER BY pbp.period_key, hpl.date_from, hsr.code
        """

        self._cr.execute(query, params)
        rows = self._cr.dictfetchall()

        # Procesar resultados
        total = 0.0
        list_detail = []
        by_period = {}

        for row in rows:
            total += row['total']
            list_detail.append({
                'line_id': row['line_id'],
                'payslip_id': row['payslip_id'],
                'payslip_number': row['payslip_number'],
                'date_from': row['date_from'],
                'date_to': row['date_to'],
                'rule_code': row['rule_code'],
                'rule_name': row['rule_name'],
                'category_code': row['category_code'],
                'total': row['total'],
                'period_key': row['period_key'],
            })

            period_key = row['period_key']
            if period_key not in by_period:
                by_period[period_key] = {'total': 0.0, 'line_ids': []}
            by_period[period_key]['total'] += row['total']
            by_period[period_key]['line_ids'].append(row['line_id'])

        return {
            'total': total,
            'list': list_detail,
            'by_period': by_period,
        }

    def get_auxilio_transporte_pagado(
        self,
        contract_id,
        date_from,
        date_to,
        exclude_payslip_id=None,
        states=('done', 'paid'),
    ):
        """
        Obtiene los valores de auxilio de transporte pagados en el periodo.

        Usa la categoria AUX y el campo es_auxilio_transporte=True para identificar reglas de auxilio.
        Tambien considera la categoria BASIC como sueldo fijo para referencia.

        Args:
            contract_id: ID del contrato
            date_from: Fecha inicio del periodo de acumulacion
            date_to: Fecha fin del periodo de acumulacion
            exclude_payslip_id: ID de nomina a excluir
            states: Estados de nomina a incluir

        Returns:
            dict: {
                'total_auxilio': float - Total de auxilio pagado,
                'total_basic': float - Total de BASIC (sueldo),
                'total_dias_auxilio': float - Total de dias de auxilio pagados,
                'count_periods': int - Numero de periodos con auxilio,
                'promedio_auxilio': float - Promedio de auxilio por periodo,
                'promedio_dias_auxilio': float - Promedio de dias de auxilio por periodo,
                'list': [...] - Detalle de lineas,
                'by_period': {...} - Agrupado por periodo (incluye dias_auxilio)
            }
        """
        if states is None:
            states_list = ['done', 'paid']
        elif isinstance(states, tuple):
            states_list = list(states)
        elif isinstance(states, list):
            states_list = states
        else:
            states_list = [states]

        params = {
            'contract_id': contract_id,
            'date_from': date_from,
            'date_to': date_to,
            'exclude_payslip_id': exclude_payslip_id or 0,
            'states': tuple(states_list) if states_list else ('done', 'paid'),
        }

        query = """
        WITH payslips_by_period AS (
            SELECT
                hp.id AS payslip_id,
                hp.number AS payslip_number,
                hp.date_from,
                hp.date_to,
                TO_CHAR(hp.date_from, 'YYYY-MM') AS period_key,
                CASE WHEN EXTRACT(DAY FROM hp.date_to) <= 15 THEN 1 ELSE 2 END AS quincena
            FROM hr_payslip hp
            WHERE hp.contract_id = %(contract_id)s
              AND hp.state IN %(states)s
              AND hp.date_from >= %(date_from)s
              AND hp.date_to <= %(date_to)s
              AND (hp.id != %(exclude_payslip_id)s OR %(exclude_payslip_id)s = 0)
        )
        SELECT
            hpl.id AS line_id,
            hpl.slip_id AS payslip_id,
            pbp.payslip_number,
            hpl.date_from,
            hpl.date_to,
            hsr.code AS rule_code,
            COALESCE(hsr.name->>'es_CO', hsr.name->>'en_US', hsr.code) AS rule_name,
            hsrc.code AS category_code,
            hsrc_parent.code AS parent_category_code,
            hpl.total,
            hpl.quantity,
            pbp.period_key,
            pbp.quincena,
            CASE
                -- Categoria AUX o subcategoria de AUX = auxilio de transporte
                WHEN hsrc.code = 'AUX' OR hsrc_parent.code = 'AUX' THEN 'auxilio'
                -- Campo es_auxilio_transporte marcado = auxilio de transporte
                WHEN hsr.es_auxilio_transporte = TRUE THEN 'auxilio'
                -- Categoria BASIC = sueldo
                WHEN hsrc.code = 'BASIC' THEN 'basic'
                ELSE 'other'
            END AS tipo_concepto
        FROM hr_payslip_line hpl
        INNER JOIN payslips_by_period pbp ON pbp.payslip_id = hpl.slip_id
        INNER JOIN hr_salary_rule hsr ON hsr.id = hpl.salary_rule_id
        -- Odoo 19: hr.payslip.line.category_id es related (no columna fisica). Usar hsr.category_id.
        INNER JOIN hr_salary_rule_category hsrc ON hsrc.id = hsr.category_id
        LEFT JOIN hr_salary_rule_category hsrc_parent ON hsrc.parent_id = hsrc_parent.id
        WHERE hpl.total > 0
          AND (
              -- Categoria AUX o subcategoria de AUX (auxilio de transporte)
              hsrc.code = 'AUX' OR hsrc_parent.code = 'AUX'
              -- O reglas marcadas explicitamente como auxilio de transporte
              OR hsr.es_auxilio_transporte = TRUE
              -- O categoria BASIC (sueldo)
              OR hsrc.code = 'BASIC'
          )
        ORDER BY pbp.period_key, pbp.quincena, hsr.code
        """

        self._cr.execute(query, params)
        rows = self._cr.dictfetchall()

        # Procesar resultados
        total_auxilio = 0.0
        total_basic = 0.0
        total_dias_auxilio = 0.0
        list_detail = []
        by_period = {}
        periodos_con_auxilio = set()

        for row in rows:
            tipo = row.get('tipo_concepto', 'other')
            period_key = row['period_key']
            quincena = row.get('quincena', 1)
            period_quincena_key = f"{period_key}-Q{quincena}"
            quantity = row.get('quantity', 0) or 0

            line_detail = {
                'line_id': row['line_id'],
                'payslip_id': row['payslip_id'],
                'payslip_number': row['payslip_number'],
                'date_from': row['date_from'],
                'date_to': row['date_to'],
                'rule_code': row['rule_code'],
                'rule_name': row['rule_name'],
                'category_code': row['category_code'],
                'total': row['total'],
                'quantity': quantity,
                'period_key': period_key,
                'quincena': quincena,
                'tipo_concepto': tipo,
            }
            list_detail.append(line_detail)

            # Agrupar por periodo-quincena
            if period_quincena_key not in by_period:
                by_period[period_quincena_key] = {
                    'total_auxilio': 0.0,
                    'total_basic': 0.0,
                    'dias_auxilio': 0.0,
                    'line_ids': [],
                    'period_key': period_key,
                    'quincena': quincena,
                }

            by_period[period_quincena_key]['line_ids'].append(row['line_id'])

            if tipo == 'auxilio':
                total_auxilio += row['total']
                total_dias_auxilio += quantity
                by_period[period_quincena_key]['total_auxilio'] += row['total']
                by_period[period_quincena_key]['dias_auxilio'] += quantity
                periodos_con_auxilio.add(period_quincena_key)
            elif tipo == 'basic':
                total_basic += row['total']
                by_period[period_quincena_key]['total_basic'] += row['total']

        count_periods = len(periodos_con_auxilio)
        promedio_auxilio = total_auxilio / count_periods if count_periods > 0 else 0.0
        promedio_dias_auxilio = total_dias_auxilio / count_periods if count_periods > 0 else 0.0

        return {
            'total_auxilio': total_auxilio,
            'total_basic': total_basic,
            'total_dias_auxilio': total_dias_auxilio,
            'count_periods': count_periods,
            'promedio_auxilio': promedio_auxilio,
            'promedio_dias_auxilio': promedio_dias_auxilio,
            'list': list_detail,
            'by_period': by_period,
        }

    def _combine_results(self, payslip_data, leave_data, calculation_type):
        """
        Combina resultados de nómina y ausencias.
        """
        # Combinar totales
        combined_total = payslip_data['total'] + leave_data['total']
        
        # Combinar totals_by_type
        combined_totals = {}
        for key in payslip_data['totals_by_type'].keys():
            combined_totals[key] = (
                payslip_data['totals_by_type'].get(key, 0.0) +
                leave_data['totals_by_type'].get(key, 0.0)
            )
        
        # Combinar listas
        combined_list = payslip_data['list'] + leave_data['list']
        
        # Combinar by_period
        combined_by_period = {}
        all_periods = set(payslip_data['by_period'].keys()) | set(leave_data['by_period'].keys())
        for period_key in all_periods:
            payslip_period = payslip_data['by_period'].get(period_key, {'total': 0.0, 'line_ids': []})
            leave_period = leave_data['by_period'].get(period_key, {'total': 0.0, 'line_ids': []})
            
            combined_by_period[period_key] = {
                'total': payslip_period['total'] + leave_period['total'],
                'line_ids': payslip_period['line_ids'] + leave_period['line_ids'],
            }
            
            # Combinar totales por tipo
            for key in combined_totals.keys():
                combined_by_period[period_key][key] = (
                    payslip_period.get(key, 0.0) + leave_period.get(key, 0.0)
                )
        
        # Combinar by_category o by_base_field
        result = {
            'total': combined_total,
            'totals_by_type': combined_totals,
            'list': combined_list,
            'by_period': combined_by_period,
        }
        
        if calculation_type == 'retenciones':
            # Combinar by_category
            combined_by_category = {}
            all_categories = set(payslip_data.get('by_category', {}).keys()) | set(leave_data.get('by_category', {}).keys())
            for cat_code in all_categories:
                payslip_cat = payslip_data.get('by_category', {}).get(cat_code, {'total': 0.0, 'line_ids': []})
                leave_cat = leave_data.get('by_category', {}).get(cat_code, {'total': 0.0, 'line_ids': []})
                combined_by_category[cat_code] = {
                    'total': payslip_cat['total'] + leave_cat['total'],
                    'line_ids': payslip_cat['line_ids'] + leave_cat['line_ids'],
                }
            result['by_category'] = combined_by_category
            
        elif calculation_type == 'prestaciones':
            # Combinar by_base_field
            combined_by_base_field = {}
            all_base_fields = set(payslip_data.get('by_base_field', {}).keys()) | set(leave_data.get('by_base_field', {}).keys())
            for base_field in all_base_fields:
                payslip_base = payslip_data.get('by_base_field', {}).get(base_field, {'total': 0.0, 'line_ids': []})
                leave_base = leave_data.get('by_base_field', {}).get(base_field, {'total': 0.0, 'line_ids': []})
                combined_by_base_field[base_field] = {
                    'total': payslip_base['total'] + leave_base['total'],
                    'line_ids': payslip_base['line_ids'] + leave_base['line_ids'],
                }
            result['by_base_field'] = combined_by_base_field
        
        return result
