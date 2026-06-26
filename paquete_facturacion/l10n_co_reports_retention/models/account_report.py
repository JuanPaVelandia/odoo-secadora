from odoo import models


class AccountReport(models.Model):
    _inherit = 'account.report'

    def _get_dynamic_lines(self, options, all_column_groups_expression_totals, warnings=None):
        lines = super()._get_dynamic_lines(options, all_column_groups_expression_totals, warnings)
        if self.env.context.get("from_retention", False):
            for line in lines:
                if isinstance(line, tuple) and len(line) > 1 and isinstance(line[1], dict):
                    line[1]["unfolded"] = True

        return lines
