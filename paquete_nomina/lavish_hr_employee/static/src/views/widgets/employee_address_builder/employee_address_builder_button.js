/** @odoo-module **/

import { Component } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardWidgetProps } from "@web/views/widgets/standard_widget_props";
import { EmployeeAddressBuilderDialog } from "./employee_address_builder_dialog";

/**
 * Widget que muestra un boton al lado del campo private_street en el formulario de empleado
 * Solo visible para empleados de Colombia (private_country_id = 49)
 * Abre un dialogo modal para construir direcciones estructuradas
 */
export class EmployeeAddressBuilderButton extends Component {
    static template = "lavish_hr_employee.EmployeeAddressBuilderButton";
    static props = {
        ...standardWidgetProps,
    };

    setup() {
        this.dialog = useService("dialog");
    }

    get isVisible() {
        if (!this.props.record) {
            return false;
        }
        const countryId = this.props.record.data?.private_country_id;
        return countryId && countryId[0] === 49;
    }

    openBuilder() {
        this.dialog.add(EmployeeAddressBuilderDialog, {
            record: this.props.record,
            onApply: (addressData) => this.applyAddress(addressData),
        });
    }

    async applyAddress(addressData) {
        await this.props.record.update({
            private_state_id: addressData.state_id,
            private_city_id: addressData.city_id,
            private_zip: addressData.zip,
            private_neighborhood_id: addressData.neighborhood_id,
            private_street: addressData.street,
            private_street2: addressData.street2 || '',
            main_road: addressData.main_road,
            name_road: addressData.name_road,
            main_letter_road: addressData.main_letter_road,
            prefix_main_road: addressData.prefix_main_road,
            sector_main_road: addressData.sector_main_road,
            generator_road_number: addressData.generator_road_number,
            generator_road_letter: addressData.generator_road_letter,
            generator_road_sector: addressData.generator_road_sector,
            generator_plate_number: addressData.generator_plate_number,
            generator_plate_sector: addressData.generator_plate_sector,
            complement_name_a: addressData.complement_name_a,
            complement_number_a: addressData.complement_number_a,
            complement_name_b: addressData.complement_name_b,
            complement_number_b: addressData.complement_number_b,
            complement_name_c: addressData.complement_name_c,
            complement_text_c: addressData.complement_text_c,
        });
    }
}

export const employeeAddressBuilderButton = {
    component: EmployeeAddressBuilderButton,
    extractProps: ({ attrs }) => {
        return {};
    },
};

registry.category("view_widgets").add("employee_address_builder_button", employeeAddressBuilderButton);
