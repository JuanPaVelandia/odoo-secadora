# -*- coding: utf-8 -*-
"""
PRESTACIONES - CONSTRUCTOR DE AJUSTES DE LIQUIDACIÓN
====================================================
Clase constructora para calcular ajustes de liquidación de prestaciones.

Responsabilidades:
- Calcular monto adeudado
- Cargar provisiones y pagos acumulados
- Calcular ajuste (adeudado - acumulado)
- Construir resultado con detalle completo
"""
from datetime import date
import logging

_logger = logging.getLogger(__name__)


class PrestacionAdjustmentBuilder:
    """
    Constructor para calcular ajustes de liquidación de prestaciones.

    Flujo:
    1. calculate_total_owed() - Calcula total adeudado
    2. load_accumulated() - Carga provisiones y pagos
    3. compute_adjustment() - Calcula ajuste
    4. build_result() - Construye resultado final
    """

    DIVISOR_MAP = {
        'prima': 180,
        'cesantias': 360,
        'intereses': 360,
        'vacaciones': 720,
    }

    def __init__(self, env, localdict, tipo_prestacion, context):
        """
        Inicializa el constructor.

        Args:
            env: Odoo environment
            localdict: Diccionario de contexto (slip, contract, etc.)
            tipo_prestacion: 'prima', 'cesantias', 'intereses', 'vacaciones'
            context: 'liquidacion' | 'pago'
        """
        self.env = env
        self.localdict = localdict
        self.tipo_prestacion = tipo_prestacion
        self.context = context

        self.slip = localdict['slip']
        self.contract = localdict['contract']

        # Resultados del cálculo
        self.prestacion_result = None
        self.monto_adeudado = 0.0
        self.acumulados = None
        self.ajuste = 0.0

    def calculate_total_owed(self):
        """
        Paso 1: Calcula el total adeudado de la prestación.

        Returns:
            self (fluent interface)
        """
        prestaciones_service = self.env['hr.salary.rule.prestaciones']
        self.prestacion_result = prestaciones_service.calculate_prestacion(
            self.localdict,
            self.tipo_prestacion,
            context=self.context,
            provision_type='simple'
        )

        if not self.prestacion_result or len(self.prestacion_result) < 6:
            raise ValueError(f"Error calculando {self.tipo_prestacion}")

        base_diaria, dias, porcentaje, nombre, log, detail = self.prestacion_result

        # Extraer monto adeudado del detalle
        if isinstance(detail, dict):
            self.monto_adeudado = detail.get('metricas', {}).get('valor_total', 0)
            if not self.monto_adeudado and base_diaria and dias:
                divisor = self.DIVISOR_MAP.get(self.tipo_prestacion, 360)
                self.monto_adeudado = (base_diaria * 30 * dias) / divisor
        else:
            self.monto_adeudado = (base_diaria * dias * porcentaje) / 100 if porcentaje else 0

        return self

    def load_accumulated(self):
        """
        Paso 2: Carga provisiones y pagos acumulados del período.

        Returns:
            self (fluent interface)
        """
        if self.context != 'liquidacion':
            # Si no es liquidación, no hay acumulados
            self.acumulados = {
                'total': 0,
                'provisiones': {'total': 0, 'detalle': []},
                'pagos': {'total': 0, 'detalle': []},
            }
            return self

        loader = self.env['hr.salary.rule.prestaciones.provision.loader']
        date_from, date_to = self._get_period()

        self.acumulados = loader.load_total_accumulated(
            self.contract.id,
            self.tipo_prestacion,
            date_from,
            date_to,
            exclude_slip_id=self.slip.id
        )

        return self

    def compute_adjustment(self):
        """
        Paso 3: Calcula el ajuste (adeudado - acumulado).

        Returns:
            self (fluent interface)
        """
        total_acumulado = self.acumulados['total']
        self.ajuste = self.monto_adeudado - total_acumulado
        return self

    def build_result(self):
        """
        Paso 4: Construye el resultado final para hr.payslip.

        Returns:
            tuple: (amount, qty, rate, name, log, data)
        """
        if not self.prestacion_result:
            return (0, 0, 0, 'Error', '', {'aplica': False})

        base_diaria, dias, porcentaje, nombre, log, detail = self.prestacion_result

        # Si ajuste es negativo o cero, ya se pagó todo
        if self.ajuste <= 0 and self.context == 'liquidacion':
            return self._build_already_paid_result(nombre, log)

        # Si NO es liquidación, retornar resultado original
        if self.context != 'liquidacion':
            return self._adapt_original_result()

        # Construir resultado con ajuste
        return self._build_adjusted_result(base_diaria, dias, porcentaje, nombre, log, detail)

    # =========================================================================
    # MÉTODOS AUXILIARES PRIVADOS
    # =========================================================================

    def _get_period(self):
        """
        Obtiene el período de consulta según el tipo de prestación.

        Returns:
            tuple: (date_from, date_to)
        """
        if self.tipo_prestacion == 'prima':
            # Semestre actual
            if self.slip.date_to.month <= 6:
                return (date(self.slip.date_to.year, 1, 1), date(self.slip.date_to.year, 6, 30))
            else:
                return (date(self.slip.date_to.year, 7, 1), date(self.slip.date_to.year, 12, 31))

        elif self.tipo_prestacion in ('cesantias', 'intereses'):
            # Año actual
            return (date(self.slip.date_to.year, 1, 1), self.slip.date_to)

        elif self.tipo_prestacion == 'vacaciones':
            # Desde inicio o última fecha de corte
            date_from = self.contract.date_vacaciones or self.contract.date_start
            return (date_from, self.slip.date_to)

        else:
            # Default: año actual
            return (date(self.slip.date_to.year, 1, 1), self.slip.date_to)

    def _build_already_paid_result(self, nombre, log):
        """
        Construye resultado cuando ya se pagó/provisionó todo.

        Returns:
            tuple: Resultado con valores en cero
        """
        return (0, 0, 0, f'{nombre} - Ya liquidado', log, {
            'aplica': False,
            'motivo': f'{self.tipo_prestacion.upper()} ya liquidada',
            'monto_adeudado': self.monto_adeudado,
            'total_provisionado': self.acumulados['provisiones']['total'],
            'total_pagado': self.acumulados['pagos']['total'],
            'total_acumulado': self.acumulados['total'],
            'ajuste': self.ajuste,
            'detalle_provisiones': self.acumulados['provisiones']['detalle'],
            'detalle_pagos': self.acumulados['pagos']['detalle'],
        })

    def _adapt_original_result(self):
        """
        Adapta resultado original sin ajuste (para pagos normales).

        Returns:
            tuple: Resultado adaptado
        """
        base_diaria, dias, porcentaje, nombre, log, detail = self.prestacion_result
        return self._adapt_to_slip_format(base_diaria, dias, porcentaje, nombre, log, detail)

    def _build_adjusted_result(self, base_diaria, dias, porcentaje, nombre, log, detail):
        """
        Construye resultado con ajuste aplicado.

        Args:
            base_diaria, dias, porcentaje, nombre, log, detail: Componentes del resultado

        Returns:
            tuple: Resultado ajustado
        """
        # Enriquecer detalle con información de ajuste
        if isinstance(detail, dict):
            detail['monto_adeudado'] = self.monto_adeudado
            detail['total_provisionado'] = self.acumulados['provisiones']['total']
            detail['total_pagado'] = self.acumulados['pagos']['total']
            detail['total_acumulado'] = self.acumulados['total']
            detail['ajuste'] = self.ajuste
            detail['tiene_ajuste'] = True
            detail['detalle_provisiones'] = self.acumulados['provisiones']['detalle']
            detail['detalle_pagos'] = self.acumulados['pagos']['detalle']

            # Actualizar métricas
            if 'metricas' in detail:
                detail['metricas']['valor_original'] = self.monto_adeudado
                detail['metricas']['valor_total'] = self.ajuste

        # Ajustar base para que el total sea el ajuste
        divisor = self.DIVISOR_MAP.get(self.tipo_prestacion, 360)
        if dias > 0:
            base_ajustada = (self.ajuste * divisor) / (30 * dias)
        else:
            base_ajustada = 0

        return self._adapt_to_slip_format(base_ajustada, dias, porcentaje, nombre, log, detail)

    def _adapt_to_slip_format(self, base_diaria, dias, porcentaje, nombre, log, detail):
        """
        Adapta resultado al formato esperado por hr.payslip.

        Returns:
            tuple: (amount, qty, rate, name, log, data)
        """
        # Calcular monto total
        if isinstance(detail, dict):
            monto_total = detail.get('metricas', {}).get('valor_total', 0)
            if not monto_total and base_diaria and dias:
                divisor = self.DIVISOR_MAP.get(self.tipo_prestacion, 360)
                monto_total = (base_diaria * 30 * dias) / divisor
        else:
            monto_total = (base_diaria * dias * porcentaje) / 100 if porcentaje else 0

        # Obtener fechas del periodo
        if isinstance(detail, dict):
            fecha_inicio = detail.get('periodo', {}).get('fecha_inicio')
            fecha_fin = detail.get('periodo', {}).get('fecha_fin')
        else:
            fecha_inicio = self.slip.date_from.isoformat() if self.slip.date_from else None
            fecha_fin = self.slip.date_to.isoformat() if self.slip.date_to else None

        # Construir data
        data = {
            'monto_total': monto_total,
            'fecha_inicio': fecha_inicio,
            'fecha_fin': fecha_fin,
            'data_kpi': {
                'base_diaria': base_diaria,
                'base_mensual': base_diaria * 30 if base_diaria else 0,
                'days_worked': dias,
                'tipo_prestacion': self.tipo_prestacion,
            },
            'aplica': detail.get('aplica', True) if isinstance(detail, dict) else True,
            'detail': detail,
        }

        # Agregar acumulados si existen
        if isinstance(detail, dict):
            if 'acum_line_ids' in detail:
                data['acum_line_ids'] = detail['acum_line_ids']
            if 'source_rule_ids' in detail:
                data['source_rule_ids'] = detail['source_rule_ids']

        return (base_diaria * 30 if base_diaria else 0, dias, porcentaje, nombre, log, data)
