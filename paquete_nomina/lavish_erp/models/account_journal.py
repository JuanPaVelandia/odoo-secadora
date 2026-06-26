from odoo import api, fields, models, _
from odoo.addons.base.models.ir_sequence import _update_nogap
from datetime import datetime, date
from odoo.exceptions import ValidationError


class AccountJournalInherit(models.Model):
	_inherit = "account.journal"

	# Campos relacionados para mostrar info de resolucion DIAN
	use_dian_control = fields.Boolean(
		related='sequence_id.use_dian_control',
		string='Control DIAN',
		readonly=True
	)
	dian_remaining_numbers = fields.Integer(
		string='Números Restantes',
		compute='_compute_dian_resolution_info',
		help='Cantidad de números disponibles en la resolución activa'
	)
	dian_remaining_days = fields.Integer(
		string='Días Restantes',
		compute='_compute_dian_resolution_info',
		help='Días hasta el vencimiento de la resolución activa'
	)
	dian_resolution_number = fields.Char(
		string='Resolución Activa',
		compute='_compute_dian_resolution_info'
	)
	dian_resolution_date_to = fields.Date(
		string='Vence',
		compute='_compute_dian_resolution_info'
	)

	@api.depends('sequence_id', 'sequence_id.dian_resolution_ids', 'sequence_id.use_dian_control')
	def _compute_dian_resolution_info(self):
		for journal in self:
			journal.dian_remaining_numbers = 0
			journal.dian_remaining_days = 0
			journal.dian_resolution_number = False
			journal.dian_resolution_date_to = False

			if journal.sequence_id and journal.sequence_id.use_dian_control:
				active_res = journal.sequence_id.dian_resolution_ids.filtered(
					lambda r: r.active_resolution
				)
				if active_res:
					res = active_res[0]
					journal.dian_resolution_number = res.resolution_number
					journal.dian_resolution_date_to = res.date_to
					# Numeros restantes
					journal.dian_remaining_numbers = max(0, res.number_to - res.number_next_actual + 1)
					# Dias restantes
					if res.date_to:
						today = date.today()
						delta = res.date_to - today
						journal.dian_remaining_days = max(0, delta.days)

	sequence_id = fields.Many2one('ir.sequence', string='Secuencia de Asientos',
								help="Este campo contiene la informacion relacionada con la numeracion de"
									" los asientos contables de este diario.", copy=False)
	sequence_number_next = fields.Integer(string='Siguiente Numero',
										help='El siguiente numero de secuencia se usara para la proxima factura.',
										compute='_compute_seq_number_next',
										inverse='_inverse_seq_number_next')
	refund_sequence_id = fields.Many2one('ir.sequence', string='Secuencia de Notas Credito',
										help="Este campo contiene la informacion relacionada con la "
											"numeracion de las notas credito de este diario.",
										copy=False)
	refund_sequence_number_next = fields.Integer(string='Siguiente Numero Nota Credito',
												help='El siguiente numero de secuencia se usara para la proxima '
													'nota credito.',
												compute='_compute_refund_seq_number_next',
												inverse='_inverse_refund_seq_number_next')

	@api.depends('sequence_id.use_date_range', 'sequence_id.number_next_actual')
	def _compute_seq_number_next(self):
		for journal in self:
			if journal.sequence_id:
				sequence = journal.sequence_id._get_current_sequence()
				journal.sequence_number_next = sequence.number_next_actual
			else:
				journal.sequence_number_next = 1

	def _inverse_seq_number_next(self):
		for journal in self:
			if journal.sequence_id and journal.sequence_number_next:
				sequence = journal.sequence_id._get_current_sequence()
				sequence.sudo().number_next = journal.sequence_number_next

	@api.depends('refund_sequence_id.use_date_range', 'refund_sequence_id.number_next_actual')
	def _compute_refund_seq_number_next(self):
		for journal in self:
			if journal.refund_sequence_id and journal.refund_sequence:
				sequence = journal.refund_sequence_id._get_current_sequence()
				journal.refund_sequence_number_next = sequence.number_next_actual
			else:
				journal.refund_sequence_number_next = 1

	def _inverse_refund_seq_number_next(self):
		for journal in self:
			if journal.refund_sequence_id and journal.refund_sequence and journal.refund_sequence_number_next:
				sequence = journal.refund_sequence_id._get_current_sequence()
				sequence.sudo().number_next = journal.refund_sequence_number_next

	@api.constrains("refund_sequence_id", "sequence_id")
	def _check_journal_sequence(self):
		for journal in self:
			if (
					journal.refund_sequence_id
					and journal.sequence_id
					and journal.refund_sequence_id == journal.sequence_id
			):
				raise ValidationError(
					_(
						"En el diario '%s', se usa la misma secuencia como "
						"Secuencia de Asientos y Secuencia de Notas Credito."
					)
					% journal.display_name
				)
			if journal.sequence_id and not journal.sequence_id.company_id:
				raise ValidationError(
					_(
						"La compania no esta configurada en la secuencia '%s' del "
						"diario '%s'."
					)
					% (journal.sequence_id.display_name, journal.display_name)
				)
			if journal.refund_sequence_id and not journal.refund_sequence_id.company_id:
				raise ValidationError(
					_(
						"La compania no esta configurada en la secuencia '%s' usada como "
						"secuencia de notas credito del diario '%s'."
					)
					% (journal.refund_sequence_id.display_name, journal.display_name)
				)

	@api.model_create_multi
	def create(self, vals_list):
		for vals in vals_list:
			# Crear secuencia principal si no existe
			if not vals.get("sequence_id"):
				vals["sequence_id"] = self._create_sequence(vals).id
			
			# Crear secuencia de reembolso si es necesario
			if (vals.get("type") in ("sale", "purchase") 
				and vals.get("refund_sequence") 
				and not vals.get("refund_sequence_id")):
				vals["refund_sequence_id"] = self._create_sequence(vals, refund=True).id
		
		return super().create(vals_list)


	@api.model
	def _prepare_sequence(self, vals, refund=False):
		code = vals.get("code") and vals["code"].upper() or ""
		prefix = "%s%s/%%(range_year)s/" % (refund and "R" or "", code)
		seq_vals = {
			"name": "%s %s"
					% (vals.get("name", _("Secuencia")), refund and _("Reembolso") + " " or ""),
			"company_id": vals.get("company_id") or self.env.company.id,
			"implementation": "no_gap",
			"prefix": code,
			"padding": 4,
			#"use_date_range": True,
		}
		return seq_vals

	@api.model
	def _create_sequence(self, vals, refund=False):
		seq_vals = self._prepare_sequence(vals, refund=refund)
		return self.env["ir.sequence"].sudo().create(seq_vals)



class IrSequenceInherit(models.Model):
	_inherit = 'ir.sequence'


	DIAN_TYPE = [
		('electronic_invoice', 'Factura Electronica'),
		('paper_invoice', 'Factura de Papel'),
		('pos_invoice', 'Factura POS'),
		('support_document', 'Documento Soporte'),
		('equivalent_document', 'Documento Equivalente'),
	]

	use_dian_control = fields.Boolean('Usar resoluciones DIAN', default=False)
	remaining_numbers = fields.Integer(default=1, help='Numeros restantes')
	remaining_days = fields.Integer(default=1, help='Dias restantes')
	sequence_dian_type = fields.Selection(DIAN_TYPE, 'Tipo', default='electronic_invoice')
	dian_resolution_ids = fields.One2many('ir.sequence.dian_resolution', 'sequence_id', 'Resoluciones DIAN')

	@api.model
	def check_active_resolution(self, sequence_id):    
		dian_resolutions_sequences_ids = self.search([('use_dian_control', '=', True),('id', '=', sequence_id)])
		for record in dian_resolutions_sequences_ids:
			if record:
				if len( record.dian_resolution_ids ) > 1:
					actual_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
					for resolution in record.dian_resolution_ids:
						if resolution.number_next_actual >= resolution.number_from and resolution.number_next_actual <= resolution.number_to and  actual_date <= resolution.date_to:
							self.check_active_resolution_cron()
							return True
		return False

	@api.model
	def check_active_resolution_cron(self):
		dian_resolutions_sequences_ids = self.search([('use_dian_control', '=', True)])
		for record in dian_resolutions_sequences_ids:
			if record:
				if len( record.dian_resolution_ids ) > 1:
					actual_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
					_active_resolution = False
					for resolution in record.dian_resolution_ids:
						if resolution.number_next_actual >= resolution.number_from and resolution.number_next_actual <= resolution.number_to and  actual_date <= resolution.date_to and resolution.active_resolution:
							continue
					_active_resolution = False
					for resolution in record.dian_resolution_ids:
						if _active_resolution:
							continue
						if resolution.number_next_actual >= resolution.number_from and resolution.number_next_actual <= resolution.number_to and  actual_date <= resolution.date_to:
							record.dian_resolution_ids.write({
								'active_resolution' : False
							})
							resolution.write({
									'active_resolution' : True        
							}) 
							_active_resolution = True                           

	def _next(self, sequence_date=None):
		# El base desplegado (SaaS) espera que ir_sequence_date sea datetime
		# (hace dt.replace(tzinfo=None)). Algunos callers (p.ej.
		# custom_account_treasury) pasan un date (rec.date), lo que revienta con
		# TypeError. Coercionamos date -> datetime antes de seguir.
		seq_date = sequence_date or self.env.context.get('ir_sequence_date')
		if isinstance(seq_date, date) and not isinstance(seq_date, datetime):
			sequence_date = datetime.combine(seq_date, datetime.min.time())
		if not self.use_dian_control:
			return super(IrSequenceInherit, self)._next(sequence_date=sequence_date)
		seq_dian_actual = self.env['ir.sequence.dian_resolution'].search([('sequence_id','=',self.id),('active_resolution','=',True)], limit=1)
		if seq_dian_actual.exists(): 
			number_actual = seq_dian_actual._next()
			if seq_dian_actual['number_next']-1 > seq_dian_actual['number_to']:
				seq_dian_next = self.env['ir.sequence.dian_resolution'].search([('sequence_id','=',self.id),('active_resolution','=',True)], limit=1, offset=1)
				if seq_dian_next.exists():
					seq_dian_actual.active_resolution = False
					return seq_dian_next._next()
			return number_actual
		return super(IrSequenceInherit, self)._next(sequence_date=sequence_date)

	@api.constrains('dian_resolution_ids')
	def val_active_resolution(self):
		_active_resolution = 0
		if self.use_dian_control:
			for record in self.dian_resolution_ids:
				if record.active_resolution:
					_active_resolution += 1
			if _active_resolution > 1:
				raise ValidationError( _('El sistema necesita solo una resolucion DIAN activa') )
			if _active_resolution == 0:
				raise ValidationError( _('El sistema necesita al menos una resolucion DIAN activa') )

class IrSequenceDianResolution(models.Model):
    _name = 'ir.sequence.dian_resolution'
    _rec_name = "sequence_id"
    _description = "Resolucion DIAN de Secuencia"

    def _get_number_next_actual(self):
        for element in self:
            element.number_next_actual = element.number_next

    def _set_number_next_actual(self):
        for record in self:
            record.write({'number_next': record.number_next_actual or 0})

    @api.depends('number_from')
    def _get_initial_number(self):
        for record in self:
            if not record.number_next:
                record.number_next = record.number_from

    resolution_number = fields.Char('Numero de Resolucion', required=True)
    date_from = fields.Date('Desde', required=True)
    date_to = fields.Date('Hasta', required=True)
    number_from = fields.Integer('Numero Inicial', required=True)
    number_to = fields.Integer('Numero Final', required=True)
    number_next = fields.Integer('Siguiente Numero', compute='_get_initial_number', store=True)
    number_next_actual = fields.Integer(compute='_get_number_next_actual', inverse='_set_number_next_actual',
                                        string='Siguiente Numero Actual', required=True, default=1,
                                        help="Siguiente numero de esta secuencia")
    active_resolution = fields.Boolean('Resolucion Activa', required=False, default=False)
    sequence_id = fields.Many2one("ir.sequence", 'Secuencia Principal', required=True, ondelete='cascade')

    def _next(self):
        number_next = _update_nogap(self, 1)
        return self.sequence_id.get_next_char(number_next)

