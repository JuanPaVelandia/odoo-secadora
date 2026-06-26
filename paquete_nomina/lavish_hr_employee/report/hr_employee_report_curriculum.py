# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools.safe_eval import safe_eval

import io
import base64
import logging

_logger = logging.getLogger(__name__)

# Odoo 19: pypdf es la libreria recomendada (reemplaza PyPDF2)
try:
    from pypdf import PdfReader, PdfWriter
except ImportError:
    try:
        from PyPDF2 import PdfReader, PdfWriter
    except ImportError:
        _logger.warning("No se encontro pypdf ni PyPDF2. Funcionalidad PDF limitada.")
        PdfReader = None
        PdfWriter = None


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    def open_hr_employee_report_curriculum(self):
        """Abre el wizard para generar informe configurable de hoja de vida"""
        return {
            'name': _('Informe configurable hoja de vida'),
            'type': 'ir.actions.act_window',
            'res_model': 'hr.employee.report.curriculum',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_employee_ids': self.ids,
            }
        }


class HrEmployeeReportCurriculum(models.TransientModel):
    _name = 'hr.employee.report.curriculum'
    _description = 'Informe configurable hoja de vida'

    employee_ids = fields.Many2many(
        'hr.employee',
        string='Empleados'
    )
    domain_documents = fields.Char(
        string='Filtro documentos'
    )
    include_resume_curriculum = fields.Boolean(
        string='Incluir formato datos personales'
    )
    document_ids = fields.One2many(
        'hr.employee.report.curriculum.documents',
        'report_id',
        string='Documentos'
    )
    order_fields = fields.Many2many(
        'ir.model.fields',
        domain="[('model', '=', 'documents.document'), ('ttype', 'not in', ['many2many', 'one2many', 'text', 'binary'])]",
        string='Campos para ordenar'
    )
    save_favorite = fields.Boolean(
        string='Guardar como favorito'
    )
    name = fields.Char(
        string='Nombre'
    )
    favorite_id = fields.Many2one(
        'hr.employee.report.curriculum.favorites',
        string='Favorito'
    )
    pdf_file = fields.Binary(
        'PDF file'
    )
    pdf_file_name = fields.Char(
        'PDF name'
    )

    @api.depends('name')
    def _compute_display_name(self):
        for record in self:
            record.display_name = _("Informe configurable hoja de vida")

    @api.onchange('domain_documents', 'order_fields')
    def load_documents(self):
        """Carga los documentos basados en el filtro aplicado usando search_read"""
        for record in self:
            record.document_ids = False

            if not record.employee_ids:
                continue

            # Obtener work_contact_ids usando search_read
            employee_data = self.env['hr.employee'].search_read(
                [('id', 'in', record.employee_ids.ids)],
                ['work_contact_id']
            )
            work_contact_ids = [
                e['work_contact_id'][0]
                for e in employee_data
                if e.get('work_contact_id')
            ]

            if not work_contact_ids:
                continue

            # Dominio obligatorio: documentos PDF del partner del empleado
            domain = [
                ('partner_id', 'in', work_contact_ids),
                ('mimetype', 'ilike', 'pdf')
            ]

            if record.domain_documents:
                try:
                    domain += safe_eval(record.domain_documents)
                except Exception as e:
                    _logger.warning(f"Error evaluando filtro de documentos: {e}")
                    continue

            # Construir orden de busqueda
            lst_order = ['partner_id']
            if record.order_fields:
                order_field_data = self.env['ir.model.fields'].search_read(
                    [('id', 'in', record.order_fields.ids)],
                    ['name']
                )
                for field in order_field_data:
                    if field['name'] not in lst_order:
                        lst_order.append(field['name'])

            str_order = ','.join(lst_order)

            # Buscar documentos con search_read
            documents = self.env['documents.document'].search_read(
                domain,
                ['id', 'partner_id'],
                order=str_order
            )

            lst_documents = []
            for i, doc in enumerate(documents, start=1):
                vals = {
                    'sequence': i,
                    'partner_id': doc['partner_id'][0] if doc.get('partner_id') else False,
                    'document_id': doc['id'],
                }
                lst_documents.append((0, 0, vals))

            record.document_ids = lst_documents

    def _get_documents_data(self):
        """Obtiene datos de documentos optimizado con search_read"""
        self.ensure_one()

        if not self.document_ids:
            return {}

        # Obtener IDs de documentos
        doc_line_data = self.env['hr.employee.report.curriculum.documents'].search_read(
            [('report_id', '=', self.id)],
            ['sequence', 'partner_id', 'document_id'],
            order='sequence'
        )

        if not doc_line_data:
            return {}

        # Obtener IDs unicos de documentos
        document_ids = [d['document_id'][0] for d in doc_line_data if d.get('document_id')]

        # Leer documentos en batch
        documents_data = self.env['documents.document'].search_read(
            [('id', 'in', document_ids)],
            ['id', 'name', 'mimetype', 'attachment_id']
        )
        docs_by_id = {d['id']: d for d in documents_data}

        # Obtener attachments en batch
        attachment_ids = [
            d['attachment_id'][0]
            for d in documents_data
            if d.get('attachment_id')
        ]
        if attachment_ids:
            attachments_data = self.env['ir.attachment'].search_read(
                [('id', 'in', attachment_ids)],
                ['id', 'raw', 'datas']
            )
            attachments_by_id = {a['id']: a for a in attachments_data}
        else:
            attachments_by_id = {}

        # Construir resultado agrupado por partner
        result = {}
        for line in doc_line_data:
            partner_id = line['partner_id'][0] if line.get('partner_id') else None
            doc_id = line['document_id'][0] if line.get('document_id') else None

            if not partner_id or not doc_id:
                continue

            doc = docs_by_id.get(doc_id, {})
            attachment_id = doc.get('attachment_id')[0] if doc.get('attachment_id') else None
            attachment = attachments_by_id.get(attachment_id, {})

            if partner_id not in result:
                result[partner_id] = []

            result[partner_id].append({
                'sequence': line['sequence'],
                'name': doc.get('name', ''),
                'mimetype': doc.get('mimetype', ''),
                'raw': attachment.get('raw'),
            })

        return result

    def _get_employees_data(self):
        """Obtiene datos de empleados optimizado con search_read"""
        self.ensure_one()

        if not self.employee_ids:
            return []

        return self.env['hr.employee'].search_read(
            [('id', 'in', self.employee_ids.ids)],
            ['id', 'name', 'work_contact_id']
        )

    def generate_pdf(self):
        """Genera el PDF combinando documentos de empleados"""
        self.ensure_one()

        if not PdfWriter or not PdfReader:
            raise ValidationError(_("Libreria PDF no disponible. Instale pypdf: pip install pypdf"))

        # Guardar favorito si el check estaba marcado
        if self.save_favorite:
            self.save_favorite_process()

        # Obtener reporte de datos personales
        report_personal_data = self.env['ir.actions.report']._get_report_from_name(
            'lavish_hr_employee.report_personal_data_form_template'
        )
        if not report_personal_data:
            report_personal_data = self.env['ir.actions.report'].search([
                ('report_name', '=', 'lavish_hr_employee.report_personal_data_form_template'),
            ], limit=1)

        # Obtener datos usando search_read
        employees_data = self._get_employees_data()
        documents_by_partner = self._get_documents_data()

        files_to_merge = []
        filename = 'Informe Hoja de vida.pdf'

        # Recorrer empleados
        for employee in employees_data:
            employee_name = employee.get('name', '')
            work_contact_id = employee['work_contact_id'][0] if employee.get('work_contact_id') else None

            # Incluir formato datos personales
            if self.include_resume_curriculum and report_personal_data:
                try:
                    pdf_content, content_type = report_personal_data._render_qweb_pdf(
                        report_personal_data.id,
                        [employee['id']]
                    )
                    files_to_merge.append((employee_name, 'Formato Datos Personales', pdf_content))
                except Exception as e:
                    _logger.warning(f"Error generando PDF para {employee_name}: {e}")

            # Obtener documentos del empleado
            if work_contact_id and work_contact_id in documents_by_partner:
                docs = sorted(documents_by_partner[work_contact_id], key=lambda x: x['sequence'])
                for doc in docs:
                    if not doc.get('mimetype') or 'pdf' not in doc['mimetype'].lower():
                        raise ValidationError(_(
                            "El archivo '%s' no es formato PDF, por favor verificar."
                        ) % doc.get('name', ''))

                    if doc.get('raw'):
                        files_to_merge.append((employee_name, doc['name'], doc['raw']))

        if not files_to_merge:
            raise ValidationError(_("No hay documentos para generar el informe."))

        # Unir PDFs usando pypdf (Odoo 19)
        writer = PdfWriter()

        for file_info in files_to_merge:
            employee_name, doc_name, pdf_bytes = file_info
            try:
                reader = PdfReader(io.BytesIO(pdf_bytes))
                for page in reader.pages:
                    writer.add_page(page)
            except Exception as e:
                msg_error = _('Empleado: %s\nDocumento: %s\nError: %s') % (
                    employee_name, doc_name, str(e)
                )
                raise ValidationError(msg_error)

        result_stream = io.BytesIO()
        writer.write(result_stream)

        # Guardar PDF
        self.write({
            'pdf_file': base64.encodebytes(result_stream.getvalue()),
            'pdf_file_name': filename,
        })

        # Descargar reporte
        return {
            'name': 'InformeHojaDeVida',
            'type': 'ir.actions.act_url',
            'url': f"web/content/?model=hr.employee.report.curriculum&id={self.id}"
                   f"&filename_field=pdf_file_name&field=pdf_file&download=true"
                   f"&filename={self.pdf_file_name}",
            'target': 'self',
        }

    def save_favorite_process(self):
        """Guarda la configuracion actual como favorito"""
        self.ensure_one()

        if not self.name:
            raise ValidationError(_("Debe digitar un nombre para guardar como favorito."))
        if not self.domain_documents:
            raise ValidationError(_("Debe seleccionar un filtro para guardar como favorito."))

        self.env['hr.employee.report.curriculum.favorites'].create({
            'name': self.name,
            'domain_documents': self.domain_documents,
        })

    @api.onchange('favorite_id')
    def load_favorite_process(self):
        """Carga la configuracion del favorito seleccionado"""
        if self.favorite_id:
            self.domain_documents = self.favorite_id.domain_documents


class HrEmployeeReportCurriculumDocuments(models.TransientModel):
    _name = 'hr.employee.report.curriculum.documents'
    _description = 'Informe configurable hoja de vida - documentos'
    _order = 'sequence'

    report_id = fields.Many2one(
        'hr.employee.report.curriculum',
        string='Reporte',
        required=True,
        ondelete='cascade'
    )
    sequence = fields.Integer(
        string='Secuencia',
        required=True,
        default=10
    )
    partner_id = fields.Many2one(
        'res.partner',
        string='Empleado',
        required=True
    )
    document_id = fields.Many2one(
        'documents.document',
        string='Documento',
        required=True
    )


class HrEmployeeReportCurriculumFavorites(models.Model):
    _name = 'hr.employee.report.curriculum.favorites'
    _description = 'Informe configurable hoja de vida - favoritos'

    name = fields.Char(
        string='Nombre',
        required=True
    )
    domain_documents = fields.Char(
        string='Filtro documentos',
        required=True
    )

    _curriculum_favorites_uniq = models.Constraint('unique(name)',
                                                   'Ya existe un favorito con este nombre, por favor verificar.')
