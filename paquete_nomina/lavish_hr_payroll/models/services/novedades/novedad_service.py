# -*- coding: utf-8 -*-
"""
Servicio de Novedades - Manejo de novedades diferentes para nómina
"""

import logging

_logger = logging.getLogger(__name__)


class NovedadService:
    """
    Servicio para procesar novedades diferentes en el cálculo de nómina.
    """

    def __init__(self, env, payslip, batch_ctx=None):
        self.env = env
        self.payslip = payslip
        self.batch_ctx = batch_ctx
        self.employee_id = payslip.employee_id.id
        self.date_from = payslip.date_from
        self.date_to = payslip.date_to

    def get_novedades(self):
        """
        Obtiene las novedades del empleado en el período.
        Solo incluye novedades en estado 'approved' (aprobadas).

        Returns:
            recordset de hr.novelties.different.concepts
        """
        if self.batch_ctx:
            novedades = self.batch_ctx.get_employee_novelties(self.employee_id)
            return novedades.filtered(lambda n: n.state == 'approved')

        domain = [
            ('employee_id', '=', self.employee_id),
            ('date', '>=', self.date_from),
            ('date', '<=', self.date_to),
            ('state', '=', 'approved'),
        ]

        return self.env['hr.novelties.different.concepts'].search(domain)

    def filtrar_por_estructura(self, novedades=None):
        """
        Filtra novedades aplicables a la estructura del payslip.

        Lógica:
        - Sin estructuras definidas: aplica solo a 'nomina' y 'contrato' (liquidación)
        - Con estructuras definidas: aplica solo si la estructura del payslip está en la lista

        Args:
            novedades: recordset de novedades (opcional)

        Returns:
            recordset filtrado
        """
        if novedades is None:
            novedades = self.get_novedades()

        struct_id = self.payslip.struct_id.id if self.payslip.struct_id else False
        struct_process = getattr(self.payslip, 'struct_process', False)

        resultado = self.env['hr.novelties.different.concepts']

        # Procesos donde aplican novedades sin estructura específica
        PROCESOS_GENERALES = ['nomina', 'contrato']

        for novedad in novedades:
            # Ignorar novedades con monto cero
            if novedad.amount == 0:
                continue

            tiene_estructuras = novedad.salary_structure_ids and len(novedad.salary_structure_ids) > 0

            if not tiene_estructuras:
                # Sin estructuras definidas: aplica solo a nómina y liquidación de contrato
                if struct_process in PROCESOS_GENERALES:
                    resultado |= novedad
                    _logger.debug(
                        "Novedad %s incluida (sin estructura, proceso=%s)",
                        novedad.id, struct_process
                    )
            else:
                # Con estructuras definidas: verificar si la estructura actual está en la lista
                if struct_id and struct_id in novedad.salary_structure_ids.ids:
                    resultado |= novedad
                    _logger.debug(
                        "Novedad %s incluida (estructura %s en lista)",
                        novedad.id, struct_id
                    )

        return resultado

    def procesar_novedades(self, localdict):
        """
        Procesa las novedades y genera líneas.

        Args:
            localdict: Diccionario local del cálculo

        Returns:
            dict con líneas de novedades
        """
        novedades = self.filtrar_por_estructura()
        lineas = {}

        for novedad in novedades:
            linea = self._crear_linea_novedad(novedad, localdict)
            if linea:
                lineas[linea['code']] = linea

        return lineas

    def _crear_linea_novedad(self, novedad, localdict):
        """
        Crea una línea para una novedad.

        Args:
            novedad: hr.novelties.different.concepts record
            localdict: Diccionario local

        Returns:
            dict con datos de la línea o None
        """
        rule = novedad.salary_rule_id
        if not rule:
            return None

        amount = novedad.amount
        code = f'NOV_{novedad.id}'

        return {
            'sequence': rule.sequence,
            'code': code,
            'name': novedad.description or novedad.name or rule.name,
            'salary_rule_id': rule.id,
            'contract_id': self.payslip.contract_id.id,
            'employee_id': self.employee_id,
            'entity_id': False,
            'amount': amount,
            'quantity': 1.0,
            'rate': 100.0,
            'total': round(amount),
            'slip_id': self.payslip.id,
            'run_id': self.payslip.payslip_run_id.id if self.payslip.payslip_run_id else False,
            'novedad_id': novedad.id,
        }

    def get_resumen(self):
        """
        Obtiene resumen de novedades.

        Returns:
            dict con resumen
        """
        novedades = self.filtrar_por_estructura()

        devengos = 0
        deducciones = 0
        detalle = []

        for nov in novedades:
            rule = nov.salary_rule_id
            es_deduccion = rule.category_id.code in ['DED', 'DEDUCCION'] if rule and rule.category_id else False

            if es_deduccion:
                deducciones += abs(nov.amount)
            else:
                devengos += nov.amount

            detalle.append({
                'id': nov.id,
                'nombre': nov.description or nov.name,
                'regla': rule.code if rule else '',
                'monto': nov.amount,
                'fecha': nov.date,
                'es_deduccion': es_deduccion
            })

        return {
            'total_devengos': devengos,
            'total_deducciones': deducciones,
            'cantidad': len(novedades),
            'detalle': detalle
        }
