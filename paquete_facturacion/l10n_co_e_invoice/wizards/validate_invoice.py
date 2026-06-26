# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError
from datetime import datetime
import logging
_logger = logging.getLogger(__name__)
class ValidateInvoice(models.TransientModel):
    _name = 'ati.validate.invoice'
    _description = "Wizard - Validate multiple invoice"

    def validate_invoice(self):
        """
        Procesa facturas en lotes de 10, validando su estado antes de publicar
        """
        BATCH_SIZE = 10
        invoices = self._context.get('active_ids', [])
        total_invoices = len(invoices)
        processed = 0
        failed = []
        
        try:
            for start in range(0, total_invoices, BATCH_SIZE):
                batch = invoices[start:start + BATCH_SIZE]
                
                for invoice_id in batch:
                    try:
                        invoice = self.env['account.move'].browse(invoice_id)
                        
                        if not invoice.exists():
                            failed.append((invoice_id, _("Factura no encontrada")))
                            continue
                        
                        if invoice.state == 'posted':
                            _logger.info(f'Factura {invoice.name} ya está publicada, procediendo con validación DIAN')
                            invoice.dian_send_invoice()
                        elif invoice.state == 'draft':
                            _logger.info(f'Publicando factura {invoice.name} y validando en DIAN')
                            invoice.action_post()
                            invoice.dian_send_invoice()
                        else:
                            failed.append((invoice.name, f"Estado inválido: {invoice.state}"))
                            continue
                            
                        processed += 1
                        
                        if len(batch) == BATCH_SIZE:
                            self.env.cr.commit()
                    except Exception as e:
                        failed.append((invoice.name if invoice else invoice_id, str(e)))
                        _logger.error(f"Error procesando factura {invoice.name if invoice else invoice_id}: {str(e)}")
                        continue
                        
                _logger.info(f'Procesadas {processed} de {total_invoices} facturas')
        except Exception as e:
            raise UserError(_("Error en el proceso por lotes: %s") % str(e))
        
        finally:
            message = f"Proceso completado:\n"
            message += f"- Facturas procesadas: {processed}/{total_invoices}\n"
            
            if failed:
                message += "\nFacturas con error:\n"
                for invoice_name, error in failed:
                    message += f"- {invoice_name}: {error}\n"
                    
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Resultado de la Validación'),
                    'message': message,
                    'type': 'info' if not failed else 'warning',
                    'sticky': True,
                }
            }

    def _validate_batch(self, batch):
        """
        Valida un lote de facturas
        Returns:
            tuple: (procesadas, fallidas)
        """
        processed = []
        failed = []
        
        for invoice_id in batch:
            try:
                invoice = self.env['account.move'].browse(invoice_id)
                if not invoice.exists():
                    failed.append((invoice_id, "Factura no encontrada"))
                    continue
                    
                if invoice.state == 'posted':
                    invoice.dian_send_invoice()
                elif invoice.state == 'draft':
                    invoice.action_post()
                    invoice.dian_send_invoice()
                else:
                    failed.append((invoice.name, f"Estado inválido: {invoice.state}"))
                    continue
                    
                processed.append(invoice.name)
                
            except Exception as e:
                failed.append((invoice.name if invoice else invoice_id, str(e)))
                
        return processed, failed

class AccountMoveReversal(models.TransientModel):
    _inherit = "account.move.reversal"

    concepto_credit_note = fields.Selection(
        [("1", "Devolución parcial de los bienes y/o no aceptación parcial del servicio"),
        ("2", "Anulación de factura electrónica"),
        ("3", "Rebaja total aplicada"),
        ("4", "Ajuste de precio"),
        ("5", "Descuento comercial por pronto pago"),
        ("6", "Descuento comercial por volumen de ventas")],
        string="Concepto Corrección",
    )
    concept_debit_note = fields.Selection(
        [
            ("1", "Intereses"),
            ("2", "Gastos por cobrar"),
            ("3", "Cambio del valor"),
            ("4", "Otros"),
        ],
        u"Debito Concepto Corrección",
    )
    def reverse_moves(self, is_modify=False):
        res = super().reverse_moves(is_modify=is_modify)
        credit_note = self.env["account.move"].browse(res["res_id"])
        moves_old = self.move_ids
        for rec in moves_old:
            credit_note.write({ "concept_debit_note": self.concept_debit_note,
                            "concepto_credit_note": self.concepto_credit_note,
                            })
        return res
class ValidateInvoice(models.TransientModel):
    _name = 'application.response.wizard'
    _description = "Wizard - Eventos Dian"
