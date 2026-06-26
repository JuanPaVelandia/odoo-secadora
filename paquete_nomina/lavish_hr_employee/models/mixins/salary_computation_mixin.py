# -*- coding: utf-8 -*-
"""
Mixin para cálculos de nómina y totalizaciones
Incluye decorador para registrar métodos de conceptos automáticamente
"""

from odoo import models, api, _
from odoo.exceptions import UserError
from decimal import Decimal, ROUND_HALF_UP
from functools import wraps
from typing import Tuple, List, Dict, Any, Callable, Optional
from ...utils.constants import DAYS_MONTH, PRECISION_TECHNICAL

# ============================================
# DECORADOR PARA CONCEPTOS
# ============================================

# Registro global de conceptos
CONCEPT_REGISTRY = {}


def concept_method(
    code: str,
    name: str,
    report_type: Optional[str] = None,
    category: Optional[str] = None
):
    """
    Decorador para registrar métodos de conceptos de nómina

    Args:
        code: Código del concepto (ej: 'BASIC', 'AUX000')
        name: Nombre descriptivo del concepto
        report_type: Tipo de reporte ('basic', 'ssocial', 'provision', etc.)
        category: Categoría del concepto para totalizaciones

    Usage:
        @concept_method('BASIC', 'Sueldo Básico', report_type='basic')
        def _basic(self, localdict):
            ...
            return rate, qty, percentage, name_override, html_log, data
    """
    def decorator(func: Callable) -> Callable:
        # Registrar el concepto
        CONCEPT_REGISTRY[code] = {
            'name': name,
            'method': func.__name__,
            'report_type': report_type,
            'category': category,
        }

        @wraps(func)
        def wrapper(self, localdict):
            try:
                return func(self, localdict)
            except Exception as e:
                # Manejo centralizado de errores
                self._raise_concept_error(localdict, code, name, e)

        # Marcar el método como concepto registrado
        wrapper._is_concept = True
        wrapper._concept_code = code
        wrapper._concept_name = name

        return wrapper

    return decorator


class PayrollComputationMixin(models.AbstractModel):
    """
    Mixin abstracto para cálculos de nómina
    Proporciona métodos de totalización, redondeo y helpers matemáticos
    """
    _name = 'payroll.computation.mixin'
    _description = 'Mixin para Cálculos de Nómina'

    # ============================================
    # MANEJO DE ERRORES
    # ============================================

    def _raise_concept_error(self, localdict, code: str, name: str, exception: Exception):
        """
        Levanta error formateado para conceptos

        Args:
            localdict: Diccionario local del cálculo
            code: Código del concepto
            name: Nombre del concepto
            exception: Excepción original
        """
        self.ensure_one()
        payslip = localdict.get('slip')
        employee = localdict.get('employee')

        error_msg = _(
            "Error en concepto %(code)s - %(name)s\n"
            "Empleado: %(employee)s\n"
            "Nómina: %(payslip)s\n"
            "Error: %(error)s"
        ) % {
            'code': code,
            'name': name,
            'employee': employee.name if employee else 'N/A',
            'payslip': payslip.name if payslip else 'N/A',
            'error': str(exception)
        }

        raise UserError(error_msg) from exception

    # ============================================
    # MÉTODOS DE REDONDEO
    # ============================================

    def _round_value(self, value: float, method: str = 'no_round') -> float:
        """
        Redondea valor según método especificado

        Args:
            value: Valor a redondear
            method: Método ('no_round', 'round1', 'round100', 'round1000', 'round2d')

        Returns:
            Valor redondeado
        """
        if method == 'no_round':
            return value
        elif method == 'round1':
            return round(value)
        elif method == 'round100':
            return round(value / 100) * 100
        elif method == 'round1000':
            return round(value / 1000) * 1000
        elif method == 'round2d':
            return round(value, 2)

        return value

    def _decimal_round(self, value: Decimal, places: int = 2) -> Decimal:
        """
        Redondea Decimal con precisión específica

        Args:
            value: Valor Decimal
            places: Decimales a mantener

        Returns:
            Decimal redondeado
        """
        if places == 0:
            return value.quantize(Decimal('1'), rounding=ROUND_HALF_UP)

        quantizer = Decimal(10) ** -places
        return value.quantize(quantizer, rounding=ROUND_HALF_UP)

    # ============================================
    # TOTALIZACIONES
    # ============================================

    def _get_totalizar_categorias(
        self,
        localdict: Dict,
        categorias: Optional[List[str]] = None,
        categorias_excluir: Optional[List[str]] = None,
        incluir_current: bool = True,
        incluir_before: bool = False,
        incluir_multi: bool = False
    ) -> Tuple[float, float]:
        """
        Totaliza conceptos por categorías

        Args:
            localdict: Diccionario local con datos de nómina
            categorias: Lista de códigos de categorías a incluir
            categorias_excluir: Lista de códigos de categorías a excluir
            incluir_current: Incluir líneas de la nómina actual
            incluir_before: Incluir líneas de nóminas anteriores del periodo
            incluir_multi: Incluir múltiples valores

        Returns:
            Tuple (total_amount, total_quantity)
        """
        payslip = localdict.get('slip')
        if not payslip:
            return 0.0, 0.0

        total_amount = 0.0
        total_qty = 0.0

        # Obtener líneas según filtros
        lines = []

        if incluir_current:
            lines.extend(payslip.line_ids)

        if incluir_before:
            # Buscar nóminas anteriores del mismo periodo
            previous_slips = self.env['hr.payslip'].search([
                ('employee_id', '=', payslip.employee_id.id),
                ('date_from', '>=', payslip.date_from),
                ('date_to', '<=', payslip.date_to),
                ('id', '!=', payslip.id),
                ('state', 'in', ['done', 'paid'])
            ])
            for slip in previous_slips:
                lines.extend(slip.line_ids)

        # Filtrar por categorías
        for line in lines:
            if not line.salary_rule_id:
                continue

            rule = line.salary_rule_id
            category_code = rule.category_id.code if rule.category_id else ''

            # Verificar inclusión
            if categorias and category_code not in categorias:
                continue

            # Verificar exclusión
            if categorias_excluir:
                if isinstance(categorias_excluir, str):
                    categorias_excluir = [categorias_excluir]
                if category_code in categorias_excluir:
                    continue

            total_amount += line.total
            total_qty += line.quantity

        return total_amount, total_qty

    def _get_total_by_codes(
        self,
        localdict: Dict,
        codes: List[str],
        incluir_current: bool = True
    ) -> float:
        """
        Totaliza conceptos por códigos de regla

        Args:
            localdict: Diccionario local
            codes: Lista de códigos de reglas salariales
            incluir_current: Incluir líneas de la nómina actual

        Returns:
            Total acumulado
        """
        payslip = localdict.get('slip')
        if not payslip:
            return 0.0

        lines = payslip.line_ids if incluir_current else []
        total = sum(
            line.total
            for line in lines
            if line.salary_rule_id and line.salary_rule_id.code in codes
        )

        return total

    # ============================================
    # CÁLCULOS DE BASE SALARIAL
    # ============================================

    def _calcular_base_prestacional(
        self,
        localdict: Dict,
        incluir_auxilios: bool = True,
        incluir_prima: bool = False
    ) -> Tuple[Decimal, List[str]]:
        """
        Calcula la base prestacional (para cesantías, prima, etc.)

        Args:
            localdict: Diccionario local
            incluir_auxilios: Incluir auxilio de transporte
            incluir_prima: Incluir prima como parte de la base

        Returns:
            Tuple (base_decimal, pasos_calculo)
        """
        contract = localdict['contract']
        pasos = []

        # Base salarial
        base = Decimal(str(contract.wage))
        pasos.append(f"Salario base: {float(base):.2f}")

        # Devengos salariales
        total_dev, _ = self._get_totalizar_categorias(
            localdict,
            categorias=['DEV_SALARIAL'],
            incluir_current=True
        )

        if total_dev > 0:
            base += Decimal(str(total_dev))
            pasos.append(f"+ Devengos salariales: {total_dev:.2f}")

        # Auxilio de transporte
        if incluir_auxilios:
            total_aux, _ = self._get_totalizar_categorias(
                localdict,
                categorias=['AUX_TRANS'],
                incluir_current=True
            )
            if total_aux > 0:
                base += Decimal(str(total_aux))
                pasos.append(f"+ Auxilio de transporte: {total_aux:.2f}")

        # Prima (para intereses de cesantías)
        if incluir_prima:
            total_prima, _ = self._get_totalizar_categorias(
                localdict,
                categorias=['PRIMA'],
                incluir_current=True
            )
            if total_prima > 0:
                base += Decimal(str(total_prima))
                pasos.append(f"+ Prima: {total_prima:.2f}")

        pasos.append(f"Base total: {float(base):.2f}")

        return base, pasos

    # ============================================
    # CÁLCULOS DE DÍAS
    # ============================================

    def _calcular_dias_trabajados(
        self,
        localdict: Dict,
        descontar_ausencias: bool = True
    ) -> Tuple[Decimal, List[str]]:
        """
        Calcula días trabajados efectivos

        Args:
            localdict: Diccionario local
            descontar_ausencias: Si descontar ausencias no remuneradas

        Returns:
            Tuple (dias_decimal, pasos_calculo)
        """
        worked_days = localdict.get('worked_days', {})
        pasos = []

        # Días base (ODOO 18: worked_days es dict de recordsets)
        work100 = worked_days.get('WORK100')
        dias_base = Decimal(str(work100.number_of_days if work100 else 0))
        pasos.append(f"Días base: {float(dias_base):.2f}")

        if descontar_ausencias:
            # Descontar ausencias (ODOO 18: iterar sobre items del dict)
            ausencias = sum(
                Decimal(str(wd.number_of_days))
                for code, wd in worked_days.items()
                if code.startswith('LEAVE') and wd
            )

            if ausencias > 0:
                dias_base -= ausencias
                pasos.append(f"- Ausencias: {float(ausencias):.2f}")

        pasos.append(f"Total días trabajados: {float(dias_base):.2f}")

        return dias_base, pasos

    def _calcular_valor_diario(self, salario_mensual: float) -> Decimal:
        """
        Calcula valor diario desde salario mensual

        Args:
            salario_mensual: Salario mensual

        Returns:
            Valor diario como Decimal
        """
        return Decimal(str(salario_mensual)) / Decimal(str(DAYS_MONTH))

    # ============================================
    # PROYECCIONES SALARIALES
    # ============================================

    def _proyectar_salario_mes(
        self,
        localdict: Dict,
        dias_trabajados: Decimal
    ) -> Tuple[Decimal, List[str]]:
        """
        Proyecta salario del mes completo desde días trabajados

        Args:
            localdict: Diccionario local
            dias_trabajados: Días trabajados hasta ahora

        Returns:
            Tuple (salario_proyectado, pasos)
        """
        contract = localdict['contract']
        pasos = []

        # Valor diario
        valor_diario = self._calcular_valor_diario(contract.wage)
        pasos.append(f"Valor diario: {float(valor_diario):.2f}")

        # Días faltantes
        dias_faltantes = Decimal(str(DAYS_MONTH)) - dias_trabajados
        pasos.append(f"Días faltantes: {float(dias_faltantes):.2f}")

        # Proyección
        proyeccion = valor_diario * Decimal(str(DAYS_MONTH))
        pasos.append(f"Proyección mes: {float(proyeccion):.2f}")

        return proyeccion, pasos

    # ============================================
    # VALIDACIONES
    # ============================================

    def _validar_contrato_activo(self, contract, fecha) -> bool:
        """Valida si contrato está activo en fecha"""
        if not contract:
            return False

        if contract.date_start and contract.date_start > fecha:
            return False

        if contract.date_end and contract.date_end < fecha:
            return False

        return contract.state == 'open'

    def _validar_tope_smmlv(
        self,
        valor: Decimal,
        parametros_anuales,
        multiplicador: int = 2
    ) -> Tuple[bool, str]:
        """
        Valida si un valor supera tope en SMMLV

        Args:
            valor: Valor a validar
            parametros_anuales: Registro de parámetros anuales
            multiplicador: Multiplicador de SMMLV (2 para aux transporte, etc.)

        Returns:
            Tuple (supera_tope, mensaje)
        """
        tope = Decimal(str(parametros_anuales.smmlv_monthly)) * Decimal(str(multiplicador))
        supera = valor > tope

        mensaje = (
            f"Valor {float(valor):.2f} supera tope de {multiplicador} SMMLV ({float(tope):.2f})"
            if supera
            else f"Valor {float(valor):.2f} no supera tope"
        )

        return supera, mensaje
