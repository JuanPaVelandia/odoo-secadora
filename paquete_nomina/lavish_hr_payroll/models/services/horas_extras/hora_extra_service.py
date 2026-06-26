# -*- coding: utf-8 -*-
"""
Servicio de Horas Extras - Manejo de horas extras para nómina y liquidación
"""

import logging
from datetime import date
from dateutil.relativedelta import relativedelta

_logger = logging.getLogger(__name__)


class HoraExtraService:
    """
    Servicio para procesar horas extras en el cálculo de nómina.

    Maneja:
    - Cálculo de valor de horas extras por tipo
    - Inclusión en base de prestaciones (cesantías, prima)
    - Lógica de promedio para liquidaciones
    """

    # Factores de recargo según legislación colombiana
    FACTORES_RECARGO = {
        'overtime_rn': 0.35,      # Recargo Nocturno 35%
        'overtime_ext_d': 1.25,   # Extra Diurna 125%
        'overtime_ext_n': 1.75,   # Extra Nocturna 175%
        'overtime_eddf': 2.00,    # Extra Diurna Dom/Fest 200%
        'overtime_endf': 2.50,    # Extra Nocturna Dom/Fest 250%
        'overtime_dof': 1.75,     # Dominical/Festivo 175%
        'overtime_rndf': 1.10,    # Recargo Nocturno Dom/Fest 110%
        'overtime_rdf': 0.75,     # Recargo Dominical/Festivo 75%
        'overtime_rnf': 2.10,     # Recargo Nocturno Festivo 210%
    }

    NOMBRES_TIPO = {
        'overtime_rn': 'Recargo Nocturno 35%',
        'overtime_ext_d': 'Hora Extra Diurna 25%',
        'overtime_ext_n': 'Hora Extra Nocturna 75%',
        'overtime_eddf': 'Hora Extra Dom/Fest Diurna 100%',
        'overtime_endf': 'Hora Extra Dom/Fest Nocturna 150%',
        'overtime_dof': 'Dominical/Festivo 75%',
        'overtime_rndf': 'Recargo Nocturno Dom/Fest 110%',
        'overtime_rdf': 'Recargo Dominical/Festivo 75%',
        'overtime_rnf': 'Recargo Nocturno Festivo 210%',
    }

    # Como mostrar el porcentaje en el nombre de la linea:
    #   'recargo' -> percentage incluye 100% base, se muestra el recargo neto (percentage - 100)
    #   'raw'     -> percentage es el recargo total puro, se muestra tal cual
    PERCENTAGE_DISPLAY_MODE = {
        'overtime_rn': 'raw',        # 35 -> "35%"
        'overtime_ext_d': 'recargo', # 125 -> "25%"
        'overtime_ext_n': 'recargo', # 175 -> "75%"
        'overtime_eddf': 'recargo',  # 205 -> "105%"
        'overtime_endf': 'recargo',  # 255 -> "155%"
        'overtime_dof': 'recargo',   # 180 -> "80%" (dominical TOTAL incluye base)
        'overtime_rndf': 'raw',      # 115 -> "115%" (recargo puro acumulado)
        'overtime_rdf': 'raw',       # 80 -> "80%"
        'overtime_rnf': 'raw',       # 210 -> "210%"
    }

    def __init__(self, env, payslip, batch_ctx=None):
        self.env = env
        self.payslip = payslip
        self.batch_ctx = batch_ctx
        self.employee_id = payslip.employee_id.id
        self.contract = payslip.contract_id
        self.date_from = payslip.date_from
        self.date_to = payslip.date_to
        self.struct_process = getattr(payslip, 'struct_process', 'nomina')

    def get_horas_extras(self, date_from=None, date_to=None):
        """
        Obtiene las horas extras del empleado en el período.

        Args:
            date_from: Fecha inicio (opcional, usa payslip.date_from)
            date_to: Fecha fin (opcional, usa payslip.date_to)

        Returns:
            recordset de hr.overtime
        """
        date_from = date_from or self.date_from
        date_to = date_to or self.date_to

        # Usar date_only y date_end_only para busquedas por fecha
        # ya que date y date_end ahora son Datetime
        domain = [
            ('employee_id', '=', self.employee_id),
            ('date_only', '>=', date_from),
            ('date_end_only', '<=', date_to),
            ('state', '!=', 'revertido'),  # Excluir revertidas
        ]

        return self.env['hr.overtime'].search(domain)

    def _get_base_hours(self, reference_date=None):
        """
        Determina las horas base (divisor) segun la jornada legal vigente.

        Prioriza:
        1. hr.company.working.hours por fecha (Ley 2101 / 2466)
        2. hr.annual.parameters.hours_monthly del anio del periodo
        3. Fallback 240 (formula clasica antigua)
        """
        reference_date = reference_date or self.date_to or self.date_from
        company_id = self.contract.company_id.id if self.contract and self.contract.company_id else self.env.company.id

        WorkingHours = self.env['hr.company.working.hours']
        if reference_date:
            cfg = WorkingHours.search([
                ('company_id', '=', company_id),
                ('effective_date', '<=', reference_date),
            ], order='effective_date desc', limit=1)
            if cfg:
                horas = cfg.hours_to_pay or cfg.hours_per_month
                if horas and horas > 0:
                    return float(horas)

        Annual = self.env['hr.annual.parameters']
        ap = Annual.search([
            ('year', '=', (reference_date or self.date_to).year),
            ('company_ids', 'in', [company_id]),
        ], limit=1)
        if not ap:
            ap = Annual.search([('year', '=', (reference_date or self.date_to).year)], limit=1)
        if ap and ap.hours_monthly and ap.hours_monthly > 0:
            return float(ap.hours_monthly)

        return 240.0

    def _resolve_overtime_type(self, tipo, reference_date, company_id):
        """Busca hr.type.overtime vigente para la fecha y empresa, con fallback."""
        TypeOvertime = self.env['hr.type.overtime']
        record = None
        if reference_date and hasattr(TypeOvertime, 'get_percentage_for_date'):
            record = TypeOvertime.get_percentage_for_date(tipo, reference_date, company_id)
        if not record:
            domain = [('type_overtime', '=', tipo), ('active', '=', True)]
            record = TypeOvertime.search(
                domain + [('company_id', '=', company_id)],
                order='valid_from desc', limit=1
            ) or TypeOvertime.search(domain, order='valid_from desc', limit=1)
        return record

    def calcular_valor_horas(self, salario_base=None):
        """
        Calcula el valor monetario de las horas extras del periodo.

        Lee:
        - Divisor (horas base): desde hr.company.working.hours / hr.annual.parameters
          segun la fecha. Implementa Ley 2101/2021 (reduccion gradual de jornada).
        - Factor de cada concepto: desde hr.type.overtime.percentage segun la fecha
          de cada registro de hr.overtime. Implementa Ley 2466/2025 (recargo
          dominical progresivo 80%/90%/100%).

        Si no hay registro en hr.type.overtime, usa FACTORES_RECARGO / NOMBRES_TIPO
        como fallback de compatibilidad.

        Args:
            salario_base: Salario base mensual (opcional, usa contrato)

        Returns:
            dict con detalle y totales
        """
        if salario_base is None:
            salario_base = self.contract.wage or 0

        company_id = self.contract.company_id.id if self.contract and self.contract.company_id else self.env.company.id
        base_hours_default = self._get_base_hours()
        valor_hora_default = (salario_base / base_hours_default) if salario_base and base_hours_default else 0

        horas_extras = self.get_horas_extras()
        detalle = []
        total = 0
        acumulado = {tipo: {'cantidad': 0.0, 'valor': 0.0, 'factor': None, 'nombre': None}
                     for tipo in self.FACTORES_RECARGO}

        for he in horas_extras:
            reference_date = he.date_only or (he.date.date() if he.date else self.date_to)
            base_hours = self._get_base_hours(reference_date)
            valor_hora = (salario_base / base_hours) if salario_base and base_hours else 0

            for tipo in self.FACTORES_RECARGO:
                cantidad = getattr(he, tipo, 0) or 0
                if cantidad <= 0:
                    continue

                ot_type = self._resolve_overtime_type(tipo, reference_date, company_id)
                if ot_type and ot_type.percentage:
                    factor = float(ot_type.percentage) / 100.0
                    display_mode = self.PERCENTAGE_DISPLAY_MODE.get(tipo, 'raw')
                    if display_mode == 'recargo':
                        pct_label = int(round(float(ot_type.percentage) - 100.0))
                    else:
                        pct_label = int(round(float(ot_type.percentage)))
                    base_name = self.NOMBRES_TIPO.get(tipo, tipo).rsplit(' ', 1)[0]
                    nombre = f"{base_name} {pct_label}%"
                else:
                    factor = self.FACTORES_RECARGO[tipo]
                    nombre = self.NOMBRES_TIPO.get(tipo, tipo)

                valor = round(valor_hora * factor * cantidad, 0)
                acumulado[tipo]['cantidad'] += cantidad
                acumulado[tipo]['valor'] += valor
                acumulado[tipo]['factor'] = factor
                acumulado[tipo]['nombre'] = nombre

        for tipo, data in acumulado.items():
            if data['cantidad'] <= 0:
                continue
            factor = data['factor'] if data['factor'] is not None else self.FACTORES_RECARGO[tipo]
            unitario = round(valor_hora_default * factor, 0) if valor_hora_default else 0
            detalle.append({
                'tipo': tipo,
                'nombre': data['nombre'] or self.NOMBRES_TIPO.get(tipo, tipo),
                'cantidad': data['cantidad'],
                'factor': factor,
                'valor_unitario': unitario,
                'valor_total': data['valor'],
            })
            total += data['valor']

        return {
            'salario_base': salario_base,
            'valor_hora': valor_hora_default,
            'base_hours': base_hours_default,
            'detalle': detalle,
            'total': total,
            'overtime_ids': horas_extras.ids
        }

    def get_extras_para_base_prestaciones(self, meses_acumulacion=None):
        """
        Obtiene el valor de horas extras para incluir en base de prestaciones.

        Lógica:
        - Si es el mismo mes de la liquidación: NO se promedia
        - Si son varios meses: se promedia sobre los meses

        Args:
            meses_acumulacion: Número de meses a considerar (opcional)

        Returns:
            dict con extras_base y detalle
        """
        # Para liquidación, calcular desde fecha inicio hasta fecha liquidación
        date_liquidacion = getattr(self.payslip, 'date_liquidacion', None)

        if date_liquidacion and self.struct_process == 'contrato':
            # Liquidación de contrato
            return self._calcular_extras_liquidacion(date_liquidacion, meses_acumulacion)
        else:
            # Nómina normal: extras del período actual
            extras = self.calcular_valor_horas()
            return {
                'extras_base': extras['total'],
                'total_extras': extras['total'],
                'meses': 1,
                'promediado': False,
                'detalle': extras['detalle']
            }

    def _calcular_extras_liquidacion(self, date_liquidacion, meses_acumulacion=None):
        """
        Calcula extras para liquidación de contrato.

        Si trabajó menos de 3 meses: NO se promedia, se suma directo
        Si trabajó 3+ meses: se promedia sobre los últimos 3 meses (o los meses trabajados)
        """
        fecha_inicio_contrato = self.contract.date_start

        # Calcular meses trabajados
        if fecha_inicio_contrato:
            delta = relativedelta(date_liquidacion, fecha_inicio_contrato)
            meses_trabajados = delta.years * 12 + delta.months
            if delta.days > 0:
                meses_trabajados += 1
        else:
            meses_trabajados = 1

        # Si es el mismo mes (menos de 1 mes completo), no promediar
        if meses_trabajados <= 1:
            extras = self.calcular_valor_horas()
            return {
                'extras_base': extras['total'],
                'total_extras': extras['total'],
                'meses': 1,
                'promediado': False,
                'detalle': extras['detalle'],
                'nota': 'Mismo mes - No se promedia'
            }

        # Si trabajó más de 1 mes, buscar extras de los últimos meses
        meses_a_promediar = min(meses_trabajados, meses_acumulacion or 3)

        # Buscar desde hace X meses hasta la fecha de liquidación
        date_from_acum = date_liquidacion - relativedelta(months=meses_a_promediar)
        if date_from_acum < fecha_inicio_contrato:
            date_from_acum = fecha_inicio_contrato

        extras_periodo = self.get_horas_extras(date_from_acum, date_liquidacion)

        # Calcular total
        salario_base = self.contract.wage or 0
        valor_hora = salario_base / 240 if salario_base else 0

        total_extras = 0
        detalle = []

        for tipo, factor in self.FACTORES_RECARGO.items():
            cantidad = sum(getattr(he, tipo, 0) or 0 for he in extras_periodo)
            if cantidad > 0:
                valor = round(valor_hora * factor * cantidad, 0)
                detalle.append({
                    'tipo': tipo,
                    'nombre': self.NOMBRES_TIPO.get(tipo, tipo),
                    'cantidad': cantidad,
                    'factor': factor,
                    'valor_total': valor
                })
                total_extras += valor

        # Promediar sobre los meses
        extras_promedio = round(total_extras / meses_a_promediar, 0) if meses_a_promediar > 0 else 0

        return {
            'extras_base': extras_promedio,
            'total_extras': total_extras,
            'meses': meses_a_promediar,
            'promediado': meses_a_promediar > 1,
            'detalle': detalle,
            'nota': f'Promediado sobre {meses_a_promediar} meses' if meses_a_promediar > 1 else 'No promediado'
        }

    def procesar_horas_extras(self, localdict):
        """
        Procesa horas extras y genera líneas de nómina.

        Args:
            localdict: Diccionario local del cálculo

        Returns:
            dict con líneas de horas extras
        """
        extras = self.calcular_valor_horas()
        lineas = {}

        for item in extras['detalle']:
            if item['valor_total'] <= 0:
                continue

            # Buscar regla salarial para este tipo de hora extra
            tipo_overtime = self.env['hr.type.overtime'].search([
                ('type_overtime', '=', item['tipo'].replace('overtime_', 'overtime_'))
            ], limit=1)

            rule = tipo_overtime.salary_rule if tipo_overtime else None

            code = f"HE_{item['tipo'].upper()}"
            lineas[code] = {
                'sequence': rule.sequence if rule else 100,
                'code': code,
                'name': item['nombre'],
                'salary_rule_id': rule.id if rule else None,
                'contract_id': self.contract.id,
                'employee_id': self.employee_id,
                'entity_id': False,
                'amount': item['valor_total'],
                'quantity': item['cantidad'],
                'rate': item['factor'] * 100,
                'total': item['valor_total'],
                'slip_id': self.payslip.id,
                'run_id': self.payslip.payslip_run_id.id if self.payslip.payslip_run_id else False,
            }

        return lineas

    def get_resumen(self):
        """
        Obtiene resumen de horas extras.

        Returns:
            dict con resumen
        """
        extras = self.calcular_valor_horas()
        extras_base = self.get_extras_para_base_prestaciones()

        total_horas = sum(item['cantidad'] for item in extras['detalle'])

        return {
            'total_horas': total_horas,
            'total_valor': extras['total'],
            'extras_para_base': extras_base['extras_base'],
            'promediado': extras_base.get('promediado', False),
            'meses_promedio': extras_base.get('meses', 1),
            'detalle': extras['detalle'],
            'nota': extras_base.get('nota', '')
        }
