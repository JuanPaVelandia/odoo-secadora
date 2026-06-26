/** @odoo-module **/

import { OrderReceipt } from "@point_of_sale/app/screens/receipt_screen/receipt/order_receipt";
import { patch } from "@web/core/utils/patch";

// Usar template de recibo colombiano
// En Odoo 18/OWL 2, los props se heredan automáticamente del componente padre
// No es necesario redefinir Orderline.props ya que el template usa los datos disponibles
patch(OrderReceipt, {
    template: "l10n_co_e_pos.OrderReceiptCO",
});
