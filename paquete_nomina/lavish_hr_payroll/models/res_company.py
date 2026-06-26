# -*- coding: utf-8 -*-

from odoo import models


class ResCompany(models.Model):
    _inherit = "res.company"

    def _lavish_hr_payroll_settings_proxy(self):
        """Create a transient settings record with the right company context."""
        self.ensure_one()
        return self.env["res.config.settings"].with_company(self).create({"company_id": self.id})

    def action_setup_salary_categories(self):
        self.ensure_one()
        return self._lavish_hr_payroll_settings_proxy().action_setup_salary_categories()

    def action_setup_leave_types(self):
        self.ensure_one()
        return self._lavish_hr_payroll_settings_proxy().action_setup_leave_types()

    def action_generate_salary_rules(self):
        self.ensure_one()
        return self._lavish_hr_payroll_settings_proxy().action_generate_salary_rules()

