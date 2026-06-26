from odoo import models, fields, api, _
from odoo.exceptions import AccessError, UserError, ValidationError
from contextlib import contextmanager
import logging

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
	_inherit = "account.move"

	# ========== CAMPOS PERSONALIZADOS ==========
	advance_payment_count = fields.Integer(string='Cantidad de Anticipos')
	has_advance_payment = fields.Boolean(string='Tiene Anticipos')

	# Campo para identificar asientos de anticipo
	is_advance_entry = fields.Boolean(
		string='Es Asiento de Anticipo',
		default=False,
		help='Marca si este asiento fue creado para aplicar un anticipo a una factura'
	)

	# Campo para identificar asientos de préstamo
	is_loan_entry = fields.Boolean(
		string='Es Asiento de Préstamo',
		default=False,
		help='Marca si este asiento fue creado para aplicar un préstamo a una factura'
	)

	force_partner_account = fields.Boolean(
		string='Forzar Cuenta del Tercero',
		help='Permite forzar una cuenta diferente a la configurada en el tercero'
	)
	forced_account_id = fields.Many2one(
		'account.account',
		string='Cuenta Forzada',
		domain="[('active', '=', True), ('company_ids', '=', company_id)]"
	)

	# Campo para habilitar multi-tercero en líneas
	enable_multi_partner = fields.Boolean(
		string='Habilitar Multi-Tercero',
		default=True,
		help='Permite asignar diferentes terceros a las líneas de productos (Solo en facturas, NC y recibos)'
	)

	# Campo computed para verificar anticipos disponibles
	has_advances = fields.Boolean(
		string='Tiene Anticipos Disponibles',
		compute='_compute_has_advances',
		store=False
	)

	# Campo computed para verificar préstamos disponibles
	has_loans = fields.Boolean(
		string='Tiene Préstamos Disponibles',
		compute='_compute_has_loans',
		store=False
	)

	# ========== VALIDACIONES ==========

	# @api.constrains('enable_multi_partner', 'move_type')
	# def _check_multi_partner_document_type(self):
	# 	"""Validar que multi-tercero solo se use en tipos de documento permitidos."""
	# 	allowed_types = ('out_invoice', 'out_refund', 'in_invoice', 'in_refund', 'out_receipt', 'in_receipt')
	# 	for move in self:
	# 		if move.enable_multi_partner and move.move_type not in allowed_types:
	# 			raise ValidationError(
	# 				_('Multi-Tercero solo está disponible para facturas, notas de crédito y recibos.')
	# 			)

	# ========== ONCHANGES ==========

	@api.onchange('force_partner_account')
	def _onchange_force_partner_account(self):
		"""Limpiar cuenta forzada si se desmarca la opción."""
		if not self.force_partner_account:
			self.forced_account_id = False
		else:
			self._update_forced_account_lines()

	@api.onchange('forced_account_id')
	def _onchange_forced_account_id(self):
		"""Actualizar líneas cuando cambia la cuenta forzada."""
		if self.force_partner_account and self.forced_account_id:
			self._update_forced_account_lines()

	@api.onchange('partner_id')
	def _onchange_partner_id(self):
		"""
		Override para manejar multi-partner.
		Llama al método nativo pero preserva partners personalizados si multi-partner está activo.
		"""
		res = super()._onchange_partner_id()

		if self.enable_multi_partner:
			pass

		return res

	# ========== MÉTODOS OVERRIDE CRÍTICOS ==========

	@api.model_create_multi
	def create(self, vals_list):
		"""
		Override para preservar partner_id en líneas cuando enable_multi_partner=True.

		El problema: Odoo sobrescribe partner_id de las líneas con el commercial_partner_id
		del header durante la creación Y durante el cálculo de impuestos.

		Solución:
		1. Guardamos los partner_ids originales de invoice_line_ids
		2. Restauramos los partners después del create
		3. Actualizamos los partners de las líneas de impuesto según las líneas de producto
		"""
		# Guardar partner_ids originales de las líneas para cada move
		original_partners_list = []  # Lista de dicts {idx_linea: partner_id}
		for vals in vals_list:
			partners_for_move = {}
			if vals.get('enable_multi_partner') and vals.get('invoice_line_ids'):
				for idx, line_command in enumerate(vals['invoice_line_ids']):
					if isinstance(line_command, (list, tuple)) and len(line_command) >= 3:
						# Command format: [0, 0, {vals}] para crear
						if line_command[0] == 0 and isinstance(line_command[2], dict):
							line_vals = line_command[2]
							if line_vals.get('partner_id'):
								partners_for_move[idx] = line_vals['partner_id']
			original_partners_list.append(partners_for_move)

		# Crear los moves
		moves = super().create(vals_list)

		# Restaurar partner_ids y actualizar impuestos si hay multi-partner
		for move_idx, move in enumerate(moves):
			if move_idx < len(original_partners_list) and original_partners_list[move_idx]:
				partners_for_move = original_partners_list[move_idx]
				if move.enable_multi_partner:
					# Obtener solo líneas de producto
					product_lines = move.invoice_line_ids.filtered(
						lambda l: l.display_type == 'product' or not l.display_type
					)

					# Construir mapeo de line_id -> partner_id y restaurar partners
					line_partner_map = {}
					for idx, partner_id in partners_for_move.items():
						if idx < len(product_lines):
							line = product_lines[idx]
							line_partner_map[line.id] = partner_id
							# Restaurar partner en la línea
							if line.partner_id.id != partner_id:
								line.with_context(skip_invoice_sync=True).write({
									'partner_id': partner_id
								})

					# Actualizar partners en líneas de impuesto
					if line_partner_map:
						move._update_tax_lines_partner(line_partner_map)

		return moves

	def _update_tax_lines_partner(self, line_partner_map):
		"""
		Actualiza el partner de las líneas de impuesto basándose en las líneas de producto.

		Para cada línea de impuesto:
		- Si el impuesto es usado por UN solo partner: asignar ese partner
		- Si el impuesto es compartido por MÚLTIPLES partners: dividir la línea
		"""
		self.ensure_one()
		if not self.enable_multi_partner:
			return

		# Mapear impuestos a sus datos de producto (partner + base)
		# {tax_id: [{partner_id, base_amount}, ...]}
		tax_to_products = {}
		for inv_line in self.invoice_line_ids.filtered(lambda l: l.display_type == 'product'):
			partner_id = line_partner_map.get(inv_line.id) or inv_line.partner_id.id
			base_amount = inv_line.price_subtotal
			for tax in inv_line.tax_ids:
				if tax.id not in tax_to_products:
					tax_to_products[tax.id] = []
				tax_to_products[tax.id].append({
					'partner_id': partner_id,
					'base_amount': base_amount,
					'tax': tax,
				})

		currency = self.currency_id
		is_sale = self.is_sale_document(include_receipts=True)

		# Procesar cada línea de impuesto
		for tax_line in self.line_ids.filtered(lambda l: l.display_type == 'tax'):
			tax = tax_line.tax_line_id or (
				tax_line.tax_repartition_line_id.tax_id if tax_line.tax_repartition_line_id else False
			)
			if not tax or tax.id not in tax_to_products:
				continue

			products_with_tax = tax_to_products[tax.id]

			# Caso 1: Solo un producto usa este impuesto - asignar partner
			if len(products_with_tax) == 1:
				new_partner_id = products_with_tax[0]['partner_id']
				if tax_line.partner_id.id != new_partner_id:
					tax_line.with_context(skip_invoice_sync=True).write({
						'partner_id': new_partner_id
					})
				continue

			# Caso 2: Múltiples productos - dividir la línea de impuesto
			total_base = sum(p['base_amount'] for p in products_with_tax)
			original_amount = abs(tax_line.debit or tax_line.credit)

			# Calcular montos por partner
			split_data = []
			remaining_amount = original_amount
			for i, prod in enumerate(products_with_tax):
				if i == len(products_with_tax) - 1:
					tax_amount = remaining_amount
				else:
					proportion = prod['base_amount'] / total_base if total_base else 0
					tax_amount = currency.round(original_amount * proportion)
					remaining_amount -= tax_amount

				split_data.append({
					'partner_id': prod['partner_id'],
					'amount': tax_amount,
					'base_amount': prod['base_amount'],
				})

			# Actualizar primera línea con el primer partner
			first_split = split_data[0]
			update_vals = {'partner_id': first_split['partner_id']}
			if tax_line.debit:
				update_vals['debit'] = first_split['amount']
			else:
				update_vals['credit'] = first_split['amount']

			tax_line.with_context(skip_invoice_sync=True, check_move_validity=False).write(update_vals)

			# Crear nuevas líneas para los demás partners
			for split in split_data[1:]:
				new_line_vals = {
					'move_id': self.id,
					'partner_id': split['partner_id'],
					'account_id': tax_line.account_id.id,
					'name': tax_line.name,
					'display_type': 'tax',
					'tax_line_id': tax.id,
					'tax_repartition_line_id': tax_line.tax_repartition_line_id.id if tax_line.tax_repartition_line_id else False,
					'debit': split['amount'] if tax_line.debit else 0,
					'credit': split['amount'] if not tax_line.debit else 0,
					'amount_currency': -split['amount'] if not tax_line.debit else split['amount'],
					'currency_id': currency.id,
					'tax_base_amount': split['base_amount'],
				}
				self.env['account.move.line'].with_context(
					skip_invoice_sync=True,
					check_move_validity=False
				).create(new_line_vals)


	def _inverse_partner_id(self):
		"""
		Override CRÍTICO para permitir multi-partner en invoices.

		En Odoo 18 nativo (línea 2171-2177):
		- FUERZA que todas las líneas tengan el mismo partner que el move
		- Hace: line.partner_id = invoice.commercial_partner_id

		Nuestra lógica:
		- Si enable_multi_partner = False: comportamiento estándar
		- Si enable_multi_partner = True: solo actualiza líneas sin partner o con partner igual al move
		"""
		for invoice in self:
			if not invoice.enable_multi_partner:
				super(AccountMove, invoice)._inverse_partner_id()
				continue

			if invoice.is_invoice(True):
				for line in invoice.line_ids + invoice.invoice_line_ids:
					if not line.partner_id or line.partner_id == invoice.partner_id:
						line.partner_id = invoice.commercial_partner_id
						line._inverse_partner_id()

	@contextmanager
	def _sync_invoice(self, container):
		"""
		Override CRÍTICO para evitar que Odoo sobrescriba partner_id de las líneas.

		PROBLEMA en Odoo nativo (account_move.py línea ~3186):
		El método _sync_invoice hace:
		   move.line_ids.partner_id = after[move]['commercial_partner_id']
		Esto FUERZA el partner del header a TODAS las líneas.

		SOLUCIÓN:
		Cuando enable_multi_partner=True, guardamos los partner_ids originales
		de las líneas ANTES del sync, y los restauramos DESPUÉS.

		BENEFICIO ADICIONAL:
		Al preservar partner_id, el método nativo _prepare_base_line_grouping_key()
		agrupa impuestos POR PARTNER (ya que partner_id está en la clave de agrupación).
		Esto significa que los impuestos se calcularán SEPARADOS por propietario automáticamente.
		"""
		# Guardar partner_ids originales de líneas con partner diferente al header
		original_partners = {}  # {line_id: partner_id}

		for move in container['records']:
			if getattr(move, 'enable_multi_partner', False) and move.is_invoice(include_receipts=True):
				for line in move.invoice_line_ids.filtered(lambda l: l.display_type == 'product' and l.partner_id):
					if line.partner_id != move.commercial_partner_id:
						original_partners[line.id] = line.partner_id.id

		# Ejecutar sync nativo (esto forzará partner_id al commercial_partner_id)
		with super()._sync_invoice(container):
			yield

		# Restaurar partner_ids originales
		if original_partners:
			for line_id, partner_id in original_partners.items():
				line = self.env['account.move.line'].browse(line_id)
				if line.exists():
					line.with_context(skip_invoice_sync=True).write({
						'partner_id': partner_id
					})

	def action_post(self):
		"""
		Override para preservar partners en facturas multi-partner durante el posting.

		PROBLEMA en Odoo nativo (account_move.py línea ~5127-5132):
		Antes de postear, Odoo "corrige" las líneas con partner diferente:
		   wrong_lines.write({'partner_id': invoice.commercial_partner_id.id})

		SOLUCIÓN:
		Guardamos los partners originales ANTES del super() y los restauramos DESPUÉS.
		"""
		# Guardar partners de líneas multi-partner antes del post
		partners_to_restore = {}  # {move_id: {line_id: partner_id}}

		for move in self.filtered(lambda m: m.is_invoice() and m.enable_multi_partner):
			line_partners = {}
			for line in move.line_ids.filtered(lambda l: l.partner_id and l.partner_id != move.commercial_partner_id):
				line_partners[line.id] = line.partner_id.id
			if line_partners:
				partners_to_restore[move.id] = line_partners

		# Ejecutar post estándar (esto "corregirá" los partners)
		result = super().action_post()

		# Restaurar partners originales
		for move_id, line_partners in partners_to_restore.items():
			for line_id, partner_id in line_partners.items():
				line = self.env['account.move.line'].browse(line_id)
				if line.exists() and line.partner_id.id != partner_id:
					line.with_context(skip_invoice_sync=True).write({
						'partner_id': partner_id
					})

		return result

	# ========== MÉTODOS DE CUENTA FORZADA ==========

	def _update_forced_account_lines(self):
		"""Actualizar las líneas con la cuenta forzada."""
		if not self.force_partner_account or not self.forced_account_id:
			return

		payment_term_lines = self.line_ids.filtered(
			lambda line: line.display_type == 'payment_term' or
			line.account_id.account_type in ('asset_receivable', 'liability_payable')
		)

		if payment_term_lines and self.forced_account_id:
			payment_term_lines.write({'account_id': self.forced_account_id.id})

	def _get_partner_account(self):
		"""Obtener cuenta del partner con soporte para forzar cuenta."""
		self.ensure_one()
		if self.force_partner_account and self.forced_account_id:
			return self.forced_account_id
		else:
			if self.move_type in ('out_invoice', 'out_refund', 'out_receipt'):
				return self.partner_id.property_account_receivable_id
			else:
				return self.partner_id.property_account_payable_id

	# ========== MÉTODOS DE ANTICIPOS ==========

	@api.depends('payment_state', 'partner_id')
	def _compute_has_advances(self):
		"""Verificar si el partner tiene anticipos disponibles."""
		for move in self:
			move.has_advances = False
			if move.state != 'posted' or not move.is_invoice():
				continue

			# Buscar líneas de anticipo disponibles para este partner
			advance_lines = self.env['account.move.line'].search([
				('partner_id', '=', move.commercial_partner_id.id),
				('account_id.used_for_advance_payment', '=', True),
				('reconciled', '=', False),
				('parent_state', '=', 'posted'),
				('company_id', '=', move.company_id.id),
				'|', ('amount_residual', '!=', 0.0), ('amount_residual_currency', '!=', 0.0),
			], limit=1)
			move.has_advances = bool(advance_lines)

	@api.depends('payment_state', 'partner_id')
	def _compute_has_loans(self):
		"""Verificar si el partner tiene préstamos disponibles."""
		for move in self:
			move.has_loans = False
			if move.state != 'posted' or not move.is_invoice():
				continue

			# Buscar líneas de préstamo disponibles para este partner
			loan_lines = self.env['account.move.line'].search([
				('partner_id', '=', move.commercial_partner_id.id),
				('account_id.used_for_loan', '=', True),
				('reconciled', '=', False),
				('parent_state', '=', 'posted'),
				('company_id', '=', move.company_id.id),
				'|', ('amount_residual', '!=', 0.0), ('amount_residual_currency', '!=', 0.0),
			], limit=1)
			move.has_loans = bool(loan_lines)

	def _compute_payments_widget_to_reconcile_info(self):
		"""
		Override para incluir cuentas de anticipo en el widget de pagos pendientes.
		"""
		for move in self:
			move.invoice_outstanding_credits_debits_widget = False
			move.invoice_has_outstanding = False

			if move.state != 'posted' \
					or move.payment_state not in ('not_paid', 'partial') \
					or not move.is_invoice(include_receipts=True):
				continue

			# Obtener cuentas normales (receivable/payable)
			pay_term_lines = move.line_ids.filtered(
				lambda line: line.account_id.account_type in ('asset_receivable', 'liability_payable')
			)

			# Obtener cuentas de anticipo
			advance_accounts = self.env['account.account'].search([
				('used_for_advance_payment', '=', True),
				('company_ids', '=', move.company_id.id)
			])

			# Obtener cuentas de préstamos
			loan_accounts = self.env['account.account'].search([
				('used_for_loan', '=', True),
				('company_ids', '=', move.company_id.id)
			])

			# Combinar todas las cuentas
			all_accounts = pay_term_lines.account_id | advance_accounts | loan_accounts

			domain = [
				('account_id', 'in', all_accounts.ids),
				('parent_state', '=', 'posted'),
				('partner_id', '=', move.commercial_partner_id.id),
				('reconciled', '=', False),
				'|', ('amount_residual', '!=', 0.0), ('amount_residual_currency', '!=', 0.0),
			]

			payments_widget_vals = {'outstanding': True, 'content': [], 'move_id': move.id}

			if move.is_inbound():
				domain.append(('balance', '<', 0.0))
				payments_widget_vals['title'] = _('Créditos pendientes')
			else:
				domain.append(('balance', '>', 0.0))
				payments_widget_vals['title'] = _('Débitos pendientes')

			# Buscar líneas
			lines_found = self.env['account.move.line'].search(domain)
			has_advance_lines = any(line.account_id.is_advance_account for line in lines_found)
			has_loan_lines = any(line.account_id.is_loan_account for line in lines_found)

			# Ajustar título si hay anticipos o préstamos
			if has_advance_lines and has_loan_lines:
				if move.is_inbound():
					payments_widget_vals['title'] = _('Créditos, Anticipos y Préstamos pendientes')
				else:
					payments_widget_vals['title'] = _('Débitos, Anticipos y Préstamos pendientes')
			elif has_advance_lines:
				if move.is_inbound():
					payments_widget_vals['title'] = _('Créditos y Anticipos pendientes')
				else:
					payments_widget_vals['title'] = _('Débitos y Anticipos pendientes')
			elif has_loan_lines:
				if move.is_inbound():
					payments_widget_vals['title'] = _('Créditos y Préstamos pendientes')
				else:
					payments_widget_vals['title'] = _('Débitos y Préstamos pendientes')

			# Construir contenido del widget
			for idx, line in enumerate(lines_found, 1):
				if line.currency_id == move.currency_id:
					amount = abs(line.amount_residual_currency)
				else:
					amount = line.company_currency_id._convert(
						abs(line.amount_residual),
						move.currency_id,
						move.company_id,
						line.date,
					)

				if move.currency_id.is_zero(amount):
					continue

				# Etiquetar anticipos y préstamos
				label = line.ref or line.move_id.name
				if line.account_id.used_for_advance_payment:
					label = _('Anticipo #%d: %s') % (idx, label)
				elif line.account_id.used_for_loan:
					label = _('Préstamo #%d: %s') % (idx, label)
				else:
					label = _('#%d: %s') % (idx, label)

				payments_widget_vals['content'].append({
					'journal_name': label,
					'amount': amount,
					'currency_id': move.currency_id.id,
					'id': line.id,
					'move_id': line.move_id.id,
					'date': fields.Date.to_string(line.date),
					'account_payment_id': line.payment_id.id,
					'is_advance': line.account_id.used_for_advance_payment,
					'is_loan': line.account_id.used_for_loan,
					'line_number': idx,
				})

			if not payments_widget_vals['content']:
				continue

			move.invoice_outstanding_credits_debits_widget = payments_widget_vals
			move.invoice_has_outstanding = True

	def js_assign_outstanding_line(self, line_id):
		"""
		Override para manejar anticipos y préstamos.
		- Si es cuenta de anticipo → crea asiento de cruce de anticipo
		- Si es cuenta de préstamo → crea asiento de cruce de préstamo
		- Si es pago normal → comportamiento estándar
		"""
		self.ensure_one()
		line = self.env['account.move.line'].browse(line_id)

		if not line:
			raise UserError(_("No se encontró la línea seleccionada."))

		# Si es anticipo, crear asiento de cruce
		if line.account_id.used_for_advance_payment:
			return self._create_advance_cross_entry(line)
		# Si es préstamo, crear asiento de cruce
		elif line.account_id.used_for_loan:
			return self._create_loan_cross_entry(line)
		else:
			# Comportamiento estándar
			return super().js_assign_outstanding_line(line_id)

	def _create_advance_cross_entry(self, advance_line):
		"""
		Crea asiento contable para cruzar anticipo con factura.
		"""
		self.ensure_one()

		if self.state != 'posted':
			raise UserError(_('Solo se pueden aplicar anticipos a facturas contabilizadas.'))

		# Obtener líneas de cuenta por cobrar/pagar
		invoice_lines = self.line_ids.filtered(
			lambda l: l.account_id.account_type in ('asset_receivable', 'liability_payable')
			and not l.reconciled
		)

		if not invoice_lines:
			raise UserError(_('No hay líneas pendientes de pago en esta factura.'))

		# Calcular monto a aplicar
		amount_to_apply = min(abs(advance_line.amount_residual), abs(self.amount_residual))

		# Conversión de moneda si es necesario
		if self.currency_id != advance_line.currency_id:
			amount_to_apply = advance_line.currency_id._convert(
				amount_to_apply,
				self.currency_id,
				self.company_id,
				fields.Date.today()
			)
		journal = self.company_id.advance_payment_journal_id
		if not journal:
			journal = self.env['account.journal'].search([
				('type', '=', 'general'),
				('company_id', '=', self.company_id.id)
			], limit=1)
		if not journal:
			raise UserError(_('No se encontró un diario para registrar el cruce de anticipo.'))

		# Determinar cuentas y montos según tipo de factura
		if self.move_type in ('out_invoice', 'in_refund'):
			debit_account = advance_line.account_id
			credit_account = invoice_lines[0].account_id
			debit_amount = amount_to_apply
			credit_amount = amount_to_apply
		else:
			debit_account = invoice_lines[0].account_id
			credit_account = advance_line.account_id
			debit_amount = amount_to_apply
			credit_amount = amount_to_apply

		# Preparar líneas del asiento
		debit_line_vals = {
			'account_id': debit_account.id,
			'partner_id': self.partner_id.id,
			'name': _('Aplicación de anticipo de %s') % advance_line.move_id.name,
			'debit': debit_amount,
			'credit': 0.0,
		}

		credit_line_vals = {
			'account_id': credit_account.id,
			'partner_id': self.partner_id.id,
			'name': _('Aplicación a factura %s') % self.name,
			'debit': 0.0,
			'credit': credit_amount,
		}

		# Solo agregar currency_id si hay moneda extranjera
		if self.currency_id != self.company_currency_id:
			debit_line_vals['currency_id'] = self.currency_id.id
			debit_line_vals['amount_currency'] = debit_amount
			credit_line_vals['currency_id'] = self.currency_id.id
			credit_line_vals['amount_currency'] = -credit_amount

		# Crear asiento de cruce
		move_vals = {
			'move_type': 'entry',
			'date': fields.Date.today(),
			'journal_id': journal.id,
			'currency_id': self.currency_id.id,
			'ref': _('Aplicación de anticipo a %s') % self.name,
			'is_advance_entry': True,
			'line_ids': [
				(0, 0, debit_line_vals),
				(0, 0, credit_line_vals)
			]
		}

		# Crear y contabilizar
		cross_move = self.env['account.move'].with_context(skip_invoice_sync=True).create(move_vals)
		cross_move.action_post()

		# Reconciliar
		lines_to_reconcile = self.env['account.move.line']
		lines_to_reconcile |= advance_line
		lines_to_reconcile |= cross_move.line_ids.filtered(lambda l: l.account_id == advance_line.account_id)
		lines_to_reconcile |= invoice_lines
		lines_to_reconcile |= cross_move.line_ids.filtered(lambda l: l.account_id == invoice_lines[0].account_id)

		# Reconciliar por cuenta
		for account in lines_to_reconcile.account_id:
			account_lines = lines_to_reconcile.filtered(lambda l: l.account_id == account)
			if len(account_lines) > 1:
				account_lines.reconcile()

		return True

	def _create_loan_cross_entry(self, loan_line):
		"""
		Crea asiento contable para cruzar préstamo con factura.
		Funciona de manera similar a _create_advance_cross_entry.
		"""
		self.ensure_one()

		if self.state != 'posted':
			raise UserError(_('Solo se pueden aplicar préstamos a facturas contabilizadas.'))

		# Obtener líneas de cuenta por cobrar/pagar
		invoice_lines = self.line_ids.filtered(
			lambda l: l.account_id.account_type in ('asset_receivable', 'liability_payable')
			and not l.reconciled
		)

		if not invoice_lines:
			raise UserError(_('No hay líneas pendientes de pago en esta factura.'))

		# Calcular monto a aplicar
		amount_to_apply = min(abs(loan_line.amount_residual), abs(self.amount_residual))

		# Conversión de moneda si es necesario
		if self.currency_id != loan_line.currency_id:
			amount_to_apply = loan_line.currency_id._convert(
				amount_to_apply,
				self.currency_id,
				self.company_id,
				fields.Date.today()
			)

		# Obtener diario (usar el mismo que anticipos o buscar uno general)
		journal = self.company_id.advance_payment_journal_id
		if not journal:
			journal = self.env['account.journal'].search([
				('type', '=', 'general'),
				('company_id', '=', self.company_id.id)
			], limit=1)
		if not journal:
			raise UserError(_('No se encontró un diario para registrar el cruce de préstamo.'))

		# Determinar cuentas y montos según tipo de factura
		if self.move_type in ('out_invoice', 'in_refund'):
			debit_account = loan_line.account_id
			credit_account = invoice_lines[0].account_id
			debit_amount = amount_to_apply
			credit_amount = amount_to_apply
		else:
			debit_account = invoice_lines[0].account_id
			credit_account = loan_line.account_id
			debit_amount = amount_to_apply
			credit_amount = amount_to_apply

		# Preparar líneas del asiento
		debit_line_vals = {
			'account_id': debit_account.id,
			'partner_id': self.partner_id.id,
			'name': _('Aplicación de préstamo de %s') % loan_line.move_id.name,
			'debit': debit_amount,
			'credit': 0.0,
		}

		credit_line_vals = {
			'account_id': credit_account.id,
			'partner_id': self.partner_id.id,
			'name': _('Aplicación a factura %s (Préstamo)') % self.name,
			'debit': 0.0,
			'credit': credit_amount,
		}

		# Solo agregar currency_id si hay moneda extranjera
		if self.currency_id != self.company_currency_id:
			debit_line_vals['currency_id'] = self.currency_id.id
			debit_line_vals['amount_currency'] = debit_amount
			credit_line_vals['currency_id'] = self.currency_id.id
			credit_line_vals['amount_currency'] = -credit_amount

		# Crear asiento de cruce
		move_vals = {
			'move_type': 'entry',
			'date': fields.Date.today(),
			'journal_id': journal.id,
			'currency_id': self.currency_id.id,
			'ref': _('Aplicación de préstamo a %s') % self.name,
			'is_advance_entry': False,  # Marcar como False para diferenciarlo de anticipos
			'is_loan_entry': True,  # Nuevo campo para identificar asientos de préstamos
			'line_ids': [
				(0, 0, debit_line_vals),
				(0, 0, credit_line_vals)
			]
		}

		# Crear y contabilizar
		cross_move = self.env['account.move'].with_context(skip_invoice_sync=True).create(move_vals)
		cross_move.action_post()

		# Reconciliar
		lines_to_reconcile = self.env['account.move.line']
		lines_to_reconcile |= loan_line
		lines_to_reconcile |= cross_move.line_ids.filtered(lambda l: l.account_id == loan_line.account_id)
		lines_to_reconcile |= invoice_lines
		lines_to_reconcile |= cross_move.line_ids.filtered(lambda l: l.account_id == invoice_lines[0].account_id)

		# Reconciliar por cuenta
		for account in lines_to_reconcile.account_id:
			account_lines = lines_to_reconcile.filtered(lambda l: l.account_id == account)
			if len(account_lines) > 1:
				account_lines.reconcile()

		return True

	def js_remove_outstanding_partial(self, partial_id):
		"""
		Override para eliminar anticipos y préstamos aplicados.
		- Si el partial es de un asiento de anticipo → lo elimina
		- Si el partial es de un asiento de préstamo → lo elimina
		- Si es normal → comportamiento estándar
		"""
		self.ensure_one()
		partial = self.env['account.partial.reconcile'].browse(partial_id)

		if not partial:
			return super().js_remove_outstanding_partial(partial_id)

		# Verificar si involucra asiento de anticipo o préstamo
		moves_involved = partial.debit_move_id.move_id | partial.credit_move_id.move_id
		advance_moves = moves_involved.filtered(lambda m: m.is_advance_entry)
		loan_moves = moves_involved.filtered(lambda m: m.is_loan_entry)

		# Combinar asientos de anticipos y préstamos
		special_moves = advance_moves | loan_moves

		if special_moves:
			# Desreconciliar
			partial.unlink()

			# Cancelar y eliminar asientos de anticipo/préstamo
			for move in special_moves:
				if move.state == 'posted':
					move.button_draft()
				move.button_cancel()
				move.with_context(force_delete=True).unlink()

			return True
		else:
			return super().js_remove_outstanding_partial(partial_id)