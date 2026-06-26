# tests/test_expected_vs_actual.py
# -*- coding: utf-8 -*-
from odoo.tests.common import SavepointCase, tagged
from odoo import fields
from datetime import date

# ====== CONFIGURA AQUÍ TUS ESPERADOS ======
# Pon números (float/int) donde quieras validar; deja None para omitir.
EXPECTED = {
    "tolerances": {
        "abs": 0.01,     # tolerancia absoluta ($)
        "rel": 0.0005,   # tolerancia relativa (0.05%)
    },
    "by_code": {
        # Ejemplos (reemplaza según tu caso):
        # "BASIC": 2_000_000.00,
        # "AUX000": 162_000.00,
        # "AUX00C": 0.00,
        # "TOTALDEV": 2_162_000.00,   # si quieres validar totales por código
        # "TOTALDED": -172_000.00,    # usa el mismo signo que en tus líneas
        # "NET": 1_990_000.00,
        # "CESANTIAS": None,          # Agregará estos cuando estén implementados
        # "INTERESES": None,
        # "PRIMA": None,
    },
    "totals": {
        # Estos se calculan de todas las líneas:
        # "TOTALDEV": 2_162_000.00,   # suma de positivas
        # "TOTALDED": -172_000.00,    # suma de negativas (normalizado a negativo)
        # "NET": 1_990_000.00,        # dev + ded
    }
}

def approx_equal(a, b, abs_tol=0.01, rel_tol=0.0005):
    if a == b:
        return True
    if a is None or b is None:
        return False
    if abs(a - b) <= abs_tol:
        return True
    denom = max(abs(a), abs(b), 1.0)
    return abs(a - b) / denom <= rel_tol

@tagged('standard', '-at_install')
class TestExpectedVsActual(SavepointCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.emp = cls.env['hr.employee'].create({'name': 'Empleado QA Expected'})
        structure_type = cls.env.ref('lavish_hr_payroll.structure_type_employee')
        calendar = cls.env.ref('resource.resource_calendar_std')

        cls.contract = cls.env['hr.contract'].create({
            'name': 'Contrato QA Expected',
            'employee_id': cls.emp.id,
            'date_start': date.today().replace(day=1),
            'wage': 2_000_000.0,
            'state': 'open',
            'resource_calendar_id': calendar.id,
            'structure_type_id': structure_type.id,
        })

        cls.date_from = fields.Date.to_date(fields.Date.today().replace(day=1))
        # fin de mes robusto (28/29/30/31)
        for d in (31, 30, 29, 28):
            try:
                cls.date_to = fields.Date.to_date(cls.date_from.replace(day=1, month=cls.date_from.month+1) - fields.timedelta(days=1))
                break
            except ValueError:
                continue

    def _build_and_compute(self):
        # Limpia nóminas previas del periodo
        slips = self.env['hr.payslip'].search([
            ('employee_id', '=', self.emp.id),
            ('date_from', '=', self.date_from),
            ('date_to', '=', self.date_to),
        ])
        slips.write({'state': 'draft'})
        slips.unlink()

        struct = self.contract.structure_type_id.default_struct_id or self.contract.structure_type_id
        slip = self.env['hr.payslip'].create({
            'employee_id': self.emp.id,
            'contract_id': self.contract.id,
            'struct_id': struct.id,
            'date_from': self.date_from,
            'date_to': self.date_to,
            'company_id': self.emp.company_id.id,
        })

        # En tu motor, los métodos de regla deberían poblar esto (si no, no pasa nada)
        slip._localdict_rule_logs = []

        if hasattr(slip, 'compute_sheet'):
            slip.compute_sheet()
        elif hasattr(slip, 'action_compute'):
            slip.action_compute()
        else:
            self.fail("hr.payslip no tiene método de cálculo.")

        return slip

    def _collect_actuals(self, slip):
        """
        Devuelve:
          - by_code_lines: totales por code desde líneas (suma si se repite)
          - by_code_logs:  totales por code desde logs (si existen)
          - totals_lines:  TOTALDEV (positivos), TOTALDED (negativos normalizados a negativo), NET
        """
        by_code_lines = {}
        for line in slip.line_ids:
            code = (line.code or "").upper()
            by_code_lines[code] = by_code_lines.get(code, 0.0) + float(line.total or 0.0)

        # Totales desde líneas
        total_dev = sum((float(l.total or 0.0) for l in slip.line_ids if (l.total or 0.0) > 0.0), 0.0)
        total_ded_raw = sum((float(l.total or 0.0) for l in slip.line_ids if (l.total or 0.0) < 0.0), 0.0)
        total_ded = total_ded_raw if total_ded_raw <= 0.0 else -abs(total_ded_raw)
        net = total_dev + total_ded

        totals_lines = {
            "TOTALDEV": total_dev,
            "TOTALDED": total_ded,  # normalizado a negativo
            "NET": net,
        }

        # Desde logs (opcional)
        by_code_logs = {}
        logs = getattr(slip, '_localdict_rule_logs', []) or []
        for log in logs:
            code = (log.get('code') or "").upper()
            out = log.get('output') or {}
            amt = float(out.get('amount') or 0.0)
            if code:
                by_code_logs[code] = amt

        return by_code_lines, by_code_logs, totals_lines

    def test_00_dump_actuals_para_copiar(self):
        """
        Este test siempre pasa y SOLO imprime los valores actuales
        para que puedas copiarlos a EXPECTED.
        """
        slip = self._build_and_compute()
        lines, logs, totals = self._collect_actuals(slip)

        print("\n===== ACTUALES (pégalos en EXPECTED) =====")
        print("by_code (líneas):", {k: round(v, 2) for k, v in sorted(lines.items()) if v != 0})
        if logs:
            print("by_code (logs):  ", {k: round(v, 2) for k, v in sorted(logs.items()) if v != 0})
        print("totals (líneas):  ", {k: round(v, 2) for k, v in totals.items()})
        print("==========================================")
        
        # Información adicional para debug
        print(f"Nómina ID: {slip.id}")
        print(f"Empleado: {slip.employee_id.name}")
        print(f"Período: {slip.date_from} - {slip.date_to}")
        print(f"Salario contrato: {slip.contract_id.wage}")
        print(f"Total líneas: {len(slip.line_ids)}")
        
        # No aserta: sirve como helper de inspección

    def test_10_validate_by_code(self):
        slip = self._build_and_compute()
        lines, logs, totals = self._collect_actuals(slip)
        abs_tol = EXPECTED["tolerances"]["abs"]
        rel_tol = EXPECTED["tolerances"]["rel"]

        for code, expected in (EXPECTED.get("by_code") or {}).items():
            if expected is None:
                continue  # omite si no configuraste este code
            code_u = (code or "").upper()
            actual = None
            # Preferimos exacto por líneas; si no existe, probamos logs
            if code_u in lines:
                actual = lines[code_u]
            elif code_u in logs:
                actual = logs[code_u]

            self.assertIsNotNone(
                actual,
                f"No se encontró el código '{code_u}' ni en líneas ni en logs."
            )
            self.assertTrue(
                approx_equal(expected, actual, abs_tol=abs_tol, rel_tol=rel_tol),
                f"[{code_u}] Esperado={expected:.2f} vs Actual={actual:.2f} (abs_tol={abs_tol}, rel_tol={rel_tol})"
            )

    def test_11_validate_totals(self):
        slip = self._build_and_compute()
        _, _, totals = self._collect_actuals(slip)
        abs_tol = EXPECTED["tolerances"]["abs"]
        rel_tol = EXPECTED["tolerances"]["rel"]

        for key, expected in (EXPECTED.get("totals") or {}).items():
            if expected is None:
                continue
            key_u = key.upper()
            actual = totals.get(key_u)
            self.assertIsNotNone(actual, f"No se pudo calcular '{key_u}' desde líneas.")
            self.assertTrue(
                approx_equal(expected, actual, abs_tol=abs_tol, rel_tol=rel_tol),
                f"[{key_u}] Esperado={expected:.2f} vs Actual={actual:.2f} (abs_tol={abs_tol}, rel_tol={rel_tol})"
            )