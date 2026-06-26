/** @odoo-module **/

import { Component, useState, onWillStart } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { useService } from "@web/core/utils/hooks";

/**
 * Diálogo modal para construir direcciones colombianas estructuradas
 * Carga los códigos de nomenclatura DIAN desde account.nomenclature.code
 */
export class AddressBuilderDialog extends Component {
    static template = "lavish_erp.AddressBuilderDialog";
    static components = { Dialog };
    static props = {
        record: Object,
        onApply: Function,
        close: Function,
    };

    setup() {
        this.orm = useService("orm");

        // Estado local del diálogo
        this.state = useState({
            // Opciones cargadas desde account.nomenclature.code
            main_road_options: [],      // type_code = 'principal'
            main_letter_options: [],    // type_code = 'letter'
            prefix_options: [],         // type_code = 'qualifying' (solo BIS)
            sector_options: [],         // type_code = 'qualifying' (NORTE, SUR, etc)
            complement_options: [],     // type_code = 'additional'

            // Vía Principal - [id, abbreviation]
            main_road: [0, ''],
            name_road: '',
            main_letter_road: [0, ''],
            prefix_main_road: [0, ''],
            sector_main_road: [0, ''],

            // Vía Generadora
            generator_road_number: 0,
            generator_road_letter: [0, ''],
            generator_road_sector: [0, ''],

            // Placa
            generator_plate_number: 0,
            generator_plate_sector: [0, ''],

            // Complementos - [id, abbreviation]
            complement_name_a: [0, ''],
            complement_number_a: '',
            complement_name_b: [0, ''],
            complement_number_b: '',
            complement_name_c: [0, ''],
            complement_text_c: '',

            // Barrios (desde código postal)
            neighborhoods: [],
            selectedNeighborhood: '',

            // Preview
            previewAddress: 'Complete los campos para generar la dirección...',

            // Loading state
            loading: true,
        });

        // Cargar nomenclatura al iniciar
        onWillStart(async () => {
            await this.loadNomenclature();
            this.loadExistingData();
        });
    }

    /**
     * Carga los códigos de nomenclatura desde el backend
     */
    async loadNomenclature() {
        try {
            const nomenclature = await this.orm.searchRead(
                'account.nomenclature.code',
                [['active', '=', true]],
                ['id', 'name', 'abbreviation', 'type_code'],
                { order: 'sequence, abbreviation' }
            );

            // Clasificar por tipo
            const principal = [];
            const letter = [];
            const qualifying = [];
            const additional = [];

            for (const item of nomenclature) {
                const option = {
                    id: item.id,
                    name: `[${item.abbreviation}] ${item.name}`,
                    abbreviation: item.abbreviation,
                };

                switch (item.type_code) {
                    case 'principal':
                        principal.push(option);
                        break;
                    case 'letter':
                        letter.push(option);
                        break;
                    case 'qualifying':
                        // BIS va a prefijos, el resto a sectores
                        if (item.abbreviation === 'BIS') {
                            qualifying.unshift(option);  // BIS primero
                        } else {
                            qualifying.push(option);
                        }
                        break;
                    case 'additional':
                        additional.push(option);
                        break;
                }
            }

            // Separar prefijos (BIS) de sectores (NORTE, SUR, etc)
            const prefixes = qualifying.filter(q => q.abbreviation === 'BIS');
            const sectors = qualifying.filter(q => q.abbreviation !== 'BIS');

            this.state.main_road_options = principal;
            this.state.main_letter_options = letter;
            this.state.prefix_options = prefixes;
            this.state.sector_options = sectors;
            this.state.complement_options = additional;
            this.state.loading = false;

            console.log("Nomenclatura cargada:", {
                principal: principal.length,
                letter: letter.length,
                prefixes: prefixes.length,
                sectors: sectors.length,
                additional: additional.length,
            });

        } catch (error) {
            console.error("Error cargando nomenclatura:", error);
            this.state.loading = false;
        }
    }

    /**
     * Carga datos existentes del registro si los hay
     */
    loadExistingData() {
        const record = this.props.record;
        if (!record || !record.data) return;

        const data = record.data;

        // Cargar valores existentes si hay
        if (data.name_road) {
            this.state.name_road = data.name_road;
        }
        if (data.main_road && data.main_road[0]) {
            this.state.main_road = [data.main_road[0], this.getAbbreviation(data.main_road[0], 'principal')];
        }
        if (data.main_letter_road && data.main_letter_road[0]) {
            this.state.main_letter_road = [data.main_letter_road[0], this.getAbbreviation(data.main_letter_road[0], 'letter')];
        }
        if (data.prefix_main_road && data.prefix_main_road[0]) {
            this.state.prefix_main_road = [data.prefix_main_road[0], this.getAbbreviation(data.prefix_main_road[0], 'prefix')];
        }
        if (data.sector_main_road && data.sector_main_road[0]) {
            this.state.sector_main_road = [data.sector_main_road[0], this.getAbbreviation(data.sector_main_road[0], 'sector')];
        }
        if (data.generator_road_number) {
            this.state.generator_road_number = data.generator_road_number;
        }
        if (data.generator_road_letter && data.generator_road_letter[0]) {
            this.state.generator_road_letter = [data.generator_road_letter[0], this.getAbbreviation(data.generator_road_letter[0], 'letter')];
        }
        if (data.generator_road_sector && data.generator_road_sector[0]) {
            this.state.generator_road_sector = [data.generator_road_sector[0], this.getAbbreviation(data.generator_road_sector[0], 'sector')];
        }
        if (data.generator_plate_number) {
            this.state.generator_plate_number = data.generator_plate_number;
        }
        if (data.generator_plate_sector && data.generator_plate_sector[0]) {
            this.state.generator_plate_sector = [data.generator_plate_sector[0], this.getAbbreviation(data.generator_plate_sector[0], 'sector')];
        }
        if (data.complement_name_a && data.complement_name_a[0]) {
            this.state.complement_name_a = [data.complement_name_a[0], this.getAbbreviation(data.complement_name_a[0], 'additional')];
        }
        if (data.complement_number_a) {
            this.state.complement_number_a = data.complement_number_a;
        }
        if (data.complement_name_b && data.complement_name_b[0]) {
            this.state.complement_name_b = [data.complement_name_b[0], this.getAbbreviation(data.complement_name_b[0], 'additional')];
        }
        if (data.complement_number_b) {
            this.state.complement_number_b = data.complement_number_b;
        }
        if (data.complement_name_c && data.complement_name_c[0]) {
            this.state.complement_name_c = [data.complement_name_c[0], this.getAbbreviation(data.complement_name_c[0], 'additional')];
        }
        if (data.complement_text_c) {
            this.state.complement_text_c = data.complement_text_c;
        }

        this.updatePreview();
    }

    /**
     * Obtiene la abreviatura de un ID de nomenclatura
     */
    getAbbreviation(id, type) {
        let options = [];
        switch (type) {
            case 'principal':
                options = this.state.main_road_options;
                break;
            case 'letter':
                options = this.state.main_letter_options;
                break;
            case 'prefix':
                options = this.state.prefix_options;
                break;
            case 'sector':
                options = this.state.sector_options;
                break;
            case 'additional':
                options = this.state.complement_options;
                break;
        }
        const found = options.find(o => o.id === id);
        return found ? found.abbreviation : '';
    }

    /**
     * Obtiene la abreviatura de una opción por su ID
     */
    findAbbreviation(id, optionsList) {
        const found = optionsList.find(o => o.id === parseInt(id));
        return found ? found.abbreviation : '';
    }

    /**
     * Actualiza el preview de la dirección
     */
    updatePreview() {
        const parts = [];

        // Vía Principal: TIPO NUMERO LETRA BIS SECTOR
        const mainRoadId = this.state.main_road[0];
        if (mainRoadId) {
            const mainRoadAbbr = this.findAbbreviation(mainRoadId, this.state.main_road_options);
            if (mainRoadAbbr) {
                let mainPart = mainRoadAbbr;

                if (this.state.name_road) {
                    mainPart += ` ${this.state.name_road}`;
                }

                const mainLetterId = this.state.main_letter_road[0];
                if (mainLetterId) {
                    const letterAbbr = this.findAbbreviation(mainLetterId, this.state.main_letter_options);
                    if (letterAbbr) mainPart += ` ${letterAbbr}`;
                }

                const prefixId = this.state.prefix_main_road[0];
                if (prefixId) {
                    const prefixAbbr = this.findAbbreviation(prefixId, this.state.prefix_options);
                    if (prefixAbbr) mainPart += ` ${prefixAbbr}`;
                }

                const sectorId = this.state.sector_main_road[0];
                if (sectorId) {
                    const sectorAbbr = this.findAbbreviation(sectorId, this.state.sector_options);
                    if (sectorAbbr) mainPart += ` ${sectorAbbr}`;
                }

                parts.push(mainPart);
            }
        } else if (this.state.name_road) {
            // Si no hay tipo pero sí número
            parts.push(`CL ${this.state.name_road}`);
        }

        // Vía Generadora: # NUMERO LETRA SECTOR
        if (this.state.generator_road_number) {
            let genPart = `# ${this.state.generator_road_number}`;

            const genLetterId = this.state.generator_road_letter[0];
            if (genLetterId) {
                const letterAbbr = this.findAbbreviation(genLetterId, this.state.main_letter_options);
                if (letterAbbr) genPart += ` ${letterAbbr}`;
            }

            const genSectorId = this.state.generator_road_sector[0];
            if (genSectorId) {
                const sectorAbbr = this.findAbbreviation(genSectorId, this.state.sector_options);
                if (sectorAbbr) genPart += ` ${sectorAbbr}`;
            }

            parts.push(genPart);
        }

        // Placa: - NUMERO SECTOR
        if (this.state.generator_plate_number) {
            let platePart = `- ${this.state.generator_plate_number}`;

            const plateSectorId = this.state.generator_plate_sector[0];
            if (plateSectorId) {
                const sectorAbbr = this.findAbbreviation(plateSectorId, this.state.sector_options);
                if (sectorAbbr) platePart += ` ${sectorAbbr}`;
            }

            parts.push(platePart);
        }

        // Complementos
        const compAId = this.state.complement_name_a[0];
        if (compAId && this.state.complement_number_a) {
            const compAbbr = this.findAbbreviation(compAId, this.state.complement_options);
            if (compAbbr) parts.push(`${compAbbr} ${this.state.complement_number_a}`);
        }

        const compBId = this.state.complement_name_b[0];
        if (compBId && this.state.complement_number_b) {
            const compAbbr = this.findAbbreviation(compBId, this.state.complement_options);
            if (compAbbr) parts.push(`${compAbbr} ${this.state.complement_number_b}`);
        }

        const compCId = this.state.complement_name_c[0];
        if (compCId && this.state.complement_text_c) {
            const compAbbr = this.findAbbreviation(compCId, this.state.complement_options);
            if (compAbbr) parts.push(`${compAbbr} ${this.state.complement_text_c}`);
        }

        this.state.previewAddress = parts.length > 0
            ? parts.join(' ').toUpperCase()
            : 'Complete los campos para generar la dirección...';
    }

    /**
     * Limpia todos los campos
     */
    clearAll() {
        // Vía Principal
        this.state.main_road = [0, ''];
        this.state.name_road = '';
        this.state.main_letter_road = [0, ''];
        this.state.prefix_main_road = [0, ''];
        this.state.sector_main_road = [0, ''];

        // Vía Generadora
        this.state.generator_road_number = 0;
        this.state.generator_road_letter = [0, ''];
        this.state.generator_road_sector = [0, ''];

        // Placa
        this.state.generator_plate_number = 0;
        this.state.generator_plate_sector = [0, ''];

        // Complementos
        this.state.complement_name_a = [0, ''];
        this.state.complement_number_a = '';
        this.state.complement_name_b = [0, ''];
        this.state.complement_number_b = '';
        this.state.complement_name_c = [0, ''];
        this.state.complement_text_c = '';

        this.state.selectedNeighborhood = '';

        this.updatePreview();
    }

    /**
     * Aplica la dirección generada
     */
    apply() {
        // Preparar datos para enviar al backend
        const addressData = {
            street: this.state.previewAddress,
            name_road: this.state.name_road,
            main_road: this.state.main_road[0] || false,
            main_letter_road: this.state.main_letter_road[0] || false,
            prefix_main_road: this.state.prefix_main_road[0] || false,
            sector_main_road: this.state.sector_main_road[0] || false,
            generator_road_number: this.state.generator_road_number || 0,
            generator_road_letter: this.state.generator_road_letter[0] || false,
            generator_road_sector: this.state.generator_road_sector[0] || false,
            generator_plate_number: this.state.generator_plate_number || 0,
            generator_plate_sector: this.state.generator_plate_sector[0] || false,
            complement_name_a: this.state.complement_name_a[0] || false,
            complement_number_a: this.state.complement_number_a || '',
            complement_name_b: this.state.complement_name_b[0] || false,
            complement_number_b: this.state.complement_number_b || '',
            complement_name_c: this.state.complement_name_c[0] || false,
            complement_text_c: this.state.complement_text_c || '',
        };

        console.log("Aplicando dirección:", addressData);

        this.props.onApply(addressData);
        this.props.close();
    }

    /**
     * Cancela y cierra el diálogo
     */
    cancel() {
        this.props.close();
    }
}
