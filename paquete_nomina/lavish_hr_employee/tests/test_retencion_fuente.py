# -*- coding: utf-8 -*-
"""
Tests para retención en la fuente (Art. 383, 386, 206 ET).

Tabla de retención (rangos en UVT — Decreto 2231/2023 y ss.):
  0   –  95 UVT:  0%
  95  – 150 UVT: 19%  base: (base - 95)*19% + 0   UVT
  150 – 360 UVT: 28%  base: (base -150)*28% + 10  UVT
  360 – 640 UVT: 33%  base: (base -360)*33% + 69  UVT
  640 – 945 UVT: 35%  base: (base -640)*35% + 162 UVT
  945 –2300 UVT: 37%  base: (base -945)*37% + 268 UVT
 2300 –   ∞ UVT: 39%  base: (base-2300)*39% + 770 UVT
"""
from types import SimpleNamespace
from odoo.tests.common import TransactionCase, tagged

# UVT 2025 (Resolución DIAN 187/2024)
UVT_2025 = 47_065.0

TABLA = [
    (0,    95,   0,    0,   0),
    (95,  150,  19,   95,   0),
    (150, 360,  28,  150,  10),
    (360, 640,  33,  360,  69),
    (640, 945,  35,  640, 162),
    (945, 2300, 37,  945, 268),
    (2300, float('inf'), 39, 2300, 770),
]


def aplicar_tabla(base_uvt, uvt_value):
    """Implementación directa de la tabla Art. 383 ET para verificación."""
    for desde, hasta, tarifa, resta, suma in TABLA:
        if desde <= base_uvt < hasta:
            if desde == 0:
                return 0.0
            return (((base_uvt - resta) * (tarifa / 100.0)) + suma) * uvt_value
    return 0.0


def _make_annual_params(uvt=UVT_2025):
    return SimpleNamespace(
        value_uvt=uvt,
        tope_renta_exenta_25_mensual=240,     # 240 UVT mensual
        tope_limite_global_mensual=1340 / 12,  # ~111.6 UVT mensual
        tope_dependientes_mensual=32,
        tope_medicina_prepagada_mensual=16,
        tope_intereses_vivienda_mensual=100,
    )


def _make_contract_p1(retention_procedure='100'):
    return SimpleNamespace(
        retention_procedure=retention_procedure,
        rtf_rate=0.0,
    )


# ─── Tests de tabla de retención (sin BD) ────────────────────────────────────

class TestTablaRetencion:
    """Verificaciones directas de la tabla Art. 383 ET."""

    UVT = UVT_2025

    def test_rango_cero_no_retiene(self):
        # Base de 90 UVT → rango 0-95 → 0%
        assert aplicar_tabla(90, self.UVT) == 0.0

    def test_limite_inferior_rango_cero(self):
        assert aplicar_tabla(0, self.UVT) == 0.0

    def test_rango_19_pct_base_100_uvt(self):
        # 100 UVT en rango 95-150 → (100-95)*19% + 0 = 0.95 UVT × valor_uvt
        esperado = ((100 - 95) * 0.19 + 0) * self.UVT
        assert abs(aplicar_tabla(100, self.UVT) - esperado) < 1.0

    def test_rango_28_pct_base_200_uvt(self):
        esperado = ((200 - 150) * 0.28 + 10) * self.UVT
        assert abs(aplicar_tabla(200, self.UVT) - esperado) < 1.0

    def test_rango_33_pct_base_400_uvt(self):
        esperado = ((400 - 360) * 0.33 + 69) * self.UVT
        assert abs(aplicar_tabla(400, self.UVT) - esperado) < 1.0

    def test_rango_35_pct_base_800_uvt(self):
        esperado = ((800 - 640) * 0.35 + 162) * self.UVT
        assert abs(aplicar_tabla(800, self.UVT) - esperado) < 1.0

    def test_rango_37_pct_base_1000_uvt(self):
        esperado = ((1000 - 945) * 0.37 + 268) * self.UVT
        assert abs(aplicar_tabla(1000, self.UVT) - esperado) < 1.0

    def test_rango_39_pct_base_2500_uvt(self):
        esperado = ((2500 - 2300) * 0.39 + 770) * self.UVT
        assert abs(aplicar_tabla(2500, self.UVT) - esperado) < 1.0

    def test_tabla_es_progresiva(self):
        # A mayor base, mayor retención
        rets = [aplicar_tabla(b, self.UVT) for b in [0, 100, 200, 400, 800, 1000, 2500]]
        for i in range(1, len(rets)):
            assert rets[i] >= rets[i - 1]

    def test_limite_exacto_95_uvt(self):
        # En 95 exacto entra al rango 19% pero resta_uvt = 95 → resultado = suma_uvt × UVT = 0
        assert aplicar_tabla(95, self.UVT) == 0.0

    def test_limite_exacto_150_uvt(self):
        # Justo en 150 entra al rango 28%
        esperado = ((150 - 150) * 0.28 + 10) * self.UVT
        assert abs(aplicar_tabla(150, self.UVT) - esperado) < 1.0


# ─── Tests de renta exenta 25% (Art. 206 num. 10 ET) ─────────────────────────

class TestRentaExenta25:

    UVT = UVT_2025
    TOPE_MENSUAL_UVT = 240

    def _calcular_25(self, subtotal, uvt=UVT_2025, tope_uvt=240):
        valor = subtotal * 0.25
        tope = tope_uvt * uvt
        return min(valor, tope)

    def test_25_pct_sin_tope(self):
        subtotal = 4_000_000.0
        r = self._calcular_25(subtotal)
        self.assertAlmostEqual = lambda a, b, d: abs(a - b) <= d
        assert abs(r - subtotal * 0.25) < 1.0

    def test_25_pct_con_tope_240_uvt(self):
        # Salario muy alto → queda topado en 240 UVT
        subtotal = 100_000_000.0
        r = self._calcular_25(subtotal)
        tope = 240 * self.UVT
        assert abs(r - tope) < 1.0

    def test_tope_exacto_240_uvt(self):
        # Subtotal donde 25% = 240 UVT exacto
        subtotal_exacto = 240 * self.UVT / 0.25
        r = self._calcular_25(subtotal_exacto)
        assert abs(r - 240 * self.UVT) < 1.0

    def test_25_pct_smmlv(self):
        smmlv = 1_423_500.0
        r = self._calcular_25(smmlv)
        assert abs(r - smmlv * 0.25) < 1.0


# ─── Tests de integración con modelo Odoo ────────────────────────────────────

@tagged('standard', 'retencion_fuente', 'post_install', '-at_install')
class TestRetencionFuente(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.annual_params = _make_annual_params()

    def _aplicar_tabla_via_modulo(self, base_uvt, subtotal_pesos, contract=None):
        """Invoca _aplicar_tabla_retencion_ret del modelo."""
        rule = self.env['hr.salary.rule.retenciones'].browse([])
        c = contract or _make_contract_p1()
        return rule._aplicar_tabla_retencion_ret(base_uvt, subtotal_pesos, self.annual_params, c)

    def test_sin_retencion_bajo_95_uvt(self):
        retencion, rate, _ = self._aplicar_tabla_via_modulo(90, 90 * UVT_2025)
        self.assertEqual(retencion, 0.0)
        self.assertEqual(rate, 0)

    def test_retencion_rango_19_pct(self):
        base_uvt = 120.0
        retencion, rate, _ = self._aplicar_tabla_via_modulo(base_uvt, base_uvt * UVT_2025)
        esperado = ((120 - 95) * 0.19 + 0) * UVT_2025
        self.assertAlmostEqual(retencion, esperado, delta=1.0)
        self.assertEqual(rate, 19)

    def test_retencion_rango_28_pct(self):
        base_uvt = 250.0
        retencion, rate, _ = self._aplicar_tabla_via_modulo(base_uvt, base_uvt * UVT_2025)
        esperado = ((250 - 150) * 0.28 + 10) * UVT_2025
        self.assertAlmostEqual(retencion, esperado, delta=1.0)
        self.assertEqual(rate, 28)

    def test_procedimiento_2_tasa_fija(self):
        contract = SimpleNamespace(retention_procedure='102', rtf_rate=20.0)
        subtotal = 5_000_000.0
        retencion, rate, info = self._aplicar_tabla_via_modulo(100, subtotal, contract)
        self.assertAlmostEqual(retencion, subtotal * 0.20, delta=1.0)
        self.assertEqual(rate, 20.0)
        self.assertEqual(info['procedimiento'], '102')

    def test_retencion_positiva_sobre_95_uvt(self):
        # Cualquier base > 95 UVT debe generar retención > 0
        base_uvt = 96.0
        retencion, _, _ = self._aplicar_tabla_via_modulo(base_uvt, base_uvt * UVT_2025)
        self.assertGreater(retencion, 0)

    def test_renta_exenta_25_sin_tope(self):
        rule = self.env['hr.salary.rule.retenciones'].browse([])
        subtotal = 3_000_000.0
        r = rule._calcular_renta_exenta_25_ret(subtotal, self.annual_params)
        self.assertAlmostEqual(r['valor_aplicado'], subtotal * 0.25, delta=1.0)

    def test_renta_exenta_25_con_tope_240_uvt(self):
        rule = self.env['hr.salary.rule.retenciones'].browse([])
        subtotal = 200_000_000.0
        r = rule._calcular_renta_exenta_25_ret(subtotal, self.annual_params)
        tope = 240 * UVT_2025
        self.assertAlmostEqual(r['valor_aplicado'], tope, delta=1.0)
