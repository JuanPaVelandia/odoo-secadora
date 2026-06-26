/** @odoo-module **/

import { Component } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardWidgetProps } from "@web/views/widgets/standard_widget_props";
import { AddressBuilderDialog } from "./address_builder_dialog";

/**
 * Widget auxiliar que muestra un botón al lado del campo street
 * Solo visible para contactos de Colombia (country_id = 49)
 * Abre un diálogo modal para construir direcciones estructuradas
 */
export class AddressBuilderButton extends Component {
    static template = "lavish_erp.AddressBuilderButton";
    static props = {
        ...standardWidgetProps,
    };

    setup() {
        this.dialog = useService("dialog");
        console.log("AddressBuilderButton setup - widget loaded successfully!");
    }

    /**
     * Determina si el botón debe mostrarse
     * Solo para Colombia (country_id = 49) y cuando no está en modo readonly
     */
    get isVisible() {
        // Verificar que tenemos record y no estamos en readonly
        if (this.props.readonly || !this.props.record) {
            return false;
        }

        // Acceso defensivo a country_id usando optional chaining
        const countryId = this.props.record.data?.country_id;
        return countryId && countryId[0] === 49; // Colombia
    }

    /**
     * Abre el diálogo constructor de direcciones
     */
    openBuilder() {
        console.log("Abriendo constructor de dirección para:", this.props.record.data.name);

        this.dialog.add(AddressBuilderDialog, {
            record: this.props.record,
            onApply: (addressData) => this.applyAddress(addressData),
        });
    }

    /**
     * Aplica los datos de dirección al registro
     * Actualiza tanto el campo street como los 14+ campos estructurados invisibles
     */
    async applyAddress(addressData) {
        await this.props.record.update({
            street: addressData.street,
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

// Registrar como widget de vista
export const addressBuilderButton = {
    component: AddressBuilderButton,
    extractProps: ({ attrs }) => {
        // No extraemos nada del XML - record y readonly se pasan automáticamente
        return {};
    },
};

const viewWidgetsRegistry = registry.category("view_widgets");
if (!viewWidgetsRegistry.contains("address_builder_button")) {
    viewWidgetsRegistry.add("address_builder_button", addressBuilderButton);
}
