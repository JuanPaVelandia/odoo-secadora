from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Dict, List, Any

from dateutil.relativedelta import relativedelta
from odoo import models, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)
DAYS_MONTH = 30

# ╔════════════════════════ ParamLoader ═════════════════════════════╗
class ParamLoader:
    _CACHE: Dict[tuple[int, int], Dict[str, float]] = {}

    @classmethod
    def _read(cls, env, company_id: int, year: int) -> Dict[str, float]:
        rec = env['hr.annual.parameters'].get_for_year(
            year,
            company_id=company_id,
            raise_if_not_found=True,
        )
        return {
            'SMMLV_DAILY':   rec.smmlv_daily,
            'TOPE_25_SMMLV': rec.top_twenty_five_smmlv,
            'TOPE_40':       rec.value_porc_statute_1395 / 100,
            'INT_FACTOR':    rec.porc_integral_salary / 100,  # 0.70
        }

    @classmethod
    def for_date(cls, env, d: date) -> Dict[str, float]:
        company_id = env.company.id
        key = (company_id, d.year)
        if key not in cls._CACHE:
            cls._CACHE[key] = cls._read(env, company_id, d.year)
        return cls._CACHE[key]

# ╔════════════════════════ RuleUtils ══════════════════════════════╗
class RuleUtils:
    @staticmethod
    def category_code(rule):
        cat = rule.category_id
        while cat:
            if cat.code in ('DEV_SALARIAL', 'DEV_NO_SALARIAL'):
                return cat.code
            if cat.code in ('INDEM', 'PRESTACIONES_SOCIALES','AUX'):
                return None
            cat = cat.parent_id
        return None

    @staticmethod
    def ausencia_tipo(hstatus):
        mapping = {
            'SLN': 'SLN', 'LICENCIA_NO_REMUNERADA': 'SLN', 'SUSPENSION': 'SLN', 'LNR': 'SLN',
            'IGE': 'IGE', 'INCAPACIDAD_EPS': 'IGE',
            'IRL': 'IRL', 'INCAPACIDAD_ARL': 'IRL',
            'LMA': 'LMA', 'MATERNIDAD': 'LMA', 'LPA': 'LMA', 'PATERNIDAD': 'LMA',
            'VAC': 'VAC', 'VACDISFRUTADAS': 'VAC', 'VACDISFRUTADA': 'VAC', 'VDI': 'VAC', 'VRE': 'VAC',
            'VCO': 'VAC_COMP',  # Vacaciones compensadas en dinero
            'LR': 'LR', 'LICENCIA_REMUNERADA': 'LR', 'LT': 'LR', 'LUTO': 'LR',
            'P': 'OTR', 'PERMISO': 'OTR',
        }
        code = (hstatus.code or '').upper()
        novelty = (getattr(hstatus, 'novelty', '') or '').upper()
        return mapping.get(code, mapping.get(novelty, 'OTR'))
        
    @staticmethod
    def es_vacacion_dinero(hstatus):
        """Determina si es una vacación compensada en dinero."""
        code = (hstatus.code or '').upper()
        novelty = (getattr(hstatus, 'novelty', '') or '').upper()
        return code == 'VCO' or novelty == 'VCO'

# ╔════════════════════ IBCCalculator ═══════════════════════════════╗
class IBCCalculator:
    def __init__(self, env):
        self.env = env

    def _p(self, d: date):
        return ParamLoader.for_date(self.env, d)

    def _ibc_range(self, contract, ini: date, fin: date) -> float:
        lines = self.env['hr.payslip.line'].search([
            ('slip_id.state', 'in', ['done', 'paid']),
            ('slip_id.contract_id', '=', contract.id),
            ('date_from', '>=', ini),
            ('date_from', '<=', fin),
        ])
        base = sum(abs(l.total) for l in lines if l.salary_rule_id.base_seguridad_social)
        nos  = sum(abs(l.total) for l in lines if RuleUtils.category_code(l.salary_rule_id) == 'DEV_NO_SALARIAL')
        extra = max(0.0, nos - (base + nos) * self._p(fin)['TOPE_40'])
        return min(base + extra, self._p(fin)['TOPE_25_SMMLV'])

    def _daily_from_ss(self, contract, ref):
        ini = ref.replace(day=1) - relativedelta(months=1)
        fin = ref.replace(day=1) - timedelta(days=1)
        ss = self.env['hr.executing.social.security'].search([
            ('employee_id', '=', contract.employee_id.id),
            ('slip_id.contract_id', '=', contract.id),
            ('main', '=', True),
            ('k_start', '>=', ini), ('k_start', '<=', fin),
        ])
        if not ss:
            return None
        base = sum(l.nValorBaseSalud for l in ss)
        dias = sum((l.nDiasLiquidados or 0) + (l.nDiasVacaciones or 0) + (l.nDiasLicenciaRenumerada or 0) +
                   (l.nDiasMaternidad or 0) + (l.nDiasIncapacidadEPS or 0) + (l.nDiasIncapacidadARP or 0) -
                   (l.nDiasLicencia or 0) for l in ss)
        return base / dias if dias else None

    # API públicos ---------------------------------------------------
    def daily_prev(self, contract, ref):
        """
        Obtiene el IBC diario del mes anterior.
        
        Args:
            contract: Contrato del empleado
            ref: Fecha de referencia
            
        Returns:
            IBC diario del mes anterior o IBC basado en el salario actual si no hay datos previos
        """
        d = self._daily_from_ss(contract, ref)
        if d and d > 0:
            return d
            
        # Intentar obtener desde nómina del mes anterior
        ini = ref.replace(day=1) - relativedelta(months=1)
        fin = ref.replace(day=1) - timedelta(days=1)
        ibc_mes = self._ibc_range(contract, ini, fin)
        
        if ibc_mes and ibc_mes > 0:
            return ibc_mes / DAYS_MONTH
            
        # Si no hay datos válidos del mes anterior, computar desde el salario actual
        # Esto evita valores IBC cero o muy bajos que afectarían el cálculo de ausencias
        _logger.info(f"No hay IBC previo para contrato {contract.name}. Usando salario actual.")
        return contract.wage / DAYS_MONTH

    def base_diaria(self, salar, nosalar, ref):
        p = self._p(ref)
        extra = max(0.0, nosalar - (salar + nosalar) * p['TOPE_40'])
        return min(salar + extra, p['TOPE_25_SMMLV']) / DAYS_MONTH

# ╔════════════════════ IbdContext ══════════════════════════════════╗
@dataclass
class IbdContext:
    payslip:  'hr.payslip'
    contract: 'hr.contract'
    integral: bool = False

    basic_monto: float = 0.0
    basic_dias:  float = 0.0
    devengos:    float = 0.0
    no_salarial: float = 0.0

    aus_por_tipo:  Dict[str, float] = field(default_factory=dict)
    dias_por_tipo: Dict[str, float] = field(default_factory=dict)

    prev_ibc_daily: float | None = None
    ibc_final:      float = 0.0
    limits_info:    Dict[str, Any] = field(default_factory=dict)
    html:           str = ""

# ╔════════════════ EarningsProcessor ═══════════════════════════════╗
class EarningsProcessor:
    def __init__(self, env):
        self.env = env

    def apply(self, pl_dict, ctx: IbdContext, write=True):
        if not pl_dict:
            return
        for per in pl_dict.values():
            cur = per.get('current_month', {})
            for ent in cur.get('entries', []):
                pl = ent['payslip_id']
                
                # Verificar si es ausencia
                if pl.leave_id:
                    leave_type = pl.leave_id.holiday_status_id
                    ausencia_tipo = RuleUtils.ausencia_tipo(leave_type)
                    es_vacacion = ausencia_tipo in ('VAC', 'VAC_COMP')
                    es_vacacion_dinero = RuleUtils.es_vacacion_dinero(leave_type)
                    
                    # Procesamos todas las ausencias excepto vacaciones disfrutadas
                    # Las vacaciones en dinero sí se procesan aquí como devengo
                    if not es_vacacion or es_vacacion_dinero:
                        continue
                
                # También saltamos las estructuras específicas de vacaciones
                if pl.slip_id and pl.slip_id.struct_id.process == 'vacaciones':
                    continue
                    
                # Procesar según la categoría
                cat = RuleUtils.category_code(pl.salary_rule_id)
                
                if cat == 'BASIC':
                    ctx.basic_monto += pl.total
                    if not ctx.basic_dias:
                        ctx.basic_dias = sum(w.number_of_days for w in ctx.payslip.worked_days_line_ids if w.code == 'WORK100') or DAYS_MONTH
                        
                # Vacaciones disfrutadas se consideran como devengo salarial
                elif cat == 'DEV_SALARIAL' and not getattr(pl.salary_rule_id, 'liquidar_con_base', False):
                    ctx.devengos += pl.total
                    
                    # Si son vacaciones, registramos días para control
                    if pl.leave_id and RuleUtils.ausencia_tipo(pl.leave_id.holiday_status_id) == 'VAC':
                        vac_days = 0
                        for l in pl.leave_id.line_ids:
                            if ctx.payslip.date_from <= l.date <= ctx.payslip.date_to:
                                vac_days += l.days_payslip
                                
                        ctx.aus_por_tipo['VAC'] = ctx.aus_por_tipo.get('VAC', 0.0) + pl.total
                        ctx.dias_por_tipo['VAC'] = ctx.dias_por_tipo.get('VAC', 0.0) + vac_days
                        _logger.info(f"Vacaciones disfrutadas: {vac_days} días, monto: {pl.total}")
                        
                elif cat == 'DEV_NO_SALARIAL':
                    # Excluir si tiene excluir_seguridad_social o excluir_40_porciento_ss
                    rule = pl.salary_rule_id
                    if rule and (rule.excluir_seguridad_social or rule.excluir_40_porciento_ss):
                        continue
                    # Vacaciones compensadas en dinero son no salariales
                    if pl.leave_id and RuleUtils.es_vacacion_dinero(pl.leave_id.holiday_status_id):
                        ctx.no_salarial += pl.total
                        _logger.info(f"Vacaciones compensadas (dinero): {pl.total}")
                    else:
                        ctx.no_salarial += pl.total
                    
                if write:
                    pl.amount_base = pl.total

# ╔══════════════ MultiInputProcessor ══════════════════════════════╗
class MultiInputProcessor:
    """Procesa los inputs múltiples (`rules_multi`) generados por los `@compute`.

    Ignora los que estén relacionados con ausencias (ya los manejará
    `AbsenceProcessor`).
    """

    def __init__(self, env):
        self.env = env

    def apply(self, rules_multi, ctx: IbdContext):
        if not rules_multi:
            return
        for rm in rules_multi.values():
            cur = rm.get('current', {})
            rule = cur.get('object')
            if not rule:
                continue
            if not rule:
                continue
            # Si hay ausencias asociadas a este input múltiple lo dejamos a AbsenceProcessor
            if cur.get('leave'):
                continue
            total = cur.get('total', 0.0)
            cat = RuleUtils.category_code(rule)
            
            if cat == 'DEV_SALARIAL':
                # Excluir si tiene excluir_seguridad_social
                if rule.excluir_seguridad_social:
                    continue
                ctx.devengos += total
            elif cat == 'DEV_NO_SALARIAL':
                # Excluir si tiene excluir_seguridad_social o excluir_40_porciento_ss
                if rule.excluir_seguridad_social or rule.excluir_40_porciento_ss:
                    continue
                ctx.no_salarial += total

# ╔══════════════════ AbsenceProcessor ═════════════════════════════╗
class AbsenceProcessor:
    """Procesa ausencias del período de nómina.

    * Usa bandera `liquidar_con_base` de la regla para decidir si el diario
      proviene del IBC mes anterior (`IBCCalculator.daily_prev`) o del mes
      actual (`IBCCalculator.base_diaria`).
    * Suspensión (SLN) no suma al IBC y descuenta días.
    """

    def __init__(self, env):
        self.env = env

    # ---------------------------------------------------------------- collect
    def _collect(self, pl_dict) -> Dict[int, List['hr.payslip.line']]:
        res: Dict[int, List['hr.payslip.line']] = {}
        if not pl_dict:
            return res
        for per in pl_dict.values():
            cur = per.get('current_month', {})
            for ent in cur.get('entries', []):
                pl = ent['payslip_id']
                # Solo procesamos ausencias que NO sean vacaciones disfrutadas,
                # ya que estas ahora se manejan en EarningsProcessor
                # Las vacaciones compensadas en dinero no tienen ausencia real
                if pl.leave_id:
                    ausencia_tipo = RuleUtils.ausencia_tipo(pl.leave_id.holiday_status_id)
                    es_vacacion_dinero = RuleUtils.es_vacacion_dinero(pl.leave_id.holiday_status_id)
                    
                    if ausencia_tipo != 'VAC' or es_vacacion_dinero:
                        res.setdefault(pl.leave_id.id, []).append(pl)
        return res

    # ---------------------------------------------------------------- apply
    def apply(self, pl_dict, ctx: IbdContext, ibc_calc: IBCCalculator, write=True):
        # Recolectar ausencias
        leave_map = self._collect(pl_dict)
        if not leave_map:
            return
        
        # Función para verificar si una fecha está en el período
        def day_in(d):
            return ctx.payslip.date_from <= d <= ctx.payslip.date_to
        
        # Parámetros básicos
        ref = ctx.payslip.date_to
        params = ParamLoader.for_date(self.env, ref)
        smmlv_d = params['SMMLV_DAILY']
        base_d = ibc_calc.base_diaria(ctx.basic_monto + ctx.devengos, ctx.no_salarial, ref)
        cached_prev = None
        
        # Procesar cada ausencia una vez por su ID único
        for lv_id, lines in leave_map.items():
            for pl in lines:
                # Procesamos cada línea de payslip individualmente
                leave = pl.leave_id
                typ = RuleUtils.ausencia_tipo(leave.holiday_status_id)
                
                # Obtener tasa según la secuencia
                rate, _ = leave.holiday_status_id.get_rate_concept_id(pl.sequence)
                
                # Determinar valor diario para esta línea
                if pl.salary_rule_id.liquidar_con_base:
                    # Si liquidar_con_base está activo, intentamos usar el IBC mes anterior
                    if cached_prev is None:
                        cached_prev = ibc_calc.daily_prev(ctx.contract, ref)
                        ctx.prev_ibc_daily = cached_prev
                    
                    # Si no hay datos del mes anterior o son insuficientes, usamos el mes actual
                    if not cached_prev or cached_prev < (smmlv_d * 0.5):  # Umbral mínimo
                        _logger.info(f"IBC mes anterior no disponible o muy bajo ({cached_prev}). Usando base actual para {leave.name}")
                        val_dia = max(base_d * rate, smmlv_d)
                    else:
                        val_dia = max(cached_prev * rate, smmlv_d)
                else:
                    # Si no tiene liquidar_con_base, siempre usamos el mes actual
                    val_dia = max(base_d * rate, smmlv_d)
                
                # Contar días en período y calcular montos
                dias_en_periodo = 0
                for l in leave.line_ids:
                    if day_in(l.date):
                        dias_en_periodo += l.days_payslip
                
                # Calcular valores
                monto = 0.0 if typ == 'SLN' else val_dia * dias_en_periodo
                valor_base = round(val_dia * dias_en_periodo, 2)
                
                # Actualizar base si se pide
                if write:
                    pl.amount_base = valor_base
                
                # Actualizar contadores en el contexto
                ctx.aus_por_tipo[typ] = ctx.aus_por_tipo.get(typ, 0.0) + monto
                ctx.dias_por_tipo[typ] = ctx.dias_por_tipo.get(typ, 0.0) + dias_en_periodo           

# ╔════════════ VacationPrevProcessor ══════════════════════════════╗
class VacationPrevProcessor:
    """Ajusta vacaciones iniciadas antes del mes y continuadas dentro del slip."""

    def __init__(self, env):
        self.env = env

    def _collect_prev(self, pl_dict):
        res = []
        if not pl_dict:
            return res
        for per in pl_dict.values():
            bef = per.get('before_month', {})
            for ent in bef.get('entries', []):
                pl = ent['payslip_id']
                # Solo procesar vacaciones disfrutadas (no las compensadas en dinero)
                if (pl.leave_id and 
                    getattr(pl.leave_id.holiday_status_id, 'is_vacation', False) and 
                    not RuleUtils.es_vacacion_dinero(pl.leave_id.holiday_status_id)):
                    res.append(pl)
        return res

    def apply(self, pl_dict, ctx: IbdContext, ibc_calc: IBCCalculator, write=True):
        pls = self._collect_prev(pl_dict)
        if not pls:
            return
            
        ref = ctx.payslip.date_to
        params = ParamLoader.for_date(self.env, ref)
        smmlv_d = params['SMMLV_DAILY']
        
        # Obtener IBC diario del mes anterior
        dp = ibc_calc.daily_prev(ctx.contract, ref)
        
        # Si no hay IBC previo válido, usar el actual
        if not dp or dp < (smmlv_d * 0.5):  # Umbral mínimo (50% del SMMLV diario)
            _logger.info(f"IBC mes anterior no disponible o muy bajo para vacaciones previas. Usando base actual.")
            base_d = ibc_calc.base_diaria(ctx.basic_monto + ctx.devengos, ctx.no_salarial, ref)
            dp = max(base_d, smmlv_d)
            
        ctx.prev_ibc_daily = dp
        
        for pl in pls:
            rate, _ = pl.leave_id.holiday_status_id.get_rate_concept_id(pl.sequence)
            dias = pl.leave_id.number_of_days_in_payslip or 1
            val = max(dp * rate, smmlv_d) * dias
            ctx.aus_por_tipo['VAC_PREV'] = ctx.aus_por_tipo.get('VAC_PREV', 0.0) + val
            ctx.dias_por_tipo['VAC_PREV'] = ctx.dias_por_tipo.get('VAC_PREV', 0.0) + dias
            if write:
                pl.amount_base = val

# ╔════════════════════ HtmlBuilder ════════════════════════════════╗
class HtmlBuilder:
    @staticmethod
    def money(v):
        return "${:,.0f}".format(v).replace(',', '.')

    @classmethod
    def render(cls, ctx: IbdContext):
        rows = [
            ('BÁSICO', int(ctx.basic_dias), ctx.basic_monto),
            ('DEVENGOS', '-', ctx.devengos),
        ]
        for typ in sorted(ctx.aus_por_tipo):
            rows.append((typ, int(ctx.dias_por_tipo.get(typ, 0)), ctx.aus_por_tipo[typ]))
        rows.append(('NO SALARIAL', '-', ctx.no_salarial))
        total = sum(r[2] for r in rows)

        h = ["<div class='p-3 border rounded bg-light'>",
             "<h5>Detalle devengado e IBC</h5>",
             "<table class='table table-sm'>",
             "<thead><tr><th>Concepto</th><th class='text-end'>Días</th><th class='text-end'>Valor</th></tr></thead><tbody>"]
        for lbl, d, v in rows:
            h.append(f"<tr><td>{lbl}</td><td class='text-end'>{d}</td><td class='text-end'>{cls.money(v)}</td></tr>")
        h.append(f"<tr class='table-dark'><td><strong>TOTAL</strong></td><td></td><td class='text-end'>{cls.money(total)}</td></tr>")
        if ctx.prev_ibc_daily:
            h.append(f"<tr><td colspan='2'><b>IBC diario mes anterior</b></td><td class='text-end'>{cls.money(ctx.prev_ibc_daily)}</td></tr>")
        h.append(f"<tr><td colspan='2'><b>IBC mes actual</b></td><td class='text-end'>{cls.money(ctx.ibc_final)}</td></tr>")
        if ctx.integral:
            h.append("<tr><td colspan='3' class='text-warning'>Salario integral – factor 70 %</td></tr>")
        if ctx.limits_info.get('applied_40'):
            h.append(f"<tr><td colspan='3' class='text-info'>Se aplicó límite 40 % – excedente {cls.money(ctx.limits_info['extra_40'])}</td></tr>")
        if ctx.limits_info.get('applied_25'):
            h.append("<tr><td colspan='3' class='text-info'>Aplicado tope 25 SMMLV.</td></tr>")
        h.append("</tbody></table></div>")
        return ''.join(h)

# ╔══════════════ PayrollIbdService ════════════════════════════════╗
class PayrollIbdService(models.AbstractModel):
    _name = 'payroll.ibd.service'
    _description = 'Motor de cálculo IBD completo'

    def compute(self, localdict, payslip: 'hr.payslip', write_lines=True):
        """
        Método principal que orquesta todo el proceso de cálculo del IBC.
        
        Fórmula general:
        IBC = BÁSICO + DEVENGOS + VACACIONES DISFRUTADAS + AUSENCIAS (excepto SLN) + EXCEDENTE_40%
        
        Args:
            localdict: Diccionario con variables y reglas para el cálculo
            payslip: Recibo de nómina del empleado
            write_lines: Si se deben actualizar las líneas de nómina
            
        Returns:
            Contexto con los resultados del cálculo
        """
        contract = payslip.contract_id
        ctx = IbdContext(payslip=payslip, contract=contract, integral=(contract.modality_salary == 'integral'))
        ibc_calc = IBCCalculator(self.env)

        # 1) ejecutar procesadores ------------------------------------------------
        # Procesar devengos básicos (incluye vacaciones disfrutadas)
        ep = EarningsProcessor(self.env)
        ep.apply(localdict.get('payslip_lines', {}), ctx, write_lines)
        
        # Procesar inputs múltiples
        mp = MultiInputProcessor(self.env)
        mp.apply(localdict.get('rules_multi', {}), ctx)
        
        # Procesar ausencias (excepto vacaciones disfrutadas)
        ap = AbsenceProcessor(self.env)
        ap.apply(localdict.get('payslip_lines', {}), ctx, ibc_calc, write_lines)
        
        # Procesar vacaciones iniciadas antes del período
        vp = VacationPrevProcessor(self.env)
        vp.apply(localdict.get('payslip_lines', {}), ctx, ibc_calc, write_lines)

        # 2) cálculo de IBC -----------------------------------------------------
        # Nota: las vacaciones disfrutadas ya están en ctx.devengos y también en ctx.aus_por_tipo['VAC'],
        # así que debemos evitar contarlas dos veces.
        
        # Sumamos todos los componentes salariales
        # - Básico
        # - Otros devengos salariales 
        # - Ausencias remuneradas (excepto SLN)
        # Evitamos sumar VAC que ya está en devengos
        ausencias_suma = sum(v for k, v in ctx.aus_por_tipo.items() 
                            if k != 'SLN' and k != 'VAC' and k != 'VAC_COMP')
        
        total_salarial = ctx.basic_monto + ctx.devengos + ausencias_suma
        
        # Para auditoría
        _logger.info(f"""
        Componentes IBC:
        - Básico: {ctx.basic_monto}
        - Devengos: {ctx.devengos} (incluye vacaciones disfrutadas: {ctx.aus_por_tipo.get('VAC', 0)})
        - Ausencias (exc. SLN/VAC): {ausencias_suma}
        - No salarial: {ctx.no_salarial}
        """)
        
        # Si es salario integral, aplicar 70%
        if ctx.integral:
            factor_int = ParamLoader.for_date(self.env, payslip.date_to)['INT_FACTOR']
            total_salarial *= factor_int
            
        pvals = ParamLoader.for_date(self.env, payslip.date_to)

        # Calcular excedente del 40% para no salariales (Ley 1393)
        extra_40 = max(0.0, ctx.no_salarial - (total_salarial + ctx.no_salarial) * pvals['TOPE_40'])
        ibc_pre = total_salarial + extra_40
        
        # Aplicar tope 25 SMMLV
        ibc_final = min(ibc_pre, pvals['TOPE_25_SMMLV'])

        ctx.ibc_final = ibc_final
        ctx.limits_info = {
            'extra_40': extra_40,
            'applied_40': extra_40 > 0,
            'tope25': pvals['TOPE_25_SMMLV'],
            'applied_25': ibc_final < ibc_pre,
        }

        # 3) HTML --------------------------------------------------------------
        ctx.html = HtmlBuilder.render(ctx)

        # Opcional: escribir en el payslip para auditoría
        if write_lines and hasattr(payslip, 'ibc_html'):
            payslip.ibc_html = ctx.html

        return ctx
