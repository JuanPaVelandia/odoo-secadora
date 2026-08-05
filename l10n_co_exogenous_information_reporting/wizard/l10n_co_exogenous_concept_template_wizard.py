# -*- coding: utf-8 -*-
import base64
import io
import logging

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

from odoo import api, fields, models, _, Command
from odoo.exceptions import UserError

from odoo.addons.l10n_co_exogenous_information_reporting.models.l10n_co_exogenous_format_field_account import (
    NATURE_ACCOUNT_SELECTION,
)

_logger = logging.getLogger(__name__)

JOURNAL_TYPE_SELECTION = [
    ('all', 'Todos los diarios'),
    ('sale', 'Ventas'),
    ('purchase', 'Compras'),
    ('cash', 'Efectivo'),
    ('bank', 'Banco'),
    ('general', 'Varios'),
    ('situation', 'Situación de apertura'),
]

NATURE_CODE_LABELS = dict(NATURE_ACCOUNT_SELECTION)
NATURE_VALID_CODES = [code for code, _label in NATURE_ACCOUNT_SELECTION]
JOURNAL_TYPE_VALID_CODES = [code for code, _label in JOURNAL_TYPE_SELECTION]


class L10nCoExogenousConceptTemplateWizard(models.TransientModel):
    """Wizard para exportar/importar plantilla de conceptos exógena.

    Exporta un Excel con encabezados configurables (formato, columnas elegidas
    y opción de tipo de diario) que el usuario llena y reimporta para crear
    o actualizar conceptos y su configuración de cuentas por columna.
    """
    _name = 'l10n_co.exogenous_concept_template_wizard'
    _description = 'Plantilla de conceptos exógena (export/import)'

    company_id = fields.Many2one(
        'res.company',
        string='Compañía',
        default=lambda self: self.env.company,
        required=True,
    )
    format_id = fields.Many2one(
        'l10n_co.exogenous_format',
        string='Formato',
        required=True,
        help='Formato DIAN o distrital para el cual se generará la plantilla',
    )
    apply_concepts = fields.Boolean(
        related='format_id.apply_concepts', readonly=True,
    )
    column_ids = fields.Many2many(
        'l10n_co.exogenous_format_field',
        'l10n_co_exogenous_concept_tpl_wiz_field_rel',
        'wizard_id',
        'field_id',
        string='Columnas a incluir',
        help='Columnas del formato (source=journal_items) que aparecerán en la plantilla. '
             'Si se deja vacío se incluyen todas las columnas configurables.',
    )
    journal_type = fields.Selection(
        JOURNAL_TYPE_SELECTION,
        string='Tipo de diario',
        default='all',
        required=True,
        help='Tipo de diario al que apunta la plantilla. Se guarda como metadato '
             'en el Excel y se ofrece como sugerencia por fila durante la importación.',
    )
    include_existing = fields.Boolean(
        string='Pre-cargar conceptos existentes',
        default=False,
        help='Si está marcado, la plantilla se exporta con los conceptos ya creados '
             'para este formato (código y nombre rellenos). Útil para auditar o ampliar.',
    )
    include_examples = fields.Boolean(
        string='Incluir fila ejemplo',
        default=True,
        help='Agrega una fila ejemplo con valores demostrativos.',
    )

    binary_file = fields.Binary(string='Plantilla generada', readonly=True)
    binary_file_name = fields.Char(string='Nombre archivo plantilla', readonly=True)

    import_file = fields.Binary(string='Plantilla a importar')
    import_file_name = fields.Char(string='Nombre archivo importado')

    import_summary = fields.Text(string='Resumen del último import', readonly=True)

    @api.onchange('format_id')
    def _onchange_format_id(self):
        self.column_ids = [Command.clear()]
        if not self.format_id:
            return
        cols = self._available_columns()
        self.column_ids = [Command.set(cols.ids)]

    def _available_columns(self):
        """Columnas elegibles del formato (journal_items, ordenadas)."""
        self.ensure_one()
        if not self.format_id:
            return self.env['l10n_co.exogenous_format_field']
        return self.env['l10n_co.exogenous_format_field'].search([
            ('format_ids', 'in', self.format_id.id),
            ('source', '=', 'journal_items'),
        ], order='sequence, id')

    # ============================================================
    # EXPORT
    # ============================================================
    def action_export_template(self):
        self.ensure_one()
        if not self.format_id:
            raise UserError(_('Seleccione un formato.'))

        columns = self.column_ids or self._available_columns()
        if not columns:
            raise UserError(_(
                'El formato %s no tiene columnas (source=journal_items) configuradas.'
            ) % self.format_id.code)

        wb = Workbook()
        self._build_concepts_sheet(wb, columns)
        self._build_instructions_sheet(wb, columns)
        self._build_lookup_sheet(wb)

        buf = io.BytesIO()
        wb.save(buf)

        file_name = 'plantilla_conceptos_%s_%s.xlsx' % (
            self.format_id.code or 'fmt', self.journal_type or 'all',
        )
        self.binary_file = base64.b64encode(buf.getvalue())
        self.binary_file_name = file_name

        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/%s/%d/binary_file/%s?download=true' % (
                self._name, self.id, file_name,
            ),
            'target': 'self',
        }

    def _build_concepts_sheet(self, wb, columns):
        ws = wb.active
        ws.title = 'Conceptos'

        header_font = Font(bold=True, color='FFFFFF')
        header_fill = PatternFill(start_color='4472C4', end_color='4472C4', fill_type='solid')
        sub_fill = PatternFill(start_color='8FAADC', end_color='8FAADC', fill_type='solid')
        info_fill = PatternFill(start_color='FFF2CC', end_color='FFF2CC', fill_type='solid')
        thin = Side(style='thin', color='999999')
        border = Border(left=thin, right=thin, top=thin, bottom=thin)
        center = Alignment(horizontal='center', vertical='center', wrap_text=True)
        left = Alignment(horizontal='left', vertical='center', wrap_text=True)

        ws['A1'] = 'Formato'
        ws['B1'] = '[%s] %s' % (self.format_id.code or '', self.format_id.name or '')
        ws['A2'] = 'Tipo diario'
        ws['B2'] = dict(JOURNAL_TYPE_SELECTION).get(self.journal_type, self.journal_type)
        ws['A3'] = 'Compañía'
        ws['B3'] = self.company_id.name
        for row in (1, 2, 3):
            ws.cell(row=row, column=1).font = Font(bold=True)
            ws.cell(row=row, column=1).fill = info_fill
            ws.cell(row=row, column=2).fill = info_fill

        header_row = 5
        sub_row = 6
        fixed_headers = [
            ('Código', 12),
            ('Nombre', 60),
            ('Tipo diario fila', 18),
        ]
        col_idx = 1
        for label, width in fixed_headers:
            cell = ws.cell(row=header_row, column=col_idx, value=label)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = center
            cell.border = border
            ws.merge_cells(start_row=header_row, start_column=col_idx,
                           end_row=sub_row, end_column=col_idx)
            ws.column_dimensions[get_column_letter(col_idx)].width = width
            col_idx += 1

        first_dyn_col = col_idx
        for col in columns:
            label = '[%s] %s' % (col.attribute or '', col.name or col.attribute or '')
            ws.merge_cells(start_row=header_row, start_column=col_idx,
                           end_row=header_row, end_column=col_idx + 1)
            top_cell = ws.cell(row=header_row, column=col_idx, value=label)
            top_cell.font = header_font
            top_cell.fill = header_fill
            top_cell.alignment = center
            top_cell.border = border

            sub_pat = ws.cell(row=sub_row, column=col_idx, value='Patrón cuentas')
            sub_nat = ws.cell(row=sub_row, column=col_idx + 1, value='Naturaleza')
            for c in (sub_pat, sub_nat):
                c.font = Font(bold=True)
                c.fill = sub_fill
                c.alignment = center
                c.border = border
            ws.column_dimensions[get_column_letter(col_idx)].width = 22
            ws.column_dimensions[get_column_letter(col_idx + 1)].width = 18
            ws.column_dimensions[get_column_letter(col_idx)].number_format = '@'
            col_idx += 2

        last_col_idx = col_idx - 1
        ws.row_dimensions[header_row].height = 32
        ws.row_dimensions[sub_row].height = 22
        ws.freeze_panes = ws.cell(row=sub_row + 1, column=4)

        first_data_row = sub_row + 1

        # Validaciones de datos
        nat_first = first_dyn_col + 1
        for col in columns:
            letter = get_column_letter(nat_first)
            dv = DataValidation(
                type='list',
                formula1='Listas!$A$2:$A$%d' % (1 + len(NATURE_ACCOUNT_SELECTION)),
                allow_blank=True,
            )
            dv.error = 'Naturaleza no válida. Use el desplegable.'
            dv.errorTitle = 'Naturaleza inválida'
            ws.add_data_validation(dv)
            dv.add('%s%d:%s1000' % (letter, first_data_row, letter))
            nat_first += 2

        jt_letter = get_column_letter(3)
        dv_jt = DataValidation(
            type='list',
            formula1='Listas!$C$2:$C$%d' % (1 + len(JOURNAL_TYPE_SELECTION)),
            allow_blank=True,
        )
        dv_jt.error = 'Tipo de diario no válido.'
        dv_jt.errorTitle = 'Diario inválido'
        ws.add_data_validation(dv_jt)
        dv_jt.add('%s%d:%s1000' % (jt_letter, first_data_row, jt_letter))

        rows_data = []
        if self.include_existing:
            Concept = self.env['l10n_co.exogenous_concept']
            existing = Concept.search([
                *Concept._check_company_domain(self.company_id),
                ('format_id', '=', self.format_id.id),
            ], order='code')
            for concept in existing:
                row = [concept.code or '', concept.name or '', self.journal_type or '']
                fa_by_field = {
                    fa.format_field_id.id: fa
                    for fa in concept.field_account_ids if fa.format_field_id
                }
                for col in columns:
                    fa = fa_by_field.get(col.id)
                    row.append(fa.account_pattern if fa else '')
                    row.append(fa.nature_account if fa else '')
                rows_data.append(row)

        if self.include_examples and not rows_data:
            example = ['9999', 'Ejemplo - Reemplace por su concepto', self.journal_type or 'all']
            for col in columns:
                example.append('')
                example.append('db_cr')
            rows_data.append(example)

        pat_col_indices = set()
        for i in range(len(columns)):
            pat_col_indices.add(first_dyn_col + i * 2)
        for r_offset, row_values in enumerate(rows_data):
            for c_offset, value in enumerate(row_values):
                col_n = 1 + c_offset
                cell = ws.cell(row=first_data_row + r_offset, column=col_n, value=value)
                cell.border = border
                cell.alignment = left if c_offset in (0, 1) else center
                if col_n in pat_col_indices:
                    cell.number_format = '@'

        for col_n in pat_col_indices:
            for r in range(first_data_row, first_data_row + 200):
                cell = ws.cell(row=r, column=col_n)
                if cell.number_format != '@':
                    cell.number_format = '@'

    def _build_instructions_sheet(self, wb, columns):
        ws = wb.create_sheet('Instrucciones')
        title_font = Font(bold=True, size=14, color='FFFFFF')
        title_fill = PatternFill(start_color='4472C4', end_color='4472C4', fill_type='solid')
        head_font = Font(bold=True)

        ws['A1'] = 'Plantilla de conceptos - Información Exógena'
        ws['A1'].font = title_font
        ws['A1'].fill = title_fill
        ws.merge_cells('A1:D1')
        ws.row_dimensions[1].height = 24

        lines = [
            '1. La hoja "Conceptos" tiene 3 columnas fijas (Código, Nombre, Tipo diario) y dos columnas por '
            'cada columna del formato seleccionado (Patrón y Naturaleza).',
            '2. El formato y la compañía se reconocen automáticamente al importar (no los modifique).',
            '3. "Patrón cuentas" admite varios patrones separados por coma. Use % como comodín. '
            'Ejemplo: 5105%, 5110%.',
            '4. "Naturaleza" debe ser uno de los códigos válidos (use el desplegable). Lista a la derecha.',
            '5. "Tipo diario fila" es metadato (no obligatorio). Sirve para anotar a qué tipo de diario aplica '
            'la fila si esta plantilla mezcla varios.',
            '6. Al importar, los conceptos se crean si no existen (por código + formato + compañía) o se '
            'actualizan los existentes. Las configuraciones por columna se actualizan/recrean.',
        ]
        for i, text in enumerate(lines, start=3):
            ws.cell(row=i, column=1, value=text).alignment = Alignment(wrap_text=True, vertical='top')
            ws.merge_cells(start_row=i, start_column=1, end_row=i, end_column=4)
            ws.row_dimensions[i].height = 32

        head_row = i + 2
        ws.cell(row=head_row, column=1, value='Códigos válidos de Naturaleza').font = head_font
        ws.cell(row=head_row, column=3, value='Códigos válidos de Tipo diario').font = head_font
        for j, (code, label) in enumerate(NATURE_ACCOUNT_SELECTION, start=1):
            ws.cell(row=head_row + j, column=1, value=code)
            ws.cell(row=head_row + j, column=2, value=label)
        for j, (code, label) in enumerate(JOURNAL_TYPE_SELECTION, start=1):
            ws.cell(row=head_row + j, column=3, value=code)
            ws.cell(row=head_row + j, column=4, value=label)

        cols_row = head_row + max(len(NATURE_ACCOUNT_SELECTION), len(JOURNAL_TYPE_SELECTION)) + 3
        ws.cell(row=cols_row, column=1, value='Columnas incluidas en esta plantilla').font = head_font
        ws.cell(row=cols_row + 1, column=1, value='Atributo').font = head_font
        ws.cell(row=cols_row + 1, column=2, value='Etiqueta').font = head_font
        ws.cell(row=cols_row + 1, column=3, value='XSD').font = head_font
        for k, col in enumerate(columns, start=2):
            ws.cell(row=cols_row + k, column=1, value=col.attribute or '')
            ws.cell(row=cols_row + k, column=2, value=col.name or '')
            ws.cell(row=cols_row + k, column=3, value=col.xsd_type or '')

        for letter, width in (('A', 24), ('B', 36), ('C', 24), ('D', 32)):
            ws.column_dimensions[letter].width = width

    def _build_lookup_sheet(self, wb):
        ws = wb.create_sheet('Listas')
        ws['A1'] = 'naturaleza_codigo'
        ws['B1'] = 'naturaleza_etiqueta'
        ws['C1'] = 'tipo_diario_codigo'
        ws['D1'] = 'tipo_diario_etiqueta'
        for c in ('A1', 'B1', 'C1', 'D1'):
            ws[c].font = Font(bold=True)
        for i, (code, label) in enumerate(NATURE_ACCOUNT_SELECTION, start=2):
            ws.cell(row=i, column=1, value=code)
            ws.cell(row=i, column=2, value=label)
        for i, (code, label) in enumerate(JOURNAL_TYPE_SELECTION, start=2):
            ws.cell(row=i, column=3, value=code)
            ws.cell(row=i, column=4, value=label)
        ws.sheet_state = 'hidden'

    # ============================================================
    # IMPORT
    # ============================================================
    def action_import_template(self):
        self.ensure_one()
        if not self.import_file:
            raise UserError(_('Adjunte el archivo de plantilla a importar.'))
        if not self.format_id:
            raise UserError(_('Seleccione el formato al que pertenecen los conceptos importados.'))

        try:
            buf = io.BytesIO(base64.b64decode(self.import_file))
            wb = load_workbook(buf, data_only=True)
        except Exception as e:
            raise UserError(_('No se pudo leer el archivo: %s') % str(e))

        if 'Conceptos' not in wb.sheetnames:
            raise UserError(_('La plantilla no contiene la hoja "Conceptos".'))
        ws = wb['Conceptos']

        header_row = 5
        sub_row = 6
        first_data_row = 7

        column_specs = []
        col = 4
        max_col = ws.max_column or 4
        while col <= max_col:
            label_cell = ws.cell(row=header_row, column=col).value
            if not label_cell:
                col += 1
                continue
            attribute = self._extract_attribute(label_cell)
            if not attribute:
                col += 2
                continue
            ff = self.env['l10n_co.exogenous_format_field'].search([
                ('format_ids', 'in', self.format_id.id),
                ('attribute', '=', attribute),
            ], limit=1)
            if not ff:
                _logger.warning("Plantilla: columna '%s' no existe en formato %s",
                                attribute, self.format_id.code)
                col += 2
                continue
            column_specs.append({
                'pat_col': col,
                'nat_col': col + 1,
                'format_field': ff,
                'attribute': attribute,
            })
            col += 2

        if not column_specs:
            raise UserError(_(
                'No se encontraron columnas válidas en la plantilla para el formato %s.'
            ) % self.format_id.code)

        Concept = self.env['l10n_co.exogenous_concept']
        FieldAccount = self.env['l10n_co.exogenous_format_field_account']

        created_concepts = 0
        updated_concepts = 0
        created_fa = 0
        updated_fa = 0
        skipped_rows = 0
        warnings = []

        row = first_data_row
        empty_streak = 0
        while empty_streak < 5:
            code_value = ws.cell(row=row, column=1).value
            name_value = ws.cell(row=row, column=2).value
            if not code_value and not name_value:
                empty_streak += 1
                row += 1
                continue
            empty_streak = 0
            row_journal = ws.cell(row=row, column=3).value

            code = str(code_value).strip() if code_value is not None else ''
            if not code:
                skipped_rows += 1
                warnings.append(_('Fila %d: sin código, omitida.') % row)
                row += 1
                continue

            if row_journal and str(row_journal).strip() not in JOURNAL_TYPE_VALID_CODES:
                warnings.append(_('Fila %d: tipo diario "%s" no es válido.')
                                % (row, row_journal))

            concept = Concept.search([
                *Concept._check_company_domain(self.company_id),
                ('code', '=', code),
                ('format_id', '=', self.format_id.id),
            ], limit=1)
            vals = {
                'code': code,
                'name': str(name_value).strip() if name_value else (concept.name if concept else code),
                'format_id': self.format_id.id,
                'company_id': self.company_id.id,
            }
            if concept:
                concept.write({k: v for k, v in vals.items() if v not in (None, '')})
                updated_concepts += 1
            else:
                concept = Concept.create(vals)
                created_concepts += 1

            existing_fa_by_field = {
                fa.format_field_id.id: fa
                for fa in concept.field_account_ids if fa.format_field_id
            }

            for spec in column_specs:
                pat_cell = ws.cell(row=row, column=spec['pat_col'])
                pat_value = pat_cell.value
                nat_value = ws.cell(row=row, column=spec['nat_col']).value

                if isinstance(pat_value, float):
                    fmt = (pat_cell.number_format or '').lower()
                    if '%' in fmt:
                        # Excel guardó "5105%" como 51.05 con formato %.
                        # Recuperar el numero original multiplicando *100.
                        recovered = int(round(pat_value * 100))
                        pat_value = '%d%%' % recovered
                    elif pat_value == int(pat_value):
                        pat_value = '%d' % int(pat_value)
                    else:
                        pat_value = str(pat_value)

                pat = str(pat_value).strip() if pat_value not in (None, '') else ''
                nat = str(nat_value).strip() if nat_value else ''

                if not pat and not nat:
                    continue

                if nat and nat not in NATURE_VALID_CODES:
                    warnings.append(_(
                        'Fila %d, columna %s: naturaleza "%s" inválida, ignorada.'
                    ) % (row, spec['attribute'], nat))
                    nat = ''

                fa = existing_fa_by_field.get(spec['format_field'].id)
                fa_vals = {
                    'concept_id': concept.id,
                    'format_field_id': spec['format_field'].id,
                    'company_id': self.company_id.id,
                }
                if pat:
                    fa_vals['account_pattern'] = pat
                if nat:
                    fa_vals['nature_account'] = nat

                if fa:
                    fa.write({k: v for k, v in fa_vals.items()
                              if k not in ('concept_id', 'format_field_id', 'company_id')})
                    if pat:
                        accounts = fa._get_accounts_from_pattern()
                        fa.account_ids = [Command.set(accounts.ids)]
                        if not accounts:
                            warnings.append(_(
                                'Fila %d, columna %s: patrón "%s" no coincidió con ninguna cuenta de %s.'
                            ) % (row, spec['attribute'], pat, self.company_id.name))
                    updated_fa += 1
                else:
                    fa_vals.setdefault('nature_account', 'db_cr')
                    new_fa = FieldAccount.create(fa_vals)
                    if pat:
                        accounts = new_fa._get_accounts_from_pattern()
                        new_fa.account_ids = [Command.set(accounts.ids)]
                        if not accounts:
                            warnings.append(_(
                                'Fila %d, columna %s: patrón "%s" no coincidió con ninguna cuenta de %s.'
                            ) % (row, spec['attribute'], pat, self.company_id.name))
                    created_fa += 1

            row += 1

        summary_lines = [
            _('Conceptos creados: %d') % created_concepts,
            _('Conceptos actualizados: %d') % updated_concepts,
            _('Configuraciones de columna creadas: %d') % created_fa,
            _('Configuraciones de columna actualizadas: %d') % updated_fa,
            _('Filas omitidas: %d') % skipped_rows,
        ]
        if warnings:
            summary_lines.append('')
            summary_lines.append(_('Avisos:'))
            summary_lines.extend(warnings[:50])
            if len(warnings) > 50:
                summary_lines.append(_('... y %d avisos más') % (len(warnings) - 50))
        self.import_summary = '\n'.join(summary_lines)

        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    @staticmethod
    def _extract_attribute(label):
        """Extrae el atributo XSD desde un encabezado tipo '[pago] Pago deducible'."""
        if not label:
            return ''
        text = str(label).strip()
        if text.startswith('[') and ']' in text:
            return text[1:text.index(']')].strip()
        return text.split(' ', 1)[0].strip()
