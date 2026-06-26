/** @odoo-module */

import { patch } from "@web/core/utils/patch";
import { TicketScreen } from "@point_of_sale/app/screens/ticket_screen/ticket_screen";
import { NcTypePopup } from "@l10n_co_e_pos/app/popups/nc_type_popup/nc_type_popup";
import { makeAwaitable } from "@point_of_sale/app/utils/make_awaitable_dialog";

patch(TicketScreen.prototype, {
    //@override
    async addAdditionalRefundInfo(order, destinationOrder) {
        // Abrir popup de tipo de NC para compañías colombianas
        // Verificar si la orden está facturada (tiene account_move)
        // In Odoo PoS (v18), invoicing info is stored in `order.raw`.
        const isInvoiced = Boolean(order?.raw?.account_move) || order.state === "done";

        if (this.pos.company.country_id?.code === "CO" && isInvoiced) {
            const payload = await makeAwaitable(this.dialog, NcTypePopup, {
                order: destinationOrder,
                originalOrder: order,
            });

            // MEJORA: No permitir cancelar el popup (prioridad alta)
            // Si el usuario cancela, lanzar error para detener el flujo
            if (!payload) {
                throw new Error(
                    "Debe seleccionar un tipo de nota crédito para continuar.\n\n" +
                    "El tipo de nota crédito es obligatorio según la normativa DIAN."
                );
            }

            destinationOrder.set_l10n_co_edi_nc_type(payload);
        }
        await super.addAdditionalRefundInfo(...arguments);
    },
});
