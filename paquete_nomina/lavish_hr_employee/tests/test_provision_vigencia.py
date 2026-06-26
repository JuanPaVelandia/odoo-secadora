# -*- coding: utf-8 -*-

from datetime import date
from types import SimpleNamespace
from unittest import SkipTest
from unittest.mock import patch

from odoo.tests.common import TransactionCase, tagged


@tagged('standard', 'provision_vigencia', 'post_install', '-at_install')
class TestProvisionVigencia(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.partner = cls.env['res.partner'].create({
            'name': 'Empleado QA Provision Vigencia',
        })
        cls.employee = cls.env['hr.employee'].create({
            'name': 'Empleado QA Provision Vigencia',
            'company_id': cls.company.id,
            'work_contact_id': cls.partner.id,
        })
        cls.structure = cls.env['hr.payroll.structure'].search([], limit=1)
        if not cls.structure:
            raise SkipTest('No existe una estructura de nómina disponible para crear la regla salarial de prueba.')
        cls.category = cls.env['hr.salary.rule.category'].create({
            'name': 'QA Provision Vigencia',
            'code': 'QAPRVVIG',
        })
        cls.rule = cls.env['hr.salary.rule'].create({
            'name': 'Provision Vigencia QA',
            'code': 'PRV_QA_VIG',
            'sequence': 10,
            'struct_id': cls.structure.id,
            'category_id': cls.category.id,
            'condition_select': 'none',
            'amount_select': 'fix',
            'amount_fix': 0.0,
            'type_concepts': 'contrato',
        })
        cls.provision_account = cls.env['account.account'].create({
            'name': 'Provision Vigencia QA',
            'code': '99126001',
            'account_type': 'liability_current',
            'company_ids': [(6, 0, cls.company.ids)],
        })
        cls.counterpart_account = cls.env['account.account'].create({
            'name': 'Contra Provision Vigencia QA',
            'code': '99126002',
            'account_type': 'expense',
            'company_ids': [(6, 0, cls.company.ids)],
        })
        cls.env['hr.salary.rule.accounting'].create({
            'salary_rule': cls.rule.id,
            'company': cls.company.id,
            'credit_account': cls.provision_account.id,
            'debit_account': cls.counterpart_account.id,
        })
        cls.journal = cls.env['account.journal'].search([
            ('type', '=', 'general'),
            ('company_id', '=', cls.company.id),
        ], limit=1)
        if not cls.journal:
            cls.journal = cls.env['account.journal'].create({
                'name': 'Journal QA Provision',
                'code': 'QAPV',
                'type': 'general',
                'company_id': cls.company.id,
            })

    def _create_move(self, amount, move_date):
        move = self.env['account.move'].create({
            'move_type': 'entry',
            'journal_id': self.journal.id,
            'date': move_date,
            'line_ids': [
                (0, 0, {
                    'name': 'Provision QA debit',
                    'account_id': self.counterpart_account.id,
                    'debit': amount,
                    'credit': 0.0,
                }),
                (0, 0, {
                    'name': 'Provision QA credit',
                    'account_id': self.provision_account.id,
                    'partner_id': self.partner.id,
                    'debit': 0.0,
                    'credit': amount,
                }),
            ],
        })
        move.action_post()
        return move

    def test_obtener_saldo_contable_filtra_por_vigencia_actual(self):
        self._create_move(1600036.0, date(2025, 12, 31))
        self._create_move(94444.0, date(2026, 1, 31))

        slip = SimpleNamespace(id=501, date_from=date(2026, 1, 1))
        saldo = self.rule._obtener_saldo_contable_provision({
            'employee': self.employee,
            'slip': slip,
        }, self.rule.code)

        self.assertEqual(
            saldo,
            94444.0,
            'El saldo contable solo debe considerar movimientos de la vigencia 2026.',
        )

    def test_get_total_previous_provision_limita_al_rango_vigente(self):
        self._create_move(1600036.0, date(2025, 12, 31))
        january_move = self._create_move(94444.0, date(2026, 1, 31))
        self._create_move(50000.0, date(2026, 2, 15))

        slip = SimpleNamespace(id=502, date_from=date(2026, 2, 1))
        total, line_ids = self.rule._get_total_previous_provision(
            {'slip': slip, 'employee': self.employee},
            date(2026, 1, 1),
            date(2026, 1, 31),
            self.rule.code,
        )

        expected_line_ids = january_move.line_ids.filtered(
            lambda line: line.account_id == self.provision_account and line.partner_id == self.partner
        ).ids

        self.assertEqual(
            total,
            94444.0,
            'El acumulado previo solo debe sumar lo ya provisionado en el rango vigente.',
        )
        self.assertEqual(
            line_ids,
            expected_line_ids,
            'Solo deben devolverse las líneas contables del rango vigente consultado.',
        )

    def test_calculate_provision_liquidacion_no_descuenta_saldo_contable(self):
        annual_parameters = SimpleNamespace(
            smmlv_monthly=1300000.0,
            transportation_assistance_monthly=162000.0,
            provision_days_method='periodo',
            provision_quincenal_mode='second_only',
        )
        contract = SimpleNamespace(
            id=701,
            sequence='CTR-QA',
            contract_type_id=False,
            modality_salary='basico',
            date_start=date(2025, 1, 1),
            date_end=False,
            modality_aux='no',
            only_wage='wage',
            not_pay_auxtransportation=False,
            not_validate_top_auxtransportation=False,
            full_auxtransportation_settlement=False,
            wage=3000000.0,
        )
        struct = SimpleNamespace(id=1, name='Contrato', process='contrato')
        slip = SimpleNamespace(
            id=702,
            struct_process='contrato',
            struct_id=struct,
            date_from=date(2026, 1, 1),
            date_to=date(2026, 1, 31),
            employee_id=self.employee,
            use_manual_days=False,
            manual_days=0.0,
            use_manual_vacation_days=False,
            manual_vacation_days=0.0,
            leave_days_ids=[],
            worked_days_line_ids=[],
            line_ids=[],
        )
        data_payslip = {
            'employee': self.employee,
            'contract': contract,
            'slip': slip,
            'annual_parameters': annual_parameters,
            'rules': {},
        }
        config_params = {
            'simple_provisions': True,
            'prst_wo_susp': False,
            'prst_wo_absences': False,
            'promedio_detectar_cambios': False,
            'prima_incluye_auxilio': False,
            'cesantias_incluye_auxilio': False,
            'vacaciones_incluye_auxilio': False,
            'aux_prst': False,
        }
        salary_result = {
            'salario_total': 3000000.0,
            'dias_pagados': 30.0,
            'salario_mensual_actual': 3000000.0,
            'franjas': [],
            'hubo_cambio_salario': False,
        }

        with patch.object(type(self.rule), '_validar_condiciones_prestacion', return_value={
            'aplica': True,
            'validaciones': [],
            'warnings': [],
            'config_override': {},
        }), patch.object(
            type(self.rule), '_aprendiz_tiene_prestaciones', return_value=(True, '')
        ), patch.object(
            type(self.rule), '_get_provision_config_params', return_value=config_params
        ), patch.object(
            type(self.rule), '_get_biweekly_context', return_value=(False, '')
        ), patch.object(
            type(self.rule), '_provision_incluye_auxilio', return_value={'aplica': False}
        ), patch.object(
            type(self.rule), '_obtener_saldo_contable_provision', return_value=1600036.0
        ), patch.object(
            type(self.rule), '_obtener_valor_liquidacion', return_value=94444.0
        ), patch.object(
            type(self.env['hr.salary.rule.basic']),
            '_calcular_salario_periodo_con_cambios',
            return_value=salary_result,
        ), patch.object(
            type(self.env['hr.salary.rule.aux']),
            '_calcular_base_validacion_tope',
            return_value=0.0,
        ):
            amount, quantity, rate, name, _, data_visual = self.rule._calculate_provision(
                data_payslip, 'cesantias'
            )

        self.assertEqual(
            amount,
            94444.0,
            'La liquidación debe devolver el valor calculado completo sin descontar saldo contable histórico.',
        )
        self.assertEqual(quantity, 1)
        self.assertEqual(rate, 100)
        self.assertNotIn('SALDO CONTABLE', name)
        self.assertEqual(data_visual['saldo_contable'], 1600036.0)
        self.assertEqual(data_visual['ajuste'], 0.0)
        self.assertEqual(data_visual['valor_liquidacion'], 94444.0)
