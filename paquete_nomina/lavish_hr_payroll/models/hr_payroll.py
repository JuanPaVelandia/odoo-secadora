# -*- coding: utf-8 -*-
import base64
import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class HrPayslipWorkedDays(models.Model):
    """Extension de dias trabajados para nomina colombiana"""
    _inherit = 'hr.payslip.worked_days'

    symbol = fields.Char('+/-', size=8)
    number_of_days = fields.Float(digits='Payroll')
    number_of_hours = fields.Float(digits='Payroll')
    number_of_days_aux = fields.Float(digits='Payroll')
    number_of_hours_aux = fields.Float(digits='Payroll')
    amount_aux = fields.Float(digits='Payroll', string="Auxilio Transporte")
    amount = fields.Monetary(
        string='Amount',
        compute=False,
        store=True,
        copy=True
    )
    display_type = fields.Selection([
        ('normal', 'Normal'),
        ('days', 'Dias Trabajados'),
        ('line_section', 'Seccion'),
        ('line_note', 'Nota')
    ], string='Tipo de Visualizacion', default='normal',
       help='Determina como se visualiza la linea en reportes e interfaces')


class HrPayslip(models.Model):
    """Extension de nomina para Colombia"""
    _inherit = 'hr.payslip'

    mail_state = fields.Selection([
        ('draft', 'Pendiente'),
        ('sent', 'Enviado'),
        ('failed', 'Error')
    ], string='Estado Email', default='draft', tracking=True)
    mail_sent_date = fields.Datetime('Fecha Envio')
    mail_error_msg = fields.Text('Error de Envio')
    compute_date = fields.Date('Computed On')
    basic_wage = fields.Monetary(compute='_compute_basic_net', store=True)
    gross_wage = fields.Monetary(compute='_compute_basic_net', store=True)
    net_wage = fields.Monetary(compute='_compute_basic_net', store=True)
    total_deduction = fields.Monetary(
        compute='_compute_total_deduction',
        store=True,
        string='Total Deducciones (monetario)'
    )
    identification_id = fields.Char(
        related='employee_id.identification_id',
        string='Cedula',
        store=True,
        index=True
    )
    department_id = fields.Many2one(
        related='employee_id.department_id',
        string='Departamento',
        store=True
    )

    def _filter_not_in_contract_payslips(self):
        """
        Evita falsos positivos del banner de contrato cuando el recibo ya tiene
        un contrato asignado que cubre el período, aunque `hr.version` no tenga
        sincronizadas las fechas de contrato.
        """
        def _get_contract_dates(slip):
            date_start = slip.version_id.contract_date_start
            date_end = slip.version_id.contract_date_end
            if slip.contract_id:
                date_start = date_start or slip.contract_id.date_start
                date_end = date_end or slip.contract_id.date_end
            return date_start, date_end

        return self.filtered(
            lambda slip:
            not slip.is_refund_payslip
            and slip.date_from
            and slip.date_to
            and (
                lambda contract_dates: (
                    not contract_dates[0]
                    or contract_dates[0] > slip.date_to
                    or (contract_dates[1] and contract_dates[1] < slip.date_from)
                )
            )(_get_contract_dates(slip))
        )

    @api.depends('line_ids.total', 'line_ids.category_id')
    def _compute_total_deduction(self):
        for payslip in self:
            deduction_codes = ('DED', 'DEDUCCIONES', 'DEDUCCION', 'SS_EMP')
            total = sum(
                line.total
                for line in payslip.line_ids
                if line.category_id.code in deduction_codes
            )
            payslip.total_deduction = abs(total)

    def action_open_payslip(self):
        """Abre el formulario de la nomina en una nueva ventana."""
        self.ensure_one()
        return {
            'name': _('Nomina - %s') % self.employee_id.name,
            'type': 'ir.actions.act_window',
            'res_model': 'hr.payslip',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_send_payslip_email(self):
        """Envia el comprobante de nomina por correo electronico."""
        self.ensure_one()

        if not (self.employee_id.work_email or self.employee_id.personal_email):
            raise UserError(
                _("El empleado %s no tiene configurado un correo electronico.")
                % self.employee_id.name
            )

        template = self.env.ref('lavish_hr_payroll.email_template_payslip_smart')

        try:
            report = self.struct_id.report_id
            pdf_content, dummy = self.env['ir.actions.report']._render_qweb_pdf(
                report,
                self.id
            )

            attachment = self.env['ir.attachment'].create({
                'name': "Comprobante_nomina_%s_%s.pdf" % (
                    self.employee_id.work_contact_id.vat,
                    self.name
                ),
                'type': 'binary',
                'datas': base64.b64encode(pdf_content),
                'res_model': 'hr.payslip',
                'res_id': self.id,
            })

            template.with_context(
                no_grouped_keys=True,
                force_send=True
            ).send_mail(
                self.id,
                force_send=True,
                email_values={
                    'attachment_ids': [(4, attachment.id)]
                },
                raise_exception=True
            )

            self.write({
                'mail_state': 'sent',
                'mail_sent_date': fields.Datetime.now(),
                'mail_error_msg': False
            })

            self.message_post(
                body=_("Comprobante de nomina enviado por correo electronico.")
            )

        except Exception as e:
            error_msg = str(e)
            self.write({
                'mail_state': 'failed',
                'mail_error_msg': error_msg
            })
            raise UserError(_("Error al enviar el correo: %s") % error_msg)
