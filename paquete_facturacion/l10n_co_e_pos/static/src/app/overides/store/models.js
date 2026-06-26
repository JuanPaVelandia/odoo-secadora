/** @odoo-module */

import { PosOrder } from "@point_of_sale/app/models/pos_order";
import { PosPayment } from "@point_of_sale/app/models/pos_payment";
import { PosOrderline } from "@point_of_sale/app/models/pos_order_line";
import { patch } from "@web/core/utils/patch";
import { formatCurrency } from "@point_of_sale/app/models/utils/currency";

patch(PosOrderline.prototype, {
  getDisplayData() {
    var res = super.getDisplayData(...arguments);
    res.default_code = this.get_product().default_code;
    res.uom_name = this.uom_id ? this.uom_id.name : "";
    res.quantity = this.get_quantity_str();
    res.qty = this.get_quantity();
    const qty = this.get_quantity();
    let price;
    if (qty === 0) {
      price = this.get_display_price() === 0 ? 0 : this.get_display_price();
    } else {
      price = this.get_display_price() / qty;
    }
    res.totalco = formatCurrency(price, this.currency);
    // Agregar precio subtotal sin formatear para evitar regex en templates OWL
    res.price_subtotal_raw = this.get_display_price();
    return res;
  },
});

patch(PosOrder.prototype, {
  setup(_defaultObj, options) {
    super.setup(...arguments);
    // Campos DIAN - inicializar después de super.setup()
    this.dian_number = this.dian_number || false;
    this.dian_cufe = this.dian_cufe || false;
    this.dian_co_qr_data = this.dian_co_qr_data || false;
    this.dian_ei_is_valid = this.dian_ei_is_valid || false;
    this.dian_state_dian_document = this.dian_state_dian_document || false;
    this.dian_resolution_number = this.dian_resolution_number || false;
    this.dian_resolution_date = this.dian_resolution_date || "";
    this.dian_resolution_date_to = this.dian_resolution_date_to || false;
    this.dian_resolution_number_to = this.dian_resolution_number_to || false;
    this.dian_resolution_number_from = this.dian_resolution_number_from || false;
    this.dian_invoice_date = this.dian_invoice_date || false;
    this.dian_invoice_date_xml = this.dian_invoice_date_xml || false;
    this.dian_invoice_date_due = this.dian_invoice_date_due || false;
    this.dian_invoice_origin = this.dian_invoice_origin || false;
    this.dian_ref = this.dian_ref || false;
    this.dian_formatedNit = this.dian_formatedNit || false;
    this.dian_company_idname = this.dian_company_idname || false;
    this.pos_number = this.pos_number || false;
    this.l10n_co_edi_nc_type = this.l10n_co_edi_nc_type || false;
  },

  init_from_JSON(json) {
    super.init_from_JSON(...arguments);
    this.set_dian_number(json.dian_number || false);
    this.set_dian_cufe(json.dian_cufe || false);
    this.set_dian_co_qr_data(json.dian_co_qr_data || false);
    this.set_dian_ei_is_valid(json.dian_ei_is_valid || false);
    this.set_dian_state_dian_document(json.dian_state_dian_document || false);
    this.set_dian_resolution_number(json.dian_resolution_number || false);
    this.set_dian_resolution_date(json.dian_resolution_date || false);
    this.set_dian_resolution_date_to(json.dian_resolution_date_to || false);
    this.set_dian_resolution_number_to(json.dian_resolution_number_to || false);
    this.set_dian_resolution_number_from(
      json.dian_resolution_number_from || false
    );
    this.set_dian_invoice_date(json.dian_invoice_date || false);
    this.set_dian_invoice_date_xml(json.dian_invoice_date_xml || false);
    this.set_dian_invoice_date_due(json.dian_invoice_date_due || false);
    this.set_dian_invoice_origin(json.dian_invoice_origin || false);
    this.set_dian_ref(json.dian_ref || false);
    this.set_dian_formatedNit(json.dian_formatedNit || false);
    this.set_dian_company_idname(json.dian_company_idname || false);
    this.set_pos_number(json.pos_number || false);
    this.set_l10n_co_edi_nc_type(json.l10n_co_edi_nc_type || false);
    this.set_to_invoice(Boolean(json.dian_number) || false);
  },

  export_for_printing() {
    const receipt = super.export_for_printing(...arguments);

    // MEJORA: Re-fetch latest data from DB (patrón Brasil)
    // Útil cuando se reimprime después de facturar o retry EDI
    const order = this.models && this.models["pos.order"]
      ? this.models["pos.order"].get(this.id)
      : this;

    // Datos principales de facturación DIAN
    receipt.dian_number = order.get_dian_number();
    receipt.dian_cufe = order.get_dian_cufe();
    receipt.dian_co_qr_data = order.get_dian_co_qr_data();
    receipt.qr_code = order.get_qr_code(order.get_dian_co_qr_data());

    // Estado y validación DIAN
    receipt.dian_ei_is_valid = order.get_dian_ei_is_valid();
    receipt.dian_state_dian_document = order.get_dian_state_dian_document();

    // Resolución DIAN
    receipt.dian_resolution_number = order.get_dian_resolution_number();
    receipt.dian_resolution_date = order.get_dian_resolution_date();
    receipt.dian_resolution_date_to = order.get_dian_resolution_date_to();
    receipt.dian_resolution_number_to = order.get_dian_resolution_number_to();
    receipt.dian_resolution_number_from = order.get_dian_resolution_number_from();

    // Fechas de facturación
    receipt.dian_invoice_date = order.get_dian_invoice_date();
    receipt.dian_invoice_date_xml = order.get_dian_invoice_date_xml();
    receipt.dian_invoice_date_due = order.get_dian_invoice_date_due();

    // Referencias y datos adicionales
    receipt.dian_invoice_origin = order.get_dian_invoice_origin();
    receipt.dian_ref = order.get_dian_ref();

    // Datos de la compañía
    receipt.dian_formatedNit = order.get_dian_formatedNit();
    receipt.dian_company_idname = order.get_dian_company_idname();

    // Datos de la orden POS
    receipt.pos_number = order.get_pos_number();
    receipt.to_invoice = order.is_to_invoice();
    receipt.config_name = order.config.name;

    // Cliente
    receipt.client = order.get_partner();

    // MEJORA: Agregar tipo de NC para refunds
    receipt.l10n_co_edi_nc_type = order.get_l10n_co_edi_nc_type();
    if (receipt.l10n_co_edi_nc_type) {
      // Obtener descripción del tipo de NC
      const ncTypes = {
        "1": "Devolución parcial de bienes y/o no aceptación parcial del servicio",
        "2": "Anulación de la factura electrónica",
        "3": "Rebaja total aplicada",
        "4": "Descuento parcial o total",
        "5": "Rescisión: nulidad por falta de requisitos",
        "6": "Otros",
      };
      receipt.l10n_co_edi_nc_type_label = ncTypes[receipt.l10n_co_edi_nc_type] || "N/A";
    }

    // Mostrar método DIAN en el recibo
    if (receipt.paymentlines && receipt.paymentlines.length) {
      receipt.paymentlines = receipt.paymentlines.map((line) => {
        const dianMethod = line.payment_method_id?.method_payment_id?.name;
        const methodName = dianMethod || line.payment_method || line.payment_method_name;
        return {
          ...line,
          payment_method_display: methodName || line.payment_method_display,
        };
      });
    }

    return receipt;
  },

  export_as_JSON() {
    const data = super.export_as_JSON(...arguments);
    data.dian_number = this.get_dian_number();
    data.dian_cufe = this.get_dian_cufe();
    data.dian_co_qr_data = this.get_dian_co_qr_data();
    data.dian_ei_is_valid = this.get_dian_ei_is_valid();
    data.dian_state_dian_document = this.get_dian_state_dian_document();
    data.dian_resolution_number = this.get_dian_resolution_number();
    data.dian_resolution_date = this.get_dian_resolution_date();
    data.dian_resolution_date_to = this.get_dian_resolution_date_to();
    data.dian_resolution_number_to = this.get_dian_resolution_number_to();
    data.dian_resolution_number_from = this.get_dian_resolution_number_from();
    data.dian_invoice_date = this.get_dian_invoice_date();
    data.dian_invoice_date_xml = this.get_dian_invoice_date_xml();
    data.dian_invoice_date_due = this.get_dian_invoice_date_due();
    data.dian_invoice_origin = this.get_dian_invoice_origin();
    data.dian_ref = this.get_dian_ref();
    data.dian_formatedNit = this.get_dian_formatedNit();
    data.dian_company_idname = this.get_dian_company_idname();
    data.pos_number = this.get_pos_number();
    data.l10n_co_edi_nc_type = this.get_l10n_co_edi_nc_type();
    return data;
  },

  get_qr_code(qr_data) {
    if (qr_data) {
      const codeWriter = new window.ZXing.BrowserQRCodeSvgWriter();
      const qr_code_svg = new XMLSerializer().serializeToString(
        codeWriter.write(qr_data, 150, 150)
      );
      return "data:image/svg+xml;base64," + window.btoa(qr_code_svg);
    } else {
      return false;
    }
  },
  set_pos_number(pos_number) {
    this.pos_number = pos_number;
  },
  get_pos_number() {
    return this.pos_number;
  },

  get_dian_number() {
    return this.dian_number;
  },
  set_dian_number(dian_number) {
    this.dian_number = dian_number;
  },
  get_dian_cufe() {
    return this.dian_cufe;
  },
  set_dian_cufe(dian_cufe) {
    this.dian_cufe = dian_cufe;
  },
  get_dian_co_qr_data() {
    return this.dian_co_qr_data;
  },
  set_dian_co_qr_data(dian_co_qr_data) {
    this.dian_co_qr_data = dian_co_qr_data;
  },
  get_dian_ei_is_valid() {
    return this.dian_ei_is_valid;
  },
  set_dian_ei_is_valid(dian_ei_is_valid) {
    this.dian_ei_is_valid = dian_ei_is_valid;
  },
  get_dian_state_dian_document() {
    return this.dian_state_dian_document;
  },
  set_dian_state_dian_document(dian_state_dian_document) {
    this.dian_state_dian_document = dian_state_dian_document;
  },
  get_dian_resolution_number() {
    return this.dian_resolution_number;
  },
  set_dian_resolution_number(dian_resolution_number) {
    this.dian_resolution_number = dian_resolution_number;
  },
  get_dian_resolution_date() {
    return this.dian_resolution_date;
  },
  set_dian_resolution_date(dian_resolution_date) {
    this.dian_resolution_date = dian_resolution_date;
  },
  get_dian_resolution_date_to() {
    return this.dian_resolution_date_to;
  },
  set_dian_resolution_date_to(dian_resolution_date_to) {
    this.dian_resolution_date_to = dian_resolution_date_to;
  },
  get_dian_resolution_number_to() {
    return this.dian_resolution_number_to;
  },
  set_dian_resolution_number_to(dian_resolution_number_to) {
    this.dian_resolution_number_to = dian_resolution_number_to;
  },
  get_dian_resolution_number_from() {
    return this.dian_resolution_number_from;
  },
  set_dian_resolution_number_from(dian_resolution_number_from) {
    this.dian_resolution_number_from = dian_resolution_number_from;
  },
  get_dian_invoice_date() {
    return this.dian_invoice_date;
  },
  set_dian_invoice_date(dian_invoice_date) {
    this.dian_invoice_date = dian_invoice_date;
  },
  get_dian_invoice_date_xml() {
    return this.dian_invoice_date_xml;
  },
  set_dian_invoice_date_xml(dian_invoice_date_xml) {
    this.dian_invoice_date_xml = dian_invoice_date_xml;
  },
  get_dian_invoice_date_due() {
    return this.dian_invoice_date_due;
  },
  set_dian_invoice_date_due(dian_invoice_date_due) {
    this.dian_invoice_date_due = dian_invoice_date_due;
  },
  get_dian_invoice_origin() {
    return this.dian_invoice_origin;
  },
  set_dian_invoice_origin(dian_invoice_origin) {
    this.dian_invoice_origin = dian_invoice_origin;
  },
  get_dian_ref() {
    return this.dian_ref;
  },
  set_dian_ref(dian_ref) {
    this.dian_ref = dian_ref;
  },
  get_dian_formatedNit() {
    return this.dian_formatedNit;
  },
  set_dian_formatedNit(dian_formatedNit) {
    this.dian_formatedNit = dian_formatedNit;
  },
  get_dian_company_idname() {
    return this.dian_company_idname;
  },
  set_dian_company_idname(dian_company_idname) {
    this.dian_company_idname = dian_company_idname;
  },
  get_l10n_co_edi_nc_type() {
    return this.l10n_co_edi_nc_type;
  },
  set_l10n_co_edi_nc_type(nc_type) {
    this.l10n_co_edi_nc_type = nc_type;
  },
});

patch(PosPayment.prototype, {
  export_for_printing() {
    const payment = super.export_for_printing(...arguments);
    const posMethodName = this.payment_method_id?.name || "";
    const dianMethodName = this.payment_method_id?.method_payment_id?.length > 1
      ? this.payment_method_id.method_payment_id[1]
      : "";
    payment.payment_method = dianMethodName || posMethodName;
    payment.payment_method_display = dianMethodName
      ? `${posMethodName} (${dianMethodName})`
      : posMethodName;
    return payment;
  },
});
