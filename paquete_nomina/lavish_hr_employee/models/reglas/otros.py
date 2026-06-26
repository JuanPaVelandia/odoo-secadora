# -*- coding: utf-8 -*-

"""
REGLAS SALARIALES - MÉTODOS AUXILIARES Y TOTALES
=================================================

Métodos genéricos y de utilidad reutilizables
"""

from odoo import models, api
from odoo.addons.lavish_hr_employee.models.hr_slip_data_structures import CategoryCollection
from .config_reglas import crear_log_data, crear_resultado_regla, crear_resultado_vacio, crear_data_kpi

class HrSalaryRuleOtros(models.AbstractModel):
    """Mixin para métodos de utilidad, totales y filtros genéricos"""

    _name = 'hr.salary.rule.otros'
    _description = 'Métodos Auxiliares y Totales'

    def _get_base_dias_empleado(self, employee, default=360):
        """
        Obtiene base de días (360/365) desde el empleado.
        """
        from .config_reglas import normalizar_base_dias, DAYS_YEAR

        if employee:
            try:
                base_dias = employee.base_dias_prestaciones
            except (AttributeError, KeyError):
                base_dias = None
        else:
            base_dias = None
        return normalizar_base_dias(base_dias, default=DAYS_YEAR if default is None else default)


    # ══════════════════════════════════════════════════════════════════════════
    # MÉTODOS DE DATOS DEL PERÍODO ACTUAL
    # ══════════════════════════════════════════════════════════════════════════

    def _get_current_period_data(self, localdict, filters=None):
        """
        Obtiene datos del período ACTUAL (mes en proceso) desde localdict['rules'].
        Compatible con Odoo 19 - usa estructura nativa.

        Args:
            localdict: Diccionario de contexto de nómina
            filters: Dict con filtros a aplicar
                {
                    'rules': ['BASIC', 'HE001'],           # Códigos de reglas específicas
                    'categories': ['BASIC', 'DEV_SALARIAL'],  # Códigos de categorías
                    'exclude_rules': ['BASIC'],            # Excluir reglas
                    'exclude_categories': ['DED'],         # Excluir categorías
                    'base_prima': True,                    # Solo reglas con base_prima=True
                    'base_cesantias': True,                # Solo reglas con base_cesantias=True
                    'base_ss': True,                       # Solo reglas con base_seguridad_social=True
                    'base_vacaciones': True,               # Solo reglas con base_vacaciones=True
                    'min_amount': 1000,                    # Monto mínimo
                    'conditions': lambda rule: rule.code.startswith('HE')  # Condición custom
                }

        Returns:
            dict: {
                'total': float,
                'quantity': float,
                'by_rule': {code: {'total': X, 'quantity': Y, 'rule': obj}},
                'by_category': {code: {'total': X, 'quantity': Y}}
            }
        """
        filters = filters or {}

        # Inicializar resultado
        result = {
            'total': 0.0,
            'quantity': 0.0,
            'by_rule': {},
            'by_category': {}
        }

        # Obtener rules desde localdict (Odoo 19 nativo)
        rules = localdict.get('rules', {})

        if not rules:
            return result

        # Procesar cada regla
        for code, rule_data in rules.items():
            rule_obj = rule_data.rule
            total = rule_data.total
            quantity = rule_data.quantity

            if not rule_obj:
                continue

            # Aplicar filtros
            if not self._passes_current_period_filters(rule_obj, filters):
                continue

            # Agregar a totales
            result['total'] += total
            result['quantity'] += quantity

            # Agregar por regla
            result['by_rule'][code] = {
                'total': total,
                'quantity': quantity,
                'rule': rule_obj
            }

            # Agregar por categoría
            if rule_obj.category_id:
                cat_code = rule_obj.category_id.code
                if cat_code not in result['by_category']:
                    result['by_category'][cat_code] = {'total': 0.0, 'quantity': 0.0}

                result['by_category'][cat_code]['total'] += total
                result['by_category'][cat_code]['quantity'] += quantity

        return result


    def _passes_current_period_filters(self, rule_obj, filters):
        """
        Verifica si una regla pasa todos los filtros especificados.

        Args:
            rule_obj: Objeto hr.salary.rule
            filters: Dict con filtros

        Returns:
            bool: True si pasa todos los filtros
        """
        if not filters:
            return True

        # Filtro de reglas específicas
        if 'rules' in filters:
            rules_filter = filters['rules'] if isinstance(filters['rules'], list) else [filters['rules']]
            if rule_obj.code not in rules_filter:
                return False

        # Filtro de reglas excluidas
        if 'exclude_rules' in filters:
            excluded = filters['exclude_rules'] if isinstance(filters['exclude_rules'], list) else [filters['exclude_rules']]
            if rule_obj.code in excluded:
                return False

        # Filtro de categorías
        if 'categories' in filters and rule_obj.category_id:
            categories = filters['categories'] if isinstance(filters['categories'], list) else [filters['categories']]
            cat_code = rule_obj.category_id.code
            parent_code = rule_obj.category_id.parent_id.code if rule_obj.category_id.parent_id else None

            if not (cat_code in categories or parent_code in categories):
                return False

        # Filtro de categorías excluidas
        if 'exclude_categories' in filters and rule_obj.category_id:
            excluded = filters['exclude_categories'] if isinstance(filters['exclude_categories'], list) else [filters['exclude_categories']]
            cat_code = rule_obj.category_id.code
            parent_code = rule_obj.category_id.parent_id.code if rule_obj.category_id.parent_id else None

            if cat_code in excluded or parent_code in excluded:
                return False

        # Filtros de base
        if 'base_prima' in filters and filters['base_prima']:
            if not rule_obj.base_prima:
                return False

        if 'base_cesantias' in filters and filters['base_cesantias']:
            if not rule_obj.base_cesantias:
                return False

        if 'base_ss' in filters and filters['base_ss']:
            if not rule_obj.base_seguridad_social:
                return False

        if 'base_vacaciones' in filters and filters['base_vacaciones']:
            if not rule_obj.base_vacaciones:
                return False

        # Filtro de condiciones custom
        if 'conditions' in filters and callable(filters['conditions']):
            if not filters['conditions'](rule_obj):
                return False

        return True


    # ══════════════════════════════════════════════════════════════════════════
    # MÉTODOS DE LÍNEAS DE NÓMINA (TRAZABILIDAD)
    # ══════════════════════════════════════════════════════════════════════════

    def _build_payslip_line_info(
        self,
        line,
        include_total=True,
        include_amount=True,
        include_quantity=True,
        date_format=None,
        fallback_payslip_number='Borrador',
    ):
        """
        Construye un dict estandar para trazabilidad de hr.payslip.line.

        Args:
            line: hr.payslip.line (recordset de 1) o vacío
            include_total: Incluir total en el dict
            include_amount: Incluir amount en el dict
            include_quantity: Incluir quantity en el dict
            date_format: strftime opcional para date_from/date_to

        Returns:
            dict: Datos de la línea con claves homogéneas
        """
        if not line:
            info = {
                'id': None,
                'payslip_id': None,
                'payslip_number': None,
                'date_from': None,
                'date_to': None,
            }
            if include_total:
                info['total'] = 0
            if include_quantity:
                info['quantity'] = 0
            if include_amount:
                info['amount'] = 0
            return info

        line = line[:1]
        if not line:
            return {
                'id': None,
                'payslip_id': None,
                'payslip_number': None,
                'date_from': None,
                'date_to': None,
                'total': 0 if include_total else None,
                'quantity': 0 if include_quantity else None,
                'amount': 0 if include_amount else None,
            }

        line = line[0]
        slip = line.slip_id
        date_from = line.date_from
        date_to = line.date_to

        if date_format:
            date_from = date_from.strftime(date_format) if date_from else None
            date_to = date_to.strftime(date_format) if date_to else None

        payslip_number = slip.number if slip else None
        if slip and not payslip_number and fallback_payslip_number is not None:
            payslip_number = fallback_payslip_number

        info = {
            'id': line.id,
            'payslip_id': slip.id if slip else None,
            'payslip_number': payslip_number,
            'date_from': date_from,
            'date_to': date_to,
        }
        if include_total:
            info['total'] = line.total
        if include_quantity:
            info['quantity'] = line.quantity
        if include_amount:
            info['amount'] = line.amount
        return info

    def _build_payslip_lines_summary(
        self,
        lines,
        include_total=True,
        include_amount=True,
        include_quantity=True,
        date_format=None,
        fallback_payslip_number='Borrador',
    ):
        """
        Resume líneas de nómina con total, promedio y trazabilidad.

        Args:
            lines: recordset de hr.payslip.line
            include_total: Incluir total en cada línea
            include_amount: Incluir amount en cada línea
            include_quantity: Incluir quantity en cada línea
            date_format: strftime opcional para date_from/date_to

        Returns:
            dict: {
                'total': float,
                'promedio': float,
                'count': int,
                'fecha_ultimo_calculo': date or str,
                'payslip_id_anterior': int or None,
                'payslip_lines': list
            }
        """
        if not lines:
            return {
                'total': 0,
                'promedio': 0,
                'count': 0,
                'fecha_ultimo_calculo': None,
                'payslip_id_anterior': None,
                'payslip_lines': [],
            }

        total = 0
        payslip_lines = []
        fecha_ultimo = None
        payslip_id_anterior = None

        for line in lines:
            if fecha_ultimo is None:
                fecha_ultimo = line.date_to
                payslip_id_anterior = line.slip_id.id if line.slip_id else None

            total += line.total
            payslip_lines.append(
                self._build_payslip_line_info(
                    line,
                    include_total=include_total,
                    include_amount=include_amount,
                    include_quantity=include_quantity,
                    date_format=date_format,
                    fallback_payslip_number=fallback_payslip_number,
                )
            )

        count = len(lines)
        promedio = total / count if count else 0
        if date_format and fecha_ultimo:
            fecha_ultimo = fecha_ultimo.strftime(date_format)

        return {
            'total': total,
            'promedio': promedio,
            'count': count,
            'fecha_ultimo_calculo': fecha_ultimo,
            'payslip_id_anterior': payslip_id_anterior,
            'payslip_lines': payslip_lines,
        }

    def _build_payslip_line_info_from_row(
        self,
        row,
        include_total=True,
        include_amount=True,
        include_quantity=True,
        date_format=None,
        fallback_payslip_number='Borrador',
    ):
        """
        Construye dict de trazabilidad desde una fila SQL de hr.payslip.line.

        Args:
            row: Dict con datos de hr.payslip.line + payslip_number
            include_total: Incluir total en el dict
            include_amount: Incluir amount en el dict
            include_quantity: Incluir quantity en el dict
            date_format: strftime opcional para date_from/date_to

        Returns:
            dict: Datos de la línea con claves homogéneas
        """
        if not row:
            info = {
                'id': None,
                'payslip_id': None,
                'payslip_number': None,
                'date_from': None,
                'date_to': None,
            }
            if include_total:
                info['total'] = 0
            if include_quantity:
                info['quantity'] = 0
            if include_amount:
                info['amount'] = 0
            return info

        date_from = row.get('date_from')
        date_to = row.get('date_to')
        if date_format:
            date_from = date_from.strftime(date_format) if date_from else None
            date_to = date_to.strftime(date_format) if date_to else None

        payslip_number = row.get('payslip_number')
        if not payslip_number and fallback_payslip_number is not None:
            payslip_number = fallback_payslip_number

        info = {
            'id': row.get('id'),
            'payslip_id': row.get('payslip_id'),
            'payslip_number': payslip_number,
            'date_from': date_from,
            'date_to': date_to,
        }
        if include_total:
            info['total'] = row.get('total') or 0
        if include_quantity:
            info['quantity'] = row.get('quantity') or 0
        if include_amount:
            info['amount'] = row.get('amount') or 0
        return info

    def _get_payslip_lines_summary_sql(
        self,
        contract_id,
        code,
        date_from,
        date_to,
        states=('done', 'paid'),
        limit=None,
        include_total=True,
        include_amount=True,
        include_quantity=True,
        date_format=None,
        fallback_payslip_number='Borrador',
    ):
        """
        Obtiene resumen de líneas de nómina por SQL (mes completo por rango).

        Args:
            contract_id: ID de hr.contract
            code: Código de la regla salarial (ej: 'IBD')
            date_from: Fecha inicio (inclusive)
            date_to: Fecha fin (inclusive)
            states: Estados válidos de la nómina
            limit: Limitar cantidad de líneas

        Returns:
            dict con total, promedio, count, fecha_ultimo_calculo y payslip_lines
        """
        if not contract_id or not code or not date_from or not date_to:
            return {
                'total': 0,
                'promedio': 0,
                'count': 0,
                'fecha_ultimo_calculo': None,
                'payslip_id_anterior': None,
                'payslip_lines': [],
            }

        if isinstance(states, str):
            states = (states,)
        else:
            states = tuple(states) if states else ('done', 'paid')
        limit_clause = ''
        params = [contract_id, code, states, date_from, date_to]
        if limit:
            limit_clause = 'LIMIT %s'
            params.append(limit)

        query = f"""
            SELECT
                l.id,
                l.slip_id AS payslip_id,
                l.date_from,
                l.date_to,
                l.total,
                l.amount,
                l.quantity,
                p.number AS payslip_number
            FROM hr_payslip_line AS l
            LEFT JOIN hr_payslip AS p
                ON p.id = l.slip_id
            WHERE
                l.contract_id = %s
                AND l.code = %s
                AND l.state_slip IN %s
                AND l.date_from >= %s
                AND l.date_to <= %s
            ORDER BY l.date_to DESC, l.id DESC
            {limit_clause}
        """

        self._cr.execute(query, params)
        rows = self._cr.dictfetchall()

        if not rows:
            return {
                'total': 0,
                'promedio': 0,
                'count': 0,
                'fecha_ultimo_calculo': None,
                'payslip_id_anterior': None,
                'payslip_lines': [],
            }

        total = sum(row.get('total') or 0 for row in rows)
        count = len(rows)
        promedio = total / count if count else 0
        fecha_ultimo = rows[0].get('date_to')
        payslip_id_anterior = rows[0].get('payslip_id')

        payslip_lines = [
            self._build_payslip_line_info_from_row(
                row,
                include_total=include_total,
                include_amount=include_amount,
                include_quantity=include_quantity,
                date_format=date_format,
                fallback_payslip_number=fallback_payslip_number,
            )
            for row in rows
        ]

        if date_format and fecha_ultimo:
            fecha_ultimo = fecha_ultimo.strftime(date_format)

        return {
            'total': total,
            'promedio': promedio,
            'count': count,
            'fecha_ultimo_calculo': fecha_ultimo,
            'payslip_id_anterior': payslip_id_anterior,
            'payslip_lines': payslip_lines,
        }

    def _get_previous_payslip_line(self, contract, code, date_from, states=('done', 'paid'), order='date_to desc'):
        """
        Obtiene la última línea de nómina anterior a una fecha.

        Args:
            contract: hr.contract o ID
            code: Código de regla salarial
            date_from: Fecha desde (excluyente)
            states: Estados de nómina válidos
            order: Orden de búsqueda

        Returns:
            recordset: hr.payslip.line (0 o 1)
        """
        if not contract or not code or not date_from:
            return self.env['hr.payslip.line'].browse()

        try:
            contract_id = contract.id
        except (AttributeError, KeyError):
            contract_id = contract
        domain = [
            ('slip_id.contract_id', '=', contract_id),
            ('code', '=', code),
            ('state_slip', 'in', list(states)),
            ('date_from', '<', date_from),
        ]
        return self.env['hr.payslip.line'].search(domain, order=order, limit=1)


    # ══════════════════════════════════════════════════════════════════════════
    # MÉTODOS DE TOTALIZACIÓN
    # ══════════════════════════════════════════════════════════════════════════

    def _total_by_afecta_totales(self, localdict, target):
        """
        Suma reglas por clasificación efectiva de afecta_totales.
        target: 'devengo' | 'deduccion'
        """
        rules = localdict.get('rules', {})
        total = 0.0
        details = {}
        for code, rule_data in rules.items():
            if not rule_data:
                continue
            if code in ('TOTALDEV', 'TOTALDED', 'NET'):
                continue
            rule_obj = rule_data.rule
            if not rule_obj:
                continue
            afecta = rule_obj._get_afecta_totales_effective()
            if afecta != target:
                continue
            total += rule_data.total
            details[code] = rule_data.total
        return total, details

    def _calculate_total_from_categories(self, localdict, category_codes):
        """
        Calcula totales desde localdict['categories'] directamente.
        Más eficiente - usa totales ya acumulados en vez de iterar reglas.
        Soporta tanto dict como CategoryCollection.

        Args:
            localdict: Diccionario de contexto
            category_codes: Lista de códigos de categorías a sumar

        Returns:
            tuple: (total, 1, 100, False, category_totals, details)
        """
        categories = localdict.get('categories', CategoryCollection())
        rules = localdict.get('rules', {})

        total = 0
        category_totals = {}
        details = {}

        # Iterar por los códigos de categoría solicitados
        for cat_code in category_codes:
            try:
                cat_data = categories.get(cat_code)
            except (AttributeError, TypeError):
                cat_data = categories.get(cat_code, {}) if isinstance(categories, dict) else {}

            # Verificar si la categoría existe y tiene datos
            if cat_data:
                # Soportar tanto dict como CategoryCollection
                try:
                    cat_total = cat_data.total
                    # CategoryCollection: obtener reglas desde cat_data.rules
                    try:
                        for rule in cat_data.rules:
                            details[rule.code] = rule.total
                    except (AttributeError, KeyError):
                        pass
                except (AttributeError, KeyError):
                    cat_total = cat_data.get('total', 0) if isinstance(cat_data, dict) else 0
                    # Dict: obtener reglas desde rule_codes si existe
                    if isinstance(cat_data, dict) and 'rule_codes' in cat_data:
                        for rule_code in cat_data['rule_codes']:
                            if rules and rule_code in rules:
                                rule_data = rules.get(rule_code)
                                details[rule_code] = rule_data.total if rule_data else 0

                total += cat_total
                category_totals[cat_code] = cat_total

        return total, 1, 100, False, category_totals, details


    def _calculate_total_from_rules(self, localdict, categories, exclude_not_in_net=True):
        """
        Calcula totales desde localdict['rules'] por categorías.

        NOTA: Este método es un wrapper de compatibilidad.
        Internamente usa _calculate_total_from_categories() que es más eficiente.

        Args:
            localdict: Diccionario de contexto
            categories: Lista de códigos de categorías a sumar
            exclude_not_in_net: Si True, excluye reglas con not_computed_in_net=True (no usado actualmente)

        Returns:
            tuple: (total, 1, 100, False, category_totals, details)
        """
        # Usar el método más eficiente que lee directamente de categories
        return self._calculate_total_from_categories(localdict, categories)


    # ══════════════════════════════════════════════════════════════════════════
    # MÉTODOS DE EMPLEADO Y PARTNER
    # ══════════════════════════════════════════════════════════════════════════

    def _get_employee_partner_id(self, employee):
        """
        Obtiene el partner_id del empleado para transacciones contables.

        Args:
            employee: Objeto hr.employee

        Returns:
            int: ID del partner asociado al empleado
        """
        # Prioridad 1 (Odoo 19): work_contact_id
        if employee.work_contact_id:
            return employee.work_contact_id.id

        # Prioridad 2 (Odoo 19): partner del usuario
        if employee.user_id and employee.user_id.partner_id:
            return employee.user_id.partner_id.id

        # Prioridad 3: Buscar partner con mismo nombre
        partner = self.env['res.partner'].search([
            ('name', '=', employee.name)
        ], limit=1)

        if partner:
            return partner.id

        return False


    def _calculate_total_from_categories_adapted(self, localdict, category_codes):
        """
        Calcula totales desde CategoryCollection.
        DEPRECATED: Usar _calculate_total_from_categories() que ahora soporta ambos formatos.
        Mantenido por compatibilidad hacia atrás.
        """
        return self._calculate_total_from_categories(localdict, category_codes)

    def _totaldev(self, localdict):
        """Calcula el total de devengos desde CategoryCollection.

        Categorias incluidas:
        - DEV_SALARIAL: Basico, horas extras, comisiones, etc.
        - DEV_NO_SALARIAL: Auxilios varios (alimentacion, movilidad, etc.)
        - AUX: Auxilio de transporte y conectividad (sin parent, evita doble conteo)
        - PRESTACIONES_SOCIALES, PRIMA, IND: Otras prestaciones

        Categorias excluidas de TOTALDEV:
        - AUSENCIA_NO_PAGO: Licencias no remuneradas, suspensiones (sin parent)
        """
        total, details = self._total_by_afecta_totales(localdict, 'devengo')
        return total, 1, 100, False, {'DEVENGOS': total}, details

    # =========================================================================
    # LIMITE DE DEDUCCIONES AL 50% DE DEVENGOS (Art. 149 CST)
    # =========================================================================

    # Categorias obligatorias por defecto (si no hay configuracion en hr.deduction.priority)
    CATEGORIAS_OBLIGATORIAS_DEFAULT = ['BASE_SEC', 'SSOCIAL', 'RETENCION', 'SSOCIAL001', 'SSOCIAL002', 'SSOCIAL003', 'SSOCIAL004']

    def _get_categorias_obligatorias(self, company_id=None):
        """
        Obtiene las categorías/códigos obligatorios desde hr.deduction.priority.
        Si no hay configuración, usa los valores por defecto.
        """
        DeductionPriority = self.env.get('hr.deduction.priority')
        
        if DeductionPriority:
            mandatory_codes = DeductionPriority.get_mandatory_categories(company_id)
            if mandatory_codes:
                return mandatory_codes
        
        return set(self.CATEGORIAS_OBLIGATORIAS_DEFAULT)

    def _get_priority_for_deduction(self, rule_code, category_code, company_id=None):
        """
        Obtiene la prioridad configurada para una deducción.
        
        Returns:
            dict: {'sequence': int, 'is_mandatory': bool}
        """
        DeductionPriority = self.env.get('hr.deduction.priority')
        
        if DeductionPriority:
            priority_info = DeductionPriority.get_priority_for_rule(rule_code, category_code, company_id)
            if priority_info.get('found'):
                return priority_info
        
        # Valor por defecto
        is_mandatory = rule_code in self.CATEGORIAS_OBLIGATORIAS_DEFAULT or \
                       category_code in self.CATEGORIAS_OBLIGATORIAS_DEFAULT
        
        return {
            'sequence': 10 if is_mandatory else 999,
            'is_mandatory': is_mandatory,
            'found': False,
        }

    def _get_deducciones_ordenadas(self, localdict):
        """
        Obtiene deducciones ordenadas por secuencia para aplicar limite.
        
        Args:
            localdict: Diccionario de contexto
            
        Returns:
            list: Lista de dicts ordenada por secuencia:
                [
                    {
                        'codigo': str,
                        'nombre': str,
                        'valor': float (positivo),
                        'secuencia': int,
                        'categoria': str,
                        'es_obligatoria': bool,
                        'rule': hr.salary.rule,
                    }
                ]
        """
        rules = localdict.get('rules', {})
        deducciones = []
        company = localdict.get('company')
        if not company and localdict.get('payslip'):
            company = localdict['payslip'].company_id
        categorias_obligatorias = self._get_categorias_obligatorias(
            company.id if company else None
        )
        
        for code, rule_data in rules.items():
            if not rule_data:
                continue
            
            # Obtener valor (las deducciones son negativas, convertir a positivo)
            valor = abs(rule_data.total) if rule_data.total else 0
            if valor == 0:
                continue
            
            # Obtener objeto regla
            rule_obj = rule_data.rule
            if not rule_obj:
                continue
            # Verificar si es deduccion por clasificación efectiva
            if rule_obj._get_afecta_totales_effective() != 'deduccion':
                continue

            categoria_code = rule_obj.category_id.code if rule_obj.category_id else ''
            
            # Verificar si es obligatoria
            es_obligatoria = code in categorias_obligatorias or \
                             categoria_code in categorias_obligatorias or \
                             categoria_code == 'SSOCIAL'
            
            deducciones.append({
                'codigo': code,
                'nombre': rule_obj.name or code,
                'valor': valor,
                'secuencia': rule_obj.sequence or 200,
                'categoria': categoria_code,
                'es_obligatoria': es_obligatoria,
                'rule': rule_obj,
            })
        
        # Ordenar: obligatorias primero, luego por secuencia
        deducciones.sort(key=lambda x: (not x['es_obligatoria'], x['secuencia']))
        
        return deducciones

    def _aplicar_limite_deducciones(self, deducciones, limite, localdict):
        """
        Aplica limite del 50% de devengos a las deducciones.
        
        Logica:
        1. Las deducciones obligatorias siempre se aplican completas
        2. Las deducciones limitables se aplican en orden de secuencia
        3. Si se excede el limite, se reduce parcialmente o se deja en cero
        
        Args:
            deducciones: Lista de deducciones ordenadas
            limite: Valor maximo de deducciones (None = sin limite)
            localdict: Diccionario de contexto
            
        Returns:
            tuple: (total_deducciones, info_limite)
        """
        # Si no hay limite, sumar todas
        if limite is None:
            total = sum(d['valor'] for d in deducciones)
            return -total, {
                'limite_aplicado': False,
                'total_deducciones': total,
            }
        
        acumulado = 0.0
        deducciones_aplicadas = []
        deducciones_parciales = []
        deducciones_cero = []
        total_obligatorias = 0.0
        
        for ded in deducciones:
            if ded['es_obligatoria']:
                # Obligatorias siempre se aplican completas
                acumulado += ded['valor']
                total_obligatorias += ded['valor']
                deducciones_aplicadas.append({
                    'codigo': ded['codigo'],
                    'nombre': ded['nombre'],
                    'valor_original': ded['valor'],
                    'valor_aplicado': ded['valor'],
                    'tipo': 'obligatoria',
                })
            else:
                # Limitables: verificar si caben en el limite
                disponible = limite - acumulado
                
                if disponible <= 0:
                    # No hay espacio, dejar en cero
                    deducciones_cero.append({
                        'codigo': ded['codigo'],
                        'nombre': ded['nombre'],
                        'valor_original': ded['valor'],
                        'valor_aplicado': 0,
                        'tipo': 'excluida_limite',
                    })
                elif ded['valor'] <= disponible:
                    # Cabe completa
                    acumulado += ded['valor']
                    deducciones_aplicadas.append({
                        'codigo': ded['codigo'],
                        'nombre': ded['nombre'],
                        'valor_original': ded['valor'],
                        'valor_aplicado': ded['valor'],
                        'tipo': 'limitable',
                    })
                else:
                    # Cabe parcialmente
                    valor_parcial = disponible
                    acumulado += valor_parcial
                    deducciones_parciales.append({
                        'codigo': ded['codigo'],
                        'nombre': ded['nombre'],
                        'valor_original': ded['valor'],
                        'valor_aplicado': valor_parcial,
                        'valor_pendiente': ded['valor'] - valor_parcial,
                        'tipo': 'parcial',
                    })
        
        # Guardar informacion de trazabilidad
        info_limite = {
            'limite_aplicado': True,
            'limite_50': limite,
            'total_obligatorias': total_obligatorias,
            'disponible_limitables': limite - total_obligatorias if limite > total_obligatorias else 0,
            'total_aplicado': acumulado,
            'deducciones_completas': deducciones_aplicadas,
            'deducciones_parciales': deducciones_parciales,
            'deducciones_cero': deducciones_cero,
            'cantidad_excluidas': len(deducciones_cero),
            'cantidad_parciales': len(deducciones_parciales),
        }
        
        # Guardar en localdict para trazabilidad
        localdict['LIMIT_DEDUCTIONS_INFO'] = info_limite
        
        return -acumulado, info_limite

    def _totalded(self, localdict):
        """
        Calcula el total de deducciones desde CategoryCollection.
        
        Si contract.limit_deductions = True:
        - Limita deducciones al 50% de TOTALDEV
        - Respeta categorias obligatorias (SSOCIAL, RETENCION)
        - Procesa en orden de secuencia
        """
        contract = localdict.get('contract')
        
        # Verificar si aplica limite
        if contract and contract.limit_deductions:
            # Obtener TOTALDEV
            rules = localdict.get('rules', {})
            totaldev_rule = rules.get('TOTALDEV')
            totaldev = abs(totaldev_rule.total) if totaldev_rule else 0
            
            # Calcular limite 50%
            limite = totaldev * 0.5
            
            # Obtener deducciones ordenadas
            deducciones = self._get_deducciones_ordenadas(localdict)
            
            # Aplicar limite
            total_ded, info_limite = self._aplicar_limite_deducciones(deducciones, limite, localdict)
            
            # Agregar TOTALDEV a la info
            info_limite['totaldev'] = totaldev
            localdict['LIMIT_DEDUCTIONS_INFO'] = info_limite
            
            return total_ded, 1, 100, False, info_limite, {'total_deducciones': total_ded}
        
        # Sin limite: calculo normal
        total, details = self._total_by_afecta_totales(localdict, 'deduccion')
        return total, 1, 100, False, {'DEDUCCIONES': total}, details

    def _net(self, localdict):
        """Calcula el neto a pagar (devengos - deducciones)"""
        # Calcular devengos y deducciones usando clasificación efectiva
        devengos, det_devengos = self._total_by_afecta_totales(localdict, 'devengo')
        deducciones, det_deducciones = self._total_by_afecta_totales(localdict, 'deduccion')

        # Calcular neto
        neto = devengos + deducciones  # deducciones ya vienen negativas

        # Preparar diccionario de resumen
        resumen = {
            'devengos': devengos,
            'deducciones': deducciones,
            'neto': neto,
            'categorias': {
                'DEVENGOS': devengos,
                'DEDUCCIONES': deducciones
            },
            'detalles': {
                **det_devengos,
                **det_deducciones
            }
        }

        return neto, 1, 100, False, resumen, {'neto': neto}
