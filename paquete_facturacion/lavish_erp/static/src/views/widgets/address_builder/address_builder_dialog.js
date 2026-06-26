/** @odoo-module **/

import { Component, useState, onWillStart } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { useService } from "@web/core/utils/hooks";

/**
 * Dialogo modal compacto para construir direcciones colombianas estructuradas
 * Incluye barrio con autocompletado y carga los codigos de nomenclatura DIAN
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
        this.debounceTimer = null;

        this.cityDebounceTimer = null;

        // Estado local del dialogo
        this.state = useState({
            // Opciones cargadas desde account.nomenclature.code
            main_road_options: [],
            main_letter_options: [],
            prefix_options: [],
            sector_options: [],
            complement_options: [],

            // Departamentos colombianos
            state_options: [],
            state_id: 0,

            // Ciudad
            city_id: 0,
            city_name: '',
            citySuggestions: [],
            showCitySuggestions: false,

            // Barrio
            barrio_name: '',
            barrio_id: 0,
            barrioSuggestions: [],
            showBarrioSuggestions: false,

            // Codigo Postal
            zip_code: '',

            // Via Principal - [id, abbreviation]
            main_road: [0, ''],
            name_road: '',
            main_letter_road: [0, ''],
            prefix_main_road: [0, ''],
            sector_main_road: [0, ''],

            // Via Generadora
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

            // Preview
            previewAddress: 'Complete los campos...',

            // Formato de direccion: 'short' = iniciales, 'long' = palabras completas
            addressFormat: 'short',

            // Loading state
            loading: true,
        });

        // Cargar nomenclatura al iniciar
        onWillStart(async () => {
            await this.loadStates();
            await this.loadNomenclature();
            this.loadExistingData();
        });
    }

    // ==================== CARGA DE DEPARTAMENTOS ====================

    async loadStates() {
        try {
            // Cargar departamentos colombianos (country_id = 49)
            const states = await this.orm.searchRead(
                'res.country.state',
                [['country_id', '=', 49]],
                ['id', 'name', 'code'],
                { order: 'name' }
            );
            this.state.state_options = states;
        } catch (error) {
            console.error("Error cargando departamentos:", error);
            this.state.state_options = [];
        }
    }

    // ==================== HANDLERS DE FORMATO ====================

    onFormatChange(ev) {
        this.state.addressFormat = ev.target.value;
        this.updatePreview();
    }

    // ==================== HANDLERS DE DEPARTAMENTO ====================

    onStateChange(ev) {
        const stateId = parseInt(ev.target.value) || 0;
        this.state.state_id = stateId;
        // Limpiar ciudad y barrio al cambiar departamento
        this.state.city_id = 0;
        this.state.city_name = '';
        this.state.citySuggestions = [];
        this.state.barrio_id = 0;
        this.state.barrio_name = '';
        this.state.barrioSuggestions = [];
        this.state.zip_code = '';
    }

    // ==================== HANDLERS DE CIUDAD ====================

    onCityFocus() {
        this.state.showCitySuggestions = true;
    }

    onCityBlur() {
        setTimeout(() => {
            this.state.showCitySuggestions = false;
        }, 200);
    }

    async onCityInput(ev) {
        const value = ev.target.value;
        this.state.city_name = value;
        this.state.city_id = 0;

        if (this.cityDebounceTimer) {
            clearTimeout(this.cityDebounceTimer);
        }

        if (value.length >= 2) {
            this.cityDebounceTimer = setTimeout(async () => {
                await this.searchCitySuggestions(value);
            }, 300);
        } else {
            this.state.citySuggestions = [];
        }
    }

    async searchCitySuggestions(name) {
        try {
            // Construir dominio de busqueda
            const domain = [
                ['country_id', '=', 49],
                ['name', 'ilike', name]
            ];

            // Si hay departamento seleccionado, filtrar por el
            if (this.state.state_id) {
                domain.push(['state_id', '=', this.state.state_id]);
            }

            const cities = await this.orm.searchRead(
                'res.city',
                domain,
                ['id', 'name', 'state_id'],
                { limit: 30, order: 'name' }
            );

            this.state.citySuggestions = cities.map(c => ({
                id: c.id,
                name: c.name,
                state_id: c.state_id ? c.state_id[0] : 0,
                display_name: `${c.name}${c.state_id ? ', ' + c.state_id[1] : ''}`
            }));
            this.state.showCitySuggestions = true;
        } catch (error) {
            console.error("Error buscando ciudades:", error);
            this.state.citySuggestions = [];
        }
    }

    selectCityHandler(ev, city) {
        ev.preventDefault();
        ev.stopPropagation();
        this.state.city_id = city.id;
        this.state.city_name = city.display_name || city.name;
        this.state.citySuggestions = [];
        this.state.showCitySuggestions = false;

        // Si no hay departamento seleccionado, establecerlo desde la ciudad
        if (!this.state.state_id && city.state_id) {
            this.state.state_id = city.state_id;
        }

        // Limpiar barrio si cambia la ciudad
        this.state.barrio_id = 0;
        this.state.barrio_name = '';
        this.state.barrioSuggestions = [];
        this.state.zip_code = '';
    }

    // ==================== HANDLERS DE BARRIO ====================

    onBarrioFocus() {
        this.state.showBarrioSuggestions = true;
    }

    onBarrioBlur() {
        setTimeout(() => {
            this.state.showBarrioSuggestions = false;
        }, 200);
    }

    async onBarrioInput(ev) {
        const value = ev.target.value;
        this.state.barrio_name = value;
        this.state.barrio_id = 0;

        if (this.debounceTimer) {
            clearTimeout(this.debounceTimer);
        }

        if (value.length >= 2) {
            this.debounceTimer = setTimeout(async () => {
                await this.searchBarrioSuggestions(value);
            }, 300);
        } else {
            this.state.barrioSuggestions = [];
        }
    }

    async searchBarrioSuggestions(name) {
        try {
            // Usar ciudad del estado si fue cambiada, si no usar la del record
            let cityId = this.state.city_id;
            if (!cityId) {
                const record = this.props.record;
                cityId = record?.data?.city_id?.[0] || 0;
            }

            const suggestions = await this.orm.call(
                'res.city.neighborhood',
                'search_suggestions',
                [name, cityId, 10]
            );

            this.state.barrioSuggestions = suggestions;
            this.state.showBarrioSuggestions = true;
        } catch (error) {
            console.error("Error buscando barrios:", error);
            this.state.barrioSuggestions = [];
        }
    }

    selectBarrioHandler(ev, suggestion) {
        ev.preventDefault();
        ev.stopPropagation();
        this.state.barrio_id = suggestion.id;
        this.state.barrio_name = suggestion.name;
        this.state.barrioSuggestions = [];
        this.state.showBarrioSuggestions = false;
        // Establecer codigo postal del barrio si existe
        if (suggestion.postal_code) {
            this.state.zip_code = suggestion.postal_code;
        }
    }

    // ==================== HANDLERS DE VIA PRINCIPAL ====================

    onMainRoadChange(ev) {
        const val = parseInt(ev.target.value) || 0;
        this.state.main_road = [val, ''];
        this.updatePreview();
    }

    onNameRoadInput(ev) {
        this.state.name_road = ev.target.value;
        this.updatePreview();
    }

    onMainLetterChange(ev) {
        const val = parseInt(ev.target.value) || 0;
        this.state.main_letter_road = [val, ''];
        this.updatePreview();
    }

    onPrefixChange(ev) {
        const val = parseInt(ev.target.value) || 0;
        this.state.prefix_main_road = [val, ''];
        this.updatePreview();
    }

    onSectorMainChange(ev) {
        const val = parseInt(ev.target.value) || 0;
        this.state.sector_main_road = [val, ''];
        this.updatePreview();
    }

    // ==================== HANDLERS DE VIA GENERADORA ====================

    onGenRoadNumberInput(ev) {
        this.state.generator_road_number = parseInt(ev.target.value) || 0;
        this.updatePreview();
    }

    onGenRoadLetterChange(ev) {
        const val = parseInt(ev.target.value) || 0;
        this.state.generator_road_letter = [val, ''];
        this.updatePreview();
    }

    onGenRoadSectorChange(ev) {
        const val = parseInt(ev.target.value) || 0;
        this.state.generator_road_sector = [val, ''];
        this.updatePreview();
    }

    // ==================== HANDLERS DE PLACA ====================

    onPlateNumberInput(ev) {
        this.state.generator_plate_number = parseInt(ev.target.value) || 0;
        this.updatePreview();
    }

    onPlateSectorChange(ev) {
        const val = parseInt(ev.target.value) || 0;
        this.state.generator_plate_sector = [val, ''];
        this.updatePreview();
    }

    // ==================== HANDLERS DE COMPLEMENTOS ====================

    onCompANameChange(ev) {
        const val = parseInt(ev.target.value) || 0;
        this.state.complement_name_a = [val, ''];
        this.updatePreview();
    }

    onCompANumInput(ev) {
        this.state.complement_number_a = ev.target.value;
        this.updatePreview();
    }

    onCompBNameChange(ev) {
        const val = parseInt(ev.target.value) || 0;
        this.state.complement_name_b = [val, ''];
        this.updatePreview();
    }

    onCompBNumInput(ev) {
        this.state.complement_number_b = ev.target.value;
        this.updatePreview();
    }

    onCompCNameChange(ev) {
        const val = parseInt(ev.target.value) || 0;
        this.state.complement_name_c = [val, ''];
        this.updatePreview();
    }

    onCompCTextInput(ev) {
        this.state.complement_text_c = ev.target.value;
        this.updatePreview();
    }

    // ==================== CARGA DE DATOS ====================

    async loadNomenclature() {
        try {
            const nomenclature = await this.orm.searchRead(
                'account.nomenclature.code',
                [['active', '=', true]],
                ['id', 'name', 'abbreviation', 'type_code'],
                { order: 'sequence, abbreviation' }
            );

            const principal = [];
            const letter = [];
            const qualifying = [];
            const additional = [];

            for (const item of nomenclature) {
                const option = {
                    id: item.id,
                    name: item.name,
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
                        if (item.abbreviation === 'BIS') {
                            qualifying.unshift(option);
                        } else {
                            qualifying.push(option);
                        }
                        break;
                    case 'additional':
                        additional.push(option);
                        break;
                }
            }

            const prefixes = qualifying.filter(q => q.abbreviation === 'BIS');
            const sectors = qualifying.filter(q => q.abbreviation !== 'BIS');

            this.state.main_road_options = principal;
            this.state.main_letter_options = letter;
            this.state.prefix_options = prefixes;
            this.state.sector_options = sectors;
            this.state.complement_options = additional;
            this.state.loading = false;

        } catch (error) {
            console.error("Error cargando nomenclatura:", error);
            this.state.loading = false;
        }
    }

    loadExistingData() {
        const record = this.props.record;
        if (!record || !record.data) return;

        const data = record.data;

        // Cargar departamento existente
        if (data.state_id && data.state_id[0]) {
            this.state.state_id = data.state_id[0];
        }

        // Cargar ciudad existente
        if (data.city_id && data.city_id[0]) {
            this.state.city_id = data.city_id[0];
            this.state.city_name = data.city_id[1] || '';
        }

        if (data.neighborhood_id && data.neighborhood_id[0]) {
            this.state.barrio_id = data.neighborhood_id[0];
            this.state.barrio_name = data.neighborhood_id[1] || '';
        } else if (data.street2) {
            // Si no hay neighborhood_id, usar street2 como barrio manual
            this.state.barrio_id = 0;
            this.state.barrio_name = data.street2;
        }

        // Cargar codigo postal
        if (data.zip) {
            this.state.zip_code = data.zip;
        }

        if (data.name_road) {
            this.state.name_road = data.name_road;
        }
        if (data.main_road && data.main_road[0]) {
            this.state.main_road = [data.main_road[0], ''];
        }
        if (data.main_letter_road && data.main_letter_road[0]) {
            this.state.main_letter_road = [data.main_letter_road[0], ''];
        }
        if (data.prefix_main_road && data.prefix_main_road[0]) {
            this.state.prefix_main_road = [data.prefix_main_road[0], ''];
        }
        if (data.sector_main_road && data.sector_main_road[0]) {
            this.state.sector_main_road = [data.sector_main_road[0], ''];
        }
        if (data.generator_road_number) {
            this.state.generator_road_number = data.generator_road_number;
        }
        if (data.generator_road_letter && data.generator_road_letter[0]) {
            this.state.generator_road_letter = [data.generator_road_letter[0], ''];
        }
        if (data.generator_road_sector && data.generator_road_sector[0]) {
            this.state.generator_road_sector = [data.generator_road_sector[0], ''];
        }
        if (data.generator_plate_number) {
            this.state.generator_plate_number = data.generator_plate_number;
        }
        if (data.generator_plate_sector && data.generator_plate_sector[0]) {
            this.state.generator_plate_sector = [data.generator_plate_sector[0], ''];
        }
        if (data.complement_name_a && data.complement_name_a[0]) {
            this.state.complement_name_a = [data.complement_name_a[0], ''];
        }
        if (data.complement_number_a) {
            this.state.complement_number_a = data.complement_number_a;
        }
        if (data.complement_name_b && data.complement_name_b[0]) {
            this.state.complement_name_b = [data.complement_name_b[0], ''];
        }
        if (data.complement_number_b) {
            this.state.complement_number_b = data.complement_number_b;
        }
        if (data.complement_name_c && data.complement_name_c[0]) {
            this.state.complement_name_c = [data.complement_name_c[0], ''];
        }
        if (data.complement_text_c) {
            this.state.complement_text_c = data.complement_text_c;
        }

        this.updatePreview();
    }

    // ==================== UTILIDADES ====================

    findAbbreviation(id, optionsList) {
        const found = optionsList.find(o => o.id === parseInt(id));
        return found ? found.abbreviation : '';
    }

    /**
     * Obtiene el texto para mostrar según el formato seleccionado
     * @param {number} id - ID del elemento de nomenclatura
     * @param {Array} optionsList - Lista de opciones
     * @returns {string} - Abreviatura (corto) o nombre completo (largo)
     */
    getDisplayText(id, optionsList) {
        const found = optionsList.find(o => o.id === parseInt(id));
        if (!found) return '';
        // 'short' = iniciales/abreviatura, 'long' = nombre completo
        return this.state.addressFormat === 'short' ? found.abbreviation : found.name;
    }

    updatePreview() {
        const parts = [];

        const mainRoadId = this.state.main_road[0];
        if (mainRoadId) {
            const mainRoadText = this.getDisplayText(mainRoadId, this.state.main_road_options);
            if (mainRoadText) {
                let mainPart = mainRoadText;

                if (this.state.name_road) {
                    mainPart += ` ${this.state.name_road}`;
                }

                const mainLetterId = this.state.main_letter_road[0];
                if (mainLetterId) {
                    const letterText = this.getDisplayText(mainLetterId, this.state.main_letter_options);
                    if (letterText) mainPart += ` ${letterText}`;
                }

                const prefixId = this.state.prefix_main_road[0];
                if (prefixId) {
                    const prefixText = this.getDisplayText(prefixId, this.state.prefix_options);
                    if (prefixText) mainPart += ` ${prefixText}`;
                }

                const sectorId = this.state.sector_main_road[0];
                if (sectorId) {
                    const sectorText = this.getDisplayText(sectorId, this.state.sector_options);
                    if (sectorText) mainPart += ` ${sectorText}`;
                }

                parts.push(mainPart);
            }
        } else if (this.state.name_road) {
            const defaultRoad = this.state.addressFormat === 'short' ? 'CL' : 'CALLE';
            parts.push(`${defaultRoad} ${this.state.name_road}`);
        }

        if (this.state.generator_road_number) {
            let genPart = `# ${this.state.generator_road_number}`;

            const genLetterId = this.state.generator_road_letter[0];
            if (genLetterId) {
                const letterText = this.getDisplayText(genLetterId, this.state.main_letter_options);
                if (letterText) genPart += ` ${letterText}`;
            }

            const genSectorId = this.state.generator_road_sector[0];
            if (genSectorId) {
                const sectorText = this.getDisplayText(genSectorId, this.state.sector_options);
                if (sectorText) genPart += ` ${sectorText}`;
            }

            parts.push(genPart);
        }

        if (this.state.generator_plate_number) {
            let platePart = `- ${this.state.generator_plate_number}`;

            const plateSectorId = this.state.generator_plate_sector[0];
            if (plateSectorId) {
                const sectorText = this.getDisplayText(plateSectorId, this.state.sector_options);
                if (sectorText) platePart += ` ${sectorText}`;
            }

            parts.push(platePart);
        }

        const compAId = this.state.complement_name_a[0];
        if (compAId && this.state.complement_number_a) {
            const compText = this.getDisplayText(compAId, this.state.complement_options);
            if (compText) parts.push(`${compText} ${this.state.complement_number_a}`);
        }

        const compBId = this.state.complement_name_b[0];
        if (compBId && this.state.complement_number_b) {
            const compText = this.getDisplayText(compBId, this.state.complement_options);
            if (compText) parts.push(`${compText} ${this.state.complement_number_b}`);
        }

        const compCId = this.state.complement_name_c[0];
        if (compCId && this.state.complement_text_c) {
            const compText = this.getDisplayText(compCId, this.state.complement_options);
            if (compText) parts.push(`${compText} ${this.state.complement_text_c}`);
        }

        this.state.previewAddress = parts.length > 0
            ? parts.join(' ').toUpperCase()
            : 'Complete los campos...';
    }

    clearAll() {
        // Limpiar departamento
        this.state.state_id = 0;

        // Limpiar ciudad
        this.state.city_id = 0;
        this.state.city_name = '';
        this.state.citySuggestions = [];

        // Limpiar barrio
        this.state.barrio_name = '';
        this.state.barrio_id = 0;
        this.state.barrioSuggestions = [];

        // Limpiar codigo postal
        this.state.zip_code = '';

        this.state.main_road = [0, ''];
        this.state.name_road = '';
        this.state.main_letter_road = [0, ''];
        this.state.prefix_main_road = [0, ''];
        this.state.sector_main_road = [0, ''];

        this.state.generator_road_number = 0;
        this.state.generator_road_letter = [0, ''];
        this.state.generator_road_sector = [0, ''];

        this.state.generator_plate_number = 0;
        this.state.generator_plate_sector = [0, ''];

        this.state.complement_name_a = [0, ''];
        this.state.complement_number_a = '';
        this.state.complement_name_b = [0, ''];
        this.state.complement_number_b = '';
        this.state.complement_name_c = [0, ''];
        this.state.complement_text_c = '';

        this.updatePreview();
    }

    formatMany2one(value, options) {
        if (!value || !value[0]) return false;
        const id = value[0];
        const found = options.find(o => o.id === id);
        return found ? [id, found.name] : false;
    }

    async apply() {
        const record = this.props.record;

        // Usar departamento del estado o del record original
        let stateId = this.state.state_id;
        let stateName = '';
        if (stateId) {
            const stateOpt = this.state.state_options.find(s => s.id === stateId);
            stateName = stateOpt ? stateOpt.name : '';
        } else if (record?.data?.state_id?.[0]) {
            stateId = record.data.state_id[0];
            stateName = record.data.state_id[1] || '';
        }

        // Usar ciudad del estado o del record original
        let cityId = this.state.city_id;
        let cityName = this.state.city_name;
        if (!cityId) {
            cityId = record?.data?.city_id?.[0] || 0;
            cityName = record?.data?.city_id?.[1] || '';
        }

        // Usar codigo postal del estado o del record original
        let zipCode = this.state.zip_code;
        if (!zipCode) {
            zipCode = record?.data?.zip || '';
        }

        // Si hay barrio seleccionado de la lista, usar neighborhood_id
        // Si hay barrio escrito pero no seleccionado, usar street2
        let neighborhoodId = this.state.barrio_id;
        let street2Value = '';

        if (this.state.barrio_name) {
            if (neighborhoodId) {
                // Barrio existe en la base de datos
                street2Value = '';
            } else {
                // Barrio escrito manualmente, guardar en street2
                street2Value = this.state.barrio_name.toUpperCase();
                neighborhoodId = 0;
            }
        }

        const addressData = {
            street: this.state.previewAddress,
            street2: street2Value,
            state_id: stateId ? [stateId, stateName] : false,
            city_id: cityId ? [cityId, cityName] : false,
            zip: zipCode || '',
            neighborhood_id: neighborhoodId ? [neighborhoodId, this.state.barrio_name] : false,
            name_road: this.state.name_road || '',
            main_road: this.formatMany2one(this.state.main_road, this.state.main_road_options),
            main_letter_road: this.formatMany2one(this.state.main_letter_road, this.state.main_letter_options),
            prefix_main_road: this.formatMany2one(this.state.prefix_main_road, this.state.prefix_options),
            sector_main_road: this.formatMany2one(this.state.sector_main_road, this.state.sector_options),
            generator_road_number: this.state.generator_road_number || 0,
            generator_road_letter: this.formatMany2one(this.state.generator_road_letter, this.state.main_letter_options),
            generator_road_sector: this.formatMany2one(this.state.generator_road_sector, this.state.sector_options),
            generator_plate_number: this.state.generator_plate_number || 0,
            generator_plate_sector: this.formatMany2one(this.state.generator_plate_sector, this.state.sector_options),
            complement_name_a: this.formatMany2one(this.state.complement_name_a, this.state.complement_options),
            complement_number_a: this.state.complement_number_a || '',
            complement_name_b: this.formatMany2one(this.state.complement_name_b, this.state.complement_options),
            complement_number_b: this.state.complement_number_b || '',
            complement_name_c: this.formatMany2one(this.state.complement_name_c, this.state.complement_options),
            complement_text_c: this.state.complement_text_c || '',
        };

        console.log("Aplicando direccion:", addressData);

        this.props.onApply(addressData);
        this.props.close();
    }

    cancel() {
        this.props.close();
    }
}
