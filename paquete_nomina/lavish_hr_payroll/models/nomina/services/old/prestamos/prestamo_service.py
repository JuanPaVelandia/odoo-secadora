# -*- coding: utf-8 -*-
"""
Servicio de Préstamos - Manejo de préstamos y cuotas para nómina
Implementa la lógica completa de procesamiento de préstamos según tipo de nómina
"""

import logging

_logger = logging.getLogger(__name__)


class PrestamoService:
    """
    Servicio para procesar préstamos en el cálculo de nómina.
    Maneja diferentes escenarios: nómina regular, prima, cesantías, liquidación.
    """

    def __init__(self, env, payslip, batch_ctx=None):
        self.env = env
        self.payslip = payslip
        self.batch_ctx = batch_ctx
        self.employee_id = payslip.employee_id.id
        self.contract_id = payslip.contract_id.id
        self.date_from = payslip.date_from
        self.date_to = payslip.date_to
        self._struct_process = None

    @property
    def struct_process(self):
        """Obtiene el tipo de proceso de la estructura (cached)"""
        if self._struct_process is None:
            struct = self.payslip.struct_id
            self._struct_process = struct.process if struct and 'process' in struct._fields else 'nomina'
        return self._struct_process

    @property
    def process_loans(self):
        """Verifica si se deben procesar préstamos"""
        slip = self.payslip
        return slip.process_loans if 'process_loans' in slip._fields else True

    @property
    def process_settlement_loans(self):
        """Verifica si se deben procesar préstamos de liquidación"""
        slip = self.payslip
        return slip.process_settlement_loans if 'process_settlement_loans' in slip._fields else False

    @property
    def double_installment(self):
        """Verifica si se debe procesar doble cuota"""
        slip = self.payslip
        return slip.double_installment if 'double_installment' in slip._fields else False

    def get_cuotas_pendientes(self):
        """
        Obtiene las cuotas de préstamos según el tipo de nómina.
        Implementa la lógica completa del sistema de préstamos.

        Returns:
            recordset de hr.loan.installment
        """
        if not self.process_loans:
            return self.env['hr.loan.installment']

        # Usar cuotas ya asociadas al payslip si existen
        slip = self.payslip
        if 'loan_installment_ids' in slip._fields and slip.loan_installment_ids:
            return slip.loan_installment_ids

        # Determinar cuotas según tipo de proceso
        loan_lines = self.env['hr.loan.installment']

        # Caso 1: Liquidación de contrato
        if self.struct_process == 'contrato' and self.process_settlement_loans:
            loan_lines = self._get_settlement_loans()
            # Incluir anticipos marcados para liquidación
            advance_loans = self._get_advance_loans_for_structure('liquidacion')
            loan_lines |= advance_loans

        # Caso 2: Prima de servicios
        elif self.struct_process == 'prima':
            # Anticipos de prima
            advance_loans = self._get_advance_loans_for_structure('prima')
            loan_lines |= advance_loans
            # Préstamos regulares del período
            regular_loans = self._get_regular_loan_lines()
            loan_lines |= regular_loans

        # Caso 3: Cesantías
        elif self.struct_process == 'cesantias':
            # Anticipos de cesantías
            advance_loans = self._get_advance_loans_for_structure('cesantias')
            loan_lines |= advance_loans
            # Préstamos regulares del período
            regular_loans = self._get_regular_loan_lines()
            loan_lines |= regular_loans

        # Caso 4: Nómina regular (nomina, contrato sin liquidación)
        else:
            loan_lines = self._get_regular_loan_lines()

        return loan_lines

    def _get_regular_loan_lines(self):
        """
        Obtiene las cuotas de préstamo regulares para el período.

        Returns:
            recordset de hr.loan.installment
        """
        if hasattr(self.payslip, '_get_loan_lines'):
            return self.payslip._get_loan_lines(
                self.date_from,
                self.date_to,
                self.employee_id
            )

        domain = [
            ('employee_id', '=', self.employee_id),
            ('loan_id.state', '=', 'approved'),
            ('date', '>=', self.date_from),
            ('date', '<=', self.date_to),
            ('paid', '=', False),
            ('skip', '=', False)
        ]
        return self.env['hr.loan.installment'].search(domain)

    def _get_settlement_loans(self):
        """
        Obtiene los préstamos para liquidación.
        Busca préstamos con deduct_on_settlement=True.

        Returns:
            recordset de hr.loan.installment
        """
        if hasattr(self.payslip, '_get_settlement_loans'):
            return self.payslip._get_settlement_loans(self.employee_id)

        domain = [
            ('employee_id', '=', self.employee_id),
            ('state', '=', 'approved'),
            ('deduct_on_settlement', '=', True)
        ]
        loans = self.env['hr.loan'].search(domain)
        result = self.env['hr.loan.installment']

        for loan in loans:
            pending_installments = loan.installment_ids.filtered(
                lambda x: not x.paid and not x.skip
            )
            if pending_installments:
                result |= pending_installments

        return result

    def _get_advance_loans_for_structure(self, structure_type):
        """
        Obtiene anticipos que deben descontarse en estructuras específicas.

        Args:
            structure_type: Tipo de estructura ('prima', 'cesantias', 'liquidacion')

        Returns:
            recordset de hr.loan.installment
        """
        if hasattr(self.payslip, '_get_advance_loans_for_structure'):
            return self.payslip._get_advance_loans_for_structure(
                self.employee_id,
                structure_type
            )

        domain = [
            ('employee_id', '=', self.employee_id),
            ('loan_id.state', '=', 'approved'),
            ('loan_id.deduct_in_structure', '=', True),
            ('loan_id.structure_type', '=', structure_type),
            ('paid', '=', False),
            ('skip', '=', False)
        ]
        return self.env['hr.loan.installment'].search(domain)

    def _get_loan_interest_lines(self):
        """
        Obtiene cuotas con intereses pendientes de cobro para el período.

        Returns:
            recordset de hr.loan.installment con intereses pendientes
        """
        if hasattr(self.payslip, '_get_loan_interest_lines'):
            return self.payslip._get_loan_interest_lines(
                self.date_from,
                self.date_to,
                self.employee_id
            )

        domain = [
            ('employee_id', '=', self.employee_id),
            ('loan_id.state', '=', 'approved'),
            ('loan_id.apply_interest', '=', True),
            ('date', '>=', self.date_from),
            ('date', '<=', self.date_to),
            ('interest_charged', '=', False),
            ('skip', '=', False),
            ('interest_amount', '>', 0)
        ]
        return self.env['hr.loan.installment'].search(domain)

    def get_installments_summary(self, cuotas=None):
        """
        Resumen de cuotas (capital) para reuso en reglas y reportes.

        Args:
            cuotas: recordset de hr.loan.installment (opcional)

        Returns:
            dict con total, cantidad y detalle por préstamo
        """
        cuotas = cuotas if cuotas is not None else self.get_cuotas_pendientes()
        if not cuotas:
            return {'total': 0.0, 'count': 0, 'details': []}

        total = sum(cuotas.mapped('amount'))
        details = []
        loans = cuotas.mapped('loan_id')

        for loan in loans:
            loan_cuotas = cuotas.filtered(lambda x: x.loan_id.id == loan.id)
            loan_amount = sum(loan_cuotas.mapped('amount'))
            details.append({
                'loan_id': loan.id,
                'loan_name': loan.name,
                'loan_category': loan.category_id.name if loan.category_id else '',
                'count': len(loan_cuotas),
                'amount': loan_amount,
                'installment_ids': loan_cuotas.ids,
            })

        return {
            'total': total,
            'count': len(cuotas),
            'details': details,
        }

    def procesar_prestamos(self, localdict):
        """
        Procesa los préstamos y genera líneas de descuento.

        Args:
            localdict: Diccionario local del cálculo

        Returns:
            dict con líneas de préstamos a crear
        """
        lineas = {}
        cuotas = self.get_cuotas_pendientes()

        for cuota in cuotas:
            linea = self._crear_linea_prestamo(cuota, localdict)
            if linea:
                lineas[linea['code']] = linea

        # Procesar intereses si aplica
        lineas_intereses = self._procesar_intereses(localdict)
        lineas.update(lineas_intereses)

        return lineas

    def _crear_linea_prestamo(self, cuota, localdict):
        """
        Crea una línea de descuento para una cuota de préstamo.

        Args:
            cuota: hr.loan.installment record
            localdict: Diccionario local

        Returns:
            dict con datos de la línea o None
        """
        prestamo = cuota.loan_id
        if not prestamo:
            return None

        # Obtener regla salarial del préstamo
        category = prestamo.category_id
        rule = category.salary_rule_id if category and 'salary_rule_id' in category._fields else None
        if not rule:
            _logger.warning(
                "Préstamo %s sin regla salarial configurada en categoría",
                prestamo.name
            )
            return None

        amount = -abs(cuota.amount)  # Negativo para descuento
        code = f'LOAN_{prestamo.id}_{cuota.sequence}'

        # Descripción de la cuota
        total_cuotas = len(prestamo.installment_ids)
        cat_code = category.code if category else ''
        cat_name = category.name if category else ''
        descripcion = f"Cuota {cuota.sequence}/{total_cuotas} - [{cat_code}] {cat_name}"

        return {
            'sequence': rule.sequence,
            'code': code,
            'name': descripcion,
            'salary_rule_id': rule.id,
            'contract_id': self.contract_id,
            'employee_id': self.employee_id,
            'entity_id': prestamo.entity_id.id if prestamo.entity_id else False,
            'amount': amount,
            'quantity': 1.0,
            'rate': 100.0,
            'total': round(amount),
            'slip_id': self.payslip.id,
            'run_id': self.payslip.payslip_run_id.id if self.payslip.payslip_run_id else False,
            'loan_id': prestamo.id,
            'installment_id': cuota.id,
        }

    def _procesar_intereses(self, localdict):
        """
        Procesa los intereses de préstamos para el período.

        Args:
            localdict: Diccionario local

        Returns:
            dict con líneas de intereses
        """
        lineas = {}
        cuotas_con_intereses = self._get_loan_interest_lines()

        if not cuotas_con_intereses:
            return lineas

        # Agrupar por préstamo
        prestamos_procesados = {}
        for cuota in cuotas_con_intereses:
            pid = cuota.loan_id.id
            if pid not in prestamos_procesados:
                prestamos_procesados[pid] = {
                    'prestamo': cuota.loan_id,
                    'cuotas': [],
                    'total_interes': 0
                }
            prestamos_procesados[pid]['cuotas'].append(cuota)
            prestamos_procesados[pid]['total_interes'] += cuota.interest_amount

        # Crear línea por cada préstamo con intereses
        for pid, data in prestamos_procesados.items():
            prestamo = data['prestamo']
            total_interes = data['total_interes']

            if total_interes <= 0:
                continue

            # Obtener regla de intereses
            rule = prestamo.interest_rule_id if 'interest_rule_id' in prestamo._fields else None
            if not rule:
                continue

            code = f'LOAN_INT_{pid}'
            lineas[code] = {
                'sequence': rule.sequence,
                'code': code,
                'name': f"Intereses préstamo {prestamo.name}",
                'salary_rule_id': rule.id,
                'contract_id': self.contract_id,
                'employee_id': self.employee_id,
                'entity_id': False,
                'amount': -abs(total_interes),
                'quantity': 1.0,
                'rate': 100.0,
                'total': round(-abs(total_interes)),
                'slip_id': self.payslip.id,
                'run_id': self.payslip.payslip_run_id.id if self.payslip.payslip_run_id else False,
                'loan_id': pid,
            }

        return lineas

    def get_total_descuentos(self):
        """
        Calcula el total de descuentos por préstamos.

        Returns:
            float con el total a descontar (valor positivo)
        """
        cuotas = self.get_cuotas_pendientes()
        return sum(cuota.amount for cuota in cuotas)

    def get_total_intereses(self, mark_charged=False):
        """
        Calcula el total de intereses a cobrar.

        Returns:
            dict con información de intereses
        """
        if mark_charged and hasattr(self.payslip, 'get_loan_interests'):
            return self.payslip.get_loan_interests()

        cuotas = self._get_loan_interest_lines()
        if not cuotas:
            return {'total': 0.0, 'count': 0, 'details': []}

        total = sum(cuotas.mapped('interest_amount'))

        # Detalle por préstamo
        details = []
        loans = cuotas.mapped('loan_id')
        for loan in loans:
            loan_cuotas = cuotas.filtered(lambda x: x.loan_id.id == loan.id)
            loan_interest = sum(loan_cuotas.mapped('interest_amount'))
            details.append({
                'loan_name': loan.name,
                'loan_id': loan.id,
                'interest': loan_interest,
                'count': len(loan_cuotas)
            })

        return {
            'total': total,
            'count': len(cuotas),
            'details': details
        }

    def get_resumen(self):
        """
        Obtiene resumen completo de préstamos del empleado.

        Returns:
            dict con resumen de préstamos
        """
        cuotas = self.get_cuotas_pendientes()
        resumen = self.get_installments_summary(cuotas)
        prestamos = {}

        for cuota in cuotas:
            pid = cuota.loan_id.id
            if pid not in prestamos:
                loan = cuota.loan_id
                category = loan.category_id
                prestamos[pid] = {
                    'id': pid,
                    'nombre': loan.name,
                    'categoria': category.name if category else '',
                    'categoria_code': category.code if category else '',
                    'tipo': loan.loan_type if 'loan_type' in loan._fields else 'loan',
                    'deduct_on_settlement': loan.deduct_on_settlement if 'deduct_on_settlement' in loan._fields else False,
                    'cuotas': [],
                    'total': 0
                }
            prestamos[pid]['cuotas'].append({
                'id': cuota.id,
                'numero': cuota.sequence,
                'monto': cuota.amount,
                'fecha': cuota.date,
                'interes': cuota.interest_amount if 'interest_amount' in cuota._fields else 0
            })
            prestamos[pid]['total'] += cuota.amount

        # Información de intereses
        intereses = self.get_total_intereses()

        return {
            'tipo_proceso': self.struct_process,
            'prestamos': list(prestamos.values()),
            'total_capital': resumen.get('total', 0.0),
            'total_intereses': intereses['total'],
            'total_descuento': resumen.get('total', 0.0) + intereses['total'],
            'cantidad_prestamos': len(prestamos),
            'cantidad_cuotas': resumen.get('count', 0)
        }

    def marcar_cuotas_procesadas(self, cuotas=None):
        """
        Asocia las cuotas al payslip (se marcarán como pagadas al confirmar nómina).

        Args:
            cuotas: recordset de cuotas (opcional, usa las pendientes si no se especifica)
        """
        if cuotas is None:
            cuotas = self.get_cuotas_pendientes()

        if cuotas and 'loan_installment_ids' in self.payslip._fields:
            self.payslip.loan_installment_ids = [(6, 0, cuotas.ids)]

    def marcar_intereses_cobrados(self, cuotas=None):
        """
        Marca los intereses de las cuotas como cobrados.

        Args:
            cuotas: recordset de cuotas con intereses (opcional)
        """
        if cuotas is None:
            cuotas = self._get_loan_interest_lines()

        for cuota in cuotas:
            if 'interest_charged' in cuota._fields:
                cuota.write({
                    'interest_charged': True,
                    'interest_payslip_id': self.payslip.id
                })
