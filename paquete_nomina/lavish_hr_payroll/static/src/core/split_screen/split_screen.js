/** @odoo-module **/

import { Component, useState, useRef, onMounted, onWillUnmount } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

export class SplitScreen extends Component {
    static template = "lavish_hr_payroll.SplitScreen";
    static props = {};

    setup() {
        this.splitScreenService = useService("splitScreen");
        this.notification = useService("notification");

        this.state = useState({
            isEnabled: false,
            mode: 'single',
            panels: [],
            activePanel: 1,
            showToolbar: true,
            panel2Url: '',
        });

        this._pollInterval = null;

        onMounted(() => {
            // Sync with service state
            this._pollInterval = setInterval(() => {
                const svcState = this.splitScreenService.state;
                if (this.state.isEnabled !== svcState.isEnabled ||
                    this.state.mode !== svcState.mode) {
                    this.state.isEnabled = svcState.isEnabled;
                    this.state.mode = svcState.mode;
                    this.state.panels = [...svcState.panels];
                    this.state.activePanel = svcState.activePanel;
                }
            }, 100);
        });

        onWillUnmount(() => {
            if (this._pollInterval) {
                clearInterval(this._pollInterval);
            }
        });
    }

    get isVisible() {
        return this.state.isEnabled && this.state.mode !== 'single';
    }

    toggleSplit(mode) {
        if (!this.state.isEnabled) {
            // When enabling, set panel2 URL to current page
            this.state.panel2Url = window.location.href;
        }
        this.splitScreenService.toggle(mode);
    }

    closeSplit() {
        this.splitScreenService.disable();
    }

    setActivePanel(panelId) {
        this.splitScreenService.setActivePanel(panelId);
        this.state.activePanel = panelId;
    }

    closePanel(panelId) {
        this.splitScreenService.closePanel(panelId);
    }

    maximizePanel(panelId) {
        this.splitScreenService.maximizePanel(panelId);
    }

    swapPanels() {
        this.splitScreenService.swapPanels(1, 2);
    }

    openNewWindow() {
        this.splitScreenService.cloneToNewWindow();
    }
}
