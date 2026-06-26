/** @odoo-module **/
/**
 * Filtros personalizados para reportes contables colombianos.
 *
 * Sigue el patrón nativo de Odoo 18:
 * 1. Crear clase que extienda AccountReportFilters
 * 2. Definir static template apuntando al template XML
 * 3. Registrar con AccountReport.registerCustomComponent()
 *
 * Referencia: account_reports/static/src/components/aged_partner_balance/filters.js
 */

import { AccountReport } from "@account_reports/components/account_report/account_report";
import { AccountReportFilters } from "@account_reports/components/account_report/filters/filters";
import { useState } from "@odoo/owl";

// =============================================================================
// Clase de Filtros para Balance de Prueba por Tercero
// =============================================================================

export class TrialBalancePartnerFilters extends AccountReportFilters {
    static template = "libros_contables_colombia.TrialBalancePartnerFilters";

    setup() {
        super.setup(...arguments);

        // Estado local para inputs del filtro de rango de cuentas
        this.accountRangeState = useState({
            accountFrom: '',
            accountTo: '',
            accountExcludeInput: '',
        });

        // Sincronizar estado inicial
        this._syncAccountRangeState();
    }

    _syncAccountRangeState() {
        if (this.accountRangeState && this.controller?.options) {
            this.accountRangeState.accountFrom = this.controller.options.account_from || '';
            this.accountRangeState.accountTo = this.controller.options.account_to || '';
        }
    }

    // =========================================================================
    // GETTERS PARA MOSTRAR/OCULTAR FILTROS
    // =========================================================================

    get hasHidePartnersNoMovementFilter() {
        const filterValue = this.controller.filters?.show_hide_partners_no_movement;
        return filterValue && filterValue !== 'never';
    }

    get hasHideAccountsNoMovementFilter() {
        const filterValue = this.controller.filters?.show_hide_accounts_no_movement;
        return filterValue && filterValue !== 'never';
    }

    get hasPucHierarchyFilter() {
        const filterValue = this.controller.filters?.show_puc_hierarchy;
        return filterValue && filterValue !== 'never';
    }

    get hasAccountRangeFilter() {
        return Boolean(this.controller.filters?.show_account_range);
    }

    get hasWithholdingFilters() {
        return Boolean(
            this.controller.filters?.show_withholding_filters ||
            this.controller.options?.show_withholding_filters
        );
    }

    // =========================================================================
    // GETTERS PARA VALORES DE FILTROS - Rango de Cuentas
    // =========================================================================

    get accountFrom() {
        return this.controller.options?.account_from || '';
    }

    get accountTo() {
        return this.controller.options?.account_to || '';
    }

    get accountExclude() {
        return this.controller.options?.account_exclude || [];
    }

    get selectedAccountExcludeNames() {
        return this.controller.options?.selected_account_exclude_names || [];
    }

    get hasActiveAccountFilter() {
        return !!(this.accountFrom || this.accountTo || this.accountExclude.length > 0);
    }

    get accountFilterSummary() {
        const parts = [];
        if (this.accountFrom) parts.push(`Desde: ${this.accountFrom}`);
        if (this.accountTo) parts.push(`Hasta: ${this.accountTo}`);
        if (this.accountExclude.length > 0) parts.push(`Excluir: ${this.accountExclude.length}`);
        return parts.length > 0 ? parts.join(' | ') : 'Sin filtro';
    }

    // =========================================================================
    // GETTERS PARA VALORES DE FILTROS - Retenciones
    // =========================================================================

    get conceptTypes() {
        return this.controller.options?.concept_types || [];
    }

    get selectedConceptType() {
        return this.controller.options?.concept_type_filter || 'all';
    }

    get withholdingConcepts() {
        return this.controller.options?.withholding_concepts || [];
    }

    get operationTypes() {
        return this.controller.options?.operation_types || [];
    }

    get selectedOperationType() {
        return this.controller.options?.operation_type_filter || 'all';
    }

    // =========================================================================
    // GETTERS PARA VALORES DE FILTROS - Ciudades
    // =========================================================================

    get hasCityFilter() {
        // Verificar si el filtro está habilitado en la configuración Y hay ciudades
        const filterEnabled = this.controller.filters?.show_city || false;
        const cities = this.controller.options?.cities || [];
        return filterEnabled && cities.length > 0;
    }

    get cities() {
        return this.controller.options?.cities || [];
    }

    get selectedCityIds() {
        return this.controller.options?.city_ids || [];
    }

    get hasActiveCityFilter() {
        return this.selectedCityIds.length > 0;
    }

    get selectedCitiesCount() {
        return this.selectedCityIds.length;
    }

    // =========================================================================
    // GETTERS PARA VALORES DE FILTROS - Jerarquía PUC
    // =========================================================================

    get pucHierarchyLevels() {
        return this.controller.options?.puc_hierarchy_levels || [];
    }

    get selectedPucHierarchyLevel() {
        return this.controller.options?.puc_hierarchy_level || 'all';
    }

    get selectedPucHierarchyLevelName() {
        const levels = this.pucHierarchyLevels;
        const selected = this.selectedPucHierarchyLevel;
        const level = levels.find(l => l.id === selected);
        return level ? level.name : 'Todos los niveles';
    }

    get pucDisplayModes() {
        return this.controller.options?.puc_display_modes || [];
    }

    get selectedPucDisplayMode() {
        return this.controller.options?.puc_display_mode || 'expandable';
    }

    get pucShowPartners() {
        return this.controller.options?.puc_show_partners ?? true;
    }

    get pucShowMovements() {
        return this.controller.options?.puc_show_movements ?? true;
    }

    // =========================================================================
    // GETTERS PARA FORMATO DE COLORES
    // =========================================================================

    get hasColorFormattingFilter() {
        const filterValue = this.controller.filters?.show_color_formatting;
        return filterValue && filterValue !== 'never';
    }

    get useColorFormatting() {
        return this.controller.options?.use_color_formatting ?? false;
    }

    get colorModes() {
        return this.controller.options?.color_modes || [];
    }

    get selectedColorMode() {
        return this.controller.options?.color_mode || 'accounting';
    }

    get useAccountingSymbols() {
        return this.controller.options?.use_accounting_symbols ?? false;
    }

    // =========================================================================
    // GETTERS PARA MONEDA SECUNDARIA
    // =========================================================================

    get hasSecondaryCurrencyFilter() {
        return Boolean(this.controller.filters?.show_secondary_currency);
    }

    get showSecondaryCurrency() {
        return this.controller.options?.show_secondary_currency ?? false;
    }

    get availableCurrencies() {
        return this.controller.options?.available_currencies || [];
    }

    get selectedSecondaryCurrency() {
        return this.controller.options?.secondary_currency_id || false;
    }

    // =========================================================================
    // GETTERS PARA FILTRO DE IMPUESTOS
    // =========================================================================

    get taxFilterDomain() {
        // Dominio para filtrar impuestos según el tipo de reporte
        return this.controller.options?.tax_filter_domain || [];
    }

    /**
     * Override del método para incluir el dominio de filtrado por tipo de impuesto.
     */
    getTaxMultiRecordSelectorProps() {
        const domain = this.taxFilterDomain;
        return {
            resModel: 'account.tax',
            resIds: this.controller.options.tax_ids || [],
            domain: domain,
            update: (resIds) => {
                this.filterClicked({ optionKey: 'tax_ids', optionValue: resIds, reload: true });
            },
        };
    }

    // =========================================================================
    // MÉTODOS DE ACCIÓN - Terceros sin movimiento
    // =========================================================================

    async toggleHidePartnersNoMovement() {
        await this.filterClicked({
            optionKey: 'hide_partners_no_movement',
            reload: true
        });
    }

    async toggleHideAccountsNoMovement() {
        await this.filterClicked({
            optionKey: 'hide_accounts_no_movement',
            reload: true
        });
    }

    async togglePucHierarchy() {
        await this.filterClicked({
            optionKey: 'puc_hierarchy',
            reload: true
        });
    }

    async onPucHierarchyLevelChange(levelId) {
        const levels = this.controller.options.puc_hierarchy_levels || [];
        for (const level of levels) {
            level.selected = (level.id === levelId);
        }

        await this.filterClicked({
            optionKey: 'puc_hierarchy_level',
            optionValue: levelId,
            reload: true
        });
    }

    async onPucDisplayModeChange(modeId) {
        const modes = this.controller.options.puc_display_modes || [];
        for (const mode of modes) {
            mode.selected = (mode.id === modeId);
        }

        await this.filterClicked({
            optionKey: 'puc_display_mode',
            optionValue: modeId,
            reload: true
        });
    }

    async togglePucShowPartners() {
        await this.filterClicked({
            optionKey: 'puc_show_partners',
            reload: true
        });
    }

    async togglePucShowMovements() {
        await this.filterClicked({
            optionKey: 'puc_show_movements',
            reload: true
        });
    }

    // =========================================================================
    // MÉTODOS DE ACCIÓN - Formato de Colores
    // =========================================================================

    async toggleColorFormatting() {
        await this.filterClicked({
            optionKey: 'use_color_formatting',
            reload: true
        });
    }

    async onColorModeChange(modeId) {
        const modes = this.controller.options.color_modes || [];
        for (const mode of modes) {
            mode.selected = (mode.id === modeId);
        }

        await this.filterClicked({
            optionKey: 'color_mode',
            optionValue: modeId,
            reload: true
        });
    }

    async toggleAccountingSymbols() {
        await this.filterClicked({
            optionKey: 'use_accounting_symbols',
            reload: true
        });
    }

    // =========================================================================
    // MÉTODOS DE ACCIÓN - Moneda Secundaria
    // =========================================================================

    async toggleSecondaryCurrency() {
        await this.filterClicked({
            optionKey: 'show_secondary_currency',
            reload: true
        });
    }

    async onSecondaryCurrencyChange(currencyId) {
        await this.filterClicked({
            optionKey: 'secondary_currency_id',
            optionValue: parseInt(currencyId),
            reload: true
        });
    }

    // =========================================================================
    // MÉTODOS DE ACCIÓN - Rango de Cuentas
    // =========================================================================

    onAccountFromInput(ev) {
        this.accountRangeState.accountFrom = ev.target.value;
    }

    onAccountToInput(ev) {
        this.accountRangeState.accountTo = ev.target.value;
    }

    onAccountExcludeInput(ev) {
        this.accountRangeState.accountExcludeInput = ev.target.value;
    }

    async applyAccountFrom() {
        const value = this.accountRangeState.accountFrom.trim();
        await this.filterClicked({
            optionKey: 'account_from',
            optionValue: value,
            reload: true
        });
    }

    async applyAccountTo() {
        const value = this.accountRangeState.accountTo.trim();
        await this.filterClicked({
            optionKey: 'account_to',
            optionValue: value,
            reload: true
        });
    }

    async addAccountExclude() {
        const value = this.accountRangeState.accountExcludeInput.trim();
        if (!value) return;

        const currentExclude = [...(this.controller.options.account_exclude || [])];
        if (!currentExclude.includes(value)) {
            currentExclude.push(value);
            this.accountRangeState.accountExcludeInput = '';
            await this.filterClicked({
                optionKey: 'account_exclude',
                optionValue: currentExclude,
                reload: true
            });
        }
    }

    async removeAccountExclude(code) {
        const currentExclude = [...(this.controller.options.account_exclude || [])];
        const index = currentExclude.indexOf(code);
        if (index > -1) {
            currentExclude.splice(index, 1);
            await this.filterClicked({
                optionKey: 'account_exclude',
                optionValue: currentExclude,
                reload: true
            });
        }
    }

    async clearAccountRangeFilter() {
        this.accountRangeState.accountFrom = '';
        this.accountRangeState.accountTo = '';
        this.accountRangeState.accountExcludeInput = '';

        // Limpiar todos los filtros de cuenta
        this.controller.options.account_from = '';
        this.controller.options.account_to = '';
        this.controller.options.account_exclude = [];

        await this.applyFilters('account_range');
    }

    async onAccountInputKeydown(ev, field) {
        if (ev.key === 'Enter') {
            ev.preventDefault();
            if (field === 'from') {
                await this.applyAccountFrom();
            } else if (field === 'to') {
                await this.applyAccountTo();
            } else if (field === 'exclude') {
                await this.addAccountExclude();
            }
        }
    }

    // =========================================================================
    // MÉTODOS DE ACCIÓN - Filtros de Retención
    // =========================================================================

    async onConceptTypeChange(conceptType) {
        const conceptTypes = this.controller.options.concept_types || [];
        for (const ct of conceptTypes) {
            ct.selected = (ct.id === conceptType);
        }

        await this.filterClicked({
            optionKey: 'concept_type_filter',
            optionValue: conceptType,
            reload: true
        });
    }

    async toggleWithholdingConcept(conceptId) {
        const concepts = this.controller.options.withholding_concepts || [];
        const concept = concepts.find(c => c.id === conceptId);

        if (concept) {
            concept.selected = !concept.selected;
        }

        const selectedIds = concepts.filter(c => c.selected).map(c => c.id);

        await this.filterClicked({
            optionKey: 'withholding_concept_ids',
            optionValue: selectedIds,
            reload: true
        });
    }

    async clearWithholdingFilters() {
        // Resetear tipo de concepto
        for (const ct of this.controller.options.concept_types || []) {
            ct.selected = (ct.id === 'all');
        }

        // Limpiar conceptos seleccionados
        for (const wc of this.controller.options.withholding_concepts || []) {
            wc.selected = false;
        }

        // Resetear tipo de operación
        for (const ot of this.controller.options.operation_types || []) {
            ot.selected = (ot.id === 'all');
        }

        this.controller.options.concept_type_filter = 'all';
        this.controller.options.withholding_concept_ids = [];
        this.controller.options.operation_type_filter = 'all';

        await this.applyFilters('withholding_filters');
    }

    async onOperationTypeChange(operationType) {
        const operationTypes = this.controller.options.operation_types || [];
        for (const ot of operationTypes) {
            ot.selected = (ot.id === operationType);
        }

        await this.filterClicked({
            optionKey: 'operation_type_filter',
            optionValue: operationType,
            reload: true
        });
    }

    // =========================================================================
    // MÉTODOS DE ACCIÓN - Filtro de Ciudades
    // =========================================================================

    async toggleCity(cityId) {
        const cities = this.controller.options.cities || [];
        const city = cities.find(c => c.id === cityId);

        if (city) {
            city.selected = !city.selected;
        }

        const selectedIds = cities.filter(c => c.selected).map(c => c.id);

        await this.filterClicked({
            optionKey: 'city_ids',
            optionValue: selectedIds,
            reload: true
        });
    }

    async clearCityFilter() {
        // Deseleccionar todas las ciudades
        for (const city of this.controller.options.cities || []) {
            city.selected = false;
        }

        this.controller.options.city_ids = [];

        await this.applyFilters('city_filter');
    }
}

// Registrar el componente personalizado
AccountReport.registerCustomComponent(TrialBalancePartnerFilters);
