/** @odoo-module */

import { _t } from "@web/core/l10n/translation";
import { Component, useState } from "@odoo/owl";

/**
 * Popup para seleccionar el tipo de Nota Crédito según DIAN
 * Muestra información de la factura original y permite seleccionar el concepto de corrección
 */
export class NcTypePopup extends Component {
    static template = "l10n_co_e_pos.NcTypePopup";
    static props = {
        order: Object,
        originalOrder: { type: Object, optional: true },
        getPayload: Function,
        close: Function,
    };

    setup() {

        // Opciones de tipo de NC según DIAN (con descripciones mejoradas)
        this.ncTypes = [
            {
                value: "1",
                label: _t("Devolución parcial de bienes y/o no aceptación parcial del servicio"),
                description: _t("Use este tipo cuando el cliente devuelve solo algunos productos o rechaza parcialmente un servicio")
            },
            {
                value: "2",
                label: _t("Anulación de la factura electrónica"),
                description: _t("Use este tipo para anular completamente la factura original")
            },
            {
                value: "3",
                label: _t("Rebaja total aplicada"),
                description: _t("Use este tipo cuando se aplica un descuento sobre el total de la factura")
            },
            {
                value: "4",
                label: _t("Descuento parcial o total"),
                description: _t("Use este tipo para descuentos comerciales o promocionales")
            },
            {
                value: "5",
                label: _t("Rescisión: nulidad por falta de requisitos"),
                description: _t("Use este tipo cuando la factura no cumple requisitos legales")
            },
            {
                value: "6",
                label: _t("Otros"),
                description: _t("Use este tipo para motivos no contemplados en las categorías anteriores")
            },
        ];

        // Estado del popup
        this.state = useState({
            selectedType: this.props.order.get_l10n_co_edi_nc_type() || "1", // Default: devolución parcial
        });

        // Información de la factura original
        this.originalOrder = this.props.originalOrder || {};
    }

    /**
     * Confirmar selección y cerrar popup
     */
    confirm() {
        if (!this.state.selectedType) {
            return;
        }
        // Usar getPayload para devolver el resultado
        this.props.getPayload(this.state.selectedType);
        this.props.close();
    }

    /**
     * Cancelar y cerrar popup
     */
    cancel() {
        // Cerrar sin payload (null)
        this.props.getPayload(null);
        this.props.close();
    }

    /**
     * Obtener descripción del tipo seleccionado
     */
    get selectedTypeLabel() {
        const selected = this.ncTypes.find(type => type.value === this.state.selectedType);
        return selected ? selected.label : "";
    }

    /**
     * Formatear fecha para mostrar
     */
    formatDate(dateStr) {
        if (!dateStr) return "N/A";
        try {
            const date = new Date(dateStr);
            return date.toLocaleDateString();
        } catch (e) {
            return dateStr;
        }
    }

    /**
     * Formatear monto
     */
    formatAmount(amount) {
        if (!amount && amount !== 0) return "N/A";
        return this.env.utils.formatCurrency(amount);
    }
}
