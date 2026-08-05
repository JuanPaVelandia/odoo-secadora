# -*- coding: utf-8 -*-
import json
import logging
from odoo import models, api

_logger = logging.getLogger(__name__)


class CertificateRetentionReport(models.AbstractModel):
    _name = 'report.l10n_co_exogenous_information_reporting.cert_retention'
    _description = 'Reporte PDF de certificado de retención'

    @api.model
    def _get_report_values(self, docids, data=None):
        """Prepara los datos para el template QWeb del certificado.

        Soporta dos modos:
        1. Desde historial (docids): lee certificate_data del registro
        2. Desde wizard (data): recibe cert_data directamente
        """
        docs = []

        if data and data.get('cert_data'):
            # Modo wizard: datos pasados directamente
            cert_data = data['cert_data']
            if isinstance(cert_data, str):
                cert_data = json.loads(cert_data)
            if isinstance(cert_data, dict):
                docs = [cert_data]
            elif isinstance(cert_data, list):
                docs = cert_data
        elif docids:
            # Modo historial: leer desde registros existentes
            records = self.env['l10n_co.exogenous_certificate_history'].browse(docids)
            for rec in records:
                if rec.certificate_data:
                    try:
                        cert_data = json.loads(rec.certificate_data)
                        docs.append(cert_data)
                    except (json.JSONDecodeError, TypeError):
                        _logger.warning(
                            "No se pudo parsear certificate_data del registro %s", rec.id)

        return {
            'docs': docs,
            'company': self.env.company,
        }
