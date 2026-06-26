/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

export class DianDocumentWidget extends Component {
    setup() {
        this.notification = useService("notification");
        this.action = useService("action");
    }

    async onProcessDocument() {
        try {
            const result = await this.env.model.call(
                this.props.record.resModel,
                "process_xml_content",
                [this.props.record.resId]
            );

            if (result.success) {
                this.notification.add("Documento procesado exitosamente", {
                    type: "success",
                });
                await this.props.record.load();
            } else {
                this.notification.add(result.message || "Error al procesar documento", {
                    type: "danger",
                });
            }
        } catch (error) {
            this.notification.add("Error inesperado al procesar documento", {
                type: "danger",
            });
        }
    }

    async onValidateDocument() {
        try {
            const result = await this.env.model.call(
                this.props.record.resModel,
                "validate_totals",
                [this.props.record.resId]
            );

            if (result.valid) {
                this.notification.add("Validación exitosa", {
                    type: "success",
                });
            } else {
                this.notification.add("Validación con advertencias", {
                    type: "warning",
                });
            }

            await this.props.record.load();
        } catch (error) {
            this.notification.add("Error al validar documento", {
                type: "danger",
            });
        }
    }

    async onCreateInvoice() {
        try {
            const result = await this.env.model.call(
                this.props.record.resModel,
                "create_invoice",
                [this.props.record.resId]
            );

            if (result.invoice_id) {
                this.notification.add("Factura creada exitosamente", {
                    type: "success",
                });

                await this.action.doAction({
                    type: "ir.actions.act_window",
                    res_model: "account.move",
                    res_id: result.invoice_id,
                    views: [[false, "form"]],
                    target: "current",
                });
            }
        } catch (error) {
            this.notification.add("Error al crear factura", {
                type: "danger",
            });
        }
    }
}

DianDocumentWidget.template = "dian_document_processor.DianDocumentWidget";

registry.category("view_widgets").add("dian_document_widget", {
    component: DianDocumentWidget,
});