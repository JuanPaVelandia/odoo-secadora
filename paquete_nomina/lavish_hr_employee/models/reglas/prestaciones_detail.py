# -*- coding: utf-8 -*-
"""
PRESTACIONES SOCIALES - DETALLE PARA WIDGET
============================================
Genera estructura estandarizada para visualizacion en widget JS.

Secciones del dict de salida:
 1. metricas              - KPIs principales (valor_total, base_mensual, base_diaria, dias)
 2. valores_usados        - Desglose (salario_base, variable, auxilio)
 3. promedio_salario      - Info sobre promedio ponderado de salario
 4. condiciones           - Tipo contrato, modalidad, tipo nomina
 5. dias                  - Periodo, trabajados, ausencias
 6. valor_dia             - Valor diario equivalente
 7. formula_explicacion   - Formula legal paso a paso
 8. resumen_dias          - Tabla resumen de dias con descuentos
 9. cambios_salario       - Historial cambios salariales con ponderacion
10. cambios_auxilio       - Historial auxilio con aplicabilidad
11. desglose_variables_ordenado - Tabla ordenada (sueldo, aux, variable) con %
12. debug_formula_completa      - Valores exactos, flags, pasos finales
13. desglose_transporte_sueldo  - Composicion sueldo + transporte
    metadata              - IDs, fechas, tipo
    lineas_base_variable  - Lineas formateadas para PayslipLinePrestacion
"""
from odoo import models
from datetime import date
import logging

_logger = logging.getLogger(__name__)

DIAS_MES = 30
DIAS_SEMESTRE = 180
DIAS_ANO = 360
TOPE_SMMLV_AUX = 2


# ═══════════════════════════════════════════════════════════════════════════════
# HELPERS PUROS (sin self, sin env)
# ═══════════════════════════════════════════════════════════════════════════════

def _fmt(valor):
    """Formato moneda colombiana."""
    return f"${valor:,.0f}"


def _pct(parte, total):
    """Porcentaje seguro."""
    return round(parte / total * 100, 1) if total else 0.0


def _merge(defaults, override):
    """Merge con defaults."""
    result = dict(defaults)
    if override:
        result.update(override)
    return result


def _params_from_base(base_info):
    """Extrae parametros configurables de base_info."""
    if not base_info:
        return {
            'prima': 180, 'prestaciones': 360, 'vacaciones': 720,
            'dias_vac': 15, 'tasa_int': 0.12, 'tasa_int_pct': 12,
            'tope_smmlv': 2, 'es_liquidacion': False,
        }
    ctx = base_info.get('context', 'provision')
    es_liq = ctx == 'liquidacion'
    tasa = 0.12 if es_liq else base_info.get('tasa_intereses_cesantias', 0.12)
    return {
        'prima': base_info.get('base_dias_prima', 180),
        'prestaciones': base_info.get('base_dias_prestaciones', 360),
        'vacaciones': base_info.get('base_dias_vacaciones', 720),
        'dias_vac': base_info.get('dias_vacaciones', 15),
        'tasa_int': tasa,
        'tasa_int_pct': int(tasa * 100),
        'tope_smmlv': base_info.get('tope_auxilio_smmlv', 2),
        'es_liquidacion': es_liq,
    }


def _divisor_for(tipo, params):
    """Divisor segun tipo de prestacion."""
    if tipo == 'prima':
        return params['prima']
    if tipo == 'vacaciones':
        return params['vacaciones']
    return params['prestaciones']


# Formulas legales por tipo
_FORMULA_INFO = {
    'prima': {
        'nombre': 'Prima de Servicios',
        'formula_legal': 'Un mes de salario por cada semestre trabajado (15 dias por semestre)',
        'fundamento': 'Art. 306 CST - Se paga en dos cuotas: 30 junio y 20 diciembre',
        'descuento_ausencias': 'Ausencias no pagadas descuentan dias del periodo',
    },
    'cesantias': {
        'nombre': 'Cesantias',
        'formula_legal': 'Un mes de salario por cada año de servicios',
        'fundamento': 'Art. 249 CST - Consignacion a fondo antes del 14 de febrero',
        'descuento_ausencias': 'Ausencias no pagadas descuentan dias del periodo',
    },
    'intereses': {
        'nombre': 'Intereses sobre Cesantias',
        'formula_legal': '{pct}% anual sobre cesantias prorrateado por dias trabajados',
        'fundamento': 'Art. 99 Ley 50/1990 - Tasa legal 12% anual',
        'fundamento_no_liq': 'Ley 52 de 1975 - Pago directo al empleado antes del 31 de enero',
        'descuento_ausencias': 'Proporcional a dias de cesantias',
    },
    'vacaciones': {
        'nombre': 'Vacaciones',
        'formula_legal': '{dias_vac} dias habiles de descanso remunerado por año',
        'fundamento': 'Art. 186 CST - Derecho a vacaciones por cada año de servicios',
        'descuento_ausencias': 'Ausencias no pagadas descuentan dias del periodo',
    },
}

_MODALIDAD_LABELS = {
    'basico': 'Salario basico',
    'integral': 'Salario integral',
    'variable': 'Salario variable',
}

_PERIODO_NOMBRES = {
    'prima': 'Semestre', 'cesantias': 'Año',
    'intereses': 'Año', 'vacaciones': 'Año',
}

_TIPO_NOMINA_LABELS = {
    'nomina': 'Nomina Ordinaria',
    'contrato': 'Liquidacion de Contrato',
    'vacaciones': 'Liquidacion de Vacaciones',
    'prima': 'Liquidacion de Prima',
    'cesantias': 'Liquidacion de Cesantias',
    'intereses_cesantias': 'Liquidacion de Intereses',
}

_AUX_MODALITY_LABELS = {
    'basico': 'Sin variación (fijo)',
    'variable': 'Variable (promedio)',
    'no': 'Sin auxilio',
}


# ═══════════════════════════════════════════════════════════════════════════════
# MODELO PRINCIPAL
# ═══════════════════════════════════════════════════════════════════════════════

class HrSalaryRulePrestacionesDetail(models.AbstractModel):
    """
    Generador de detalle estandarizado para widget de prestaciones.
    Produce dict con secciones para PayslipLineDetail / PayslipLineProvision JS.
    """
    _name = 'hr.salary.rule.prestaciones.detail'
    _description = 'Detalle Widget Prestaciones'

    # ─────────────────────────────────────────────────────────────────────────
    # DEFAULTS
    # ─────────────────────────────────────────────────────────────────────────

    _BASE_DEFAULTS = {
        'salary': 0, 'salary_info': {}, 'variable': 0, 'variable_total': 0,
        'variable_lines': [], 'days_worked': 0, 'auxilio': 0,
        'auxilio_promedio': 0, 'auxilio_check': {}, 'base_mensual': 0,
        'base_diaria': 0, 'context': 'provision',
        'tasa_intereses_cesantias': 0.12,
        'base_dias_prima': DIAS_SEMESTRE, 'base_dias_prestaciones': DIAS_ANO,
        'base_dias_vacaciones': 720, 'dias_vacaciones': 15,
        'tope_auxilio_smmlv': TOPE_SMMLV_AUX,
        'modality_aux': 'basico', 'auxilio_en_variable': False,
        'auxilio_method': 'N/A', 'auxilio_motivo_no_aplica': '',
        'dias_usados_promedio': 0, 'dias_ausencias': 0,
        'cesantias_calculadas': 0,
    }

    _DAYS_DEFAULTS = {
        'dias_periodo': 0, 'dias_total': 0, 'dias_ausencias_no_pago': 0,
        'dias_descuento_bonus': 0, 'dias_ausencias_general': 0,
        'detalle_ausencias': [],
    }

    # ─────────────────────────────────────────────────────────────────────────
    # ENTRY POINTS
    # ─────────────────────────────────────────────────────────────────────────

    def generate(self, localdict, tipo_prestacion, base_info, days_info, valor):
        """
        Genera detalle completo para widget.

        Args:
            localdict: dict con slip, contract, employee
            tipo_prestacion: 'prima' | 'cesantias' | 'intereses' | 'vacaciones'
            base_info: dict con salary, variable, auxilio, base_mensual, etc.
            days_info: dict con dias_periodo, dias_ausencias, dias_total
            valor: float - Valor calculado de la prestacion

        Returns:
            dict: Detalle con todas las secciones para JS
        """
        bi = _merge(self._BASE_DEFAULTS, base_info)
        di = _merge(self._DAYS_DEFAULTS, days_info)
        slip = localdict['slip']
        contract = localdict['contract']
        employee = localdict.get('employee')

        return {
            'metricas': self._sec_metricas(valor, bi, di),
            'valores_usados': self._sec_valores_usados(bi),
            'promedio_salario': self._sec_promedio_salario(bi),
            'condiciones': self._sec_condiciones(localdict, tipo_prestacion),
            'dias': self._sec_dias(di),
            'valor_dia': self._sec_valor_dia(valor, di),
            'formula_explicacion': self._sec_formula(tipo_prestacion, bi, di, valor),
            'resumen_dias': self._sec_resumen_dias(di, tipo_prestacion),
            'cambios_salario': self._sec_cambios_salario(bi),
            'cambios_auxilio': self._sec_cambios_auxilio(bi, localdict, di),
            'desglose_variables_ordenado': self._sec_desglose_variables(bi, di),
            'debug_formula_completa': self._sec_debug(localdict, tipo_prestacion, bi, di, valor),
            'desglose_transporte_sueldo': self._sec_transporte_sueldo(bi, localdict),
            'metadata': {
                'tipo_prestacion': tipo_prestacion,
                'slip_id': slip.id,
                'slip_name': slip.number or slip.name,
                'contract_id': contract.id,
                'employee_id': employee.id if employee else None,
                'employee_name': employee.name if employee else None,
                'fecha_calculo': date.today().isoformat(),
                'context': bi.get('context', 'provision'),
            },
            'aplica': True,
            'motivo': '',
            'lineas_base_variable': self._build_lineas_base_variable(bi),
        }

    def build_detail_from_calculo(self, localdict, tipo_prestacion, calculo_data):
        """
        Construye detalle visual desde el dict de _build_calculo.

        Mapea sueldo_info / variable_base / auxilio al formato de generate().
        Normaliza campo names de _get_auxilio() al formato esperado por _sec_cambios_auxilio().
        """
        si = calculo_data.get('sueldo_info', {})
        vb = calculo_data.get('variable_base', {})
        ad = calculo_data.get('auxilio', {})
        bm = calculo_data.get('base_mensual', 0)

        # Normalizar auxilio: _get_auxilio() usa 'lineas_auxilio' con campos
        # (codigo, nombre, cantidad, slip_id, slip_number) pero _sec_cambios_auxilio()
        # espera 'lineas' con (rule_code, rule_name, quantity, payslip_id, payslip_number)
        lineas_raw = ad.get('lineas_auxilio', ad.get('lineas', []))
        lineas_norm = []
        for l in lineas_raw:
            lineas_norm.append({
                'total': l.get('total', 0),
                'quantity': l.get('quantity', l.get('cantidad', 0)),
                'period_key': l.get('period_key', ''),
                'date_from': l.get('date_from', ''),
                'rule_code': l.get('rule_code', l.get('codigo', '')),
                'rule_name': l.get('rule_name', l.get('nombre', '')),
                'payslip_id': l.get('payslip_id', l.get('slip_id')),
                'payslip_number': l.get('payslip_number', l.get('slip_number', '')),
            })
        ad_norm = dict(ad)
        ad_norm['lineas'] = lineas_norm
        ad_norm.setdefault('total_aux', ad.get('total_auxilio', 0))
        ad_norm.setdefault('count_lines', len(lineas_norm))

        bi = {
            'salary': calculo_data.get('sueldo', 0),
            'salary_info': si,
            'variable': calculo_data.get('promedio', 0),
            'variable_total': sum(
                d.get('total', 0) for d in vb.get('details', [])
                if (d.get('categoria') or '').upper() not in ('BASIC', 'AUX')
            ),
            'variable_lines': vb.get('details', []),
            'days_worked': si.get('dias_a_pagar', vb.get('dias_trabajados', 0)),
            'auxilio': calculo_data.get('auxilio_valor', 0),
            'auxilio_promedio': calculo_data.get('auxilio_valor', 0),
            'auxilio_check': ad_norm,
            'base_mensual': bm,
            'base_diaria': bm / 30 if bm else 0,
            'context': calculo_data.get('context', 'pago'),
        }
        # Copiar claves extra si existen
        for key in ('tasa_intereses_cesantias', 'base_dias_prima',
                     'base_dias_prestaciones', 'base_dias_vacaciones',
                     'dias_vacaciones', 'tope_auxilio_smmlv', 'modality_aux',
                     'auxilio_en_variable', 'auxilio_method',
                     'auxilio_motivo_no_aplica', 'dias_usados_promedio',
                     'dias_ausencias', 'cesantias_calculadas'):
            if key in calculo_data:
                bi[key] = calculo_data[key]
        for key in ('formula_mode', 'tasa_provision_pct'):
            if key in calculo_data:
                bi[key] = calculo_data[key]

        di = {
            'dias_periodo': si.get('dias_periodo', calculo_data.get('dias_periodo', 0)),
            'dias_total': calculo_data.get('dias_a_pagar', 0),
            'dias_ausencias_no_pago': si.get('dias_ausencias_no_pago', 0),
            'dias_descuento_bonus': si.get('dias_descuento_bonus', 0),
            'dias_ausencias_general': si.get('dias_ausencias_general', 0),
            'detalle_ausencias': si.get('detalle_ausencias', []),
        }

        bi = _merge(self._BASE_DEFAULTS, bi)
        di = _merge(self._DAYS_DEFAULTS, di)
        return self.generate(localdict, tipo_prestacion, bi, di, calculo_data.get('amount', 0))

    # ─────────────────────────────────────────────────────────────────────────
    # SECCION 1: METRICAS
    # ─────────────────────────────────────────────────────────────────────────

    def _sec_metricas(self, valor, bi, di):
        return {
            'valor_total': valor,
            'valor_total_fmt': _fmt(valor),
            'base_mensual': bi['base_mensual'],
            'base_mensual_fmt': _fmt(bi['base_mensual']),
            'base_diaria': bi['base_diaria'],
            'base_diaria_fmt': _fmt(bi['base_diaria']),
            'dias_trabajados': di['dias_total'],
            'dias_periodo': di['dias_periodo'],
        }

    # ─────────────────────────────────────────────────────────────────────────
    # SECCION 2: VALORES USADOS
    # ─────────────────────────────────────────────────────────────────────────

    def _sec_valores_usados(self, bi):
        si = bi.get('salary_info', {})
        ac = bi.get('auxilio_check', {})
        aux_val = bi.get('auxilio_promedio', 0) or bi.get('auxilio', 0)
        mod = bi.get('modality_aux', 'basico')

        return {
            'salario_base': {
                'valor': bi['salary'],
                'valor_fmt': _fmt(bi['salary']),
                'tiene_cambios': si.get('tiene_cambios', False),
                'es_promedio': si.get('tiene_cambios', False),
                'historial': si.get('historial', []),
            },
            'variable': {
                'valor': bi['variable'],
                'valor_fmt': _fmt(bi['variable']),
                'total_acumulado': bi['variable_total'],
                'total_acumulado_fmt': _fmt(bi['variable_total']),
                'lineas_count': len(bi.get('variable_lines', [])),
                'dias_base': bi['days_worked'],
                'formula': f"({bi['variable_total']:,.0f} / {bi['days_worked'] or 1}) × {DIAS_MES}",
            },
            'auxilio': {
                'valor': aux_val,
                'valor_fmt': _fmt(aux_val),
                'valor_directo': bi['auxilio'],
                'valor_directo_fmt': _fmt(bi['auxilio']),
                'metodo': bi.get('auxilio_method', 'N/A'),
                'en_variable': bi.get('auxilio_en_variable', False),
                'total_en_variable': ac.get('total_aux', 0),
                'total_en_variable_fmt': _fmt(ac.get('total_aux', 0)),
                'lineas_aux_count': ac.get('count_lines', 0),
                'nota': self._nota_auxilio(bi),
                'aplica': aux_val > 0 or ac.get('total_aux', 0) > 0,
                'modality_aux': mod,
                'modality_aux_label': _AUX_MODALITY_LABELS.get(mod, 'N/A'),
            },
        }

    @staticmethod
    def _nota_auxilio(bi):
        mod = bi.get('modality_aux', 'basico')
        if mod == 'no':
            return "Auxilio no incluido (Contrato: modalidad = Sin auxilio)"
        motivo = bi.get('auxilio_motivo_no_aplica', '')
        if motivo:
            return f"Auxilio no aplica: {motivo}"
        if bi.get('auxilio_en_variable', False):
            return "Auxilio promediado de líneas del periodo (modalidad: Variable)"
        if bi.get('auxilio', 0) > 0:
            m = bi.get('auxilio_method', 'N/A')
            return f"Auxilio fijo vigente (modalidad: Sin variación)" if m == 'basico_fijo' else f"Auxilio calculado: método '{m}'"
        return "Auxilio no aplica"

    # ─────────────────────────────────────────────────────────────────────────
    # SECCION 3: PROMEDIO SALARIO
    # ─────────────────────────────────────────────────────────────────────────

    def _sec_promedio_salario(self, bi):
        si = bi.get('salary_info', {})
        cambios = si.get('tiene_cambios', False)
        hist = si.get('historial', [])
        prom = si.get('salario_promedio', 0)
        act = si.get('salario_actual', 0)
        razon = (f"Hubo {len(hist)} cambio(s) de salario en el periodo - se calcula promedio ponderado"
                 if cambios else "Sin cambios de salario en el periodo - se usa salario actual")
        return {
            'usa_promedio': cambios,
            'razon': razon,
            'salario_actual': act,
            'salario_promedio': prom,
            'diferencia': prom - act,
            'historial_cambios': hist,
            'cantidad_cambios': len(hist),
        }

    # ─────────────────────────────────────────────────────────────────────────
    # SECCION 4: CONDICIONES
    # ─────────────────────────────────────────────────────────────────────────

    def _sec_condiciones(self, localdict, tipo):
        contract = localdict['contract']
        slip = localdict['slip']
        proc = slip.struct_id.process if slip.struct_id else 'nomina'
        ct = contract.contract_type_id

        has_map = {
            'prima': 'has_prima', 'cesantias': 'has_cesantias',
            'intereses': 'has_intereses_cesantias', 'vacaciones': 'has_vacaciones',
        }
        hf = has_map.get(tipo)
        aplica_ct = getattr(ct, hf, True) if hf and ct else True

        mod = getattr(contract, 'modality_salary', None) or 'N/A'

        return {
            'tipo_contrato': {
                'nombre': ct.name if ct else 'N/A',
                'id': ct.id if ct else None,
                'aplica_prestacion': aplica_ct,
            },
            'modalidad_salario': {
                'valor': mod,
                'descripcion': _MODALIDAD_LABELS.get(mod, mod),
            },
            'tipo_nomina': {
                'valor': proc,
                'es_liquidacion': proc == 'contrato',
                'es_vacaciones': proc == 'vacaciones',
                'es_prima': proc == 'prima',
                'es_cesantias': proc == 'cesantias',
            },
            'contrato': {
                'fecha_inicio': contract.date_start.isoformat() if contract.date_start else None,
                'fecha_fin': contract.date_end.isoformat() if contract.date_end else None,
                'estado': contract.state,
            },
        }

    # ─────────────────────────────────────────────────────────────────────────
    # SECCION 5: DIAS
    # ─────────────────────────────────────────────────────────────────────────

    def _sec_dias(self, di):
        dp = di['dias_periodo']
        dt = di['dias_total']
        dnp = di.get('dias_ausencias_no_pago', 0)
        db = di.get('dias_descuento_bonus', 0)
        da = dnp
        det = di.get('detalle_ausencias', [])

        formula = (f"{dp} - {dnp} (no pago) - {db} (desc. bonus) = {dt}" if db > 0
                   else f"{dp} - {da} = {dt}")

        result = {
            'periodo': {
                'desde': di.get('date_from').isoformat() if di.get('date_from') else None,
                'hasta': di.get('date_to').isoformat() if di.get('date_to') else None,
                'dias_totales': dp,
            },
            'trabajados': {'dias': dt, 'formula': formula},
            'ausencias': {
                'dias_total': da,
                'dias_no_pago': dnp,
                'dias_descuento_bonus': db,
                'nota_no_pago': 'Ausencias no remuneradas (unpaid_absences=True)',
                'nota_descuento_bonus': 'Ausencias con descuento en prima/cesantias (discounting_bonus_days=True)',
            },
        }

        if det:
            agrupado = {}
            for d in det:
                t = d.get('leave_type', d.get('tipo', 'Otro'))
                agrupado.setdefault(t, {'dias': 0, 'cantidad': 0})
                agrupado[t]['dias'] += d.get('dias', 0)
                agrupado[t]['cantidad'] += 1
            result['detalle_ausencias_bonus'] = {
                'cantidad': len(det), 'dias_total': db, 'detalle': det,
                'nota': 'Estas ausencias descuentan dias para calculo de prima/cesantias aunque sean remuneradas',
                'detalle_agrupado': [{'tipo': k, **v} for k, v in agrupado.items()],
            }
        return result

    # ─────────────────────────────────────────────────────────────────────────
    # SECCION 6: VALOR DIA
    # ─────────────────────────────────────────────────────────────────────────

    def _sec_valor_dia(self, valor, di):
        dt = di['dias_total']
        vd = valor / dt if dt > 0 else 0
        return {
            'valor_diario': vd,
            'valor_diario_fmt': _fmt(vd),
            'formula': f"{_fmt(valor)} / {dt} dias = {_fmt(vd)}/dia",
            'util_para': 'Referencia para liquidaciones parciales o calculo de dias adicionales',
        }

    # ─────────────────────────────────────────────────────────────────────────
    # SECCION 7: FORMULA EXPLICACION
    # ─────────────────────────────────────────────────────────────────────────

    def _sec_formula(self, tipo, bi, di, valor):
        p = _params_from_base(bi)
        info = self._formula_info(tipo, p, bi)
        pasos = self._build_pasos(tipo, bi, di, valor, p)

        bm = bi['base_mensual']
        dias = di['dias_total']
        formula_mode = bi.get('formula_mode')
        tasa_pct = bi.get('tasa_provision_pct', 0)
        use_dias360 = formula_mode == 'dias360_pct' and bi.get('context') == 'provision'
        divisor = info['divisor']

        if tipo == 'intereses':
            ces = (bm * dias) / divisor
            resumen = {
                'formula_aplicada': f"({_fmt(bm)} x {dias} / {divisor}) x {p['tasa_int_pct']}%",
                'desarrollo': f"{_fmt(ces)} x {p['tasa_int']:.2f} = {_fmt(valor)}",
                'resultado_final': valor,
                'resultado_final_fmt': _fmt(valor),
            }
        else:
            if bi.get('formula_mode') == 'dias360_pct' and bi.get('context') == 'provision':
                tasa_pct = bi.get('tasa_provision_pct', 0)
                resumen = {
                    'formula_aplicada': f"({_fmt(bm)} x {dias} / 360) x {tasa_pct:.2f}%",
                    'desarrollo': f"{_fmt((bm * dias) / 360)} x {tasa_pct:.2f}% = {_fmt(valor)}",
                    'resultado_final': valor,
                    'resultado_final_fmt': _fmt(valor),
                }
            else:
                resumen = {
                    'formula_aplicada': f"({_fmt(bm)} x {dias}) / {divisor}",
                    'desarrollo': f"{_fmt(bm * dias)} / {divisor} = {_fmt(valor)}",
                    'resultado_final': valor,
                    'resultado_final_fmt': _fmt(valor),
                }

        return {
            'nombre_prestacion': info['nombre'],
            'formula_general': info['formula'],
            'formula_legal': info['formula_legal'],
            'divisor': info['divisor'],
            'fundamento_legal': info['fundamento'],
            'pasos': pasos,
            'resumen_calculo': resumen,
            'notas': self._notas_formula(tipo, bi, di, p),
            'descuento_ausencias': info.get('descuento_ausencias', ''),
        }

    def _formula_info(self, tipo, p, base_info=None):
        """Info de formula segun tipo."""
        base = _FORMULA_INFO.get(tipo, {})
        divisor = _divisor_for(tipo, p)
        formula_mode = (base_info or {}).get('formula_mode')
        tasa_pct = (base_info or {}).get('tasa_provision_pct', 0)

        if tipo == 'intereses':
            formula = f"Cesantias x {p['tasa_int_pct']}% x (Dias / {p['prestaciones']})"
        else:
            if formula_mode == 'dias360_pct' and (base_info or {}).get('context') == 'provision':
                divisor = 360
                formula = f"(Base Mensual x Dias Trabajados / 360) x {tasa_pct:.2f}%"
            else:
                formula = f"(Base Mensual x Dias Trabajados) / {divisor}"

        fl = base.get('formula_legal', '')
        if '{pct}' in fl:
            fl = fl.format(pct=p['tasa_int_pct'])
        if '{dias_vac}' in fl:
            fl = fl.format(dias_vac=p['dias_vac'])

        fund = base.get('fundamento', '')
        if tipo == 'intereses' and not p['es_liquidacion']:
            fund = base.get('fundamento_no_liq', fund)
        if tipo == 'intereses' and p['es_liquidacion']:
            fl += " (TASA FIJA LEGAL)"

        return {
            'nombre': base.get('nombre', tipo.upper()),
            'formula': formula,
            'formula_legal': fl,
            'divisor': divisor,
            'fundamento': fund,
            'descuento_ausencias': base.get('descuento_ausencias', ''),
            'tasa_intereses': p['tasa_int_pct'],
            'tasa_es_fija': p['es_liquidacion'],
        }

    def _build_pasos(self, tipo, bi, di, valor, p):
        """Construye pasos del calculo."""
        sal = bi['salary']
        var = bi['variable']
        aux = bi['auxilio']
        bm = bi['base_mensual']
        dias = di['dias_total']

        notas_base = []
        if var > 0:
            notas_base.append("Variable: promedio de periodos anteriores")
        if aux > 0:
            notas_base.append(f"Auxilio: salario <= {p['tope_smmlv']} SMMLV")
        else:
            notas_base.append("Auxilio: no aplica o ya en variable")

        pasos = [
            {
                'numero': 1, 'titulo': 'Calcular Base Mensual',
                'descripcion': 'Sumar salario + variable promediado + auxilio (si aplica)',
                'formula': 'Salario + Variable + Auxilio',
                'calculo': f"{_fmt(sal)} + {_fmt(var)} + {_fmt(aux)}",
                'resultado': bm, 'resultado_fmt': _fmt(bm),
                'formato': 'currency',
                'notas': " | ".join(notas_base) or "Base: salario basico",
            },
            {
                'numero': 2, 'titulo': 'Determinar Dias Trabajados',
                'descripcion': 'Dias del periodo menos ausencias no remuneradas',
                'formula': 'Dias Periodo - Ausencias',
                'calculo': 'Dias trabajados en el periodo',
                'resultado': dias, 'resultado_fmt': f"{dias} dias",
                'formato': 'integer',
                'notas': f'Ano comercial de {p["prestaciones"]} dias (meses de 30 dias)',
            },
        ]

        if tipo == 'prima':
            d = p['prima']
            if use_dias360:
                pasos.append({
                    'numero': 3, 'titulo': 'Aplicar Formula de Prima',
                    'descripcion': f'Prima = (Base x Dias / 360) x {tasa_pct:.2f}%',
                    'formula': f"({bm:,.0f} x {dias} / 360) x {tasa_pct:.2f}%",
                    'calculo': f"{_fmt((bm * dias) / 360)} x {tasa_pct:.2f}%",
                    'resultado': valor, 'resultado_fmt': _fmt(valor),
                    'formato': 'currency',
                    'notas': '360 = dias de un año comercial',
                })
            else:
                pasos.append({
                    'numero': 3, 'titulo': 'Aplicar Formula de Prima',
                    'descripcion': f'Prima = (Base x Dias) / {d}',
                    'formula': f"({bm:,.0f} x {dias}) / {d}",
                    'calculo': f"({bm * dias:,.0f}) / {d}",
                    'resultado': valor, 'resultado_fmt': _fmt(valor),
                    'formato': 'currency',
                    'notas': f'{d} = dias de un semestre (6 meses x 30 dias)',
                })
        elif tipo == 'cesantias':
            d = p['prestaciones']
            if use_dias360:
                pasos.append({
                    'numero': 3, 'titulo': 'Aplicar Formula de Cesantias',
                    'descripcion': f'Cesantias = (Base x Dias / 360) x {tasa_pct:.2f}%',
                    'formula': f"({bm:,.0f} x {dias} / 360) x {tasa_pct:.2f}%",
                    'calculo': f"{_fmt((bm * dias) / 360)} x {tasa_pct:.2f}%",
                    'resultado': valor, 'resultado_fmt': _fmt(valor),
                    'formato': 'currency',
                    'notas': '360 = dias de un año comercial',
                })
            else:
                pasos.append({
                    'numero': 3, 'titulo': 'Aplicar Formula de Cesantias',
                    'descripcion': f'Cesantias = (Base x Dias) / {d}',
                    'formula': f"({bm:,.0f} x {dias}) / {d}",
                    'calculo': f"({bm * dias:,.0f}) / {d}",
                    'resultado': valor, 'resultado_fmt': _fmt(valor),
                    'formato': 'currency',
                    'notas': f'{d} = dias de un año comercial',
                })
        elif tipo == 'intereses':
            d = p['prestaciones']
            ces = bi.get('cesantias_calculadas', 0) or ((bm * dias) / d)
            te = p['tasa_int'] * dias / d
            te_pct = round(te * 100, 2)
            pasos.append({
                'numero': 3, 'titulo': 'Cesantias Base para Intereses',
                'descripcion': 'Valor de cesantías calculado en esta nómina',
                'formula': 'Cesantias del periodo',
                'calculo': _fmt(ces),
                'resultado': ces, 'resultado_fmt': _fmt(ces),
                'formato': 'currency',
                'notas': 'Cesantías ya prorrateado por días trabajados',
            })
            pasos.append({
                'numero': 4, 'titulo': f'Aplicar Tasa Efectiva ({te_pct}%)',
                'descripcion': f'Intereses = Cesantias x {p["tasa_int_pct"]}% x ({dias} / {d})',
                'formula': f"{_fmt(ces)} x {te_pct}%",
                'calculo': f"{_fmt(ces)} x {te_pct}% = {_fmt(valor)}",
                'resultado': valor, 'resultado_fmt': _fmt(valor),
                'formato': 'currency',
                'notas': f'Tasa anual {p["tasa_int_pct"]}% x ({dias}/{d}) = {te_pct}%',
                'tasa_anual': p['tasa_int_pct'],
                'tasa_efectiva': te_pct,
                'dias_periodo': dias,
            })
        elif tipo == 'vacaciones':
            d = p['vacaciones']
            if use_dias360:
                pasos.append({
                    'numero': 3, 'titulo': 'Aplicar Formula de Vacaciones',
                    'descripcion': f'Vacaciones = (Base x Dias / 360) x {tasa_pct:.2f}%',
                    'formula': f"({bm:,.0f} x {dias} / 360) x {tasa_pct:.2f}%",
                    'calculo': f"{_fmt((bm * dias) / 360)} x {tasa_pct:.2f}%",
                    'resultado': valor, 'resultado_fmt': _fmt(valor),
                    'formato': 'currency',
                    'notas': '360 = dias de un año comercial',
                })
            else:
                pasos.append({
                    'numero': 3, 'titulo': 'Aplicar Formula de Vacaciones',
                    'descripcion': f'Vacaciones = (Base x Dias) / {d}',
                    'formula': f"({bm:,.0f} x {dias}) / {d}",
                    'calculo': f"({bm * dias:,.0f}) / {d}",
                    'resultado': valor, 'resultado_fmt': _fmt(valor),
                    'formato': 'currency',
                    'notas': f'{d} = {p["prestaciones"]} dias x 2 ({p["dias_vac"]} dias por año = 1/2 mes)',
                })

        return pasos

    def _notas_formula(self, tipo, bi, di, p):
        """Notas adicionales sobre la formula."""
        notas = []
        if bi.get('auxilio_en_variable', False):
            notas.append({'tipo': 'info', 'mensaje': 'Auxilio de transporte incluido en promedio de variable (evita duplicacion)'})
        if bi.get('auxilio', 0) > 0:
            notas.append({'tipo': 'info', 'mensaje': f"Auxilio aplica por salario <= {p['tope_smmlv']} SMMLV"})
        if p['es_liquidacion'] and tipo == 'intereses':
            notas.append({'tipo': 'legal', 'mensaje': 'Tasa de intereses fija al 12% anual (Art. 99 Ley 50/1990) - Obligatorio en liquidacion'})
        if bi.get('salary_info', {}).get('tiene_cambios', False):
            notas.append({'tipo': 'info', 'mensaje': 'Salario promediado por cambios durante el periodo'})

        dnp = di.get('dias_ausencias_no_pago', 0)
        if dnp > 0:
            notas.append({'tipo': 'descuento', 'mensaje': f"Ausencias no remuneradas: {dnp} dias descontados"})

        db = di.get('dias_descuento_bonus', 0)
        if db > 0 and tipo in ('prima', 'cesantias', 'intereses'):
            det = di.get('detalle_ausencias', [])
            tipos = list(set(a.get('leave_type', '') for a in det))[:3]
            tipos_str = ", ".join(tipos)
            if len(set(a.get('leave_type', '') for a in det)) > 3:
                tipos_str += f" (+{len(set(a.get('leave_type', '') for a in det)) - 3} mas)"
            notas.append({'tipo': 'descuento_bonus', 'mensaje': f"Ausencias con descuento en {tipo}: {db} dias ({tipos_str})"})

        da = dnp + db
        if da > 0 and tipo == 'prima':
            notas.append({'tipo': 'calculo', 'mensaje': f"Prima reducida proporcionalmente por {da} dias de ausencia total"})

        if bi.get('variable', 0) > 0:
            notas.append({'tipo': 'info', 'mensaje': 'Variable incluye devengos de periodos anteriores promediados'})

        return notas

    # ─────────────────────────────────────────────────────────────────────────
    # SECCION 8: RESUMEN DIAS
    # ─────────────────────────────────────────────────────────────────────────

    def _sec_resumen_dias(self, di, tipo):
        dp = di['dias_periodo']
        dt = di['dias_total']
        dnp = di.get('dias_ausencias_no_pago', 0)
        db = di.get('dias_descuento_bonus', 0)
        det = di.get('detalle_ausencias', [])
        nombre = _PERIODO_NOMBRES.get(tipo, 'Periodo')
        total_desc = dnp + db

        lineas = [{'orden': 1, 'concepto': f'Días del {nombre}', 'tipo': 'base',
                    'dias': dp, 'signo': '', 'icono': 'fa-calendar', 'color': 'primary'}]

        if dnp > 0:
            lineas.append({'orden': 2, 'concepto': 'Licencias no remuneradas', 'tipo': 'descuento',
                           'dias': dnp, 'signo': '-', 'icono': 'fa-minus-circle', 'color': 'danger',
                           'detalle': 'Ausencias con unpaid_absences=True'})

        if db > 0:
            agrup = {}
            for d in det:
                t = d.get('leave_type', d.get('tipo', 'Otro'))
                agrup.setdefault(t, {'dias': 0, 'cantidad': 0})
                agrup[t]['dias'] += d.get('dias', 0)
                agrup[t]['cantidad'] += 1
            lineas.append({'orden': 3, 'concepto': 'Descuento bonificación', 'tipo': 'descuento',
                           'dias': db, 'signo': '-', 'icono': 'fa-minus-circle', 'color': 'warning',
                           'detalle': 'Ausencias con discounting_bonus_days=True',
                           'detalle_agrupado': [{'tipo': k, **v} for k, v in agrup.items()]})

        f = f"{dp} - {dnp} (lic. no rem.) - {db} (desc. bonus) = {dt}" if total_desc > 0 else f"{dp} días"
        lineas.append({'orden': 99, 'concepto': 'DÍAS USADOS PARA PROMEDIO', 'tipo': 'total',
                       'dias': dt, 'signo': '=', 'icono': 'fa-check-circle', 'color': 'success',
                       'formula': f"{dp} - {total_desc} = {dt}" if total_desc > 0 else f"{dp}"})

        return {
            'tipo_prestacion': tipo, 'nombre_periodo': nombre,
            'dias_periodo': dp, 'dias_total': dt,
            'dias_ausencias_no_pago': dnp, 'dias_descuento_bonus': db,
            'total_descuentos': total_desc, 'tiene_descuentos': total_desc > 0,
            'lineas': lineas, 'formula_resumen': f,
        }

    # ─────────────────────────────────────────────────────────────────────────
    # SECCION 9: CAMBIOS DE SALARIO
    # ─────────────────────────────────────────────────────────────────────────

    def _sec_cambios_salario(self, bi):
        si = bi.get('salary_info', {})
        segs = si.get('segmentos', [])
        tiene = si.get('tiene_cambios', False)
        dias_t = si.get('dias_totales', 0)
        prom = si.get('salario_promedio', 0)

        if not tiene or not segs:
            sal = bi['salary']
            return {
                'tiene_cambios': False, 'cantidad': 1,
                'historial': [{
                    'orden': 1, 'fecha_inicio': 'Periodo actual', 'fecha_fin': '-',
                    'salario_monto': sal, 'salario_monto_fmt': _fmt(sal),
                    'dias_vigencia': dias_t or 30,
                    'ponderacion': 100.0, 'ponderacion_fmt': '100%',
                    'salario_ponderado': sal, 'salario_ponderado_fmt': _fmt(sal),
                    'motivo': 'Salario actual (sin cambios en el periodo)',
                }],
                'salario_inicial': sal, 'salario_final': sal,
                'salario_promediado': sal, 'salario_promediado_fmt': _fmt(sal),
                'diferencia_impacto': 0,
                'formula_ponderacion': f"Salario unico: {_fmt(sal)}",
                'dias_totales': dias_t or 30,
            }

        historial = []
        parts = []
        s_ini = segs[0]['salario'] if segs else 0
        s_fin = segs[-1]['salario'] if segs else 0

        for i, seg in enumerate(segs):
            d = seg.get('dias', 0)
            s = seg.get('salario', 0)
            pond = d / dias_t if dias_t > 0 else 0
            sp = s * pond
            historial.append({
                'orden': i + 1,
                'fecha_inicio': seg.get('fecha_inicio', ''),
                'fecha_fin': seg.get('fecha_fin', ''),
                'salario_monto': s, 'salario_monto_fmt': _fmt(s),
                'dias_vigencia': d,
                'ponderacion': round(pond * 100, 2),
                'ponderacion_fmt': f"{pond * 100:.1f}%",
                'salario_ponderado': sp, 'salario_ponderado_fmt': _fmt(sp),
                'motivo': 'Cambio salarial' if i > 0 else 'Salario inicial del periodo',
            })
            parts.append(f"{_fmt(s)} x {d}")

        formula = f"({' + '.join(parts)}) / {dias_t}" if dias_t > 0 else "N/A"
        diff = s_fin - prom

        return {
            'tiene_cambios': True, 'cantidad': len(segs) - 1,
            'historial': historial,
            'salario_inicial': s_ini, 'salario_inicial_fmt': _fmt(s_ini),
            'salario_final': s_fin, 'salario_final_fmt': _fmt(s_fin),
            'salario_promediado': prom, 'salario_promediado_fmt': _fmt(prom),
            'diferencia_impacto': diff, 'diferencia_impacto_fmt': _fmt(abs(diff)),
            'formula_ponderacion': formula, 'dias_totales': dias_t,
        }

    # ─────────────────────────────────────────────────────────────────────────
    # SECCION 10: CAMBIOS DE AUXILIO
    # ─────────────────────────────────────────────────────────────────────────

    def _sec_cambios_auxilio(self, bi, localdict, di):
        contract = localdict.get('contract')
        slip = localdict.get('slip')
        ac = bi.get('auxilio_check', {})
        dias_fin = bi.get('dias_usados_promedio', 0) or di.get('dias_total', 0)
        auxilio_valor = bi.get('auxilio', 0)
        method = bi.get('auxilio_method', 'N/A')
        en_var = bi.get('auxilio_en_variable', False)
        lineas_aux = ac.get('lineas', [])
        force_full_days = bool(getattr(slip, 'force_auxilio_full_days', False))
        vac_slip_ids = set()
        if force_full_days and lineas_aux:
            aux_slip_ids = {l.get('payslip_id') for l in lineas_aux if l.get('payslip_id')}
            if aux_slip_ids:
                vac_worked = self.env['hr.payslip.worked_days'].search_read(
                    [
                        ('payslip_id', 'in', list(aux_slip_ids)),
                        ('code', '=', 'VACDISFRUTADAS'),
                        ('number_of_days', '>', 0),
                    ],
                    ['payslip_id'],
                )
                vac_slip_ids = {l['payslip_id'][0] for l in vac_worked if l.get('payslip_id')}

        # Tope SMMLV
        sal_base = bi['salary']
        annual_params = localdict.get('annual_parameters')
        if not annual_params and slip:
            dr = slip.date_to or slip.date_from
            cid = slip.company_id.id if slip.company_id else None
            if dr:
                annual_params = self.env['hr.annual.parameters'].get_for_year(
                    dr.year, company_id=cid, raise_if_not_found=False)

        smmlv = getattr(annual_params, 'smmlv_monthly', 0) or 0 if annual_params else 0
        tope_m = getattr(annual_params, 'top_max_transportation_assistance', 0) or 0 if annual_params else 0
        aplica = sal_base <= tope_m if tope_m > 0 else True

        # Auxilio de la nomina actual desde rules
        aux_actual = 0
        dias_aux_actual = 0
        cod_aux = None
        nom_aux = None
        for rc, rd in (localdict.get('rules', {}) or {}).items():
            rule = getattr(rd, 'rule', None)
            if not rule:
                continue
            es_aux = False
            if rule.category_id:
                c = rule.category_id
                es_aux = c.code == 'AUX' or (c.parent_id and c.parent_id.code == 'AUX')
            if not es_aux and getattr(rule, 'es_auxilio_transporte', False):
                es_aux = True
            if es_aux:
                aux_actual += abs(getattr(rd, 'total', 0) or 0)
                dias_aux_actual += abs(getattr(rd, 'quantity', 0) or 0)
                if not cod_aux:
                    cod_aux = rule.code
                    nom_aux = rule.name

        # Historial
        historial = []
        suma = 0
        total_dias_h = 0
        for i, l in enumerate(lineas_aux):
            m = l.get('total', 0)
            dr = l.get('quantity', 0) or 0
            force_line = force_full_days and (l.get('payslip_id') in vac_slip_ids)
            if force_line:
                d = DIAS_MES
            elif dr <= 0 and m > 0 and auxilio_valor > 0:
                d = round(m / (auxilio_valor / DIAS_MES), 0)
            elif dr > 0:
                d = dr
            else:
                d = DIAS_MES
            suma += m
            total_dias_h += d
            historial.append({
                'orden': i + 1, 'periodo': l.get('period_key', ''),
                'fecha': l.get('date_from', ''), 'monto': m, 'monto_fmt': _fmt(m),
                'dias': d, 'codigo': l.get('rule_code', ''),
                'nombre': l.get('rule_name', ''),
                'payslip_id': l.get('payslip_id'),
                'payslip_number': l.get('payslip_number', ''),
            })

        # Agregar actual si no duplicado
        has_vac_current = False
        if force_full_days:
            worked_days = localdict.get('worked_days', {}) or {}
            wd = worked_days.get('VACDISFRUTADAS')
            if wd and getattr(wd, 'number_of_days', 0):
                has_vac_current = True

        if aux_actual > 0:
            sid = slip.id if slip else None
            ya = any(h.get('payslip_id') == sid for h in historial) if sid else False
            if not ya:
                per = f"{slip.date_from.year}-{slip.date_from.month:02d}" if slip and slip.date_from else ''
                if force_full_days and has_vac_current:
                    d_a = DIAS_MES
                else:
                    d_a = dias_aux_actual if dias_aux_actual > 0 else (round(aux_actual / (auxilio_valor / DIAS_MES), 0) if auxilio_valor > 0 else DIAS_MES)
                suma += aux_actual
                total_dias_h += d_a
                historial.append({
                    'orden': len(historial) + 1, 'periodo': per,
                    'fecha': str(slip.date_from) if slip and slip.date_from else '',
                    'monto': aux_actual, 'monto_fmt': _fmt(aux_actual),
                    'dias': d_a, 'codigo': cod_aux or 'AUX000',
                    'nombre': nom_aux or 'AUXILIO DE TRANSPORTE',
                    'payslip_id': slip.id if slip else None,
                    'payslip_number': slip.number if slip else '',
                    'es_actual': True,
                })

        # Auxilio aplicado
        dp = dias_fin if dias_fin > 0 else total_dias_h
        if en_var and dp > 0:
            aux_aplicado = (suma / dp) * DIAS_MES
        elif en_var and historial:
            aux_aplicado = suma / len(historial)
        else:
            aux_aplicado = auxilio_valor

        return {
            'tiene_cambios': len(historial) > 1,
            'cantidad': len(historial),
            'historial': historial,
            'total_dias': dp,
            'total_dias_historial': total_dias_h,
            'dias_finales_periodo': dias_fin,
            'auxilio_actual': auxilio_valor,
            'auxilio_actual_fmt': _fmt(auxilio_valor),
            'auxilio_aplicado': aux_aplicado,
            'auxilio_aplicado_fmt': _fmt(aux_aplicado),
            'suma_historial': suma,
            'suma_historial_fmt': _fmt(suma),
            'metodo_calculo': method,
            'en_variable': en_var,
            'total_en_variable': ac.get('total_aux', 0),
            'total_en_variable_fmt': _fmt(ac.get('total_aux', 0)),
            'lineas_count': len(lineas_aux),
            'aplicabilidad': {
                'salario_base': sal_base, 'salario_base_fmt': _fmt(sal_base),
                'smmlv_vigente': smmlv, 'smmlv_vigente_fmt': _fmt(smmlv),
                'tope_smmlv': TOPE_SMMLV_AUX,
                'tope_moneda': tope_m, 'tope_moneda_fmt': _fmt(tope_m),
                'aplica': aplica,
                'razon': f"Salario {'<=' if aplica else '>'} {TOPE_SMMLV_AUX} SMMLV ({_fmt(tope_m)})",
            },
            'nota': self._nota_auxilio(bi),
        }

    # ─────────────────────────────────────────────────────────────────────────
    # SECCION 11: DESGLOSE VARIABLES ORDENADO
    # ─────────────────────────────────────────────────────────────────────────

    def _sec_desglose_variables(self, bi, di):
        sal = bi['salary']
        aux = bi['auxilio']
        var = bi['variable']
        vt = bi['variable_total']
        vlines = bi.get('variable_lines', [])
        bm = bi['base_mensual']
        dias_u = bi.get('dias_usados_promedio', 0) or bi.get('days_worked', 0) or di.get('dias_total', DIAS_MES)

        variables = []

        # 1. Salario
        if sal > 0:
            si = bi.get('salary_info', {})
            tc = si.get('tiene_cambios', False)
            variables.append({
                'tipo': 'salario', 'orden': 1,
                'descripcion': 'Salario Base' + (' (promediado)' if tc else ''),
                'valor': sal, 'valor_fmt': _fmt(sal),
                'porcentaje_base': _pct(sal, bm), 'porcentaje_base_fmt': f"{_pct(sal, bm)}%",
                'dias_ponderados': DIAS_MES,
                'valor_diario': sal / DIAS_MES, 'valor_diario_fmt': _fmt(sal / DIAS_MES),
                'icono': 'fa-money', 'color': 'primary',
                'fuente': 'promedio_ponderado' if tc else 'contrato',
                'tiene_cambios': tc,
            })

        # 2. Auxilio
        if aux > 0:
            variables.append({
                'tipo': 'auxilio', 'orden': 2,
                'descripcion': 'Auxilio de Transporte',
                'valor': aux, 'valor_fmt': _fmt(aux),
                'porcentaje_base': _pct(aux, bm), 'porcentaje_base_fmt': f"{_pct(aux, bm)}%",
                'dias_ponderados': DIAS_MES,
                'valor_diario': aux / DIAS_MES, 'valor_diario_fmt': _fmt(aux / DIAS_MES),
                'icono': 'fa-bus', 'color': 'warning',
                'fuente': bi.get('auxilio_method', 'calculado'),
                'en_variable': bi.get('auxilio_en_variable', False),
            })

        # 3. Variable
        if var > 0:
            # Agrupar lineas (excluir AUX)
            agrup = {}
            for l in vlines:
                cc = (l.get('category_code', '') or '').upper()
                if cc == 'AUX' or l.get('es_auxilio_transporte', False):
                    continue
                cod = l.get('rule_code', 'OTROS')
                if cod not in agrup:
                    agrup[cod] = {'codigo': cod, 'nombre': l.get('rule_name', cod), 'total': 0, 'periodos': []}
                agrup[cod]['total'] += l.get('total', 0)
                agrup[cod]['periodos'].append({
                    'mes': l.get('period_key', ''),
                    'monto': l.get('total', 0), 'monto_fmt': _fmt(l.get('total', 0)),
                    'payslip_id': l.get('payslip_id'),
                })
            lineas_ord = sorted(agrup.values(), key=lambda x: x['total'], reverse=True)

            variables.append({
                'tipo': 'variable', 'orden': 3,
                'descripcion': 'Variable Promediado',
                'valor': var, 'valor_fmt': _fmt(var),
                'total_acumulado': vt, 'total_acumulado_fmt': _fmt(vt),
                'porcentaje_base': _pct(var, bm), 'porcentaje_base_fmt': f"{_pct(var, bm)}%",
                'dias_ponderados': dias_u,
                'valor_diario': var / DIAS_MES if var > 0 else 0,
                'valor_diario_fmt': _fmt(var / DIAS_MES) if var > 0 else "$0",
                'icono': 'fa-line-chart', 'color': 'success',
                'formula': f"({vt:,.0f} / {dias_u}) × {DIAS_MES}",
                'lineas_count': len(vlines), 'lineas': lineas_ord,
            })

        total = sum(v['valor'] for v in variables)
        return {
            'total_base': total, 'total_base_fmt': _fmt(total),
            'valor_diario_base': total / DIAS_MES if total > 0 else 0,
            'valor_diario_base_fmt': _fmt(total / DIAS_MES) if total > 0 else "$0",
            'componentes_count': len(variables), 'variables': variables,
            'formula_total': f"{sal:,.0f} + {aux:,.0f} + {var:,.0f} = {total:,.0f}",
        }

    # ─────────────────────────────────────────────────────────────────────────
    # SECCION 12: DEBUG FORMULA COMPLETA
    # ─────────────────────────────────────────────────────────────────────────

    def _sec_debug(self, localdict, tipo, bi, di, valor):
        slip = localdict.get('slip')
        contract = localdict.get('contract')
        si = bi.get('salary_info', {})
        p = _params_from_base(bi)
        proc = slip.struct_id.process if slip.struct_id else 'nomina'
        es_liq = proc == 'contrato'

        bm = bi['base_mensual']
        dias_f = di['dias_total']
        divisor = _divisor_for(tipo, p)

        # Cambios salario - formula inline
        segs = si.get('segmentos', [])
        cs_formula = 'N/A'
        if si.get('tiene_cambios') and segs:
            dt = si.get('dias_totales', 0)
            parts = [f"{_fmt(s['salario'])} x {s.get('dias', 0)}" for s in segs]
            cs_formula = f"({' + '.join(parts)}) / {dt}" if dt > 0 else 'N/A'

        valores_exactos = {
            'salario_base': {
                'valor': bi['salary'], 'valor_fmt': _fmt(bi['salary']),
                'fuente': 'promedio ponderado' if si.get('tiene_cambios') else 'contrato',
                'cambios': len(segs) - 1 if si.get('tiene_cambios') else 0,
                'formula': cs_formula,
            },
            'auxilio': {
                'valor': bi['auxilio'], 'valor_fmt': _fmt(bi['auxilio']),
                'fuente': bi.get('auxilio_method', 'N/A'),
                'en_variable': bi.get('auxilio_en_variable', False),
            },
            'variable': {
                'valor': bi['variable'], 'valor_fmt': _fmt(bi['variable']),
                'fuente': f"Promedio {bi['days_worked']} dias",
                'total_acumulado': bi['variable_total'],
                'formula': f"({bi['variable_total']:,.0f} / {bi['days_worked'] or 1}) × {DIAS_MES}",
            },
            'base_mensual': {
                'valor': bm, 'valor_fmt': _fmt(bm),
                'formula': f"{bi['salary']:,.0f} + {bi['auxilio']:,.0f} + {bi['variable']:,.0f}",
            },
        }

        dnp = di.get('dias_ausencias_no_pago', 0)
        db = di.get('dias_descuento_bonus', 0)
        dp = di['dias_periodo']

        dias_logica = {
            'dias_periodo': dp,
            'dias_ausencias_no_pago': dnp,
            'dias_descuento_bonus': db,
            'dias_finales': dias_f,
            'formula': f"{dp} - {dnp}" + (f" - {db}" if db > 0 else "") + f" = {dias_f}",
            'detalle_descuentos': di.get('detalle_ausencias', []),
        }

        # Pasos finales
        pasos = [
            {'numero': 1, 'titulo': 'Base Mensual',
             'formula': f"{bi['salary']:,.0f} + {bi['auxilio']:,.0f} + {bi['variable']:,.0f}",
             'resultado': bm, 'resultado_fmt': _fmt(bm)},
            {'numero': 2, 'titulo': 'Dias Trabajados',
             'formula': dias_logica['formula'],
             'resultado': dias_f, 'resultado_fmt': f"{dias_f} dias"},
            {'numero': 3, 'titulo': f'Aplicar Formula {tipo.title()}',
             'formula': f"({bm:,.0f} x {dias_f}) / {divisor}",
             'resultado': valor, 'resultado_fmt': _fmt(valor)},
        ]

        if tipo == 'intereses':
            ces_b = (bm * dias_f) / p['prestaciones']
            pasos = [
                pasos[0], pasos[1],
                {'numero': 3, 'titulo': 'Calcular Cesantias Base',
                 'formula': f"({bm:,.0f} x {dias_f}) / {p['prestaciones']}",
                 'resultado': ces_b, 'resultado_fmt': _fmt(ces_b)},
                {'numero': 4, 'titulo': f'Aplicar Tasa {p["tasa_int_pct"]}%',
                 'formula': f"{ces_b:,.0f} x {p['tasa_int_pct']}%",
                 'resultado': valor, 'resultado_fmt': _fmt(valor)},
            ]

        return {
            'tipo_prestacion': tipo,
            'contexto': bi.get('context', 'provision'),
            'valores_exactos': valores_exactos,
            'dias_logica': dias_logica,
            'flags_aplicabilidad': {
                'es_liquidacion': es_liq,
                'es_liquidacion_icono': 'fa-file-text' if es_liq else 'fa-calendar',
                'aplica_auxilio': bi['auxilio'] > 0,
                'aplica_auxilio_icono': 'fa-bus',
                'usa_promedio_salario': si.get('tiene_cambios', False),
                'usa_promedio_salario_icono': 'fa-calculator',
                'auxilio_en_variable': bi.get('auxilio_en_variable', False),
                'auxilio_en_variable_icono': 'fa-link',
                'provision_simple': bi.get('context') == 'provision',
            },
            'tipo_nomina': {
                'valor': proc,
                'descripcion': _TIPO_NOMINA_LABELS.get(proc, proc.title() if proc else 'N/A'),
                'es_liquidacion': es_liq,
                'es_vacaciones': proc == 'vacaciones',
                'es_prima': proc == 'prima',
                'es_cesantias': proc == 'cesantias',
                'es_intereses': proc == 'intereses_cesantias',
                'es_nomina': proc == 'nomina',
            },
            'pasos_calculo_final': pasos,
            'parametros_usados': {
                'base_dias_prima': p['prima'],
                'base_dias_prestaciones': p['prestaciones'],
                'base_dias_vacaciones': p['vacaciones'],
                'dias_vacaciones': p['dias_vac'],
                'tasa_intereses': p['tasa_int_pct'],
                'tope_auxilio_smmlv': p['tope_smmlv'],
            },
        }

    # ─────────────────────────────────────────────────────────────────────────
    # SECCION 13: DESGLOSE TRANSPORTE Y SUELDO
    # ─────────────────────────────────────────────────────────────────────────

    def _sec_transporte_sueldo(self, bi, localdict):
        si = bi.get('salary_info', {})
        sal = bi['salary']
        aux_d = bi['auxilio']
        en_var = bi.get('auxilio_en_variable', False)
        ac = bi.get('auxilio_check', {})
        lineas_aux = ac.get('lineas', [])
        total_aux_var = ac.get('total_aux', 0)

        hay_aux_var = en_var and len(lineas_aux) > 0
        aplica = aux_d > 0 or hay_aux_var
        aux_mostrar = aux_d
        nota = ''
        if hay_aux_var and aux_d == 0 and lineas_aux:
            s = sum(l.get('total', 0) for l in lineas_aux)
            aux_mostrar = s / len(lineas_aux)
            nota = f'Promedio de {len(lineas_aux)} periodos (incluido en variable)'

        total_bf = sal + aux_d

        # Tope
        al = self._get_auxilio_limits(localdict, sal)

        tiene_c = si.get('tiene_cambios', False)
        fuente = 'promedio_ponderado' if tiene_c else 'contrato'

        return {
            'salario': {
                'valor': sal, 'valor_fmt': _fmt(sal),
                'es_promedio': tiene_c, 'fuente': fuente,
                'cantidad_cambios': len(si.get('segmentos', [])) - 1 if tiene_c else 0,
            },
            'auxilio': {
                'valor': aux_d, 'valor_fmt': _fmt(aux_d),
                'valor_mostrar': aux_mostrar, 'valor_mostrar_fmt': _fmt(aux_mostrar),
                'aplica': aplica, 'aplica_en_variable': hay_aux_var,
                'tope_smmlv': al['tope_smmlv'],
                'tope_moneda': al['tope_moneda'], 'tope_moneda_fmt': al['tope_moneda_fmt'],
                'metodo': bi.get('auxilio_method', 'N/A'),
                'en_variable': en_var,
                'total_en_variable': total_aux_var,
                'total_en_variable_fmt': _fmt(total_aux_var),
                'smmlv_vigente': al['smmlv'], 'smmlv_vigente_fmt': al['smmlv_fmt'],
                'nota': nota,
            },
            'total_base_fija': total_bf, 'total_base_fija_fmt': _fmt(total_bf),
            'porcentaje_sueldo': _pct(sal, total_bf), 'porcentaje_sueldo_fmt': f"{_pct(sal, total_bf)}%",
            'porcentaje_auxilio': _pct(aux_d, total_bf), 'porcentaje_auxilio_fmt': f"{_pct(aux_d, total_bf)}%",
            'nota': 'Base fija mensual (sin variable)' if bi['variable'] > 0 else 'Base mensual completa',
        }

    def _get_auxilio_limits(self, localdict, salario_base=0):
        """Topes de auxilio de transporte."""
        ap = localdict.get('annual_parameters')
        if not ap:
            slip = localdict.get('slip')
            if slip:
                dr = slip.date_to or slip.date_from
                cid = slip.company_id.id if slip.company_id else None
                if dr:
                    ap = self.env['hr.annual.parameters'].get_for_year(
                        dr.year, company_id=cid, raise_if_not_found=False)

        smmlv = getattr(ap, 'smmlv_monthly', 0) or 0 if ap else 0
        tope_m = getattr(ap, 'top_max_transportation_assistance', 0) or 0 if ap else 0
        aplica = salario_base <= tope_m if salario_base > 0 and tope_m > 0 else True

        return {
            'smmlv': smmlv, 'smmlv_fmt': _fmt(smmlv),
            'tope_smmlv': TOPE_SMMLV_AUX,
            'tope_moneda': tope_m, 'tope_moneda_fmt': _fmt(tope_m),
            'aplica': aplica,
        }

    # ─────────────────────────────────────────────────────────────────────────
    # LINEAS BASE VARIABLE (para PayslipLinePrestacion)
    # ─────────────────────────────────────────────────────────────────────────

    def _build_lineas_base_variable(self, bi):
        """Lista de lineas variable formateadas para frontend (excluye AUX)."""
        vlines = bi.get('variable_lines', [])
        if not vlines:
            return []

        result = []
        for l in vlines:
            cc = (l.get('category_code', '') or '').upper()
            if cc == 'AUX' or l.get('es_auxilio_transporte', False):
                continue

            nombre = l.get('rule_name', '')
            if isinstance(nombre, dict):
                nombre = nombre.get('es_CO', nombre.get('en_US', ''))

            st = l.get('source_type', 'payslip')
            sn = l.get('payslip_number', '')
            if st == 'accumulated':
                at = l.get('accumulated_type', 'auto')
                tl = {'auto': 'Automático', 'inception': 'Carga Inicial',
                      'novelty': 'Novedad', 'absence': 'Ausencia',
                      'adjustment': 'Ajuste Manual'}.get(at, at)
                sn = f"[{tl}] {l.get('note', '')[:30]}" if l.get('note') else f"[{tl}]"
            elif st == 'current_slip':
                sn = f"[Nómina Actual] {sn}"

            result.append({
                'codigo': l.get('rule_code', l.get('rule_code_full', '')),
                'nombre': nombre,
                'total': l.get('total', 0),
                'valor_usado': l.get('amount', l.get('total', 0)),
                'tipo': st,
                'fecha': str(l.get('date_from', '')) if l.get('date_from') else '',
                'slip_number': sn,
                'payslip_id': l.get('payslip_id'),
                'categoria': l.get('category_code', ''),
                'categoria_nombre': l.get('category_name', ''),
                'periodo': l.get('period_key', ''),
                'quantity': l.get('quantity', 0),
                'accumulated_type': l.get('accumulated_type') if st == 'accumulated' else None,
                'note': l.get('note') if st == 'accumulated' else None,
            })

        result.sort(key=lambda x: abs(x.get('total', 0)), reverse=True)
        return result
