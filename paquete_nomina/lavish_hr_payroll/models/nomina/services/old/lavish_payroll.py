# -*- coding: utf-8 -*-
"""
Lavish Payroll - Módulo principal de cómputo de nómina
Integración con flujo nativo de Odoo
"""

import logging
import time

_logger = logging.getLogger(__name__)


class LavishPayrollProcessor:
    """
    Procesador de nómina que integra los servicios con el flujo nativo.
    """

    def __init__(self, env, payslip_run=None, departamentos=None):
        """
        Args:
            env: Odoo environment
            payslip_run: hr.payslip.run record (opcional)
            departamentos: Lista de nombres de departamentos a filtrar
        """
        self.env = env
        self.payslip_run = payslip_run
        self.departamentos = departamentos or ['Administración', 'Financiera']
        self._dept_ids = None

    @property
    def dept_ids(self):
        """IDs de departamentos a procesar"""
        if self._dept_ids is None:
            depts = self.env['hr.department'].search([
                ('name', 'in', self.departamentos)
            ])
            self._dept_ids = depts.ids
            _logger.info("Departamentos encontrados: %s", depts.mapped('name'))
        return self._dept_ids

    def get_payslips_to_process(self, states=None):
        """
        Obtiene nóminas a procesar filtradas por departamento.

        Args:
            states: Lista de estados (default: ['draft'])

        Returns:
            recordset de hr.payslip
        """
        states = states or ['draft']

        if self.payslip_run:
            payslips = self.payslip_run.slip_ids
        else:
            payslips = self.env['hr.payslip'].search([('state', 'in', states)])

        # Filtrar por departamentos
        if self.dept_ids:
            payslips = payslips.filtered(
                lambda s: s.employee_id.department_id.id in self.dept_ids
            )

        return payslips.filtered(lambda s: s.state in states)

    def process_with_services(self, write_to_db=True):
        """
        Procesa nóminas usando los servicios (solo ausencias, préstamos, novedades, conceptos).

        Args:
            write_to_db: Si True, actualiza hr.leave.line

        Returns:
            dict con resultados
        """
        from .lavish_payroll_compute import LavishPayrollCompute

        payslips = self.get_payslips_to_process()
        total = len(payslips)

        _logger.info("=== PROCESANDO CON SERVICIOS ===")
        _logger.info("Departamentos: %s", self.departamentos)
        _logger.info("Nóminas a procesar: %d", total)

        results = {
            'total': total,
            'processed': 0,
            'errors': [],
            'details': [],
        }

        start_time = time.time()

        for i, payslip in enumerate(payslips, 1):
            _logger.info("[%d/%d] %s - %s", i, total, payslip.number or payslip.id, payslip.employee_id.name)

            try:
                compute = LavishPayrollCompute(self.env, payslip)
                compute.build_localdict()
                result = compute.compute_all(
                    recompute_ausencias=True,
                    write_ausencias_to_db=write_to_db
                )

                detail = {
                    'payslip_id': payslip.id,
                    'employee': payslip.employee_id.name,
                    'department': payslip.employee_id.department_id.name,
                    'ausencias_valor': compute.ausencias.get_ausencias()['total_valor'],
                    'prestamos_total': compute.prestamos.get_total_descuentos(),
                    'novedades_count': compute.novedades.get_resumen()['cantidad'],
                    'conceptos_count': compute.conceptos.get_resumen()['computables'],
                    'lineas_generadas': len(result['lineas']),
                }
                results['details'].append(detail)
                results['processed'] += 1

                _logger.info("  -> Ausencias: %.2f | Préstamos: %.2f | Novedades: %d | Conceptos: %d | Líneas: %d",
                           detail['ausencias_valor'], detail['prestamos_total'],
                           detail['novedades_count'], detail['conceptos_count'],
                           detail['lineas_generadas'])

            except Exception as e:
                _logger.error("  -> ERROR: %s", str(e))
                results['errors'].append({
                    'payslip_id': payslip.id,
                    'employee': payslip.employee_id.name,
                    'error': str(e)
                })

        results['elapsed'] = time.time() - start_time
        results['rate'] = results['processed'] / results['elapsed'] if results['elapsed'] > 0 else 0

        _logger.info("=== RESUMEN ===")
        _logger.info("Procesadas: %d/%d en %.2fs (%.2f/s)", results['processed'], total, results['elapsed'], results['rate'])
        _logger.info("Errores: %d", len(results['errors']))

        return results

    def process_native(self):
        """
        Procesa nóminas usando el flujo nativo compute_sheet().

        Returns:
            dict con resultados
        """
        payslips = self.get_payslips_to_process()
        total = len(payslips)

        _logger.info("=== PROCESANDO CON FLUJO NATIVO ===")
        _logger.info("Departamentos: %s", self.departamentos)
        _logger.info("Nóminas a procesar: %d", total)

        results = {
            'total': total,
            'processed': 0,
            'errors': [],
        }

        start_time = time.time()

        for i, payslip in enumerate(payslips, 1):
            _logger.info("[%d/%d] %s - %s", i, total, payslip.number or payslip.id, payslip.employee_id.name)

            try:
                payslip.compute_sheet()
                results['processed'] += 1
                _logger.info("  -> OK: %d líneas", len(payslip.line_ids))

            except Exception as e:
                _logger.error("  -> ERROR: %s", str(e))
                results['errors'].append({
                    'payslip_id': payslip.id,
                    'employee': payslip.employee_id.name,
                    'error': str(e)
                })

        results['elapsed'] = time.time() - start_time
        results['rate'] = results['processed'] / results['elapsed'] if results['elapsed'] > 0 else 0

        _logger.info("=== RESUMEN ===")
        _logger.info("Procesadas: %d/%d en %.2fs (%.2f/s)", results['processed'], total, results['elapsed'], results['rate'])

        return results

    def compare_results(self, payslip):
        """
        Compara resultados de servicios vs nativo para un payslip.

        Args:
            payslip: hr.payslip record

        Returns:
            dict con comparación
        """
        from .lavish_payroll_compute import LavishPayrollCompute

        _logger.info("=== COMPARANDO: %s ===", payslip.employee_id.name)

        # Valores actuales (nativo)
        native_lines = {l.code: l.total for l in payslip.line_ids}
        native_total = sum(native_lines.values())

        # Valores con servicios
        compute = LavishPayrollCompute(self.env, payslip)
        compute.build_localdict()
        result = compute.compute_all(recompute_ausencias=True, write_ausencias_to_db=False)

        service_lines = {k: v.get('total', 0) for k, v in result['lineas'].items()}
        service_total = sum(service_lines.values())

        # Comparar
        comparison = {
            'payslip_id': payslip.id,
            'employee': payslip.employee_id.name,
            'native': {
                'lines_count': len(native_lines),
                'total': native_total,
            },
            'services': {
                'lines_count': len(service_lines),
                'total': service_total,
            },
            'difference': service_total - native_total,
            'only_in_native': [],
            'only_in_services': [],
            'different_values': [],
        }

        # Líneas solo en nativo
        for code in native_lines:
            if code not in service_lines:
                comparison['only_in_native'].append({'code': code, 'value': native_lines[code]})

        # Líneas solo en servicios
        for code in service_lines:
            if code not in native_lines:
                comparison['only_in_services'].append({'code': code, 'value': service_lines[code]})

        # Líneas con valores diferentes
        for code in native_lines:
            if code in service_lines:
                diff = service_lines[code] - native_lines[code]
                if abs(diff) > 0.01:
                    comparison['different_values'].append({
                        'code': code,
                        'native': native_lines[code],
                        'service': service_lines[code],
                        'diff': diff
                    })

        _logger.info("Nativo: %d líneas, Total: %.2f", comparison['native']['lines_count'], comparison['native']['total'])
        _logger.info("Servicios: %d líneas, Total: %.2f", comparison['services']['lines_count'], comparison['services']['total'])
        _logger.info("Diferencia: %.2f", comparison['difference'])

        return comparison


# ═══════════════════════════════════════════════════════════════════════════════
# FUNCIONES DE CONVENIENCIA
# ═══════════════════════════════════════════════════════════════════════════════

def test_departamentos(env, run_id, departamentos=None):
    """
    Test rápido para departamentos específicos.

    Uso:
        from odoo.addons.lavish_hr_payroll.models.services.lavish_payroll import test_departamentos
        result = test_departamentos(env, 123, ['Administración', 'Financiera'])
    """
    departamentos = departamentos or ['Administración', 'Financiera']
    payslip_run = env['hr.payslip.run'].browse(run_id)

    if not payslip_run.exists():
        return {'error': f'Payslip Run {run_id} no encontrado'}

    processor = LavishPayrollProcessor(env, payslip_run, departamentos)
    return processor.process_with_services(write_to_db=False)


def test_nativo(env, run_id, departamentos=None):
    """
    Test con flujo nativo para departamentos específicos.

    Uso:
        from odoo.addons.lavish_hr_payroll.models.services.lavish_payroll import test_nativo
        result = test_nativo(env, 123, ['Administración', 'Financiera'])
    """
    departamentos = departamentos or ['Administración', 'Financiera']
    payslip_run = env['hr.payslip.run'].browse(run_id)

    if not payslip_run.exists():
        return {'error': f'Payslip Run {run_id} no encontrado'}

    processor = LavishPayrollProcessor(env, payslip_run, departamentos)
    return processor.process_native()


def comparar_payslip(env, payslip_id):
    """
    Compara resultado de servicios vs nativo para un payslip.

    Uso:
        from odoo.addons.lavish_hr_payroll.models.services.lavish_payroll import comparar_payslip
        result = comparar_payslip(env, 456)
    """
    payslip = env['hr.payslip'].browse(payslip_id)
    if not payslip.exists():
        return {'error': f'Payslip {payslip_id} no encontrado'}

    processor = LavishPayrollProcessor(env)
    return processor.compare_results(payslip)


def run_test(env, run_id, departamentos=None, write_to_db=False):
    """
    Ejecuta test completo.

    Uso:
        from odoo.addons.lavish_hr_payroll.models.services.lavish_payroll import run_test
        result = run_test(env, 123, ['Administración', 'Financiera'])
    """
    departamentos = departamentos or ['Administración', 'Financiera']
    payslip_run = env['hr.payslip.run'].browse(run_id)

    if not payslip_run.exists():
        return {'error': f'Payslip Run {run_id} no encontrado'}

    processor = LavishPayrollProcessor(env, payslip_run, departamentos)
    return processor.process_with_services(write_to_db=write_to_db)


# Mantener compatibilidad con funciones anteriores
def test_compute_departamento(env, payslip_run, departamento_name='Administración'):
    """Compatibilidad con versión anterior"""
    processor = LavishPayrollProcessor(env, payslip_run, [departamento_name])
    return processor.process_with_services(write_to_db=False)


def test_compute_single(env, payslip_id):
    """Test detallado para un solo payslip"""
    from .lavish_payroll_compute import LavishPayrollCompute

    payslip = env['hr.payslip'].browse(payslip_id)
    if not payslip.exists():
        return {'error': f'Payslip {payslip_id} no encontrado'}

    _logger.info("=== TEST SINGLE: %s - %s ===", payslip.number, payslip.employee_id.name)

    compute = LavishPayrollCompute(env, payslip)
    compute.build_localdict()

    _logger.info("Ausencias: %s", compute.ausencias.get_resumen())
    _logger.info("Préstamos: %s", compute.prestamos.get_resumen())
    _logger.info("Novedades: %s", compute.novedades.get_resumen())
    _logger.info("Conceptos: %s", compute.conceptos.get_resumen())

    result = compute.compute_all(recompute_ausencias=True, write_ausencias_to_db=False)

    _logger.info("Líneas generadas: %d", len(result['lineas']))
    _logger.info("Totales: %s", result['totales'])

    return {
        'payslip': payslip.id,
        'ausencias': compute.ausencias.get_resumen(),
        'prestamos': compute.prestamos.get_resumen(),
        'novedades': compute.novedades.get_resumen(),
        'conceptos': compute.conceptos.get_resumen(),
        'lineas': compute.lineas.get_resumen(),
    }


def test_recompute_ausencias(env, payslip_id):
    """Test de recompute de ausencias"""
    from .ausencias import AusenciaService

    payslip = env['hr.payslip'].browse(payslip_id)
    if not payslip.exists():
        return {'error': f'Payslip {payslip_id} no encontrado'}

    ausencias = AusenciaService(env, payslip)

    original = ausencias.get_ausencias(recompute=False)
    recomputed = ausencias.get_ausencias({'IBD': payslip.contract_id.wage}, recompute=True)

    return {
        'original_total': original['total_valor'],
        'recomputed_total': recomputed['total_valor'],
        'difference': recomputed['total_valor'] - original['total_valor'],
    }
