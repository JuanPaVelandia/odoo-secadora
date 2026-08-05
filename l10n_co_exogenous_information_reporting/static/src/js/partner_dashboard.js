/** @odoo-module **/

import { Component, useState, onWillStart } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/l10n/translation";
import { user } from "@web/core/user";

/**
 * Vista OWL: Dashboard de Terceros para Información Exógena.
 * Analiza completitud de datos de terceros según la configuración de formato.
 */

const DEFAULT_KPIS = { total: 0, complete: 0, incomplete: 0, pct_complete: 0, pct_incomplete: 0 };
const STORAGE_KEY = "l10n_co_exogenous.partner_dashboard.viewState";

export class ExogenousPartnerDashboard extends Component {
    static template = "l10n_co_exogenous.PartnerDashboard";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");

        this.state = useState({
            loading: false,
            partners: [],
            kpis: { ...DEFAULT_KPIS },
            formatSettings: [],
            selectedSettingId: null,
            searchQuery: "",
            filterStatus: "all",
            mailTemplates: [],
            selectedTemplateId: null,
        });

        onWillStart(async () => {
            this._restoreState();
            await Promise.all([this._loadFormatSettings(), this._loadMailTemplates()]);
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

    async _loadMailTemplates() {
        const modelIds = await this.orm.search("ir.model", [["model", "=", "res.partner"]], { limit: 1 });
        if (!modelIds.length) return;
        const templates = await this.orm.searchRead(
            "mail.template",
            [["model_id", "=", modelIds[0]]],
            ["id", "name"],
            { order: "name" },
        );
        this.state.mailTemplates = templates;
    }

    // -- Computed helpers -----------------------------------------------------

    get filteredPartners() {
        let partners = this.state.partners;
        if (this.state.filterStatus !== "all") {
            partners = partners.filter((p) => p.status === this.state.filterStatus);
        }
        if (this.state.searchQuery) {
            const q = this.state.searchQuery.toLowerCase();
            partners = partners.filter(
                (p) =>
                    (p.name || "").toLowerCase().includes(q) ||
                    (p.vat || "").includes(q) ||
                    (p.email || "").toLowerCase().includes(q),
            );
        }
        return partners;
    }

    get selectedCount() {
        return this.state.partners.filter((p) => p.selected).length;
    }

    // -- Event handlers -------------------------------------------------------

    onSettingChange(ev) {
        this.state.selectedSettingId = parseInt(ev.target.value, 10) || null;
        this._persistState();
    }

    onTemplateChange(ev) {
        this.state.selectedTemplateId = parseInt(ev.target.value, 10) || null;
        this._persistState();
    }

    onSearchChange(ev) {
        this.state.searchQuery = ev.target.value;
        this._persistState();
    }

    onFilterChange(ev) {
        this.state.filterStatus = ev.target.value;
        this._persistState();
    }

    onTogglePartner(partnerId) {
        const partner = this.state.partners.find((p) => p.id === partnerId);
        if (partner) {
            partner.selected = !partner.selected;
            this._persistState();
        }
    }

    onSelectAll() {
        this.filteredPartners.forEach((p) => {
            p.selected = true;
        });
        this._persistState();
    }

    onDeselectAll() {
        this.state.partners.forEach((p) => {
            p.selected = false;
        });
        this._persistState();
    }

    onSelectIncomplete() {
        this.state.partners.forEach((p) => {
            p.selected = p.status === "incomplete";
        });
        this._persistState();
    }

    // -- Acciones principales -------------------------------------------------

    async onAnalyzePartners() {
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
                "action_analyze_partners_owl",
                [this.state.selectedSettingId],
            );
            this.state.partners = (result && result.partners) || [];
            this.state.kpis = (result && result.kpis) || { ...DEFAULT_KPIS };
            this._persistState();
        } catch (e) {
            this.notification.add(String(e), { title: _t("Error"), type: "danger" });
        } finally {
            this.state.loading = false;
        }
    }

    async onSendMassRequest() {
        const selected = this.state.partners.filter((p) => p.selected);
        if (!selected.length) {
            this.notification.add(_t("Seleccione al menos un tercero"), {
                title: _t("Atención"),
                type: "warning",
            });
            return;
        }
        if (!this.state.selectedTemplateId) {
            this.notification.add(_t("Seleccione una plantilla de correo"), {
                title: _t("Atención"),
                type: "warning",
            });
            return;
        }
        this.state.loading = true;
        try {
            const result = await this.orm.call(
                "l10n_co.exogenous_format_setting",
                "action_send_partner_requests_owl",
                [
                    this.state.selectedSettingId,
                    selected.map((p) => p.id),
                    this.state.selectedTemplateId,
                ],
            );
            const msg =
                `${result.sent || 0} correos programados` +
                (result.errors && result.errors.length ? `. ${result.errors.length} errores` : "");
            this.notification.add(msg, {
                title: _t("Resultado"),
                type: result.errors && result.errors.length ? "warning" : "success",
            });
        } catch (e) {
            this.notification.add(String(e), { title: _t("Error"), type: "danger" });
        } finally {
            this.state.loading = false;
        }
    }

    onOpenPartner(partnerId) {
        if (!partnerId) return;
        this.action.doAction({
            type: "ir.actions.act_window",
            name: _t("Tercero"),
            res_model: "res.partner",
            view_mode: "form",
            views: [[false, "form"]],
            res_id: partnerId,
            target: "current",
        });
    }

    async onExportExcel() {
        const selected = this.state.partners.filter((p) => p.selected);
        const partnerIds = selected.length
            ? selected.map((p) => p.id)
            : this.filteredPartners.map((p) => p.id);
        this.state.loading = true;
        try {
            const result = await this.orm.call(
                "l10n_co.exogenous_format_setting",
                "action_export_partner_data_owl",
                [this.state.selectedSettingId, partnerIds],
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

registry.category("actions").add("l10n_co_exogenous.partner_dashboard", ExogenousPartnerDashboard);
