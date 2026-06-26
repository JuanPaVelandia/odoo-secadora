# -*- coding: utf-8 -*-
from odoo import models, fields, api
from datetime import date, timedelta
from dateutil.easter import easter


HOLIDAY_TYPE = [
    ('religious', 'Religioso'),
    ('civic', 'Cívico/Histórico'),
]

DATE_TYPE = [
    ('fixed', 'Fijo'),
    ('movable', 'Trasladable (Ley Emiliani)'),
    ('easter', 'Relativo a Semana Santa'),
]


class LavishHolidays(models.Model):
    _name = 'lavish.holidays'
    _description = 'Días festivos Colombia'
    _order = 'date'

    name = fields.Char('Descripción', required=True)
    date = fields.Date('Fecha', required=True)
    year = fields.Integer('Año', compute='_compute_year', store=True)
    holiday_type = fields.Selection(HOLIDAY_TYPE, string='Tipo', default='civic')
    date_type = fields.Selection(DATE_TYPE, string='Tipo de fecha', default='fixed')
    # Para festivos fijos: mes y día
    fixed_month = fields.Integer('Mes fijo')
    fixed_day = fields.Integer('Día fijo')
    # Para festivos relativos a Semana Santa: días desde Pascua
    easter_offset = fields.Integer('Días desde Pascua', default=0,
        help='Días antes (-) o después (+) del Domingo de Pascua')
    active = fields.Boolean(default=True)

    _date_holiday_uniq = models.Constraint('unique(date)', 'Ya existe un día festivo en esta fecha, por favor verificar.')

    @api.depends('date')
    def _compute_year(self):
        for record in self:
            record.year = record.date.year if record.date else False

    @api.model
    def _get_next_monday(self, dt):
        """Obtiene el siguiente lunes (Ley Emiliani)."""
        days_until_monday = (7 - dt.weekday()) % 7
        if days_until_monday == 0:
            days_until_monday = 7
        return dt + timedelta(days=days_until_monday)

    @api.model
    def _calculate_holiday_date(self, year, holiday_def):
        """Calcula la fecha real del festivo para un año dado."""
        date_type = holiday_def.get('date_type', 'fixed')

        if date_type == 'easter':
            # Festivos relativos a Semana Santa
            easter_date = easter(year)
            offset = holiday_def.get('easter_offset', 0)
            base_date = easter_date + timedelta(days=offset)
            if holiday_def.get('movable', False):
                return self._get_next_monday(base_date)
            return base_date

        elif date_type == 'fixed':
            base_date = date(year, holiday_def['month'], holiday_def['day'])
            return base_date

        elif date_type == 'movable':
            # Ley Emiliani: se traslada al lunes siguiente
            base_date = date(year, holiday_def['month'], holiday_def['day'])
            return self._get_next_monday(base_date)

        return None

    @api.model
    def generate_holidays_for_year(self, year):
        """Genera todos los festivos colombianos para un año."""
        # Definicion de festivos colombianos
        COLOMBIAN_HOLIDAYS = [
            # Festivos fijos
            {'name': 'Año Nuevo', 'month': 1, 'day': 1, 'date_type': 'fixed', 'holiday_type': 'civic'},
            {'name': 'Día del Trabajo', 'month': 5, 'day': 1, 'date_type': 'fixed', 'holiday_type': 'civic'},
            {'name': 'Día de la Independencia', 'month': 7, 'day': 20, 'date_type': 'fixed', 'holiday_type': 'civic'},
            {'name': 'Batalla de Boyacá', 'month': 8, 'day': 7, 'date_type': 'fixed', 'holiday_type': 'civic'},
            {'name': 'Inmaculada Concepción', 'month': 12, 'day': 8, 'date_type': 'fixed', 'holiday_type': 'religious'},
            {'name': 'Navidad', 'month': 12, 'day': 25, 'date_type': 'fixed', 'holiday_type': 'religious'},

            # Festivos trasladables (Ley Emiliani)
            {'name': 'Día de los Reyes Magos', 'month': 1, 'day': 6, 'date_type': 'movable', 'holiday_type': 'religious'},
            {'name': 'Día de San José', 'month': 3, 'day': 19, 'date_type': 'movable', 'holiday_type': 'religious'},
            {'name': 'San Pedro y San Pablo', 'month': 6, 'day': 29, 'date_type': 'movable', 'holiday_type': 'religious'},
            {'name': 'Asunción de la Virgen', 'month': 8, 'day': 15, 'date_type': 'movable', 'holiday_type': 'religious'},
            {'name': 'Día de la Raza', 'month': 10, 'day': 12, 'date_type': 'movable', 'holiday_type': 'civic'},
            {'name': 'Todos los Santos', 'month': 11, 'day': 1, 'date_type': 'movable', 'holiday_type': 'religious'},
            {'name': 'Independencia de Cartagena', 'month': 11, 'day': 11, 'date_type': 'movable', 'holiday_type': 'civic'},

            # Festivos relativos a Semana Santa
            {'name': 'Jueves Santo', 'easter_offset': -3, 'date_type': 'easter', 'holiday_type': 'religious'},
            {'name': 'Viernes Santo', 'easter_offset': -2, 'date_type': 'easter', 'holiday_type': 'religious'},
            {'name': 'Ascensión del Señor', 'easter_offset': 43, 'date_type': 'easter', 'movable': True, 'holiday_type': 'religious'},
            {'name': 'Corpus Christi', 'easter_offset': 64, 'date_type': 'easter', 'movable': True, 'holiday_type': 'religious'},
            {'name': 'Sagrado Corazón de Jesús', 'easter_offset': 71, 'date_type': 'easter', 'movable': True, 'holiday_type': 'religious'},
        ]

        created = []
        for holiday_def in COLOMBIAN_HOLIDAYS:
            holiday_date = self._calculate_holiday_date(year, holiday_def)
            if holiday_date:
                existing = self.search([('date', '=', holiday_date)], limit=1)
                if not existing:
                    vals = {
                        'name': holiday_def['name'],
                        'date': holiday_date,
                        'holiday_type': holiday_def.get('holiday_type', 'civic'),
                        'date_type': holiday_def.get('date_type', 'fixed'),
                    }
                    if holiday_def.get('month'):
                        vals['fixed_month'] = holiday_def['month']
                        vals['fixed_day'] = holiday_def['day']
                    if holiday_def.get('easter_offset') is not None:
                        vals['easter_offset'] = holiday_def['easter_offset']

                    created.append(self.create(vals))

        return created

    @api.model
    def is_holiday(self, check_date):
        """Verifica si una fecha es festivo."""
        return bool(self.search([('date', '=', check_date)], limit=1))

    @api.model
    def get_holidays_between(self, date_from, date_to):
        """Obtiene festivos entre dos fechas."""
        return self.search([
            ('date', '>=', date_from),
            ('date', '<=', date_to)
        ])

    @api.model
    def count_holidays_between(self, date_from, date_to):
        """Cuenta festivos entre dos fechas."""
        return self.search_count([
            ('date', '>=', date_from),
            ('date', '<=', date_to)
        ])
