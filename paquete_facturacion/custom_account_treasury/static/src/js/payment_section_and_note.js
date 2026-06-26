/** @odoo-module **/

import { registry } from "@web/core/registry";
import { ListRenderer } from "@web/views/list/list_renderer";
import { X2ManyField, x2ManyField } from "@web/views/fields/x2many/x2many_field";
import { TextField, ListTextField } from "@web/views/fields/text/text_field";
import { CharField } from "@web/views/fields/char/char_field";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { Component, useEffect } from "@odoo/owl";

/**
 * Renderer personalizado para listas de líneas de pago con soporte de secciones y notas.
 * Extiende SectionAndNoteListRenderer del módulo account para pagos/cobros.
 */
export class PaymentSectionAndNoteListRenderer extends ListRenderer {
    static template = "custom_account_treasury.PaymentSectionAndNoteListRenderer";

    setup() {
        super.setup();
        this.titleField = "name";
        useEffect(
            (editedRecord) => this.focusToName(editedRecord),
            () => [this.editedRecord]
        );
    }

    focusToName(editRec) {
        if (editRec && editRec.isNew && this.isSectionOrNote(editRec)) {
            const col = this.columns.find((c) => c.name === this.titleField);
            if (col) {
                this.focusCell(col, null);
            }
        }
    }

    /**
     * Verifica si un registro es una sección o nota
     */
    isSectionOrNote(record = null) {
        record = record || this.record;
        return ['line_section', 'line_note'].includes(record?.data?.display_type);
    }

    /**
     * Verifica si un registro es una línea principal (banco/caja, contrapartida, etc.)
     */
    isMainLine(record = null) {
        record = record || this.record;
        return record?.data?.is_main === true;
    }

    /**
     * Obtiene el tipo de cuenta (receivable/payable) del registro
     */
    getAccountType(record = null) {
        record = record || this.record;
        const accountId = record?.data?.account_id;
        if (accountId && accountId.length > 1) {
            // El account_id es un array [id, display_name]
            // Necesitamos obtener el tipo desde los datos del registro
            return record?.data?.account_type || null;
        }
        return null;
    }

    /**
     * Clases CSS para la fila según el tipo de línea
     */
    getRowClass(record) {
        const existingClasses = super.getRowClass(record);
        const displayType = record?.data?.display_type || '';

        let additionalClasses = '';

        if (this.isSectionOrNote(record)) {
            additionalClasses = `o_is_${displayType}`;
        }

        if (this.isMainLine(record)) {
            additionalClasses += ' o_is_main_line';
        }

        // Clases para tipos de cuenta
        if (record?.data?.account_id) {
            const accountType = record?.data?.account_type;
            if (accountType === 'asset_receivable') {
                additionalClasses += ' o_account_receivable';
            } else if (accountType === 'liability_payable') {
                additionalClasses += ' o_account_payable';
            }
        }

        return `${existingClasses} ${additionalClasses}`.trim();
    }

    /**
     * Clases CSS para celdas - oculta campos irrelevantes para secciones/notas
     */
    getCellClass(column, record) {
        const classNames = super.getCellClass(column, record);

        if (this.isSectionOrNote(record)) {
            // Solo mostrar handle y name para secciones/notas
            if (column.widget !== "handle" && column.name !== this.titleField) {
                return `${classNames} o_hidden`;
            }
        }

        return classNames;
    }

    /**
     * Obtiene las columnas a mostrar según el tipo de registro
     */
    getColumns(record) {
        const columns = super.getColumns(record);

        if (this.isSectionOrNote(record)) {
            return this.getSectionColumns(columns);
        }

        return columns;
    }

    /**
     * Columnas para secciones y notas (solo handle + name con colspan)
     */
    getSectionColumns(columns) {
        const sectionCols = columns.filter(
            (col) => col.widget === "handle" || (col.type === "field" && col.name === this.titleField)
        );

        return sectionCols.map((col) => {
            if (col.name === this.titleField) {
                return { ...col, colspan: columns.length - sectionCols.length + 1 };
            }
            return { ...col };
        });
    }
}

/**
 * Campo One2Many personalizado para líneas de pago con secciones y notas
 */
export class PaymentSectionAndNoteFieldOne2Many extends X2ManyField {
    static components = {
        ...X2ManyField.components,
        ListRenderer: PaymentSectionAndNoteListRenderer,
    };
}

/**
 * Widget de texto para secciones y notas en líneas de pago
 */
export class PaymentSectionAndNoteText extends Component {
    static template = "custom_account_treasury.PaymentSectionAndNoteText";
    static props = { ...standardFieldProps };

    get componentToUse() {
        const displayType = this.props.record?.data?.display_type;
        return displayType === 'line_section' ? CharField : TextField;
    }

    get isSection() {
        return this.props.record?.data?.display_type === 'line_section';
    }

    get isNote() {
        return this.props.record?.data?.display_type === 'line_note';
    }

    get placeholder() {
        if (this.isSection) {
            return "Nombre de la sección...";
        }
        if (this.isNote) {
            return "Escriba una nota...";
        }
        return "Descripción...";
    }
}

/**
 * Versión de lista del widget de texto
 */
export class ListPaymentSectionAndNoteText extends PaymentSectionAndNoteText {
    get componentToUse() {
        const displayType = this.props.record?.data?.display_type;
        return displayType !== "line_section" ? ListTextField : CharField;
    }
}

// Registro de widgets
export const paymentSectionAndNoteFieldOne2Many = {
    ...x2ManyField,
    component: PaymentSectionAndNoteFieldOne2Many,
    additionalClasses: [...(x2ManyField.additionalClasses || []), "o_field_one2many", "o_payment_lines_field"],
};

export const paymentSectionAndNoteText = {
    component: PaymentSectionAndNoteText,
    additionalClasses: ["o_field_text"],
};

export const listPaymentSectionAndNoteText = {
    ...paymentSectionAndNoteText,
    component: ListPaymentSectionAndNoteText,
};

// Registrar en el registry de campos
registry.category("fields").add("payment_section_and_note_one2many", paymentSectionAndNoteFieldOne2Many);
registry.category("fields").add("payment_section_and_note_text", paymentSectionAndNoteText);
registry.category("fields").add("list.payment_section_and_note_text", listPaymentSectionAndNoteText);
