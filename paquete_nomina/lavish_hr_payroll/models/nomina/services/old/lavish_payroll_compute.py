# -*- coding: utf-8 -*-
"""
Lavish Payroll Compute - Orquestador principal del cálculo de nómina
Coordina todos los servicios para el procesamiento de nómina colombiana
"""

import logging
from datetime import date

from .ausencias import AusenciaService
from .prestamos import PrestamoService
from .novedades import NovedadService
from .conceptos import ConceptoService
from .lineas import LineaService

_logger = logging.getLogger(__name__)


class LavishPayrollCompute:
    """
    Orquestador principal del cálculo de nómina.
    Coordina los servicios de ausencias, préstamos, novedades, conceptos y líneas.
    """

    def __init__(self, env, payslip, batch_ctx=None):
        """
        Inicializa el orquestador con los servicios necesarios.

        Args:
            env: Odoo environment
            payslip: hr.payslip record
            batch_ctx: PayrollBatchContext opcional para procesamiento batch
        """
        self.env = env
        self.payslip = payslip
        self.batch_ctx = batch_ctx

        # Información básica
        self.employee = payslip.employee_id
        self.contract = payslip.contract_id
        self.date_from = payslip.date_from
        self.date_to = payslip.date_to

        # Tipo de proceso
        struct = payslip.struct_id
        self._struct_process = struct.process if struct and 'process' in struct._fields else 'nomina'

        # Inicializar servicios
        self.ausencias = AusenciaService(env, payslip, batch_ctx)
        self.prestamos = PrestamoService(env, payslip, batch_ctx)
        self.novedades = NovedadService(env, payslip, batch_ctx)
        self.conceptos = ConceptoService(env, payslip, batch_ctx)
        self.lineas = LineaService(env, payslip, batch_ctx)

        # Estado del cálculo
        self._localdict = None
        self._computed = False

    @property
    def struct_process(self):
        """Tipo de proceso de la estructura"""
        return self._struct_process

    def _get_annual_parameters(self):
        """
        Obtiene los parámetros anuales para el año del payslip.

        Returns:
            hr.annual.parameters record o False
        """
        year = self.date_to.year if self.date_to else self.date_from.year
        return self.env['hr.annual.parameters'].get_for_year(
            year,
            company_id=self.payslip.company_id.id,
            raise_if_not_found=True,
        )

    def build_localdict(self, base_localdict=None):
        """
        Construye el diccionario local para el cálculo.

        Args:
            base_localdict: Diccionario base opcional

        Returns:
            dict con el localdict completo
        """
        self._localdict = base_localdict.copy() if base_localdict else {}

        # Obtener parámetros anuales
        annual_params = self._get_annual_parameters()

        # Información básica
        self._localdict.update({
            'payslip': self.payslip,
            'employee': self.employee,
            'contract': self.contract,
            'company': self.payslip.company_id,
            'date_from': self.date_from,
            'date_to': self.date_to,
            'struct_process': self.struct_process,
            'annual_parameters': annual_params,
        })

        # Información de ausencias
        ausencias_info = self.ausencias.get_resumen()
        self._localdict['worked_days'] = ausencias_info['trabajados']
        self._localdict['ausencias'] = ausencias_info['ausencias_total']
        self._localdict['ausencias_no_pagadas'] = ausencias_info['ausencias_no_pagadas']
        self._localdict['dias_efectivos'] = ausencias_info['dias_efectivos']

        # Información de préstamos
        prestamos_info = self.prestamos.get_resumen()
        self._localdict['prestamos'] = prestamos_info

        # Información de novedades
        novedades_info = self.novedades.get_resumen()
        self._localdict['novedades'] = novedades_info

        # Información de conceptos
        conceptos_info = self.conceptos.get_resumen()
        self._localdict['conceptos'] = conceptos_info

        return self._localdict

    def compute_all(self, localdict=None, recompute_ausencias=True, write_ausencias_to_db=True):
        """
        Ejecuta el cálculo completo de nómina.

        Args:
            localdict: Diccionario local opcional
            recompute_ausencias: Si True, recalcula valores de ausencias con localdict
            write_ausencias_to_db: Si True, actualiza hr.leave.line en BD

        Returns:
            dict con resultados del cálculo
        """
        if localdict:
            self._localdict = localdict
        elif not self._localdict:
            self.build_localdict()

        # 1. Recomputar ausencias con localdict (actualiza hr.leave.line si write_ausencias_to_db=True)
        if recompute_ausencias:
            self.ausencias.recompute_all_leave_lines(self._localdict, write_to_db=write_ausencias_to_db)

        # 2. Procesar ausencias y generar líneas
        lineas_ausencias = self.ausencias.procesar_ausencias(self._localdict)
        self.lineas.agregar_lineas(lineas_ausencias)

        # 3. Procesar conceptos del contrato
        lineas_conceptos = self.conceptos.procesar_conceptos(self._localdict)
        self.lineas.agregar_lineas(lineas_conceptos)

        # 4. Procesar novedades
        lineas_novedades = self.novedades.procesar_novedades(self._localdict)
        self.lineas.agregar_lineas(lineas_novedades)

        # 5. Procesar préstamos
        lineas_prestamos = self.prestamos.procesar_prestamos(self._localdict)
        self.lineas.agregar_lineas(lineas_prestamos)

        # 6. Marcar cuotas de préstamos procesadas
        self.prestamos.marcar_cuotas_procesadas()

        self._computed = True

        return {
            'lineas': self.lineas.obtener_lineas(),
            'totales': self.lineas.calcular_totales(),
            'resumen': self.get_resumen()
        }

    def compute_conceptos(self, localdict=None):
        """
        Calcula solo los conceptos del contrato.

        Args:
            localdict: Diccionario local

        Returns:
            dict con líneas de conceptos
        """
        ld = localdict or self._localdict or {}
        return self.conceptos.procesar_conceptos(ld)

    def compute_novedades(self, localdict=None):
        """
        Calcula solo las novedades.

        Args:
            localdict: Diccionario local

        Returns:
            dict con líneas de novedades
        """
        ld = localdict or self._localdict or {}
        return self.novedades.procesar_novedades(ld)

    def compute_prestamos(self, localdict=None):
        """
        Calcula solo los préstamos.

        Args:
            localdict: Diccionario local

        Returns:
            dict con líneas de préstamos
        """
        ld = localdict or self._localdict or {}
        return self.prestamos.procesar_prestamos(ld)

    def compute_ausencias(self, salario_diario=0):
        """
        Calcula descuento por ausencias no pagadas.

        Args:
            salario_diario: Salario diario para cálculo

        Returns:
            dict con descuento por ausencias
        """
        return self.ausencias.calcular_descuento_ausencias(salario_diario)

    def get_dias_trabajados(self):
        """
        Obtiene información de días trabajados.

        Returns:
            dict con días y horas trabajadas
        """
        return self.ausencias.get_dias_trabajados()

    def get_dias_efectivos(self):
        """
        Obtiene días efectivos (trabajados - ausencias no pagadas).

        Returns:
            int con días efectivos
        """
        resumen = self.ausencias.get_resumen()
        return resumen['dias_efectivos']

    def get_lineas(self):
        """
        Obtiene las líneas calculadas.

        Returns:
            dict con líneas
        """
        return self.lineas.obtener_lineas()

    def get_totales(self):
        """
        Obtiene totales calculados.

        Returns:
            dict con totales por categoría
        """
        return self.lineas.calcular_totales()

    def get_resumen(self):
        """
        Obtiene resumen completo del cálculo.

        Returns:
            dict con resumen de todos los componentes
        """
        return {
            'payslip_id': self.payslip.id,
            'employee': self.employee.name,
            'contract': self.contract.name,
            'periodo': f"{self.date_from} - {self.date_to}",
            'tipo_proceso': self.struct_process,
            'ausencias': self.ausencias.get_resumen(),
            'prestamos': self.prestamos.get_resumen(),
            'novedades': self.novedades.get_resumen(),
            'conceptos': self.conceptos.get_resumen(),
            'lineas': self.lineas.get_resumen(),
            'computed': self._computed,
        }

    def preparar_lineas_db(self):
        """
        Prepara las líneas para insertar en base de datos.

        Returns:
            list de dicts listos para create()
        """
        return self.lineas.preparar_para_crear()

    def crear_lineas_db(self):
        """
        Crea las líneas en la base de datos.

        Returns:
            recordset de hr.payslip.line
        """
        return self.lineas.crear_lineas_db()


def compute_payslip(payslip, batch_ctx=None, localdict=None):
    """
    Función de conveniencia para calcular un payslip.

    Args:
        payslip: hr.payslip record
        batch_ctx: PayrollBatchContext opcional
        localdict: Diccionario local opcional

    Returns:
        dict con resultados del cálculo
    """
    compute = LavishPayrollCompute(payslip.env, payslip, batch_ctx)

    if localdict:
        compute._localdict = localdict
    else:
        compute.build_localdict()

    return compute.compute_all()


def process_batch(payslip_run, chunk_size=50, progress_callback=None):
    """
    Procesa un lote de nóminas.

    Args:
        payslip_run: hr.payslip.run record
        chunk_size: Tamaño del chunk para procesamiento
        progress_callback: Función callback para progreso (opcional)

    Returns:
        dict con estadísticas del procesamiento
    """
    payslips = payslip_run.slip_ids.filtered(lambda s: s.state == 'draft')
    total = len(payslips)

    if total == 0:
        return {'total': 0, 'processed': 0, 'errors': []}

    stats = {
        'total': total,
        'processed': 0,
        'errors': [],
        'by_status': {'success': 0, 'error': 0}
    }

    # Procesar en chunks
    for i in range(0, total, chunk_size):
        chunk = payslips[i:i + chunk_size]

        for payslip in chunk:
            try:
                result = compute_payslip(payslip)
                stats['processed'] += 1
                stats['by_status']['success'] += 1

                if progress_callback:
                    progress_callback(stats['processed'], total)

            except Exception as e:
                _logger.error("Error procesando payslip %s: %s", payslip.id, str(e))
                stats['errors'].append({
                    'payslip_id': payslip.id,
                    'employee': payslip.employee_id.name,
                    'error': str(e)
                })
                stats['by_status']['error'] += 1

    return stats
