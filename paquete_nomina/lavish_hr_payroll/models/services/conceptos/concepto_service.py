# -*- coding: utf-8 -*-
"""
Servicio de Conceptos - Manejo de conceptos de contrato para nómina
"""

import logging
from datetime import date
from odoo.addons.lavish_hr_payroll.models.utils import round_payroll_amount

_logger = logging.getLogger(__name__)


class ConceptoService:
    """
    Servicio para procesar conceptos de contrato en el cálculo de nómina.

    Los conceptos de contrato (hr.contract.concepts) son deducciones o devengos
    fijos asociados al contrato como: libranzas, embargos, ahorros, seguros, etc.
    """

    def __init__(self, env, payslip, batch_ctx=None):
        self.env = env
        self.payslip = payslip
        self.batch_ctx = batch_ctx
        self.contract_id = payslip.contract_id.id
        self.contract = payslip.contract_id
        self.date_from = payslip.date_from
        self.date_to = payslip.date_to

        # Información de estructura
        self.struct_id = payslip.struct_id.id if payslip.struct_id else False
        self.struct_process = getattr(payslip, 'struct_process', 'nomina')

    def get_conceptos(self):
        """
        Obtiene los conceptos activos del contrato.
        Solo conceptos en estado 'done' (aprobados).

        Returns:
            recordset de hr.contract.concepts
        """
        if self.batch_ctx:
            return self.batch_ctx.get_contract_concepts(self.contract_id)

        # Solo conceptos aprobados y activos
        return self.contract.concepts_ids.filtered(
            lambda c: c.state == 'done' and c.active
        )

    def filtrar_por_estructura(self, conceptos=None):
        """
        Filtra conceptos aplicables a la estructura del payslip.

        Lógica:
        - Si base_structure_only=True y concepto sin estructuras → aplica solo a nomina/contrato
        - Si tiene estructuras específicas → aplica solo a esas estructuras
        - Si base_structure_only=False y sin estructuras → aplica a todas

        Args:
            conceptos: recordset de conceptos (opcional)

        Returns:
            recordset filtrado
        """
        if conceptos is None:
            conceptos = self.get_conceptos()

        resultado = self.env['hr.contract.concepts']

        # Procesos base donde aplican conceptos genéricos
        PROCESOS_BASE = ['nomina', 'contrato']

        for concepto in conceptos:
            tiene_estructuras = concepto.payroll_structure_ids and len(concepto.payroll_structure_ids) > 0

            if tiene_estructuras:
                # Con estructuras específicas: verificar si la actual está en la lista
                if self.struct_id and self.struct_id in concepto.payroll_structure_ids.ids:
                    resultado |= concepto
                    _logger.debug(
                        "Concepto %s incluido (estructura %s en lista)",
                        concepto.id, self.struct_id
                    )
            else:
                # Sin estructuras específicas
                if concepto.base_structure_only:
                    # Solo aplica a estructuras base (nomina, contrato)
                    if self.struct_process in PROCESOS_BASE:
                        resultado |= concepto
                        _logger.debug(
                            "Concepto %s incluido (base_structure_only, proceso=%s)",
                            concepto.id, self.struct_process
                        )
                else:
                    # Aplica a todas las estructuras
                    resultado |= concepto
                    _logger.debug(
                        "Concepto %s incluido (aplica a todas las estructuras)",
                        concepto.id
                    )

        return resultado

    def filtrar_por_periodo(self, conceptos=None):
        """
        Filtra conceptos válidos para el período del payslip.

        Verifica:
        - Quincena de aplicación (aplicar: '15', '30', '0')
        - Fechas de vigencia (date_start, date_end)

        Args:
            conceptos: recordset de conceptos (opcional)

        Returns:
            recordset filtrado
        """
        if conceptos is None:
            conceptos = self.get_conceptos()

        resultado = self.env['hr.contract.concepts']

        for concepto in conceptos:
            # Verificar quincena de aplicación
            if not self._aplica_en_quincena(concepto):
                _logger.debug(
                    "Concepto %s excluido (no aplica en quincena, aplicar=%s, dia_inicio=%s)",
                    concepto.id, concepto.aplicar, self.date_from.day
                )
                continue

            # Verificar fechas de vigencia
            if not self._esta_vigente(concepto):
                _logger.debug(
                    "Concepto %s excluido (fuera de vigencia, %s - %s)",
                    concepto.id, concepto.date_start, concepto.date_end
                )
                continue

            resultado |= concepto

        return resultado

    def _aplica_en_quincena(self, concepto):
        """
        Verifica si el concepto aplica en la quincena actual.

        Args:
            concepto: hr.contract.concepts record

        Returns:
            bool
        """
        aplicar = concepto.aplicar
        dia_inicio = self.date_from.day

        if aplicar == '15':
            # Primera quincena: día inicio <= 15
            return dia_inicio <= 15
        elif aplicar == '30':
            # Segunda quincena: día inicio > 15
            return dia_inicio > 15
        else:
            # '0' = Siempre
            return True

    def _esta_vigente(self, concepto):
        """
        Verifica si el concepto está vigente en el período.

        Args:
            concepto: hr.contract.concepts record

        Returns:
            bool
        """
        # Sin fechas = siempre vigente
        if not concepto.date_start and not concepto.date_end:
            return True

        # Verificar fecha inicio
        if concepto.date_start and concepto.date_start > self.date_to:
            return False

        # Verificar fecha fin
        if concepto.date_end and concepto.date_end < self.date_from:
            return False

        return True

    def filtrar_conceptos_computables(self, conceptos=None):
        """
        Aplica todos los filtros para obtener conceptos computables.

        Combina:
        - Filtro por estructura
        - Filtro por período/quincena
        - Filtro por vigencia

        Args:
            conceptos: recordset de conceptos (opcional)

        Returns:
            recordset filtrado
        """
        if conceptos is None:
            conceptos = self.get_conceptos()

        # Aplicar filtros en secuencia
        conceptos = self.filtrar_por_estructura(conceptos)
        conceptos = self.filtrar_por_periodo(conceptos)

        return conceptos

    def procesar_conceptos(self, localdict):
        """
        Procesa los conceptos y genera líneas.

        Args:
            localdict: Diccionario local del cálculo

        Returns:
            dict con líneas de conceptos
        """
        conceptos = self.filtrar_conceptos_computables()
        lineas = {}

        for concepto in conceptos:
            try:
                linea = self._procesar_concepto(concepto, localdict)
                if linea:
                    lineas[linea['code']] = linea
            except Exception as e:
                _logger.error(
                    "Error procesando concepto %s (%s): %s",
                    concepto.id, concepto.input_id.code if concepto.input_id else 'N/A', str(e)
                )

        return lineas

    def _procesar_concepto(self, concepto, localdict):
        """
        Procesa un concepto individual usando el método del modelo.

        Args:
            concepto: hr.contract.concepts record
            localdict: Diccionario local

        Returns:
            dict con datos de la línea o None
        """
        # Usar el método existente del modelo que tiene toda la lógica
        result = concepto.get_computed_amount_for_payslip(
            payslip=self.payslip,
            date_from=self.date_from,
            date_to=self.date_to,
            localdict=localdict
        )

        if not result.get('create_line', False):
            return None

        rule = concepto.input_id
        if not rule:
            _logger.warning("Concepto %s sin regla salarial", concepto.id)
            return None

        values = result.get('values', {})
        amount = values.get('amount', 0.0)

        # No crear línea si monto es 0 (a menos que force_create)
        if amount == 0 and not result.get('force_create', False):
            return None

        code = f'CONCEPT_{concepto.id}'
        quantity = values.get('quantity', 1.0)
        rate = values.get('rate', 100.0)

        return {
            'sequence': rule.sequence,
            'code': code,
            'name': values.get('name', rule.name),
            'salary_rule_id': rule.id,
            'contract_id': self.contract_id,
            'employee_id': self.payslip.employee_id.id,
            'entity_id': False,
            'amount': amount,
            'quantity': quantity,
            'rate': rate,
            'total': float(round_payroll_amount(amount * quantity * rate / 100.0)),
            'slip_id': self.payslip.id,
            'run_id': self.payslip.payslip_run_id.id if self.payslip.payslip_run_id else False,
            'concept_id': concepto.id,
            'formula': result.get('formula', ''),
            'detail_html': result.get('detail_html', ''),
        }

    def get_resumen(self):
        """
        Obtiene resumen de conceptos del contrato.

        Returns:
            dict con resumen
        """
        todos_conceptos = self.get_conceptos()
        computables = self.filtrar_conceptos_computables(todos_conceptos)

        devengos = 0
        deducciones = 0
        detalle = []

        for c in computables:
            rule = c.input_id
            es_deduccion = rule.dev_or_ded == 'deduccion' if rule else False
            monto = c.amount or 0

            if es_deduccion:
                deducciones += abs(monto)
            else:
                devengos += monto

            detalle.append({
                'id': c.id,
                'nombre': rule.name if rule else '',
                'codigo': rule.code if rule else '',
                'estado': c.state,
                'tipo_monto': c.amount_select,
                'monto': monto,
                'aplicar': c.aplicar,
                'modalidad': c.modality_value,
                'es_deduccion': es_deduccion,
                'vigente_desde': c.date_start,
                'vigente_hasta': c.date_end,
            })

        return {
            'total': len(todos_conceptos),
            'computables': len(computables),
            'total_devengos': devengos,
            'total_deducciones': deducciones,
            'por_tipo': self._agrupar_por_tipo(computables),
            'por_aplicacion': self._agrupar_por_aplicacion(computables),
            'detalle': detalle
        }

    def _agrupar_por_tipo(self, conceptos):
        """Agrupa conceptos por categoría de regla"""
        por_tipo = {}
        for c in conceptos:
            cat = c.input_id.category_id.code if c.input_id and c.input_id.category_id else 'OTRO'
            if cat not in por_tipo:
                por_tipo[cat] = 0
            por_tipo[cat] += 1
        return por_tipo

    def _agrupar_por_aplicacion(self, conceptos):
        """Agrupa conceptos por quincena de aplicación"""
        por_aplicacion = {
            '15': 0,  # Primera quincena
            '30': 0,  # Segunda quincena
            '0': 0,   # Siempre
        }
        for c in conceptos:
            aplicar = c.aplicar or '0'
            if aplicar in por_aplicacion:
                por_aplicacion[aplicar] += 1
        return por_aplicacion

    def get_conceptos_por_tipo(self, tipo_deduccion=None):
        """
        Obtiene conceptos filtrados por tipo de deducción.

        Args:
            tipo_deduccion: 'P' (Préstamo), 'A' (Ahorro), 'S' (Seguro),
                          'L' (Libranza), 'E' (Embargo), 'R' (Retención), 'O' (Otros)

        Returns:
            recordset filtrado
        """
        conceptos = self.filtrar_conceptos_computables()

        if tipo_deduccion:
            return conceptos.filtered(lambda c: c.type_deduction == tipo_deduccion)

        return conceptos

    def get_total_por_tipo(self, tipo_deduccion):
        """
        Obtiene el total de un tipo específico de deducción.

        Args:
            tipo_deduccion: Tipo de deducción a sumar

        Returns:
            float con el total
        """
        conceptos = self.get_conceptos_por_tipo(tipo_deduccion)
        return sum(c.amount or 0 for c in conceptos)
