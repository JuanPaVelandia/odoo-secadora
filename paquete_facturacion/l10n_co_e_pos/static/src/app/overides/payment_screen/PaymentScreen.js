/** @odoo-module */

import { PaymentScreen } from "@point_of_sale/app/screens/payment_screen/payment_screen";
import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";

patch(PaymentScreen.prototype, {


    async _postPushOrderResolve(order, order_server_ids) {
        try {
            console.log('=== DEBUG _postPushOrderResolve ===');
            console.log('order_server_ids:', order_server_ids);
            console.log('is_to_invoice:', order.is_to_invoice());

            if (order.is_to_invoice()) {
                // get_invoice() espera un solo ID, tomar el primero del array
                const orderId = Array.isArray(order_server_ids) ? order_server_ids[0] : order_server_ids;
                console.log('orderId extraído:', orderId);

                // Llamar al método backend usando ORM service
                const result = await this.env.services.orm.call(
                    'pos.order',
                    'get_invoice',
                    [orderId]
                );
                console.log('Resultado de get_invoice():', result);

                // Establecer todos los datos DIAN en la orden
                if (result) {
                    console.log('Estableciendo datos DIAN...');
                    order.set_dian_number(result.number || false);
                    order.set_dian_cufe(result.cufe || false);
                    order.set_dian_co_qr_data(result.co_qr_data || false);
                    order.set_dian_ei_is_valid(result.ei_is_valid || false);
                    order.set_dian_state_dian_document(result.state_dian_document || false);
                    order.set_dian_resolution_number(result.resolution_number || false);
                    order.set_dian_resolution_date(result.resolution_date || false);
                    order.set_dian_resolution_date_to(result.resolution_date_to || false);
                    order.set_dian_resolution_number_to(result.resolution_number_to || false);
                    order.set_dian_resolution_number_from(result.resolution_number_from || false);
                    order.set_dian_invoice_date(result.invoice_date || false);
                    order.set_dian_invoice_date_xml(result.invoice_date_xml || false);
                    order.set_dian_invoice_date_due(result.invoice_date_due || false);
                    order.set_dian_invoice_origin(result.invoice_origin || false);
                    order.set_dian_ref(result.ref || false);
                    order.set_dian_formatedNit(result.formatedNit || false);
                    order.set_dian_company_idname(result.company_idname || false);
                    order.set_pos_number(result.pos_number || false);
                    console.log('Datos DIAN establecidos. dian_number:', order.get_dian_number());
                } else {
                    console.warn('get_invoice() retornó resultado vacío o falso');
                }
            } else {
                // Para órdenes sin factura, solo obtener el número POS
                const orderId = Array.isArray(order_server_ids) ? order_server_ids[0] : order_server_ids;
                const result = await this.env.services.orm.call(
                    'pos.order',
                    'get_invoice',
                    [orderId]
                );
                if (result) {
                    order.set_pos_number(result.pos_number || false);
                }
            }
        } catch (error) {
            console.error('Error al obtener datos de factura:', error);
            // No retornar array vacío aquí, continuar con el flujo normal
        }
        // Llamar al método padre para continuar el flujo
        return super._postPushOrderResolve(...arguments);
    },
    // async _isOrderValid(isForceValidate) {
    //     const result = await super._isOrderValid(...arguments);
    //     if (this.pos.isColombiaCompany()) {
    //         if (!result) {
    //             return false;
    //         }
    //         const missingFields = [];
    //         const partner = this.currentOrder.get_partner();
    //         if (this.currentOrder.is_to_invoice() || this.currentOrder._isRefundOrder()) {
    //             // Validar campos char/text
     
    //             if (!partner.vat || !partner.vat.trim()) {
    //                 missingFields.push("vat");
    //             }
    //             if (!partner.l10n_latam_identification_type_id ||
    //                 (Array.isArray(partner.l10n_latam_identification_type_id) && !partner.l10n_latam_identification_type_id[0])) {
    //                 missingFields.push("l10n_latam_identification_type_id");
    //             }
    //             if (!partner.tribute_id || (Array.isArray(partner.tribute_id) && !partner.tribute_id[0])) {
    //                 missingFields.push("tribute_id");
    //             }

    //             // Validar campos Many2many (son arrays de IDs)
    //             if (!partner.fiscal_responsability_ids || !Array.isArray(partner.fiscal_responsability_ids) || partner.fiscal_responsability_ids.length === 0) {
    //                 missingFields.push("fiscal_responsability_ids");
    //             }
    //         }
    //         if (missingFields.length > 0) {
    //             const fieldLabels = {
    //                 email: "Email",

    //                 l10n_latam_identification_type_id: "Tipo de Identificación",
    //                 vat: "NIT/CC",
    //                 fiscal_responsability_ids: "Responsabilidad Fiscal",
    //                 tribute_id: "Tributo"
    //             };
    //             const missingFieldsText = missingFields.map(f => fieldLabels[f] || f).join(", ");
    //             this.notification.add(
    //                 _t("Faltan campos obligatorios del cliente: %s. Por favor, edite el cliente antes de continuar.", missingFieldsText),
    //                 {
    //                     type: "warning",
    //                 }
    //             );
    //             return false;
    //         }
    //         return true;
    //     }
    //     return result;
    // },
    shouldDownloadInvoice() {
        // Para Colombia, nunca descargar automáticamente el PDF de factura
        // Pero SÍ permitir la impresión del ticket POS
        if (this.pos.isColombiaCompany()) {
            return false;
        }
        // Intentar llamar al método padre si existe
        if (super.shouldDownloadInvoice) {
            return super.shouldDownloadInvoice(...arguments);
        }
        return true;
    },

    async _downloadInvoice() {
        // Interceptar descarga de PDF de factura para Colombia
        // El ticket POS se imprime normalmente
        if (this.pos.isColombiaCompany()) {
            console.log('Descarga automática de PDF desactivada para Colombia (ticket POS se imprime normalmente)');
            return; // No descargar PDF
        }
        // Para otros países, comportamiento normal
        if (super._downloadInvoice) {
            return super._downloadInvoice(...arguments);
        }
    },
});
