# -*- coding: utf-8 -*-
from odoo import api, models


class PosSession(models.Model):
    _inherit = "pos.session"

    @api.model
    def _load_pos_data_models(self, config):
        res = super()._load_pos_data_models(config)
        if config.company_id.country_code == "CO":
            res.extend([
                "l10n_latam.identification.type",
                "res.city",
                "account.journal",
                "res.partner.category",
                "dian.tributes",
                "dian.fiscal.responsability",
            ])
        return res


class AccountJournalPos(models.Model):
    _name = "account.journal"
    _inherit = ["account.journal", "pos.load.mixin"]

    @api.model
    def _load_pos_data_fields(self, config):
        return ["id", "name"]

    @api.model
    def _load_pos_data_domain(self, data, config):
        journal_id = config.electronic_invoice_journal_id.id
        if not journal_id:
            return [("id", "=", False)]
        return [("id", "=", journal_id)]


class ResCityPos(models.Model):
    _name = "res.city"
    _inherit = ["res.city", "pos.load.mixin"]

    @api.model
    def _load_pos_data_fields(self, config):
        return ["id", "name", "country_id", "state_id"]

    @api.model
    def _load_pos_data_domain(self, data, config):
        return [("country_id.code", "=", "CO")]


class L10nLatamIdentificationTypePos(models.Model):
    _name = "l10n_latam.identification.type"
    _inherit = ["l10n_latam.identification.type", "pos.load.mixin"]

    @api.model
    def _load_pos_data_fields(self, config):
        return ["id", "name"]

    @api.model
    def _load_pos_data_domain(self, data, config):
        return [
            ("l10n_co_document_code", "!=", False),
            ("active", "=", True),
        ]


class ResPartnerCategoryPos(models.Model):
    _name = "res.partner.category"
    _inherit = ["res.partner.category", "pos.load.mixin"]

    @api.model
    def _load_pos_data_fields(self, config):
        return ["id", "name"]

    @api.model
    def _load_pos_data_domain(self, data, config):
        return []


class DianTributesPos(models.Model):
    _name = "dian.tributes"
    _inherit = ["dian.tributes", "pos.load.mixin"]

    @api.model
    def _load_pos_data_fields(self, config):
        return ["id", "name"]

    @api.model
    def _load_pos_data_domain(self, data, config):
        return []


class DianFiscalResponsabilityPos(models.Model):
    _name = "dian.fiscal.responsability"
    _inherit = ["dian.fiscal.responsability", "pos.load.mixin"]

    @api.model
    def _load_pos_data_fields(self, config):
        return ["id", "name"]

    @api.model
    def _load_pos_data_domain(self, data, config):
        return []
