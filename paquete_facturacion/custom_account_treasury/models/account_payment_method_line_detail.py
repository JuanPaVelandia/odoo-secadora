from odoo import fields, models, api, _
from odoo.exceptions import UserError, ValidationError


class AccountPaymentMethodLineDetail(models.Model):
	_name = 'account.payment.method.line.detail'
	_description = 'Detalle de Formas de Pago'
	_order = 'sequence, id'

	name = fields.Char(
		string='Descripción',
		compute='_compute_name',
		store=True
	)

	sequence = fields.Integer(
		string='Secuencia',
		default=10
	)

	payment_id = fields.Many2one(
		'account.payment',
		string='Pago',
		required=True,
		ondelete='cascade',
		index=True
	)

	payment_type = fields.Selection(
		related='payment_id.payment_type',
		string='Tipo de Pago',
		store=True
	)

	payment_method_id = fields.Many2one(
		'account.payment.method',
		string='Forma de Pago',
		required=True,
		domain="[('payment_type', '=', payment_type)]"
	)

	journal_id = fields.Many2one(
		'account.journal',
		string='Diario',
		required=True,
		domain="[('type', 'in', ['bank', 'cash'])]"
	)

	account_id = fields.Many2one(
		'account.account',
		string='Cuenta Contable',
		compute='_compute_account_id',
		store=True,
		readonly=False,
		domain="[('active', '=', True)]",
		help='Cuenta contable donde se registrará este método de pago. Se calcula automáticamente pero puede ser modificada por el usuario.'
	)

	amount = fields.Monetary(
		string='Monto',
		currency_field='currency_id',
		required=True
	)

	currency_id = fields.Many2one(
		'res.currency',
		string='Moneda',
		related='payment_id.currency_id',
		store=True
	)

	check_number = fields.Char(
		string='Número de Cheque',
		help='Número de cheque si la forma de pago es cheque'
	)

	is_check = fields.Boolean(
		string='Es Cheque',
		compute='_compute_is_check',
		store=True
	)

	notes = fields.Text(
		string='Notas'
	)

	@api.depends('payment_method_id', 'amount', 'journal_id')
	def _compute_name(self):
		"""Genera el nombre descriptivo de la línea"""
		for line in self:
			if line.payment_method_id and line.journal_id:
				name = f"{line.payment_method_id.name} - {line.journal_id.name}"
				if line.amount:
					name += f" ({line.currency_id.symbol}{line.amount:,.2f})"
				line.name = name
			else:
				line.name = "Nueva forma de pago"

	@api.depends('journal_id', 'payment_method_id', 'payment_id.payment_type')
	def _compute_account_id(self):
		"""
		Calcula la cuenta contable siguiendo la lógica de Odoo:
		1. Busca el payment_method_line del journal que coincida con el payment_method_id
		2. Usa payment_account_id del payment_method_line
		3. Si no existe, usa journal_id.default_account_id
		4. Como última opción, usa la primera cuenta del tipo de journal

		El campo es editable, por lo que el usuario puede cambiarlo después.
		"""
		for line in self:
			account = False

			if line.journal_id and line.payment_method_id:
				# Buscar el payment_method_line que coincida
				payment_type = line.payment_id.payment_type or 'outbound'

				# Obtener las líneas de método de pago disponibles para el journal
				payment_method_lines = line.journal_id._get_available_payment_method_lines(payment_type)

				# Buscar la línea que coincida con nuestro payment_method_id
				matching_line = payment_method_lines.filtered(
					lambda l: l.payment_method_id == line.payment_method_id
				)

				if matching_line:
					# Usar payment_account_id de la línea de método de pago
					account = matching_line[0].payment_account_id

				# Si no hay payment_account_id, usar la cuenta por defecto del journal
				if not account:
					account = line.journal_id.default_account_id

				# Como última opción, buscar una cuenta del tipo apropiado
				if not account and line.journal_id.type in ('bank', 'cash'):
					account_type = 'asset_cash' if line.journal_id.type == 'cash' else 'asset_cash_bank'
					account = self.env['account.account'].search([
						('account_type', '=', account_type),
						('company_id', '=', line.payment_id.company_id.id),
						('active', '=', True)
					], limit=1)

			# Solo actualizar si hay una cuenta válida y el campo está vacío
			# Esto permite que el usuario pueda cambiar la cuenta manualmente
			if account and not line.account_id:
				line.account_id = account
			elif not line.account_id and not account:
				# Si no hay cuenta y tampoco hay default, dejar vacío
				line.account_id = False

	@api.depends('payment_method_id', 'payment_method_id.code')
	def _compute_is_check(self):
		"""Determina si la forma de pago es cheque"""
		for line in self:
			# Determinar si es cheque basado en el código del método de pago
			line.is_check = line.payment_method_id and 'check' in (line.payment_method_id.code or '').lower()

	@api.onchange('payment_method_id')
	def _onchange_payment_method_id(self):
		"""
		Al cambiar el método de pago:
		1. Actualiza el dominio del diario
		2. Recalcula la cuenta contable
		"""
		if self.payment_method_id:
			# Obtener journals compatibles con este método de pago
			domain = [
				('type', 'in', ['bank', 'cash']),
				('company_id', '=', self.payment_id.company_id.id)
			]

			# Recalcular la cuenta contable
			self._compute_account_id_onchange()

			return {'domain': {'journal_id': domain}}

	@api.onchange('journal_id')
	def _onchange_journal_id(self):
		"""
		Al cambiar el diario, recalcula la cuenta contable
		"""
		if self.journal_id:
			self._compute_account_id_onchange()

	def _compute_account_id_onchange(self):
		"""
		Método auxiliar para recalcular la cuenta en onchange
		Fuerza la recalculación aunque account_id ya tenga valor
		"""
		for line in self:
			account = False

			if line.journal_id and line.payment_method_id:
				# Buscar el payment_method_line que coincida
				payment_type = line.payment_id.payment_type or 'outbound'

				# Obtener las líneas de método de pago disponibles para el journal
				payment_method_lines = line.journal_id._get_available_payment_method_lines(payment_type)

				# Buscar la línea que coincida con nuestro payment_method_id
				matching_line = payment_method_lines.filtered(
					lambda l: l.payment_method_id == line.payment_method_id
				)

				if matching_line:
					# Usar payment_account_id de la línea de método de pago
					account = matching_line[0].payment_account_id

				# Si no hay payment_account_id, usar la cuenta por defecto del journal
				if not account:
					account = line.journal_id.default_account_id

				# Como última opción, buscar una cuenta del tipo apropiado
				if not account and line.journal_id.type in ('bank', 'cash'):
					account_type = 'asset_cash' if line.journal_id.type == 'cash' else 'asset_cash_bank'
					account = self.env['account.account'].search([
						('account_type', '=', account_type),
						('company_id', '=', line.payment_id.company_id.id),
						('active', '=', True)
					], limit=1)

			# En onchange, siempre actualizamos la cuenta
			if account:
				line.account_id = account

	@api.constrains('account_id')
	def _check_account_id(self):
		"""Valida que la cuenta contable esté establecida antes de confirmar el pago"""
		for line in self:
			# Solo validar si el pago está en estado posted
			if line.payment_id.state == 'posted' and not line.account_id:
				raise ValidationError(_(
					"Debe establecer la cuenta contable para '%s'. "
					"Verifique que el diario '%s' tenga una cuenta por defecto configurada."
				) % (line.name or 'este método de pago', line.journal_id.name))

	@api.constrains('amount')
	def _check_amount(self):
		"""Valida que el monto sea positivo"""
		for line in self:
			if line.amount <= 0:
				raise ValidationError(_("El monto debe ser mayor a cero."))

	@api.constrains('check_number')
	def _check_check_number(self):
		"""Valida que se ingrese número de cheque si es necesario"""
		for line in self:
			if line.is_check and not line.check_number:
				raise ValidationError(_("Debe ingresar el número de cheque para pagos con cheque."))
