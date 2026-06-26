/** @odoo-module **/

import { ListController } from "@web/views/list/list_controller";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";

export class PayslipListController extends ListController {
    setup() {
        super.setup();
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.dialog = useService("dialog");
    }

    /**
     * Generar reporte de liquidación para registros seleccionados
     */
    async onGenerateSettlementReport() {
        const selectedRecords = await this.getSelectedRecords();

        if (selectedRecords.length === 0) {
            this.notification.add(_t("Por favor seleccione al menos una nómina"), {
                type: "warning"
            });
            return;
        }

        try {
            const result = await this.orm.call(
                "hr.payslip",
                "generate_settlement_report",
                [selectedRecords.map(r => r.id)],
                { context: this.props.context }
            );

            if (result && result.id) {
                // Abrir el reporte generado
                this.action.doAction({
                    type: "ir.actions.act_window",
                    res_model: "hr.payslip.settlement.report",
                    res_id: result.id,
                    views: [[false, "form"]],
                    target: "current"
                });

                this.notification.add(_t("Reporte de liquidación generado exitosamente"), {
                    type: "success"
                });
            }
        } catch (error) {
            this.notification.add(_t("Error al generar reporte: ") + error.message, {
                type: "danger"
            });
        }
    }

    /**
     * Enviar nóminas por correo (con cola de correos)
     */
    async onSendByEmail() {
        const selectedRecords = await this.getSelectedRecords();

        if (selectedRecords.length === 0) {
            this.notification.add(_t("Por favor seleccione al menos una nómina"), {
                type: "warning"
            });
            return;
        }

        this.dialog.add("lavish_hr_payroll.EmailWizardDialog", {
            title: _t("Enviar Nóminas por Correo"),
            payslipIds: selectedRecords.map(r => r.id),
            onConfirm: async (emailData) => {
                try {
                    const result = await this.orm.call(
                        "hr.payslip",
                        "send_payslips_by_email",
                        [selectedRecords.map(r => r.id)],
                        {
                            email_options: emailData,
                            use_queue: true, // Usar cola de correos
                            context: this.props.context
                        }
                    );

                    this.notification.add(
                        _t(`${result.queued_count} correo(s) agregados a la cola de envío`),
                        { type: "success" }
                    );

                    // Recargar lista
                    await this.model.root.load();
                } catch (error) {
                    this.notification.add(_t("Error al enviar correos: ") + error.message, {
                        type: "danger"
                    });
                }
            }
        });
    }

    /**
     * Imprimir nóminas seleccionadas
     */
    async onPrintPayslips() {
        const selectedRecords = await this.getSelectedRecords();

        if (selectedRecords.length === 0) {
            this.notification.add(_t("Por favor seleccione al menos una nómina"), {
                type: "warning"
            });
            return;
        }

        try {
            const result = await this.orm.call(
                "hr.payslip",
                "print_payslips",
                [selectedRecords.map(r => r.id)],
                { context: this.props.context }
            );

            if (result && result.type === "ir.actions.report") {
                this.action.doAction(result);
            }
        } catch (error) {
            this.notification.add(_t("Error al imprimir: ") + error.message, {
                type: "danger"
            });
        }
    }

    /**
     * Aprobar nóminas en lote
     */
    async onApprovePayslips() {
        const selectedRecords = await this.getSelectedRecords();

        if (selectedRecords.length === 0) {
            this.notification.add(_t("Por favor seleccione al menos una nómina"), {
                type: "warning"
            });
            return;
        }

        const draftRecords = selectedRecords.filter(r => r.state === "draft");
        if (draftRecords.length === 0) {
            this.notification.add(_t("No hay nóminas en borrador para aprobar"), {
                type: "warning"
            });
            return;
        }

        this.dialog.add("web.ConfirmationDialog", {
            title: _t("Aprobar Nóminas"),
            body: _t(`¿Desea aprobar ${draftRecords.length} nómina(s)?`),
            confirm: async () => {
                try {
                    await this.orm.call(
                        "hr.payslip",
                        "action_approve_batch",
                        [draftRecords.map(r => r.id)],
                        { context: this.props.context }
                    );

                    this.notification.add(_t("Nóminas aprobadas exitosamente"), {
                        type: "success"
                    });

                    await this.model.root.load();
                } catch (error) {
                    this.notification.add(_t("Error al aprobar: ") + error.message, {
                        type: "danger"
                    });
                }
            },
            cancel: () => {}
        });
    }

    /**
     * Generar PDF masivo
     */
    async onGeneratePDFBatch() {
        const selectedRecords = await this.getSelectedRecords();

        if (selectedRecords.length === 0) {
            this.notification.add(_t("Por favor seleccione al menos una nómina"), {
                type: "warning"
            });
            return;
        }

        try {
            const result = await this.orm.call(
                "hr.payslip",
                "generate_pdf_batch",
                [selectedRecords.map(r => r.id)],
                { context: this.props.context }
            );

            if (result && result.url) {
                // Descargar archivo ZIP con todos los PDFs
                window.location.href = result.url;

                this.notification.add(
                    _t(`${selectedRecords.length} PDF(s) generados y comprimidos`),
                    { type: "success" }
                );
            }
        } catch (error) {
            this.notification.add(_t("Error al generar PDFs: ") + error.message, {
                type: "danger"
            });
        }
    }

    /**
     * Obtener registros seleccionados
     */
    async getSelectedRecords() {
        return this.model.root.selection || [];
    }
}
