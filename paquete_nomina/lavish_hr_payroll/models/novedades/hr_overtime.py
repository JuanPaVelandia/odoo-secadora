from odoo import models, fields, api, _
from datetime import datetime, timedelta, date
from odoo.exceptions import UserError, ValidationError
import time
import pytz
class HrTypeOvertime(models.Model):
    _name = 'hr.type.overtime'
    _description = 'Tipos de horas extras'
    _order = 'type_overtime, valid_from desc'

    name = fields.Char(string="Descripcion", required=True)
    salary_rule = fields.Many2one('hr.salary.rule', string="Regla salarial")
    type_overtime = fields.Selection([
        ('overtime_rn', 'RN | Recargo nocturno'),
        ('overtime_ext_d', 'EXT-D | Extra diurna'),
        ('overtime_ext_n', 'EXT-N | Extra nocturna'),
        ('overtime_eddf', 'E-D-D/F | Extra diurna dominical/festivo'),
        ('overtime_endf', 'E-N-D/F | Extra nocturna dominical/festivo'),
        ('overtime_dof', 'D o F | Dominicales o festivos'),
        ('overtime_rndf', 'RN-D/F | Recargo nocturno dominical/festivo'),
        ('overtime_rdf', 'R-D/F | Recargo dominical/festivo'),
        ('overtime_rnf', 'RN-F | Recargo nocturno festivo')
    ], 'Tipo', required=True)

    # Porcentaje y multiplicador
    percentage = fields.Float(string='Porcentaje', help='Porcentaje total (ej: 125 para HE diurna, 35 para recargo nocturno)')
    multiplier = fields.Float(string='Multiplicador', compute='_compute_multiplier', store=True,
                              help='Multiplicador calculado (porcentaje/100)')

    # Rango de vigencia - Ley 2466/2025 establece gradualidad
    valid_from = fields.Date(string='Vigente desde', required=True, default=fields.Date.today,
                             help='Fecha desde la cual aplica este porcentaje')
    valid_to = fields.Date(string='Vigente hasta',
                           help='Fecha hasta la cual aplica (vacio = sin limite)')
    active = fields.Boolean(string='Activo', default=True)

    # Horarios - Ley 2466: Nocturna de 7pm a 6am (antes era 9pm a 6am)
    start_time = fields.Float('Hora inicio', required=True, default=0,
                              help='Hora de inicio en formato decimal (19.0 = 7:00 PM)')
    end_time = fields.Float('Hora finalizacion', required=True, default=0,
                            help='Hora de fin en formato decimal (6.0 = 6:00 AM)')
    start_time_two = fields.Float('Segunda hora de inicio', default=0)
    end_time_two = fields.Float('Segunda hora de finalizacion', default=0)

    # Dias de aplicacion
    contains_holidays = fields.Boolean(string='Aplica en festivos?')
    mon = fields.Boolean(default=False, string='Lun')
    tue = fields.Boolean(default=False, string='Mar')
    wed = fields.Boolean(default=False, string='Mie')
    thu = fields.Boolean(default=False, string='Jue')
    fri = fields.Boolean(default=False, string='Vie')
    sat = fields.Boolean(default=False, string='Sab')
    sun = fields.Boolean(default=False, string='Dom')

    # Informacion legal
    equivalence_number_ne = fields.Integer(string='Num. Equivalencia NE')
    legal_reference = fields.Char(string='Base legal',
                                  help='Articulo o ley que sustenta este porcentaje')
    notes = fields.Text(string='Notas')

    # Constraint: tipo + rango de fechas no puede solaparse
    _type_date_range_uniq = models.Constraint('unique(type_overtime, valid_from, company_id)',
                                              'Ya existe un registro para este tipo de hora extra con la misma fecha de inicio.')

    company_id = fields.Many2one('res.company', string='Compania',
                                 default=lambda self: self.env.company)

    @api.depends('percentage')
    def _compute_multiplier(self):
        for record in self:
            record.multiplier = record.percentage / 100.0 if record.percentage else 0.0

    @api.constrains('valid_from', 'valid_to')
    def _check_date_range(self):
        for record in self:
            if record.valid_to and record.valid_from > record.valid_to:
                raise ValidationError(_('La fecha de inicio debe ser anterior a la fecha de fin.'))

            # Verificar solapamiento de rangos para el mismo tipo
            domain = [
                ('id', '!=', record.id),
                ('type_overtime', '=', record.type_overtime),
                ('company_id', '=', record.company_id.id),
            ]

            overlapping = self.search(domain)
            for other in overlapping:
                # Verificar si hay solapamiento
                other_end = other.valid_to or date(2099, 12, 31)
                record_end = record.valid_to or date(2099, 12, 31)

                if not (record_end < other.valid_from or record.valid_from > other_end):
                    raise ValidationError(
                        _('El rango de fechas se solapa con otro registro existente: %s (%s - %s)') %
                        (other.name, other.valid_from, other.valid_to or 'Sin limite')
                    )

    @api.model
    def get_percentage_for_date(self, type_overtime_code, reference_date, company_id=None):
        """
        Obtiene el porcentaje vigente para un tipo de hora extra en una fecha especifica.

        Args:
            type_overtime_code: Codigo del tipo (overtime_rn, overtime_ext_d, etc.)
            reference_date: Fecha de referencia para buscar el porcentaje
            company_id: ID de la compañía (opcional, usa la actual si no se especifica)

        Returns:
            Registro hr.type.overtime vigente o False si no existe
        """
        if not company_id:
            company_id = self.env.company.id

        domain = [
            ('type_overtime', '=', type_overtime_code),
            ('valid_from', '<=', reference_date),
            ('active', '=', True),
            '|',
            ('company_id', '=', company_id),
            ('company_id', '=', False),
            '|',
            ('valid_to', '=', False),
            ('valid_to', '>=', reference_date),
        ]

        return self.search(domain, order='valid_from desc', limit=1)

class HrOvertime(models.Model):
    _name = 'hr.overtime'
    _description = 'Novedades | Horas extras'

    date = fields.Datetime('Fecha y Hora Inicio', required=True,
                           help='Fecha y hora de inicio de la jornada de horas extras')
    date_end = fields.Datetime('Fecha y Hora Fin', required=True,
                               help='Fecha y hora de fin de la jornada de horas extras')
    # Campos computados para facilitar busquedas por fecha
    date_only = fields.Date('Fecha Novedad', compute='_compute_date_only', store=True,
                            help='Fecha de la novedad (sin hora) para busquedas')
    date_end_only = fields.Date('Fecha Final Novedad', compute='_compute_date_end_only', store=True,
                                help='Fecha final (sin hora) para busquedas')
    employee_id = fields.Many2one('hr.employee', string="Empleado", index=True)
    employee_identification = fields.Char('Identificación empleado')
    department_id = fields.Many2one('hr.department', related="employee_id.department_id", readonly=True,string="Departamento")
    job_id = fields.Many2one('hr.job', related="employee_id.job_id", readonly=True,string="Servicio")
    overtime_rn = fields.Float('RN', help='Horas recargo nocturno (35%)') # EXTRA_RECARGO
    overtime_ext_d = fields.Float('EXT-D', help='Horas extra diurnas (125%)') # EXTRA_DIURNA
    overtime_ext_n = fields.Float('EXT-N', help='Horas extra nocturna (175%)') # EXTRA_NOCTURNA
    overtime_eddf = fields.Float('E-D-D/F', help='Horas extra diurnas dominical/festiva (200%)') # EXTRA_DIURNA_DOMINICAL
    overtime_endf = fields.Float('E-N-D/F', help='Horas extra nocturna dominical/festiva (250%)') # EXTRA_NOCTURNA_DOMINICAL
    overtime_dof = fields.Float('D o F', help='Horas dominicales (175%)') # DOMINICALES O FESTIVOS
    overtime_rndf = fields.Float('RN-D/F', help='Horas recargo festivo (110%)') # EXTRA_RECARGO_DOMINICAL
    overtime_rdf = fields.Float('R-D/F', help='Recargos dominicales (0.75%)', default=0)  # EXTRA_RECARGO_DOMINICAL_FESTIVO
    overtime_rnf = fields.Float('RN-F', help='Recargo festivo nocturno (210%)')  # EXTRA_RECARGO_NOCTURNO_FESTIVO
    days_actually_worked = fields.Integer('Días efectivamente laborados')
    days_snack = fields.Integer('Días refrigerio')
    justification = fields.Char('Justificación')
    state = fields.Selection([('revertido','Revertido'),('procesado','Procesado'),('nuevo','Nuevo')],'Estado')
    payslip_run_id = fields.Many2one('hr.payslip','Ref. Liquidación')
    shift_hours = fields.Float('Horas del Turno')
    #attendance_id = fields.Many2one('hr.attendance', string='Asistencia')
    total_hours = fields.Float(string='Total Horas', compute='_compute_total_hours', store=True)
    
    @api.depends('date')
    def _compute_date_only(self):
        for record in self:
            record.date_only = record.date.date() if record.date else False

    @api.depends('date_end')
    def _compute_date_end_only(self):
        for record in self:
            record.date_end_only = record.date_end.date() if record.date_end else False

    @api.depends('overtime_rn', 'overtime_ext_d', 'overtime_ext_n', 'overtime_eddf',
                'overtime_endf', 'overtime_dof', 'overtime_rndf', 'overtime_rdf', 'overtime_rnf')
    def _compute_total_hours(self):
        for record in self:
            record.total_hours = (
                record.overtime_rn + record.overtime_ext_d + record.overtime_ext_n + 
                record.overtime_eddf + record.overtime_endf + record.overtime_dof + 
                record.overtime_rndf + record.overtime_rdf + record.overtime_rnf
            )


    def action_approve(self):
        self.write({'state': 'procesado'})
        
    def action_reject(self):
        self.write({'state': 'revertido'})

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            # Calculate total hours/days
            total = sum(vals.get(field, 0) for field in [
                'shift_hours',
                'days_snack',
                'days_actually_worked',
                'overtime_rn',
                'overtime_ext_d',
                'overtime_ext_n',
                'overtime_eddf',
                'overtime_endf',
                'overtime_dof',
                'overtime_rndf',
                'overtime_rdf',
                'overtime_rnf'
            ])

            if total <= 0:
                raise UserError(_('Valores en 0 detectados | No se ha detectado la cantidad de horas / dias de la novedad ingresada!'))

            # Handle employee identification lookup
            if vals.get('employee_identification'):
                obj_employee = self.env['hr.employee'].search([
                    ('company_id', '=', self.env.company.id),
                    ('identification_id', '=', vals.get('employee_identification'))
                ], limit=1)
                if obj_employee:
                    vals['employee_id'] = obj_employee.id

            # Handle employee id lookup
            if vals.get('employee_id'):
                obj_employee = self.env['hr.employee'].search([
                    ('company_id', '=', self.env.company.id),
                    ('id', '=', vals.get('employee_id'))
                ], limit=1)
                if obj_employee:
                    vals['employee_identification'] = obj_employee.identification_id

        return super().create(vals_list)
