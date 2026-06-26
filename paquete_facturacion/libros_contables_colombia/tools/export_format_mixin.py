# -*- coding: utf-8 -*-
"""Mixin para exportacion basica a multiples formatos."""

from odoo import models
import csv
import json
import io
import base64
from datetime import datetime, date
from decimal import Decimal


class ExportFormatMixin(models.AbstractModel):
    """Mixin Version 1 - Exportacion basica a CSV, XML, JSON, TXT."""

    _name = 'export.format.mixin'
    _description = 'Mixin de Exportacion Basica'

    def _serialize_value(self, value):
        """Serializa valor para exportacion."""
        if value is None:
            return ''
        if isinstance(value, datetime):
            return value.strftime('%Y-%m-%d %H:%M:%S')
        if isinstance(value, date):
            return value.strftime('%Y-%m-%d')
        if isinstance(value, Decimal):
            return float(value)
        if isinstance(value, (list, tuple)):
            return ','.join(str(v) for v in value)
        return value

    def _format_number(self, value, decimals=2, thousands_sep=',', decimal_sep='.'):
        """Formatea numero con separadores."""
        if value is None:
            return ''
        try:
            num = float(value)
            formatted = f"{num:,.{decimals}f}"
            if thousands_sep != ',' or decimal_sep != '.':
                formatted = formatted.replace(',', 'TEMP')
                formatted = formatted.replace('.', decimal_sep)
                formatted = formatted.replace('TEMP', thousands_sep)
            return formatted
        except (ValueError, TypeError):
            return str(value)

    def export_to_csv(self, data, columns, options=None):
        """
        Exporta datos a CSV.

        Args:
            data: Lista de dicts con datos
            columns: Lista de dicts con {key, name, type}
            options: {delimiter, quotechar, encoding, include_header}

        Returns:
            bytes: Contenido CSV
        """
        options = options or {}
        delimiter = options.get('delimiter', ',')
        quotechar = options.get('quotechar', '"')
        encoding = options.get('encoding', 'utf-8')
        include_header = options.get('include_header', True)

        output = io.StringIO()
        writer = csv.writer(output, delimiter=delimiter, quotechar=quotechar,
                           quoting=csv.QUOTE_MINIMAL)

        if include_header:
            headers = [col.get('name', col.get('key', '')) for col in columns]
            writer.writerow(headers)

        for row in data:
            row_data = []
            for col in columns:
                key = col.get('key', '')
                value = row.get(key, '')
                col_type = col.get('type', 'text')

                if col_type == 'monetary':
                    value = self._format_number(value,
                                               options.get('decimal_places', 2))
                else:
                    value = self._serialize_value(value)
                row_data.append(value)
            writer.writerow(row_data)

        return output.getvalue().encode(encoding)

    def export_to_json(self, data, columns=None, options=None):
        """
        Exporta datos a JSON.

        Args:
            data: Lista de dicts con datos
            columns: Opcional - filtra solo estas columnas
            options: {indent, ensure_ascii, include_metadata}

        Returns:
            bytes: Contenido JSON
        """
        options = options or {}
        indent = options.get('indent', 2)
        ensure_ascii = options.get('ensure_ascii', False)
        include_metadata = options.get('include_metadata', True)

        if columns:
            keys = [col.get('key', '') for col in columns]
            filtered_data = []
            for row in data:
                filtered_row = {k: self._serialize_value(row.get(k))
                               for k in keys if k in row}
                filtered_data.append(filtered_row)
            export_data = filtered_data
        else:
            export_data = [{k: self._serialize_value(v) for k, v in row.items()}
                          for row in data]

        result = {
            'data': export_data,
        }

        if include_metadata:
            result['metadata'] = {
                'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'record_count': len(export_data),
                'company': self.env.company.name,
                'user': self.env.user.name,
            }

        return json.dumps(result, indent=indent, ensure_ascii=ensure_ascii).encode('utf-8')

    def export_to_xml(self, data, columns, options=None):
        """
        Exporta datos a XML basico.

        Args:
            data: Lista de dicts
            columns: Lista de columnas
            options: {root_element, row_element, encoding, pretty_print}

        Returns:
            bytes: Contenido XML
        """
        options = options or {}
        root_element = options.get('root_element', 'report')
        row_element = options.get('row_element', 'row')
        encoding = options.get('encoding', 'UTF-8')
        pretty_print = options.get('pretty_print', True)
        indent = '  ' if pretty_print else ''
        newline = '\n' if pretty_print else ''

        xml_parts = [f'<?xml version="1.0" encoding="{encoding}"?>{newline}']
        xml_parts.append(f'<{root_element}>{newline}')

        if options.get('include_metadata', True):
            xml_parts.append(f'{indent}<metadata>{newline}')
            xml_parts.append(f'{indent}{indent}<generated_at>{datetime.now().isoformat()}</generated_at>{newline}')
            xml_parts.append(f'{indent}{indent}<company>{self._escape_xml(self.env.company.name)}</company>{newline}')
            xml_parts.append(f'{indent}{indent}<record_count>{len(data)}</record_count>{newline}')
            xml_parts.append(f'{indent}</metadata>{newline}')

        xml_parts.append(f'{indent}<data>{newline}')

        for row in data:
            xml_parts.append(f'{indent}{indent}<{row_element}>{newline}')
            for col in columns:
                key = col.get('key', '')
                tag_name = col.get('xml_tag', key)
                value = self._serialize_value(row.get(key, ''))
                escaped_value = self._escape_xml(str(value))
                xml_parts.append(f'{indent}{indent}{indent}<{tag_name}>{escaped_value}</{tag_name}>{newline}')
            xml_parts.append(f'{indent}{indent}</{row_element}>{newline}')

        xml_parts.append(f'{indent}</data>{newline}')
        xml_parts.append(f'</{root_element}>')

        return ''.join(xml_parts).encode(encoding)

    def _escape_xml(self, text):
        """Escapa caracteres especiales XML."""
        if not text:
            return ''
        text = str(text)
        text = text.replace('&', '&amp;')
        text = text.replace('<', '&lt;')
        text = text.replace('>', '&gt;')
        text = text.replace('"', '&quot;')
        text = text.replace("'", '&apos;')
        return text

    def export_to_txt(self, data, columns, options=None):
        """
        Exporta datos a texto plano con formato fijo.

        Args:
            data: Lista de dicts
            columns: Lista con {key, width, align, fill}
            options: {line_separator, encoding}

        Returns:
            bytes: Contenido TXT
        """
        options = options or {}
        line_sep = options.get('line_separator', '\r\n')
        encoding = options.get('encoding', 'utf-8')

        lines = []

        if options.get('include_header', False):
            header_parts = []
            for col in columns:
                name = col.get('name', col.get('key', ''))
                width = col.get('width', 20)
                align = col.get('align', 'left')
                if align == 'right':
                    header_parts.append(name.rjust(width))
                elif align == 'center':
                    header_parts.append(name.center(width))
                else:
                    header_parts.append(name.ljust(width))
            lines.append(''.join(header_parts))

        for row in data:
            row_parts = []
            for col in columns:
                key = col.get('key', '')
                width = col.get('width', 20)
                align = col.get('align', 'left')
                fill = col.get('fill', ' ')
                col_type = col.get('type', 'text')

                value = row.get(key, '')
                if col_type == 'monetary':
                    value = self._format_number(value,
                                               col.get('decimals', 2),
                                               thousands_sep='',
                                               decimal_sep='.')
                else:
                    value = self._serialize_value(value)

                value = str(value)[:width]

                if align == 'right':
                    formatted = value.rjust(width, fill)
                elif align == 'center':
                    formatted = value.center(width, fill)
                else:
                    formatted = value.ljust(width, fill)
                row_parts.append(formatted)

            lines.append(''.join(row_parts))

        return line_sep.join(lines).encode(encoding)

    def export_to_fixed_width(self, data, field_specs):
        """
        Exporta a formato de ancho fijo (para DIAN, bancos, etc).

        Args:
            data: Lista de dicts
            field_specs: Lista de {key, start, length, type, format, default}

        Returns:
            bytes: Contenido con campos de ancho fijo
        """
        lines = []

        for row in data:
            line_chars = [' '] * sum(spec.get('length', 0) for spec in field_specs)
            current_pos = 0

            for spec in field_specs:
                length = spec.get('length', 0)
                key = spec.get('key', '')
                field_type = spec.get('type', 'text')
                default = spec.get('default', '')

                value = row.get(key, default)
                if value is None:
                    value = default

                if field_type == 'numeric':
                    decimals = spec.get('decimals', 0)
                    if decimals > 0:
                        value = str(int(float(value) * (10 ** decimals)))
                    else:
                        value = str(int(float(value) if value else 0))
                    value = value.zfill(length)[-length:]
                elif field_type == 'date':
                    if isinstance(value, (date, datetime)):
                        fmt = spec.get('format', '%Y%m%d')
                        value = value.strftime(fmt)
                    value = str(value)[:length].ljust(length)
                else:
                    value = str(value)[:length].ljust(length)

                for i, char in enumerate(value[:length]):
                    if current_pos + i < len(line_chars):
                        line_chars[current_pos + i] = char

                current_pos += length

            lines.append(''.join(line_chars))

        return '\r\n'.join(lines).encode('utf-8')

    def create_export_attachment(self, content, filename, mimetype='application/octet-stream'):
        """
        Crea attachment con el contenido exportado.

        Args:
            content: bytes del contenido
            filename: Nombre del archivo
            mimetype: Tipo MIME

        Returns:
            ir.attachment record
        """
        return self.env['ir.attachment'].create({
            'name': filename,
            'type': 'binary',
            'datas': base64.b64encode(content),
            'mimetype': mimetype,
        })

    def get_export_action(self, content, filename, mimetype='application/octet-stream'):
        """
        Retorna accion para descargar archivo.

        Args:
            content: bytes del contenido
            filename: Nombre archivo
            mimetype: Tipo MIME

        Returns:
            dict: Accion de descarga
        """
        attachment = self.create_export_attachment(content, filename, mimetype)
        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{attachment.id}?download=true',
            'target': 'self',
        }

    def export_report(self, data, columns, format_type, options=None):
        """
        Metodo unificado de exportacion.

        Args:
            data: Datos a exportar
            columns: Definicion de columnas
            format_type: 'csv', 'json', 'xml', 'txt', 'fixed'
            options: Opciones especificas del formato

        Returns:
            bytes: Contenido exportado
        """
        options = options or {}

        if format_type == 'csv':
            return self.export_to_csv(data, columns, options)
        elif format_type == 'json':
            return self.export_to_json(data, columns, options)
        elif format_type == 'xml':
            return self.export_to_xml(data, columns, options)
        elif format_type == 'txt':
            return self.export_to_txt(data, columns, options)
        elif format_type == 'fixed':
            return self.export_to_fixed_width(data, columns)
        else:
            raise ValueError(f"Formato no soportado: {format_type}")
