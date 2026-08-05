# -*- coding: utf-8 -*-
import base64
import io
import os
import logging
from lxml import etree

from odoo import api, fields, models, _, Command
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)

class L10ncoExogenousFormat(models.Model):
    _name = "l10n_co.exogenous_format"
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = "Módulo para la creación de formatos requeridos para información exógena"
    _check_company_auto = True
    _rec_name = 'display_name'

    @api.model
    def _auto_init(self):
        res = super()._auto_init()
        self._cr.execute("""
            DO $$ BEGIN
                IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE indexname = 'l10n_co_exogenous_format_code_idx') THEN
                    CREATE INDEX l10n_co_exogenous_format_code_idx ON l10n_co_exogenous_format (code);
                END IF;
                IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE indexname = 'l10n_co_exogenous_format_company_id_idx') THEN
                    CREATE INDEX l10n_co_exogenous_format_company_id_idx ON l10n_co_exogenous_format (company_id);
                END IF;
            END $$;
        """)
        _logger.info("l10n_co.exogenous_format: _auto_init completed with custom indexes")
        return res

    @api.depends('code', 'name')
    def _compute_display_name(self):
        for rec in self:
            name_format = rec.name or ''
            if len(name_format) > 100:
                name_format = name_format[:100] + '...'
            rec.display_name = f'[{rec.code}] {name_format}'

    @api.constrains('code', 'year', 'company_id')
    def _check_unique_code_year_company(self):
        for record in self:
            domain = [
                ('code', '=', record.code),
                ('year', '=', record.year),
                ('company_id', '=', record.company_id.id),
                ('id', '!=', record.id),
            ]
            if self.search_count(domain):
                raise ValidationError(_(
                    "Ya existe un formato con código %s y año %s para esta compañía"
                ) % (record.code, record.year))


    report_type = fields.Selection(
        selection=[
            ('dian', 'DIAN (Nacional)'),
            ('district', 'Distrital / Municipal (ICA)'),
        ],
        string='Tipo de reporte',
        default='dian',
        required=True,
        tracking=True,
        help='DIAN para exógena nacional, Distrital para ICA municipal')
    district_id = fields.Many2one('l10n_co.exogenous_district',
        string='Distrito / Municipio',
        tracking=True,
        help='Municipio al que pertenece este formato distrital',
        check_company=True)

    name = fields.Char(string='Nombre', tracking=True)
    code = fields.Char(string='Código', tracking=True, size=4)
    active = fields.Boolean(string='Activo', default=True, tracking=True)

    version = fields.Char(string='Versión', tracking=True)
    appendix = fields.Char(string='Anexo', tracking=True)
    year = fields.Integer(
        string='Año gravable',
        default=2024,
        required=True,
        tracking=True,
        help='Año gravable al que corresponde la versión del formato (ej: 2024, 2025)')

    document_type_table_id = fields.Many2one('l10n_co.exogenous_document_type_table', string='Tabla de tipos de documento', tracking=True, check_company=True)
    is_it_with_date_range = fields.Boolean(string='Rango de fechas?', default=True)
    apply_concepts = fields.Boolean(string='Aplicar conceptos?', default=False)
    applying_smaller_amounts = fields.Boolean(string='Aplicar cuantías menores?', default=False)
    smaller_ammounts = fields.Monetary(string='Monto máximo', currency_field='company_currency_id', default=0.0)
    company_id = fields.Many2one(
        comodel_name='res.company', string='Compañía', default=lambda self: self.env.company.id)

    company_currency_id = fields.Many2one(
        string='Moneda de la compañía',
        related='company_id.currency_id', readonly=True,
    )

    xml_element_name = fields.Char(
        string='Elemento XML',
        help='Nombre del elemento XML para cada registro (ej: pagos, ingresos, rets)')
    xml_root_element = fields.Char(
        string='Elemento raíz XML',
        default='mas',
        help='Nombre del elemento raíz del XML (generalmente "mas")')
    xsd_version = fields.Integer(
        string='Versión XSD',
        help='Versión del esquema XSD para validación')

    xsd_file = fields.Binary(
        string='Archivo XSD',
        help='Archivo XSD para validación del XML generado')
    xsd_file_name = fields.Char(
        string='Nombre archivo XSD')

    def _parse_xsd_bytes(self, raw_bytes):
        """Parsea bytes de XSD detectando encoding para preservar ñ y tildes.

        Los XSD oficiales DIAN declaran ISO-8859-1 pero los archivos pueden
        venir re-guardados en UTF-8, cp1252 o con bytes corruptos. Este método
        prueba varias codificaciones y normaliza la declaración a UTF-8 antes
        de parsear con lxml para que el texto llegue correcto al parser.
        """
        if not raw_bytes:
            return None

        decoded = None
        for enc in ('utf-8', 'iso-8859-1', 'cp1252'):
            try:
                candidate = raw_bytes.decode(enc)
            except UnicodeDecodeError:
                continue
            if '\ufffd' not in candidate:
                decoded = candidate
                break
        if decoded is None:
            decoded = raw_bytes.decode('iso-8859-1', errors='replace')

        import re
        decoded = re.sub(
            r'<\?xml[^>]*encoding\s*=\s*"[^"]+"',
            '<?xml version="1.0" encoding="UTF-8"',
            decoded, count=1)
        return etree.parse(io.BytesIO(decoded.encode('utf-8')))

    def _get_xsd_document(self):
        """Obtiene el documento XSD parseado (binario o archivo local).

        Orden de búsqueda:
        1. Campo binario xsd_file subido al registro
        2. Archivo xsd/{code}_{year}.xsd (XSD específico del año)
        3. Archivo xsd/{code}.xsd (XSD genérico)
        """
        self.ensure_one()
        if self.xsd_file:
            try:
                xsd_content = base64.b64decode(self.xsd_file)
                return self._parse_xsd_bytes(xsd_content)
            except Exception as e:
                _logger.warning("Error leyendo XSD binario: %s", str(e))

        module_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        candidate_paths = []
        if self.year:
            candidate_paths.append(os.path.join(module_path, 'xsd', f'{self.code}_{self.year}.xsd'))
        candidate_paths.append(os.path.join(module_path, 'xsd', f'{self.code}.xsd'))

        for xsd_path in candidate_paths:
            if os.path.exists(xsd_path):
                try:
                    with open(xsd_path, 'rb') as f:
                        return self._parse_xsd_bytes(f.read())
                except Exception as e:
                    _logger.warning("Error leyendo XSD %s: %s", xsd_path, str(e))
        return None

    @staticmethod
    def _fix_iso8859_documentation(text):
        """Corrige caracteres corruptos de XSD codificados en ISO-8859-1.

        Casos manejados:
        - Mojibake `Ã©`, `Ã³`, `Ã±`, `Ãº`, `Ã¡`, `Ã­` (UTF-8 leído como Latin-1
          y re-guardado como UTF-8). Detección + recodificación auto.
        - Reemplazo U+FFFD ('�') por la letra correcta usando contexto.
        """
        if not text:
            return text
        if any(p in text for p in ('Ã©', 'Ã³', 'Ã±', 'Ãº', 'Ã¡', 'Ã­', 'Ã',
                                   'Ã', 'Ã', 'Ã', 'Ã', 'Ã')):
            try:
                fixed = text.encode('latin-1').decode('utf-8')
                if '�' not in fixed:
                    text = fixed
            except (UnicodeDecodeError, UnicodeEncodeError):
                pass
        replacements = {
            'N\ufffdmero': 'Número',
            'n\ufffdmero': 'número',
            'Identificaci\ufffdn': 'Identificación',
            'identificaci\ufffdn': 'identificación',
            'Raz\ufffdn': 'Razón',
            'raz\ufffdn': 'razón',
            'Direcci\ufffdn': 'Dirección',
            'direcci\ufffdn': 'dirección',
            'Pa\ufffds': 'País',
            'pa\ufffds': 'país',
            'Tel\ufffdfono': 'Teléfono',
            'tel\ufffdfono': 'teléfono',
            'C\ufffddigo': 'Código',
            'c\ufffddigo': 'código',
            'D\ufffdgito': 'Dígito',
            'd\ufffdgito': 'dígito',
            'Verificaci\ufffdn': 'Verificación',
            'verificaci\ufffdn': 'verificación',
            'informaci\ufffdn': 'información',
            'Informaci\ufffdn': 'Información',
            'retenci\ufffdn': 'retención',
            'Retenci\ufffdn': 'Retención',
            'deducci\ufffdn': 'deducción',
            'Deducci\ufffdn': 'Deducción',
            'operaci\ufffdn': 'operación',
            'Operaci\ufffdn': 'Operación',
            'enajenaci\ufffdn': 'enajenación',
            'Enajenaci\ufffdn': 'Enajenación',
            'declaraci\ufffdn': 'declaración',
            'Declaraci\ufffdn': 'Declaración',
            'aplicaci\ufffdn': 'aplicación',
            'Aplicaci\ufffdn': 'Aplicación',
            'Munici\ufffdio': 'Municipio',
            'munici\ufffdio': 'municipio',
            'Departamen\ufffdo': 'Departamento',
            'Secci\ufffdn': 'Sección',
            'secci\ufffdn': 'sección',
            'descripci\ufffdn': 'descripción',
            'Descripci\ufffdn': 'Descripción',
            'A\ufffdo': 'Año',
            'a\ufffdo': 'año',
            'Se\ufffdor': 'Señor',
            'Compa\ufffd\ufffda': 'Compañía',
            'compa\ufffd\ufffda': 'compañía',
            'Espa\ufffdol': 'Español',
            # Tildes sueltas al final: último fallback
            '\ufffd': '',
        }
        for bad, good in replacements.items():
            if bad in text:
                text = text.replace(bad, good)
        return text.strip()

    def action_load_fields_from_xsd(self):
        """Parsea el XSD y crea/actualiza campos de formato (format_field).

        Búsqueda de campos existentes:
        1. Busca por attribute en TODO el sistema (sin filtrar por formato)
        2. Si existe pero no está vinculado a este formato → lo vincula
        3. Si no existe → lo crea y vincula
        """
        self.ensure_one()

        xsd_doc = self._get_xsd_document()
        if not xsd_doc:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Sin XSD'),
                    'message': _('No se encontró archivo XSD. Suba uno en el campo "Archivo XSD" '
                                 'o colóquelo en la carpeta xsd/%s.xsd') % self.code,
                    'type': 'warning',
                    'sticky': False,
                }
            }

        root = xsd_doc.getroot()
        ns = {'xs': 'http://www.w3.org/2001/XMLSchema'}

        element_name = self.xml_element_name
        if not element_name:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Sin elemento XML'),
                    'message': _('Configure el campo "Elemento XML" antes de cargar el XSD'),
                    'type': 'warning',
                    'sticky': False,
                }
            }

        element = root.find(f".//xs:element[@name='{element_name}']", ns)
        if element is None:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Elemento no encontrado'),
                    'message': _('No se encontró el elemento "%s" en el XSD') % element_name,
                    'type': 'danger',
                    'sticky': True,
                }
            }

        complex_type = element.find('xs:complexType', ns)
        if complex_type is None:
            return self._show_notification(_('XSD inválido'), _('No se encontró complexType'), 'danger')

        attributes = complex_type.findall('xs:attribute', ns)
        if not attributes:
            return self._show_notification(_('Sin atributos'), _('El elemento no tiene atributos'), 'warning')

        FormatField = self.env['l10n_co.exogenous_format_field']
        created = 0
        updated = 0
        linked = 0

        for seq, attr in enumerate(attributes, 1):
            attr_name = attr.get('name')
            is_required = attr.get('use') == 'required'
            documentation = ''

            doc_el = attr.find('.//xs:documentation', ns)
            if doc_el is not None and doc_el.text:
                documentation = self._fix_iso8859_documentation(doc_el.text)

            xsd_type = 'string'
            min_length = 0
            max_length = 0
            pattern = ''
            min_value = ''
            max_value = ''

            restriction = attr.find('.//xs:restriction', ns)
            if restriction is not None:
                base_type = restriction.get('base', 'xs:string')
                type_map = {
                    'xs:string': 'string', 'xs:int': 'int', 'xs:long': 'long',
                    'xs:double': 'double', 'xs:date': 'date',
                    'xs:dateTime': 'dateTime', 'xs:gYear': 'gYear',
                    'xs:positiveInteger': 'int',
                }
                xsd_type = type_map.get(base_type, 'string')

                min_len_el = restriction.find('xs:minLength', ns)
                if min_len_el is not None:
                    min_length = int(min_len_el.get('value', 0))

                max_len_el = restriction.find('xs:maxLength', ns)
                if max_len_el is not None:
                    max_length = int(max_len_el.get('value', 0))

                pattern_el = restriction.find('xs:pattern', ns)
                if pattern_el is not None:
                    pattern = pattern_el.get('value', '')

                min_inc = restriction.find('xs:minInclusive', ns)
                if min_inc is not None:
                    min_value = min_inc.get('value', '')

                max_inc = restriction.find('xs:maxInclusive', ns)
                if max_inc is not None:
                    max_value = max_inc.get('value', '')

                if not max_length and max_value:
                    max_length = len(str(max_value))

            xsd_vals = {
                'xsd_type': xsd_type,
                'xsd_required': is_required,
                'xsd_pattern': pattern or False,
                'xsd_min_value': min_value or False,
                'xsd_max_value': max_value or False,
                'min_length': min_length,
                'max_length': max_length or 0,
            }

            def _maybe_fix_name(rec, new_name):
                if not new_name or new_name == rec.attribute:
                    return None
                cur_name = rec.name or ''
                if any(p in cur_name for p in ('Ã', 'Â', '�', 'â€')):
                    return new_name
                return None

            # 1) Buscar campo ya vinculado a este formato
            existing = FormatField.search([
                ('attribute', '=', attr_name),
                ('format_ids', 'in', self.id),
            ], limit=1)

            if existing:
                vals_to_write = dict(xsd_vals)
                fix = _maybe_fix_name(existing, documentation)
                if fix:
                    vals_to_write['name'] = fix
                existing.write(vals_to_write)
                updated += 1
                continue

            # 2) Buscar campo global (mismo attribute, cualquier formato)
            global_field = FormatField.search([
                ('attribute', '=', attr_name),
            ], limit=1)

            if global_field:
                vals_to_write = dict(xsd_vals)
                fix = _maybe_fix_name(global_field, documentation)
                if fix:
                    vals_to_write['name'] = fix
                global_field.write(vals_to_write)
                global_field.write({'format_ids': [Command.link(self.id)]})
                linked += 1
            else:
                # 3) Crear campo nuevo
                xsd_vals.update({
                    'name': documentation or attr_name,
                    'attribute': attr_name,
                    'sequence': seq * 10,
                    'format_ids': [Command.link(self.id)],
                })
                FormatField.create(xsd_vals)
                created += 1

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('XSD cargado'),
                'message': _('%d creados, %d actualizados, %d vinculados desde el XSD') % (created, updated, linked),
                'type': 'success',
                'sticky': False,
            }
        }

    def _show_notification(self, title, message, ntype='info'):
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {'title': title, 'message': message, 'type': ntype, 'sticky': ntype == 'danger'}
        }

