# -*- coding: utf-8 -*-
"""
Servicio de Promedio Ponderado - Cálculo de base para prestaciones con cambios de salario

Legislación Colombiana:
- Cuando hay cambios de salario durante el año, se calcula promedio ponderado
- Fórmula: Σ(salario_i × días_i) / total_días
- Se incluye auxilio de transporte si el salario es menor a 2 SMMLV
- Se incluye promedio de horas extras de últimos 3 meses
"""

import logging
from datetime import date
from dateutil.relativedelta import relativedelta

_logger = logging.getLogger(__name__)


class PromedioService:
    """
    Servicio para calcular promedios ponderados de salario.

    Maneja:
    - Historial de cambios de salario
    - Promedio ponderado para cesantías, prima, etc.
    - Inclusión de auxilio de transporte según nivel salarial
    - Promedio de horas extras
    """

    def __init__(self, env, employee_id, contract_id=None):
        self.env = env
        self.employee_id = employee_id
        self.contract_id = contract_id
        self._historial_cache = None

    def get_historial_salarios(self, fecha_inicio, fecha_fin):
        """
        Obtiene historial de salarios del empleado en el período.

        Args:
            fecha_inicio: Fecha inicio del período
            fecha_fin: Fecha fin del período

        Returns:
            Lista de dicts con fecha_inicio, fecha_fin, salario, auxilio
        """
        # Buscar en hr.contract.change o usar el contrato actual
        ContractChange = self.env.get('hr.contract.change')

        if ContractChange:
            # Si existe modelo de cambios de contrato
            changes = ContractChange.search([
                ('employee_id', '=', self.employee_id),
                ('date', '>=', fecha_inicio),
                ('date', '<=', fecha_fin),
            ], order='date')

            if changes:
                return self._build_historial_from_changes(changes, fecha_inicio, fecha_fin)

        # Si no hay historial, usar contrato actual
        contract = self.env['hr.contract'].browse(self.contract_id)
        if not contract:
            contract = self.env['hr.contract'].search([
                ('employee_id', '=', self.employee_id),
                ('state', '=', 'open')
            ], limit=1)

        if not contract:
            return []

        # Obtener SMMLV para determinar si aplica auxilio
        smmlv = self._get_smmlv(fecha_fin)
        aplica_auxilio = contract.wage < (2 * smmlv)

        return [{
            'fecha_inicio': max(fecha_inicio, contract.date_start or fecha_inicio),
            'fecha_fin': min(fecha_fin, contract.date_end or fecha_fin),
            'salario': contract.wage,
            'auxilio': self._get_auxilio(fecha_fin) if aplica_auxilio else 0,
            'contract_id': contract.id
        }]

    def _build_historial_from_changes(self, changes, fecha_inicio, fecha_fin):
        """Construye historial desde registros de cambios"""
        historial = []
        prev_date = fecha_inicio
        prev_salario = None
        prev_auxilio = 0

        for change in changes:
            if prev_salario is not None and change.date > prev_date:
                historial.append({
                    'fecha_inicio': prev_date,
                    'fecha_fin': change.date - relativedelta(days=1),
                    'salario': prev_salario,
                    'auxilio': prev_auxilio
                })

            prev_date = change.date
            prev_salario = change.wage_new or change.wage
            smmlv = self._get_smmlv(change.date)
            prev_auxilio = self._get_auxilio(change.date) if prev_salario < (2 * smmlv) else 0

        # Último período
        if prev_salario is not None:
            historial.append({
                'fecha_inicio': prev_date,
                'fecha_fin': fecha_fin,
                'salario': prev_salario,
                'auxilio': prev_auxilio
            })

        return historial

    def _get_smmlv(self, fecha):
        """Obtiene SMMLV vigente para la fecha"""
        AnualParameter = self.env.get('hr.annual.parameters')
        if AnualParameter:
            param = AnualParameter.search([
                ('year', '=', fecha.year)
            ], limit=1)
            if param:
                return param.smmlv or 1423500  # Default 2025

        # Defaults por año
        smmlv_por_ano = {
            2024: 1300000,
            2025: 1423500,
        }
        return smmlv_por_ano.get(fecha.year, 1423500)

    def _get_auxilio(self, fecha):
        """Obtiene auxilio de transporte vigente para la fecha"""
        AnualParameter = self.env.get('hr.annual.parameters')
        if AnualParameter:
            param = AnualParameter.search([
                ('year', '=', fecha.year)
            ], limit=1)
            if param:
                return param.transportation_assistance_value or 200000

        # Defaults por año
        auxilio_por_ano = {
            2024: 162000,
            2025: 200000,
        }
        return auxilio_por_ano.get(fecha.year, 200000)

    def calcular_promedio_ponderado(self, fecha_inicio, fecha_fin, incluir_extras=True):
        """
        Calcula promedio ponderado de salarios en el período.

        Args:
            fecha_inicio: Fecha inicio
            fecha_fin: Fecha fin
            incluir_extras: Si incluir promedio de horas extras

        Returns:
            dict con promedio, detalle, extras_promedio
        """
        historial = self.get_historial_salarios(fecha_inicio, fecha_fin)

        if not historial:
            return {
                'promedio': 0,
                'promedio_sin_auxilio': 0,
                'total_dias': 0,
                'detalle': [],
                'extras_promedio': 0
            }

        total_ponderado = 0
        total_ponderado_sin_auxilio = 0
        total_dias = 0
        detalle = []

        for periodo in historial:
            dias = self._dias_entre_fechas(periodo['fecha_inicio'], periodo['fecha_fin'])
            base = periodo['salario'] + periodo.get('auxilio', 0)
            ponderado = base * dias
            ponderado_sin_aux = periodo['salario'] * dias

            detalle.append({
                'fecha_inicio': periodo['fecha_inicio'],
                'fecha_fin': periodo['fecha_fin'],
                'dias': dias,
                'salario': periodo['salario'],
                'auxilio': periodo.get('auxilio', 0),
                'base': base,
                'ponderado': ponderado
            })

            total_ponderado += ponderado
            total_ponderado_sin_auxilio += ponderado_sin_aux
            total_dias += dias

        promedio = round(total_ponderado / total_dias, 0) if total_dias > 0 else 0
        promedio_sin_aux = round(total_ponderado_sin_auxilio / total_dias, 0) if total_dias > 0 else 0

        # Calcular promedio de horas extras si aplica
        extras_promedio = 0
        if incluir_extras:
            extras_promedio = self._calcular_promedio_extras(fecha_inicio, fecha_fin)

        return {
            'promedio': promedio,
            'promedio_sin_auxilio': promedio_sin_aux,
            'promedio_con_extras': promedio + extras_promedio,
            'total_dias': total_dias,
            'total_ponderado': total_ponderado,
            'detalle': detalle,
            'extras_promedio': extras_promedio
        }

    def _calcular_promedio_extras(self, fecha_inicio, fecha_fin):
        """
        Calcula promedio de horas extras para base de prestaciones.

        Regla: últimos 3 meses (o meses trabajados si < 3)
        """
        # Calcular meses en el período
        delta = relativedelta(fecha_fin, fecha_inicio)
        meses_periodo = delta.years * 12 + delta.months
        if delta.days > 0:
            meses_periodo += 1

        # Máximo 3 meses para promedio
        meses_promedio = min(meses_periodo, 3)

        if meses_promedio <= 0:
            return 0

        # Buscar horas extras de los últimos 3 meses
        fecha_desde_extras = fecha_fin - relativedelta(months=meses_promedio)
        if fecha_desde_extras < fecha_inicio:
            fecha_desde_extras = fecha_inicio

        HrOvertime = self.env.get('hr.overtime')
        if not HrOvertime:
            return 0

        extras = HrOvertime.search([
            ('employee_id', '=', self.employee_id),
            ('date', '>=', fecha_desde_extras),
            ('date_end', '<=', fecha_fin),
            ('state', '!=', 'revertido'),
        ])

        if not extras:
            return 0

        # Calcular valor total de extras
        contract = self.env['hr.contract'].browse(self.contract_id)
        if not contract:
            contract = self.env['hr.contract'].search([
                ('employee_id', '=', self.employee_id),
                ('state', '=', 'open')
            ], limit=1)

        salario = contract.wage if contract else 0
        valor_hora = salario / 240 if salario else 0

        FACTORES = {
            'overtime_rn': 0.35,
            'overtime_ext_d': 1.25,
            'overtime_ext_n': 1.75,
            'overtime_eddf': 2.00,
            'overtime_endf': 2.50,
            'overtime_dof': 1.75,
            'overtime_rndf': 1.10,
            'overtime_rdf': 0.75,
            'overtime_rnf': 2.10,
        }

        total_extras = 0
        for tipo, factor in FACTORES.items():
            cantidad = sum(getattr(he, tipo, 0) or 0 for he in extras)
            if cantidad > 0:
                total_extras += round(valor_hora * factor * cantidad, 0)

        # Si es el mismo mes, no promediar
        if meses_periodo <= 1:
            return total_extras

        # Promediar sobre los meses
        return round(total_extras / meses_promedio, 0)

    def _dias_entre_fechas(self, fecha_inicio, fecha_fin):
        """Calcula días calendario entre dos fechas (inclusivo)"""
        return (fecha_fin - fecha_inicio).days + 1

    def calcular_dias_comerciales(self, dias_calendario):
        """
        Convierte días calendario a días comerciales (año 360).

        Args:
            dias_calendario: Días calendario

        Returns:
            Días comerciales aproximados
        """
        # Factor: 360/365.25 ≈ 0.9856
        return round(dias_calendario * 360 / 365.25, 0)

    def get_base_cesantias(self, fecha_inicio, fecha_fin):
        """
        Obtiene base para cálculo de cesantías.

        Returns:
            dict con base y días comerciales
        """
        promedio = self.calcular_promedio_ponderado(fecha_inicio, fecha_fin, incluir_extras=True)
        dias_comerciales = self.calcular_dias_comerciales(promedio['total_dias'])

        return {
            'base': promedio['promedio_con_extras'],
            'dias': dias_comerciales,
            'cesantias': round(promedio['promedio_con_extras'] * dias_comerciales / 360, 0),
            'detalle': promedio
        }

    def get_base_prima(self, fecha_inicio, fecha_fin):
        """
        Obtiene base para cálculo de prima.

        Returns:
            dict con base y días del semestre
        """
        promedio = self.calcular_promedio_ponderado(fecha_inicio, fecha_fin, incluir_extras=True)
        dias_comerciales = self.calcular_dias_comerciales(promedio['total_dias'])

        return {
            'base': promedio['promedio_con_extras'],
            'dias': dias_comerciales,
            'prima': round(promedio['promedio_con_extras'] * dias_comerciales / 360, 0),
            'detalle': promedio
        }

    def get_base_vacaciones(self, fecha_inicio, fecha_fin):
        """
        Obtiene base para cálculo de vacaciones.
        NOTA: Vacaciones NO incluye auxilio ni extras, solo salario.

        Returns:
            dict con base y días
        """
        promedio = self.calcular_promedio_ponderado(fecha_inicio, fecha_fin, incluir_extras=False)
        dias_comerciales = self.calcular_dias_comerciales(promedio['total_dias'])

        return {
            'base': promedio['promedio_sin_auxilio'],
            'dias': dias_comerciales,
            'vacaciones': round(promedio['promedio_sin_auxilio'] * dias_comerciales / 360 * 15 / 30, 0),
            'detalle': promedio
        }

    # =========================================================================
    # MÉTODOS MULTI-AÑO - Cesantías y Vacaciones que cruzan años
    # =========================================================================

    def calcular_promedio_ponderado_multi_ano(self, fecha_inicio, fecha_fin, incluir_extras=True):
        """
        Calcula promedio ponderado considerando cambios de año.
        El auxilio de transporte se aplica según el SMMLV de cada año.

        Args:
            fecha_inicio: Fecha inicio del período
            fecha_fin: Fecha fin del período
            incluir_extras: Si incluir promedio de horas extras

        Returns:
            dict con promedio global y detalle por año
        """
        historial = self.get_historial_salarios(fecha_inicio, fecha_fin)

        if not historial:
            return {
                'promedio': 0,
                'promedio_sin_auxilio': 0,
                'total_dias': 0,
                'detalle': [],
                'por_ano': {},
                'extras_promedio': 0
            }

        total_ponderado = 0
        total_ponderado_sin_aux = 0
        total_dias = 0
        detalle = []
        por_ano = {}

        for periodo in historial:
            # Dividir período si cruza años
            periodos_por_ano = self._dividir_periodo_por_ano(periodo)

            for p in periodos_por_ano:
                year = p['fecha_inicio'].year
                dias = self._dias_entre_fechas(p['fecha_inicio'], p['fecha_fin'])

                # Obtener auxilio del año correspondiente
                smmlv_ano = self._get_smmlv(p['fecha_inicio'])
                aplica_aux = p['salario'] < (2 * smmlv_ano)
                auxilio = self._get_auxilio(p['fecha_inicio']) if aplica_aux else 0

                base = p['salario'] + auxilio
                ponderado = base * dias
                ponderado_sin_aux = p['salario'] * dias

                detalle.append({
                    'year': year,
                    'fecha_inicio': p['fecha_inicio'],
                    'fecha_fin': p['fecha_fin'],
                    'dias': dias,
                    'salario': p['salario'],
                    'auxilio': auxilio,
                    'base': base,
                    'ponderado': ponderado
                })

                # Acumular por año
                if year not in por_ano:
                    por_ano[year] = {
                        'dias': 0,
                        'ponderado': 0,
                        'ponderado_sin_aux': 0
                    }
                por_ano[year]['dias'] += dias
                por_ano[year]['ponderado'] += ponderado
                por_ano[year]['ponderado_sin_aux'] += ponderado_sin_aux

                total_ponderado += ponderado
                total_ponderado_sin_aux += ponderado_sin_aux
                total_dias += dias

        promedio = round(total_ponderado / total_dias, 0) if total_dias > 0 else 0
        promedio_sin_aux = round(total_ponderado_sin_aux / total_dias, 0) if total_dias > 0 else 0

        # Calcular promedios por año
        for year in por_ano:
            por_ano[year]['promedio'] = round(
                por_ano[year]['ponderado'] / por_ano[year]['dias'], 0
            ) if por_ano[year]['dias'] > 0 else 0
            por_ano[year]['promedio_sin_aux'] = round(
                por_ano[year]['ponderado_sin_aux'] / por_ano[year]['dias'], 0
            ) if por_ano[year]['dias'] > 0 else 0

        # Calcular extras si aplica
        extras_promedio = 0
        extras_por_ano = {}
        if incluir_extras:
            extras_por_ano = self._calcular_extras_por_ano(fecha_inicio, fecha_fin)
            extras_promedio = sum(extras_por_ano.values()) / len(extras_por_ano) if extras_por_ano else 0

        return {
            'promedio': promedio,
            'promedio_sin_auxilio': promedio_sin_aux,
            'promedio_con_extras': promedio + extras_promedio,
            'total_dias': total_dias,
            'total_ponderado': total_ponderado,
            'detalle': detalle,
            'por_ano': por_ano,
            'extras_promedio': extras_promedio,
            'extras_por_ano': extras_por_ano
        }

    def _dividir_periodo_por_ano(self, periodo):
        """
        Divide un período en sub-períodos por año calendario.

        Args:
            periodo: dict con fecha_inicio, fecha_fin, salario

        Returns:
            Lista de períodos divididos por año
        """
        resultado = []
        fecha_actual = periodo['fecha_inicio']
        fecha_fin = periodo['fecha_fin']

        while fecha_actual <= fecha_fin:
            # Fin del año actual
            fin_ano = date(fecha_actual.year, 12, 31)

            if fin_ano >= fecha_fin:
                # El período termina este año
                resultado.append({
                    'fecha_inicio': fecha_actual,
                    'fecha_fin': fecha_fin,
                    'salario': periodo['salario']
                })
                break
            else:
                # El período continúa al siguiente año
                resultado.append({
                    'fecha_inicio': fecha_actual,
                    'fecha_fin': fin_ano,
                    'salario': periodo['salario']
                })
                fecha_actual = date(fecha_actual.year + 1, 1, 1)

        return resultado

    def _calcular_extras_por_ano(self, fecha_inicio, fecha_fin):
        """
        Calcula promedio de horas extras por cada año en el período.

        Returns:
            dict con {año: promedio_extras}
        """
        extras_por_ano = {}
        fecha_actual = fecha_inicio

        while fecha_actual <= fecha_fin:
            year = fecha_actual.year
            inicio_ano = max(fecha_actual, date(year, 1, 1))
            fin_ano = min(fecha_fin, date(year, 12, 31))

            # Calcular extras del año
            extras = self._calcular_promedio_extras(inicio_ano, fin_ano)
            if extras > 0:
                extras_por_ano[year] = extras

            # Siguiente año
            fecha_actual = date(year + 1, 1, 1)

        return extras_por_ano

    def calcular_cesantias_por_ano(self, fecha_inicio, fecha_fin, extras_por_ano=None):
        """
        Calcula cesantías separadas por año calendario.

        En Colombia:
        - Cesantías se liquidan por año calendario
        - Se consignan antes del 14 de febrero del año siguiente
        - Si hay liquidación, se pagan cesantías de año anterior + proporcional actual

        Args:
            fecha_inicio: Fecha inicio
            fecha_fin: Fecha fin
            extras_por_ano: Dict con extras promediadas por año (opcional)

        Returns:
            dict con cesantías por año y consolidado
        """
        promedio = self.calcular_promedio_ponderado_multi_ano(
            fecha_inicio, fecha_fin, incluir_extras=False
        )

        extras_por_ano = extras_por_ano or promedio.get('extras_por_ano', {})
        cesantias_por_ano = {}
        total_cesantias = 0
        total_intereses = 0

        for year, datos in promedio['por_ano'].items():
            dias_comerciales = self.calcular_dias_comerciales(datos['dias'])

            # Base = promedio del año + extras promediadas del año
            extras_ano = extras_por_ano.get(year, 0)
            base_ano = datos['promedio'] + extras_ano

            # Cesantías del año
            cesantias = round(base_ano * dias_comerciales / 360, 0)

            # Intereses sobre cesantías: 12% anual proporcional
            intereses = round(cesantias * dias_comerciales / 360 * 0.12, 0)

            cesantias_por_ano[year] = {
                'dias_calendario': datos['dias'],
                'dias_comerciales': dias_comerciales,
                'promedio_salario': datos['promedio'],
                'extras_promedio': extras_ano,
                'base': base_ano,
                'cesantias': cesantias,
                'intereses': intereses,
                'total': cesantias + intereses
            }

            total_cesantias += cesantias
            total_intereses += intereses

        return {
            'por_ano': cesantias_por_ano,
            'total_cesantias': total_cesantias,
            'total_intereses': total_intereses,
            'total': total_cesantias + total_intereses,
            'detalle_promedio': promedio
        }

    def get_historial_cesantias(self, fecha_inicio, fecha_fin):
        """
        Obtiene historial de cesantías para devolución o liquidación.
        Incluye cesantías de años anteriores (consignadas o pendientes).

        Args:
            fecha_inicio: Fecha inicio contrato
            fecha_fin: Fecha liquidación

        Returns:
            dict con historial por año y totales
        """
        cesantias = self.calcular_cesantias_por_ano(fecha_inicio, fecha_fin)

        # Buscar cesantías ya consignadas en fondo
        HrCesantias = self.env.get('hr.history.cesantias')
        historial = {}

        for year, datos in cesantias['por_ano'].items():
            consignada = False
            fecha_consignacion = None
            fondo = None

            if HrCesantias:
                # Buscar si ya se consignó
                registro = HrCesantias.search([
                    ('employee_id', '=', self.employee_id),
                    ('year', '=', year),
                    ('state', '=', 'done')
                ], limit=1)

                if registro:
                    consignada = True
                    fecha_consignacion = registro.date
                    fondo = registro.fondo_cesantias_id.name if registro.fondo_cesantias_id else 'N/A'

            historial[year] = {
                'cesantias': datos['cesantias'],
                'intereses': datos['intereses'],
                'total': datos['total'],
                'consignada': consignada,
                'fecha_consignacion': fecha_consignacion,
                'fondo': fondo,
                'ubicacion': fondo if consignada else 'Con empleador',
                'disponible': datos['cesantias']  # Para retiro parcial
            }

        # Calcular totales
        total_consignadas = sum(
            h['cesantias'] for h in historial.values() if h['consignada']
        )
        total_pendientes = sum(
            h['cesantias'] for h in historial.values() if not h['consignada']
        )

        return {
            'por_ano': historial,
            'total_cesantias': cesantias['total_cesantias'],
            'total_intereses': cesantias['total_intereses'],
            'total_consignadas': total_consignadas,
            'total_pendientes': total_pendientes,
            'total_disponible': cesantias['total_cesantias']
        }

    def get_vacaciones_multi_ano(self, fecha_inicio, fecha_fin):
        """
        Calcula vacaciones cuando el período cruza años.
        IMPORTANTE: Vacaciones NO incluyen auxilio de transporte.

        Args:
            fecha_inicio: Fecha inicio
            fecha_fin: Fecha fin

        Returns:
            dict con vacaciones calculadas
        """
        promedio = self.calcular_promedio_ponderado_multi_ano(
            fecha_inicio, fecha_fin, incluir_extras=False
        )
        dias_comerciales = self.calcular_dias_comerciales(promedio['total_dias'])

        # Vacaciones = salario × días / 360 × 15 / 30
        vacaciones = round(
            promedio['promedio_sin_auxilio'] * dias_comerciales / 360 * 15 / 30, 0
        )

        return {
            'promedio_salario': promedio['promedio_sin_auxilio'],
            'dias_calendario': promedio['total_dias'],
            'dias_comerciales': dias_comerciales,
            'dias_vacaciones': round(dias_comerciales * 15 / 360, 2),
            'vacaciones': vacaciones,
            'por_ano': promedio['por_ano'],
            'detalle': promedio['detalle']
        }

    def get_liquidacion_completa(self, fecha_inicio, fecha_fin, fecha_liquidacion=None):
        """
        Calcula liquidación completa multi-año.

        Args:
            fecha_inicio: Fecha inicio contrato
            fecha_fin: Fecha fin contrato
            fecha_liquidacion: Fecha de liquidación (para prima del semestre)

        Returns:
            dict con todas las prestaciones
        """
        fecha_liquidacion = fecha_liquidacion or fecha_fin

        # Cesantías por año
        cesantias = self.calcular_cesantias_por_ano(fecha_inicio, fecha_fin)

        # Vacaciones
        vacaciones = self.get_vacaciones_multi_ano(fecha_inicio, fecha_fin)

        # Prima del semestre actual
        # Determinar inicio del semestre
        if fecha_liquidacion.month <= 6:
            inicio_semestre = date(fecha_liquidacion.year, 1, 1)
        else:
            inicio_semestre = date(fecha_liquidacion.year, 7, 1)

        # Ajustar si el contrato empezó después del inicio del semestre
        inicio_prima = max(inicio_semestre, fecha_inicio)

        promedio_prima = self.calcular_promedio_ponderado(
            inicio_prima, fecha_liquidacion, incluir_extras=True
        )
        dias_prima = self.calcular_dias_comerciales(promedio_prima['total_dias'])
        prima = round(promedio_prima['promedio_con_extras'] * dias_prima / 360, 0)

        # Total liquidación
        total = (
            cesantias['total_cesantias'] +
            cesantias['total_intereses'] +
            vacaciones['vacaciones'] +
            prima
        )

        return {
            'cesantias': cesantias,
            'vacaciones': vacaciones,
            'prima': {
                'base': promedio_prima['promedio_con_extras'],
                'dias': dias_prima,
                'valor': prima,
                'periodo': f"{inicio_prima} - {fecha_liquidacion}"
            },
            'total_cesantias': cesantias['total_cesantias'],
            'total_intereses': cesantias['total_intereses'],
            'total_vacaciones': vacaciones['vacaciones'],
            'total_prima': prima,
            'total_liquidacion': total
        }
