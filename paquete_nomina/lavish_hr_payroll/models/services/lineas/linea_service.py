# -*- coding: utf-8 -*-
"""
Servicio de Líneas - Creación y totalización de líneas de nómina
"""

import logging
from collections import defaultdict
from odoo.addons.lavish_hr_payroll.models.utils import round_payroll_amount

_logger = logging.getLogger(__name__)


class LineaService:
    """
    Servicio para crear y totalizar líneas de nómina.
    Centraliza la lógica de creación de hr.payslip.line.
    """

    def __init__(self, env, payslip, batch_ctx=None):
        self.env = env
        self.payslip = payslip
        self.batch_ctx = batch_ctx
        self.contract_id = payslip.contract_id.id
        self.employee_id = payslip.employee_id.id
        self._lineas = {}
        self._totales = {}

    def agregar_linea(self, code, datos):
        """
        Agrega una línea al buffer interno.

        Args:
            code: Código único de la línea
            datos: dict con datos de la línea

        Returns:
            bool indicando si se agregó
        """
        if not code or not datos:
            return False

        # Asegurar campos requeridos
        datos.setdefault('slip_id', self.payslip.id)
        datos.setdefault('contract_id', self.contract_id)
        datos.setdefault('employee_id', self.employee_id)

        self._lineas[code] = datos
        return True

    def agregar_lineas(self, lineas_dict):
        """
        Agrega múltiples líneas desde un diccionario.

        Args:
            lineas_dict: dict {code: datos_linea}
        """
        for code, datos in lineas_dict.items():
            self.agregar_linea(code, datos)

    def crear_linea(self, rule, amount, quantity=1.0, rate=100.0, name=None, **kwargs):
        """
        Crea una línea de nómina a partir de una regla salarial.

        Args:
            rule: hr.salary.rule record
            amount: Monto de la línea
            quantity: Cantidad (default 1.0)
            rate: Porcentaje (default 100.0)
            name: Nombre personalizado (opcional)
            **kwargs: Campos adicionales

        Returns:
            dict con datos de la línea
        """
        if not rule:
            return None

        total = float(round_payroll_amount(amount * quantity * rate / 100.0))

        linea = {
            'sequence': rule.sequence,
            'code': rule.code,
            'name': name or rule.name,
            'salary_rule_id': rule.id,
            'contract_id': self.contract_id,
            'employee_id': self.employee_id,
            'entity_id': False,
            'amount': amount,
            'quantity': quantity,
            'rate': rate,
            'total': total,
            'slip_id': self.payslip.id,
            'run_id': self.payslip.payslip_run_id.id if self.payslip.payslip_run_id else False,
        }

        # Agregar campos adicionales (compatibilidad hacia atrás)
        linea.update(kwargs)

        return linea

    def obtener_lineas(self):
        """
        Obtiene todas las líneas agregadas.

        Returns:
            dict con todas las líneas
        """
        return self._lineas.copy()

    def obtener_linea(self, code):
        """
        Obtiene una línea específica por código.

        Args:
            code: Código de la línea

        Returns:
            dict con datos de la línea o None
        """
        return self._lineas.get(code)

    def eliminar_linea(self, code):
        """
        Elimina una línea del buffer.

        Args:
            code: Código de la línea

        Returns:
            bool indicando si se eliminó
        """
        if code in self._lineas:
            del self._lineas[code]
            return True
        return False

    def calcular_totales(self):
        """
        Calcula los totales por categoría.

        Returns:
            dict con totales por categoría
        """
        self._totales = {
            'BASIC': 0.0,
            'ALW': 0.0,
            'DED': 0.0,
            'GROSS': 0.0,
            'NET': 0.0,
            'SSOCIAL': 0.0,
            'PROVISION': 0.0,
            'COMP': 0.0,
            'por_categoria': defaultdict(float),
        }

        for code, linea in self._lineas.items():
            total = linea.get('total', 0.0)
            cat_code = linea.get('category_code', '')

            self._totales['por_categoria'][cat_code] += total

            # Mapeo a categorías principales
            if cat_code == 'BASIC':
                self._totales['BASIC'] += total
            elif cat_code in ['ALW', 'ALLOWANCE', 'DEVENGO']:
                self._totales['ALW'] += total
            elif cat_code in ['DED', 'DEDUCCION']:
                self._totales['DED'] += total
            elif cat_code == 'GROSS':
                self._totales['GROSS'] += total
            elif cat_code == 'NET':
                self._totales['NET'] += total
            elif cat_code in ['SSOCIAL', 'SS', 'SEGURIDAD']:
                self._totales['SSOCIAL'] += total
            elif cat_code in ['PROVISION', 'PROV']:
                self._totales['PROVISION'] += total
            elif cat_code in ['COMP', 'COMPANY']:
                self._totales['COMP'] += total

        return self._totales

    def obtener_total_categoria(self, categoria):
        """
        Obtiene el total de una categoría específica.

        Args:
            categoria: Código de categoría

        Returns:
            float con el total
        """
        if not self._totales:
            self.calcular_totales()

        return self._totales.get(categoria, self._totales['por_categoria'].get(categoria, 0.0))

    def obtener_devengos(self):
        """
        Obtiene total de devengos (ingresos).

        Returns:
            float con total de devengos
        """
        if not self._totales:
            self.calcular_totales()

        return self._totales['BASIC'] + self._totales['ALW']

    def obtener_deducciones(self):
        """
        Obtiene total de deducciones.

        Returns:
            float con total de deducciones
        """
        if not self._totales:
            self.calcular_totales()

        return abs(self._totales['DED'])

    def obtener_neto(self):
        """
        Calcula el neto a pagar.

        Returns:
            float con el neto
        """
        return self.obtener_devengos() - self.obtener_deducciones()

    def preparar_para_crear(self):
        """
        Prepara las líneas para crear en la base de datos.
        Ordena por secuencia y filtra campos válidos.

        Returns:
            list de dicts listos para create()
        """
        # Campos válidos para hr.payslip.line
        campos_validos = {
            'name', 'sequence', 'code', 'note',
            'salary_rule_id', 'contract_id', 'employee_id', 'slip_id',
            'rate', 'amount', 'quantity', 'total',
            'amount_select', 'amount_fix', 'amount_percentage',
            'partner_id', 'date_from', 'date_to',
        }

        # Obtener campos adicionales del modelo
        PayslipLine = self.env['hr.payslip.line']
        campos_modelo = set(PayslipLine._fields.keys())
        campos_validos = campos_validos | campos_modelo

        lineas_ordenadas = sorted(
            self._lineas.values(),
            key=lambda x: (x.get('sequence', 0), x.get('code', ''))
        )

        resultado = []
        for linea in lineas_ordenadas:
            linea_filtrada = {k: v for k, v in linea.items() if k in campos_validos}
            resultado.append(linea_filtrada)

        return resultado

    def crear_lineas_db(self):
        """
        Crea las líneas en la base de datos.

        Returns:
            recordset de hr.payslip.line creadas
        """
        lineas_vals = self.preparar_para_crear()
        if not lineas_vals:
            return self.env['hr.payslip.line']

        return self.env['hr.payslip.line'].create(lineas_vals)

    def get_resumen(self):
        """
        Obtiene resumen de líneas y totales.

        Returns:
            dict con resumen completo
        """
        totales = self.calcular_totales()

        return {
            'cantidad_lineas': len(self._lineas),
            'devengos': self.obtener_devengos(),
            'deducciones': self.obtener_deducciones(),
            'neto': self.obtener_neto(),
            'totales_categoria': dict(totales['por_categoria']),
            'lineas': [{
                'code': code,
                'name': linea.get('name', ''),
                'amount': linea.get('amount', 0),
                'total': linea.get('total', 0),
                'category': linea.get('category_code', ''),
            } for code, linea in self._lineas.items()]
        }

    def fusionar_linea(self, code, datos, acumular=True):
        """
        Fusiona una línea con una existente del mismo código.

        Args:
            code: Código de la línea
            datos: datos nuevos
            acumular: Si True, suma los montos. Si False, reemplaza.

        Returns:
            dict con línea fusionada
        """
        if code not in self._lineas:
            self._lineas[code] = datos
            return datos

        existente = self._lineas[code]

        if acumular:
            # Sumar montos
            existente['amount'] = existente.get('amount', 0) + datos.get('amount', 0)
            existente['quantity'] = existente.get('quantity', 1) + datos.get('quantity', 0) - 1
            existente['total'] = float(round_payroll_amount(
                existente['amount'] * existente.get('quantity', 1) * existente.get('rate', 100) / 100.0
            ))
        else:
            # Reemplazar
            existente.update(datos)

        return existente

    def agrupar_por_regla(self):
        """
        Agrupa líneas por regla salarial.

        Returns:
            dict {salary_rule_id: [lineas]}
        """
        por_regla = defaultdict(list)
        for code, linea in self._lineas.items():
            rule_id = linea.get('salary_rule_id')
            if rule_id:
                por_regla[rule_id].append(linea)
        return dict(por_regla)

    def filtrar_por_categoria(self, categoria):
        """
        Filtra líneas por categoría.

        Args:
            categoria: Código de categoría o lista de códigos

        Returns:
            dict con líneas filtradas
        """
        if isinstance(categoria, str):
            categoria = [categoria]

        return {
            code: linea
            for code, linea in self._lineas.items()
            if linea.get('category_code') in categoria
        }

    def limpiar(self):
        """Limpia todas las líneas y totales"""
        self._lineas.clear()
        self._totales.clear()
