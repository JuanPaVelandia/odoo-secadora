/** @odoo-module **/

import { Component, useState, onWillStart } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/l10n/translation";
import { user } from "@web/core/user";

/**
 * Vista OWL: Resumen de Terceros (información exógena).
 * Tabla expandible con totales y líneas de detalle por tercero.
 */

const DEFAULT_TOTALS = { debit: 0, credit: 0, formula: 0, partners: 0, lines: 0 };
const STORAGE_KEY = "l10n_co_exogenous.partner_summary.viewState";

export class ExogenousPartnerSummary extends Component {
    static template = "l10n_co_exogenous.PartnerSummary";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");

        this.state = useState({
            loading: false,
            formatSettings: [],
            selectedSettingId: null,
            summaryData: [],
            expandedPartners: {},
            totals: { ...DEFAULT_TOTALS },
            searchQuery: "",
        });

        onWillStart(async () => {
            this._restoreState();
            await this._loadFormatSettings();
        });
    }

    // -- Persistencia local ---------------------------------------------------

    _persistState() {
        try {
            const snap = { ...this.state, loading: false };
            localStorage.setItem(STORAGE_KEY, JSON.stringify(snap));
        } catch (e) {
            /* quota / private mode — ignorar */
        }
    }

    _restoreState() {
        try {
            const raw = localStorage.getItem(STORAGE_KEY);
            if (!raw) return;
            const saved = JSON.parse(raw);
            Object.assign(this.state, saved, { loading: false });
        } catch (e) {
            /* snapshot corrupto — ignorar */
        }
    }

    // -- Data loaders ---------------------------------------------------------

    async _loadFormatSettings() {
        const companyId = user.activeCompany?.id || user.context?.allowed_company_ids?.[0];
        const domain = [
            ["active", "=", true],
            ["format_setting_line_ids", "!=", false],
        ];
        if (companyId) {
            domain.push(["company_id", "=", companyId]);
        }
        const result = await this.orm.searchRead(
            "l10n_co.exogenous_format_setting",
            domain,
            ["id", "format_id", "company_id", "report_type"],
            { order: "format_id" },
        );
        this.state.formatSettings = result;
    }

    // -- Computed helpers -----------------------------------------------------

    get filteredData() {
        if (!this.state.searchQuery) return this.state.summaryData;
        const q = this.state.searchQuery.toLowerCase();
        return this.state.summaryData.filter(
            (p) => (p.name || "").toLowerCase().includes(q) || (p.vat || "").includes(q),
        );
    }

    isExpanded(partnerId) {
        return !!this.state.expandedPartners[partnerId];
    }

    formatNumber(val) {
        return (val || 0).toLocaleString("es-CO", {
            minimumFractionDigits: 0,
            maximumFractionDigits: 0,
        });
    }

    // -- Event handlers -------------------------------------------------------

    onSettingChange(ev) {
        this.state.selectedSettingId = parseInt(ev.target.value, 10) || null;
        this._persistState();
    }

    onSearchChange(ev) {
        this.state.searchQuery = ev.target.value;
        this._persistState();
    }

    onToggleExpand(partnerId) {
        if (!partnerId) return;
        if (this.state.expandedPartners[partnerId]) {
            delete this.state.expandedPartners[partnerId];
        } else {
            this.state.expandedPartners[partnerId] = true;
        }
        this._persistState();
    }

    // -- Acciones principales -------------------------------------------------

    async onGenerate() {
        if (!this.state.selectedSettingId) {
            this.notification.add(_t("Seleccione una configuración de formato"), {
                title: _t("Atención"),
                type: "warning",
            });
            return;
        }
        this.state.loading = true;
        try {
            const result = await this.orm.call(
                "l10n_co.exogenous_format_setting",
                "action_partner_summary_owl",
                [this.state.selectedSettingId],
            );
            this.state.summaryData = (result && result.data) || [];
            this.state.totals = (result && result.totals) || { ...DEFAULT_TOTALS };
            this.state.expandedPartners = {};
            this._persistState();
        } catch (e) {
            this.notification.add(String(e), { title: _t("Error"), type: "danger" });
        } finally {
            this.state.loading = false;
        }
    }

    async onExportExcel() {
        if (!this.state.selectedSettingId) return;
        this.state.loading = true;
        try {
            const result = await this.orm.call(
                "l10n_co.exogenous_format_setting",
                "action_export_partner_summary_excel_owl",
                [this.state.selectedSettingId],
            );
            if (result && result.url) {
                window.location.href = result.url;
            }
        } catch (e) {
            this.notification.add(String(e), { title: _t("Error"), type: "danger" });
        } finally {
            this.state.loading = false;
        }
    }
}

registry.category("actions").add("l10n_co_exogenous.partner_summary", ExogenousPartnerSummary);
