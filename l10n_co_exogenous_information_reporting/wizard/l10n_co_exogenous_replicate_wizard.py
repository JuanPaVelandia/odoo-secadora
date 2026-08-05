# -*- coding: utf-8 -*-
import logging

from odoo import api, fields, models, _, Command
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class L10ncoExogenousReplicateWizard(models.TransientModel):
    _name = "l10n_co.exogenous_replicate_wizard"
    _description = "Replica conceptos exógena y retenciones a otras compañías"

    source_company_id = fields.Many2one(
        'res.company', string='Compañía origen', required=True,
        default=lambda self: self.env.company,
    )
    target_company_ids = fields.Many2many(
        'res.company', string='Compañías destino', required=True,
        domain="[('id', '!=', source_company_id)]",
    )
    replicate_concepts = fields.Boolean(string='Replicar conceptos exógena', default=True)
    replicate_retentions = fields.Boolean(string='Replicar retenciones', default=True)
    replicate_certificate_configs = fields.Boolean(
        string='Replicar config. de certificados (retención)', default=True)
    replicate_income_cert_configs = fields.Boolean(
        string='Replicar config. certificados de ingresos', default=True)
    overwrite = fields.Boolean(
        string='Sobrescribir si existe',
        help='Si la compañía destino ya tiene un concepto/retención con el mismo código/nombre, '
             'actualizar sus campos. Si está apagado, se omite.',
    )
    dry_run = fields.Boolean(
        string='Solo simular (no aplica cambios)', default=True,
    )
    result_log = fields.Text(string='Resultado', readonly=True)

    def _replicate_concepts(self, target_company):
        """Replica l10n_co.exogenous_concept del origen al destino."""
        Concept = self.env['l10n_co.exogenous_concept'].sudo()
        source_concepts = Concept.with_company(self.source_company_id).search([
            ('company_id', '=', self.source_company_id.id),
        ])
        created, updated, skipped = 0, 0, 0
        for c in source_concepts:
            existing = Concept.with_company(target_company).search([
                ('company_id', '=', target_company.id),
                ('code', '=', c.code),
            ], limit=1)
            vals = {
                'name': c.name, 'code': c.code, 'format_id': c.format_id.id,
                'active': c.active, 'report_with_informan_nit': c.report_with_informan_nit,
                'company_id': target_company.id,
            }
            if existing:
                if self.overwrite:
                    if not self.dry_run:
                        existing.write(vals)
                    updated += 1
                else:
                    skipped += 1
            else:
                if not self.dry_run:
                    Concept.create(vals)
                created += 1
        return f'  Conceptos: creados={created}, actualizados={updated}, saltados={skipped} (de {len(source_concepts)})'

    def _map_account(self, account, target_company):
        if not account:
            return False
        return self.env['account.account'].sudo().with_company(target_company).search([
            ('code', '=', account.code),
            ('company_id', '=', target_company.id),
        ], limit=1)

    def _replicate_retentions(self, target_company):
        """Replica account.tax con l10n_co_exo_is_retention=True."""
        Tax = self.env['account.tax'].sudo()
        source_taxes = Tax.with_company(self.source_company_id).search([
            ('company_id', '=', self.source_company_id.id),
            ('l10n_co_exo_is_retention', '=', True),
        ])
        created, updated, skipped, account_warnings = 0, 0, 0, 0
        for t in source_taxes:
            existing = Tax.with_company(target_company).search([
                ('company_id', '=', target_company.id),
                ('name', '=', t.name),
            ], limit=1)
            base_vals = {
                'name': t.name, 'description': t.description,
                'type_tax_use': t.type_tax_use, 'amount_type': t.amount_type,
                'amount': t.amount, 'price_include': t.price_include,
                'include_base_amount': t.include_base_amount,
                'l10n_co_exo_is_retention': True,
                'l10n_co_exo_is_mayor_valor': t.l10n_co_exo_is_mayor_valor,
                'codigo_dian': t.codigo_dian if 'codigo_dian' in t._fields else False,
                'nombre_dian': t.nombre_dian if 'nombre_dian' in t._fields else False,
                'description_dian': t.description_dian if 'description_dian' in t._fields else False,
                'company_id': target_company.id,
            }
            base_vals = {k: v for k, v in base_vals.items() if k in Tax._fields}

            inv_lines, ref_lines = [], []
            for src_line, target_list in (
                (t.invoice_repartition_line_ids, inv_lines),
                (t.refund_repartition_line_ids, ref_lines),
            ):
                for line in src_line:
                    target_acc = self._map_account(line.account_id, target_company)
                    if line.account_id and not target_acc:
                        account_warnings += 1
                    target_list.append(Command.create({
                        'factor_percent': line.factor_percent,
                        'repartition_type': line.repartition_type,
                        'account_id': target_acc.id if target_acc else False,
                    }))
            if inv_lines:
                base_vals['invoice_repartition_line_ids'] = inv_lines
            if ref_lines:
                base_vals['refund_repartition_line_ids'] = ref_lines

            if existing:
                if self.overwrite:
                    if not self.dry_run:
                        existing.write({k: v for k, v in base_vals.items()
                                        if k not in ('invoice_repartition_line_ids', 'refund_repartition_line_ids')})
                    updated += 1
                else:
                    skipped += 1
            else:
                if not self.dry_run:
                    try:
                        Tax.create(base_vals)
                    except Exception as e:
                        _logger.warning('Replicate tax failed for %s: %s', t.name, e)
                        skipped += 1
                        continue
                created += 1
        line = f'  Retenciones: creadas={created}, actualizadas={updated}, saltadas={skipped} (de {len(source_taxes)})'
        if account_warnings:
            line += f' — {account_warnings} cuentas no mapeadas (revisa cuenta por code en destino)'
        return line

    def _map_accounts(self, accounts, target_company):
        if not accounts:
            return self.env['account.account']
        codes = accounts.mapped('code')
        return self.env['account.account'].sudo().with_company(target_company).search([
            ('code', 'in', codes),
            ('company_id', '=', target_company.id),
        ])

    def _replicate_certificate_configs(self, target_company):
        Cfg = self.env['l10n_co.exogenous_certificate_config'].sudo()
        Line = self.env['l10n_co.exogenous_certificate_config_line'].sudo()
        sources = Cfg.with_company(self.source_company_id).search([
            ('company_id', '=', self.source_company_id.id),
        ])
        created, updated, skipped = 0, 0, 0
        for c in sources:
            existing = Cfg.with_company(target_company).search([
                ('company_id', '=', target_company.id),
                ('certificate_type', '=', c.certificate_type),
            ], limit=1)
            vals = {
                'company_id': target_company.id,
                'certificate_type': c.certificate_type,
                'report_title': c.report_title, 'report_style': c.report_style,
                'report_template': c.report_template,
                'signer_name': c.signer_name, 'signer_position': c.signer_position,
                'signer_signature': c.signer_signature, 'article': c.article,
                'active': c.active,
                'purchase_account_ids': [Command.set(self._map_accounts(c.purchase_account_ids, target_company).ids)],
                'iva_deductible_account_ids': [Command.set(self._map_accounts(c.iva_deductible_account_ids, target_company).ids)],
            }
            if existing:
                if self.overwrite:
                    if not self.dry_run:
                        existing.write({k: v for k, v in vals.items() if k != 'company_id'})
                    updated += 1
                else:
                    skipped += 1
                continue
            if not self.dry_run:
                new_cfg = Cfg.create(vals)
                for ln in c.line_ids:
                    Line.create({
                        'config_id': new_cfg.id,
                        'concept_name': ln.concept_name if 'concept_name' in ln._fields else False,
                        'account_ids': [Command.set(self._map_accounts(ln.account_ids, target_company).ids)],
                    })
            created += 1
        return f'  Cert. retenciones: creados={created}, actualizados={updated}, saltados={skipped} (de {len(sources)})'

    def _replicate_income_cert_configs(self, target_company):
        Cfg = self.env['l10n_co.exogenous_income_cert_config'].sudo()
        sources = Cfg.with_company(self.source_company_id).search([
            ('company_id', '=', self.source_company_id.id),
        ])
        created, updated, skipped = 0, 0, 0
        for c in sources:
            existing = Cfg.with_company(target_company).search([
                ('company_id', '=', target_company.id),
                ('year', '=', c.year),
            ], limit=1)
            vals = {
                'name': c.name, 'company_id': target_company.id,
                'year': c.year, 'active': c.active, 'description': c.description,
                'form_number': c.form_number, 'issue_date': c.issue_date,
                'uvt_value': c.uvt_value,
                'patrimony_uvt': c.patrimony_uvt, 'income_uvt': c.income_uvt,
                'currency_id': c.currency_id.id,
                'account_ids': [Command.set(self._map_accounts(c.account_ids, target_company).ids)],
            }
            if existing:
                if self.overwrite:
                    if not self.dry_run:
                        existing.write({k: v for k, v in vals.items() if k != 'company_id'})
                    updated += 1
                else:
                    skipped += 1
                continue
            if not self.dry_run:
                Cfg.create(vals)
            created += 1
        return f'  Cert. ingresos:   creados={created}, actualizados={updated}, saltados={skipped} (de {len(sources)})'

    def action_run(self):
        self.ensure_one()
        if not self.target_company_ids:
            raise UserError(_('Selecciona al menos una compañía destino.'))
        if not (self.replicate_concepts or self.replicate_retentions
                or self.replicate_certificate_configs or self.replicate_income_cert_configs):
            raise UserError(_('Marca al menos una opción a replicar.'))

        log_lines = []
        if self.dry_run:
            log_lines.append('=== MODO SIMULACIÓN — no se aplica nada ===')
        log_lines.append(f'Origen: {self.source_company_id.name}')
        for tgt in self.target_company_ids:
            log_lines.append(f'\n→ Destino: {tgt.name} (id={tgt.id})')
            if self.replicate_concepts:
                log_lines.append(self._replicate_concepts(tgt))
            if self.replicate_retentions:
                log_lines.append(self._replicate_retentions(tgt))
            if self.replicate_certificate_configs:
                log_lines.append(self._replicate_certificate_configs(tgt))
            if self.replicate_income_cert_configs:
                log_lines.append(self._replicate_income_cert_configs(tgt))
        self.result_log = '\n'.join(log_lines)
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }
