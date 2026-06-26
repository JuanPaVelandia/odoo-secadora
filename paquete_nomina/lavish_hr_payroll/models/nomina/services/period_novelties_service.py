# -*- coding: utf-8 -*-
"""
Servicio de Novedades del Período
=================================

Consolida las consultas de novedades para asociarlas a la nómina:
- Ausencias (hr.leave, hr.leave.line)
- Novedades diferentes (hr.novelties.different.concepts)
- Préstamos/Cuotas (hr.loan.installment)
- Horas extras (hr.overtime)
- Conceptos de contrato (hr.contract.concepts)

NOTA: La lógica de cálculo de valores está en old/
"""

import logging

_logger = logging.getLogger(__name__)


class PeriodNoveltiesService:
    """
    Servicio unificado para consultar novedades del período de nómina.
    Solo contiene métodos de consulta, no lógica de cálculo.
    """

    def __init__(self, env, payslip, batch_ctx=None):
        self.env = env
        self.payslip = payslip
        self.batch_ctx = batch_ctx
        self.employee_id = payslip.employee_id.id
        self.contract_id = payslip.contract_id.id
        self.contract = payslip.contract_id
        self.date_from = payslip.date_from
        self.date_to = payslip.date_to
        self.struct_id = payslip.struct_id.id if payslip.struct_id else False
        self.struct_process = payslip.struct_id.process if payslip.struct_id else 'nomina'

        # Cache
        self._leaves = None
        self._leave_lines = None
        self._novedades = None
        self._prestamos = None
        self._horas_extras = None
        self._conceptos = None

    # =========================================================================
    # AUSENCIAS
    # =========================================================================

    def get_leaves(self):
        """
        Obtiene las ausencias validadas del empleado en el período.

        Returns:
            recordset de hr.leave
        """
        if self._leaves is None:
            self._leaves = self.env['hr.leave'].search([
                ('employee_id', '=', self.employee_id),
                ('state', '=', 'validate'),
                ('date_from', '<=', self.date_to),
                ('date_to', '>=', self.date_from),
            ])
        return self._leaves

    def get_leave_lines(self):
        """
        Obtiene las líneas de ausencia del período.

        Returns:
            recordset de hr.leave.line
        """
        if self._leave_lines is None:
            leave_ids = self.get_leaves().ids
            if leave_ids:
                self._leave_lines = self.env['hr.leave.line'].search([
                    ('leave_id', 'in', leave_ids),
                    ('date', '>=', self.date_from),
                    ('date', '<=', self.date_to),
                ], order='date')
            else:
                self._leave_lines = self.env['hr.leave.line']
        return self._leave_lines

    # =========================================================================
    # NOVEDADES DIFERENTES
    # =========================================================================

    def get_novedades(self):
        """
        Obtiene las novedades del empleado en el período.

        Returns:
            recordset de hr.novelties.different.concepts
        """
        if self._novedades is not None:
            return self._novedades

        if self.batch_ctx:
            self._novedades = self.batch_ctx.get_employee_novelties(self.employee_id)
            return self._novedades

        company = self.payslip.company_id
        requires_approval = company.novelty_approval_required

        domain = [
            ('employee_id', '=', self.employee_id),
            ('date', '>=', self.date_from),
            ('date', '<=', self.date_to),
        ]

        if requires_approval:
            domain.append(('state', '=', 'approved'))
        else:
            domain.append(('state', 'in', ['draft', 'approved', 'done']))

        self._novedades = self.env['hr.novelties.different.concepts'].search(domain)
        return self._novedades

    # =========================================================================
    # PRÉSTAMOS
    # =========================================================================

    def get_prestamos(self):
        """
        Obtiene las cuotas de préstamos pendientes del empleado según el tipo de nómina.

        Considera:
        - process_loans: Si se deben procesar préstamos
        - double_installment: Si se procesan dobles cuotas
        - struct_process: Tipo de estructura (nomina, contrato, prima, cesantias)
        - process_settlement_loans: Si se descuentan préstamos en liquidación

        Returns:
            recordset de hr.loan.installment
        """
        if self._prestamos is not None:
            return self._prestamos

        slip = self.payslip

        if not slip.process_loans:
            self._prestamos = self.env['hr.loan.installment']
            return self._prestamos

        # Si ya hay cuotas asociadas al payslip (ya procesadas por _process_loan_lines)
        if slip.loan_installment_ids:
            self._prestamos = slip.loan_installment_ids
            return self._prestamos

        # Determinar qué cuotas obtener según el tipo de estructura
        loan_lines = self.env['hr.loan.installment']

        if self.struct_process == 'contrato':
            if slip.process_settlement_loans:
                loan_lines = self._get_settlement_loans()
                loan_lines |= self._get_advance_loans_for_structure('liquidacion')

        # Caso 2: Prima de servicios
        elif self.struct_process == 'prima':
            loan_lines = self._get_advance_loans_for_structure('prima')

        # Caso 3: Cesantías
        elif self.struct_process == 'cesantias':
            # Solo anticipos de cesantías
            loan_lines = self._get_advance_loans_for_structure('cesantias')

        # Caso 4: Nómina regular
        else:
            loan_lines = self._get_regular_loan_lines()

        self._prestamos = loan_lines
        return self._prestamos

    def _get_regular_loan_lines(self):
        """
        Obtiene las cuotas de préstamo para nómina regular.
        Considera la opción de doble cuota.

        Returns:
            recordset de hr.loan.installment
        """
        domain = [
            ('employee_id', '=', self.employee_id),
            ('loan_id.state', '=', 'approved'),
            ('date', '>=', self.date_from),
            ('date', '<=', self.date_to),
            ('paid', '=', False),
            ('skip', '=', False),
        ]

        current_installments = self.env['hr.loan.installment'].search(domain, order='date')

        # Si está marcado para procesar doble cuota
        if self.payslip.double_installment and current_installments:
            next_domain = [
                ('employee_id', '=', self.employee_id),
                ('loan_id.state', '=', 'approved'),
                ('date', '>', self.date_to),
                ('paid', '=', False),
                ('skip', '=', False),
            ]
            next_installments = self.env['hr.loan.installment'].search(
                next_domain,
                order='date',
                limit=len(current_installments)
            )
            return current_installments + next_installments

        return current_installments

    def _get_settlement_loans(self):
        """
        Obtiene todas las cuotas pendientes de préstamos marcados para liquidación.

        Returns:
            recordset de hr.loan.installment
        """
        domain = [
            ('employee_id', '=', self.employee_id),
            ('state', '=', 'approved'),
            ('deduct_on_settlement', '=', True),
        ]
        loans = self.env['hr.loan'].search(domain)
        result = self.env['hr.loan.installment']

        for loan in loans:
            pending = loan.installment_ids.filtered(
                lambda x: not x.paid and not x.skip
            )
            if pending:
                result |= pending

        return result

    def _get_advance_loans_for_structure(self, structure_type):
        """
        Obtiene anticipos que deben descontarse en estructuras específicas.

        Args:
            structure_type: Tipo de estructura ('prima', 'cesantias', 'liquidacion')

        Returns:
            recordset de hr.loan.installment
        """
        domain = [
            ('employee_id', '=', self.employee_id),
            ('loan_id.state', '=', 'approved'),
            ('loan_id.deduct_in_structure', '=', True),
            ('loan_id.structure_type', '=', structure_type),
            ('paid', '=', False),
            ('skip', '=', False),
        ]
        return self.env['hr.loan.installment'].search(domain)

    # =========================================================================
    # HORAS EXTRAS
    # =========================================================================

    def get_horas_extras(self):
        """
        Obtiene las horas extras del empleado en el período.

        Returns:
            recordset de hr.overtime
        """
        if self._horas_extras is not None:
            return self._horas_extras

        domain = [
            ('employee_id', '=', self.employee_id),
            ('date_only', '>=', self.date_from),
            ('date_end_only', '<=', self.date_to),
            ('state', '!=', 'revertido'),
        ]

        self._horas_extras = self.env['hr.overtime'].search(domain)
        return self._horas_extras

    # =========================================================================
    # CONCEPTOS DE CONTRATO
    # =========================================================================

    def get_conceptos(self):
        """
        Obtiene los conceptos activos del contrato.

        Returns:
            recordset de hr.contract.concepts
        """
        if self._conceptos is not None:
            return self._conceptos

        if self.batch_ctx:
            self._conceptos = self.batch_ctx.get_contract_concepts(self.contract_id)
            return self._conceptos

        self._conceptos = self.contract.concepts_ids.filtered(
            lambda c: c.state == 'done' and c.active
        )
        return self._conceptos

    # =========================================================================
    # RESUMEN CONSOLIDADO
    # =========================================================================

    def get_all_novelties(self):
        """
        Obtiene todas las novedades del período en un diccionario consolidado.

        Returns:
            dict: {
                'leaves': recordset,
                'leave_lines': recordset,
                'novedades': recordset,
                'prestamos': recordset,
                'horas_extras': recordset,
                'conceptos': recordset,
            }
        """
        return {
            'leaves': self.get_leaves(),
            'leave_lines': self.get_leave_lines(),
            'novedades': self.get_novedades(),
            'prestamos': self.get_prestamos(),
            'horas_extras': self.get_horas_extras(),
            'conceptos': self.get_conceptos(),
        }

    def get_novelties_summary(self):
        """
        Obtiene un resumen con conteos de novedades.

        Returns:
            dict: {
                'ausencias_count': int,
                'novedades_count': int,
                'prestamos_count': int,
                'horas_extras_count': int,
                'conceptos_count': int,
                'total_count': int,
            }
        """
        leaves = self.get_leaves()
        novedades = self.get_novedades()
        prestamos = self.get_prestamos()
        horas_extras = self.get_horas_extras()
        conceptos = self.get_conceptos()

        return {
            'ausencias_count': len(leaves),
            'novedades_count': len(novedades),
            'prestamos_count': len(prestamos),
            'horas_extras_count': len(horas_extras),
            'conceptos_count': len(conceptos),
            'total_count': len(leaves) + len(novedades) + len(prestamos) + len(horas_extras) + len(conceptos),
        }

    # =========================================================================
    # AUSENCIAS - CONSOLIDADO
    # =========================================================================

    def get_ausencias(self):
        """
        Obtiene las ausencias consolidadas del período desde hr.leave.line.

        Returns:
            dict: {
                'total_dias': float,
                'total_dias_trabajo': float,
                'total_dias_festivo': float,
                'total_horas': float,
                'total_valor': float,
                'por_tipo': dict,
                'por_leave': dict,
                'detalle': list,
            }
        """
        resultado = {
            'total_dias': 0,
            'total_dias_trabajo': 0,
            'total_dias_festivo': 0,
            'total_horas': 0,
            'total_valor': 0,
            'por_tipo': {},
            'por_leave': {},
            'detalle': []
        }

        leave_lines = self.get_leave_lines()

        for line in leave_lines:
            leave = line.leave_id
            leave_type = leave.holiday_status_id

            # Datos básicos
            dias_payslip = line.days_payslip or 0
            dias_trabajo = line.days_work or 0
            dias_festivo = line.days_holiday or 0
            horas = line.hours or 0
            amount = line.amount or 0

            resultado['total_dias'] += dias_payslip
            resultado['total_dias_trabajo'] += dias_trabajo
            resultado['total_dias_festivo'] += dias_festivo
            resultado['total_horas'] += horas
            resultado['total_valor'] += amount

            # Agrupar por tipo de ausencia
            tipo_code = leave_type.code if leave_type.code else str(leave_type.id)
            if tipo_code not in resultado['por_tipo']:
                resultado['por_tipo'][tipo_code] = {
                    'nombre': leave_type.name,
                    'novelty': leave_type.novelty if 'novelty' in leave_type._fields else '',
                    'dias': 0,
                    'dias_trabajo': 0,
                    'dias_festivo': 0,
                    'horas': 0,
                    'valor': 0,
                    'unpaid_absences': leave_type.unpaid_absences if 'unpaid_absences' in leave_type._fields else False,
                }
            resultado['por_tipo'][tipo_code]['dias'] += dias_payslip
            resultado['por_tipo'][tipo_code]['dias_trabajo'] += dias_trabajo
            resultado['por_tipo'][tipo_code]['dias_festivo'] += dias_festivo
            resultado['por_tipo'][tipo_code]['horas'] += horas
            resultado['por_tipo'][tipo_code]['valor'] += amount

            # Agrupar por leave
            lid = leave.id
            if lid not in resultado['por_leave']:
                resultado['por_leave'][lid] = {
                    'leave_id': lid,
                    'tipo': leave_type.name,
                    'tipo_code': tipo_code,
                    'novelty': leave_type.novelty if 'novelty' in leave_type._fields else '',
                    'fecha_inicio': leave.date_from,
                    'fecha_fin': leave.date_to,
                    'dias': 0,
                    'valor': 0,
                    'lineas': [],
                }
            resultado['por_leave'][lid]['dias'] += dias_payslip
            resultado['por_leave'][lid]['valor'] += amount
            resultado['por_leave'][lid]['lineas'].append(line.id)

            # Detalle por línea
            resultado['detalle'].append({
                'id': line.id,
                'leave_id': lid,
                'date': line.date,
                'sequence': line.sequence if 'sequence' in line._fields else 0,
                'days_payslip': dias_payslip,
                'days_work': dias_trabajo,
                'days_holiday': dias_festivo,
                'hours': horas,
                'amount': amount,
                'ibc_day': line.ibc_day if 'ibc_day' in line._fields else 0,
                'ibc_base': line.ibc_base if 'ibc_base' in line._fields else 0,
            })

        return resultado

    # =========================================================================
    # ASIGNACIÓN DE NOVEDADES
    # =========================================================================

    def compute_novedades(self):
        """
        Asigna novedades diferentes al payslip actual.
        Actualiza hr_novelties_different_concepts con el payslip_id.

        Solo procesa para estructuras: nomina, contrato, otro, prima
        """
        slip = self.payslip
        process = self.struct_process

        # Solo procesar para ciertas estructuras
        if process not in ('nomina', 'contrato', 'otro', 'prima'):
            return

        domain = [
            ('payslip_id', '=', False),
            ('employee_id', '=', self.employee_id),
        ]

        # Filtrar por fechas según estructura
        if process in ('nomina', 'contrato', 'otro', 'prima'):
            domain.extend([
                ('date', '>=', self.date_from),
                ('date', '<=', self.date_to),
            ])

        novedades = self.env['hr.novelties.different.concepts'].search(domain)
        if novedades:
            novedades.write({'payslip_id': slip.id})

    def compute_extra_hours(self):
        """
        Asigna horas extras al payslip actual.
        Actualiza hr_overtime con el payslip_run_id.

        Solo procesa para estructuras: nomina, contrato, otro

        Estados hr.overtime: nuevo, procesado, revertido
        Campos fecha: date_only (Date), date_end_only (Date) - computados desde date/date_end (Datetime)
        """
        slip = self.payslip

        if self.struct_process not in ('nomina', 'contrato', 'otro'):
            return

        # Buscar horas extras no asignadas o en estado nuevo
        domain = [
            ('employee_id', '=', self.employee_id),
            ('date_only', '>=', self.date_from),
            ('date_end_only', '<=', self.date_to),
            ('payslip_run_id', '=', False),
            '|',
            ('state', '=', False),
            ('state', 'in', ['nuevo', 'procesado']),
        ]

        horas_extras = self.env['hr.overtime'].search(domain)
        if horas_extras:
            horas_extras.write({
                'payslip_run_id': slip.id,
                'state': 'procesado',
            })

    # =========================================================================
    # NÓMINAS PREVIAS DEL PERÍODO
    # =========================================================================

    def get_old_payslips(self):
        """
        Obtiene nóminas previas (vacaciones, prima) del mismo período/mes.

        Returns:
            recordset de hr.payslip
        """
        from dateutil.relativedelta import relativedelta

        slip = self.payslip
        start_date = self.date_from.replace(day=1)
        end_date = start_date + relativedelta(months=1, days=-1)

        domain = [
            ('id', '!=', slip.id),
            ('employee_id', '=', self.employee_id),
            ('contract_id', '=', self.contract_id),
            ('date_from', '>=', start_date),
            ('date_to', '<=', end_date),
            ('struct_id.process', 'in', ['vacaciones', 'prima']),
            ('state', 'in', ['done', 'paid', 'verify']),
        ]

        return self.env['hr.payslip'].search(domain)

    def assign_old_payslips(self):
        """
        Asigna nóminas previas del período al payslip actual.
        Actualiza el campo payslip_old_ids con las nóminas encontradas.
        """
        old_payslips = self.get_old_payslips()
        self.payslip.payslip_old_ids = [(6, 0, old_payslips.ids)]

    def get_old_payslips_summary(self):
        """
        Obtiene resumen de nóminas previas del período para mostrar en vista.

        Returns:
            list: Lista de diccionarios con información de cada nómina
        """
        old_payslips = self.get_old_payslips()
        summary = []

        for slip in old_payslips:
            summary.append({
                'id': slip.id,
                'name': slip.name,
                'number': slip.number,
                'process': slip.struct_id.process,
                'process_name': slip.struct_id.name,
                'date_from': slip.date_from,
                'date_to': slip.date_to,
                'state': slip.state,
                'total_devengos': sum(line.total for line in slip.line_ids if line.category_id.code == 'DEV'),
                'total_deducciones': sum(line.total for line in slip.line_ids if line.category_id.code == 'DED'),
                'net': slip.net_wage,
            })

        return summary
