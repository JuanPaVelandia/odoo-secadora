/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component } from "@odoo/owl";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

export class PaymentTotalsWidget extends Component {
    static template = "custom_account_treasury.PaymentTotalsWidget";
    static props = {
        ...standardFieldProps,
    };

    get totals() {
        return this.props.record.data[this.props.name] || {};
    }

    get conceptGroups() {
        return this.totals.concept_groups || [];
    }

    get accountGroups() {
        return this.totals.account_groups || [];
    }

    get formattedTotal() {
        return this.totals.formatted_total || '$ 0,00';
    }

    get formattedDifference() {
        return this.totals.formatted_difference || '$ 0,00';
    }

    get hasDifference() {
        return this.totals.has_difference || false;
    }

    get currencySymbol() {
        return this.totals.currency_symbol || '$';
    }
}

registry.category("fields").add("payment_totals", {
    component: PaymentTotalsWidget,
});
