from odoo import api, fields, models, _
from odoo.exceptions import ValidationError, UserError

class HrSkills(models.Model):
    _inherit = 'hr.skill'

    is_other = fields.Boolean('Es otro')

class HrSkillsEmployee(models.Model):
    _inherit = 'hr.employee.skill'

    is_other = fields.Boolean(related='skill_id.is_other')
    which_is = fields.Char('¿Cual?')

    _unique_skill_constraint = models.Constraint('unique (employee_id, skill_id, which_is)', "Two levels for the same skill is not allowed")

# class hr_resume_line(models.Model):
#     _inherit = 'hr.resume.line'
#
#     @api.model
#     def create(self, vals):
#         if vals.get('name'):
#             obj_employee = self.env['hr.resume.line'].search([('name', '=', vals.get('name'))])
#             vals['employee_id'] = obj_employee.id
#
#         res = super(hr_resume_line, self).create(vals)
#         return res

class HrResumeLineType(models.Model):
    _inherit = 'hr.resume.line.type'

    type_resume = fields.Selection([('labor', 'Laboral'),
                            ('academic', 'Académico'), ('interview', 'Entrevista')], 'Tipo', required=True, default="labor")
