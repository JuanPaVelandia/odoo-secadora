/** @odoo-module */

import { PosStore } from "@point_of_sale/app/services/pos_store";
import { patch } from "@web/core/utils/patch";

patch(PosStore.prototype, {
    // @Override
    async _processData(loadedData) {
        await super._processData(...arguments);
        if (this.isColombiaCompany()) {
            this.cities = loadedData["res.city"];
            this.l10n_latam_identification_types = loadedData["l10n_latam.identification.type"];
            this.category_id = loadedData['res.partner.category'];
            this.tribute_id = loadedData['dian.tributes'];
            this.fiscal_responsability_ids = loadedData['dian.fiscal.responsability'];
        }
    },
    isColombiaCompany() {
        return this.company.country_id?.code === "CO";
    },
});
