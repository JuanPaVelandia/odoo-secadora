/** @odoo-module **/

import { registry } from "@web/core/registry";
import { reactive } from "@odoo/owl";

/**
 * Split Screen Service
 * Manages split-screen views and multi-window functionality
 */
export const splitScreenService = {
    dependencies: ["action"],

    start(env, { action }) {
        const state = reactive({
            isEnabled: false,
            mode: 'single', // 'single', 'vertical', 'horizontal', 'quad'
            panels: [
                { id: 1, active: true, action: null, title: '' },
                { id: 2, active: false, action: null, title: '' },
                { id: 3, active: false, action: null, title: '' },
                { id: 4, active: false, action: null, title: '' },
            ],
            activePanel: 1,
            history: [],
        });

        // Enable split screen mode
        const enable = (mode = 'vertical') => {
            state.isEnabled = true;
            state.mode = mode;
            document.body.classList.add('lavish-split-screen', `split-${mode}`);
        };

        // Disable split screen mode
        const disable = () => {
            state.isEnabled = false;
            state.mode = 'single';
            state.panels.forEach((p, i) => {
                if (i > 0) {
                    p.active = false;
                    p.action = null;
                }
            });
            document.body.classList.remove('lavish-split-screen', 'split-vertical', 'split-horizontal', 'split-quad');
        };

        // Toggle split screen
        const toggle = (mode = 'vertical') => {
            if (state.isEnabled && state.mode === mode) {
                disable();
            } else {
                enable(mode);
            }
        };

        // Set active panel
        const setActivePanel = (panelId) => {
            state.activePanel = panelId;
            state.panels.forEach(p => p.active = p.id === panelId);
        };

        // Open action in specific panel
        const openInPanel = async (panelId, actionParams) => {
            const panel = state.panels.find(p => p.id === panelId);
            if (panel) {
                panel.action = actionParams;
                panel.title = actionParams.name || actionParams.res_model || 'Vista';
                panel.active = true;
                setActivePanel(panelId);
            }
        };

        // Open in new browser window
        const openInNewWindow = (url, options = {}) => {
            const {
                width = 1200,
                height = 800,
                name = 'odoo_window_' + Date.now(),
            } = options;

            const left = (screen.width - width) / 2;
            const top = (screen.height - height) / 2;

            const features = `width=${width},height=${height},left=${left},top=${top},resizable=yes,scrollbars=yes,status=yes`;

            return window.open(url, name, features);
        };

        // Open record in new window
        const openRecordInNewWindow = (model, resId, viewType = 'form') => {
            const url = `/web#model=${model}&id=${resId}&view_type=${viewType}`;
            return openInNewWindow(url, { name: `${model}_${resId}` });
        };

        // Open action in new window
        const openActionInNewWindow = (actionId) => {
            const url = `/web#action=${actionId}`;
            return openInNewWindow(url, { name: `action_${actionId}` });
        };

        // Open menu in new window
        const openMenuInNewWindow = (menuId) => {
            const url = `/web#menu_id=${menuId}`;
            return openInNewWindow(url, { name: `menu_${menuId}` });
        };

        // Clone current view to new window
        const cloneToNewWindow = () => {
            const currentUrl = window.location.href;
            return openInNewWindow(currentUrl);
        };

        // Get panel layout CSS
        const getPanelLayout = () => {
            switch (state.mode) {
                case 'vertical':
                    return {
                        gridTemplateColumns: '1fr 1fr',
                        gridTemplateRows: '1fr',
                    };
                case 'horizontal':
                    return {
                        gridTemplateColumns: '1fr',
                        gridTemplateRows: '1fr 1fr',
                    };
                case 'quad':
                    return {
                        gridTemplateColumns: '1fr 1fr',
                        gridTemplateRows: '1fr 1fr',
                    };
                default:
                    return {
                        gridTemplateColumns: '1fr',
                        gridTemplateRows: '1fr',
                    };
            }
        };

        // Swap panels
        const swapPanels = (panel1Id, panel2Id) => {
            const panel1 = state.panels.find(p => p.id === panel1Id);
            const panel2 = state.panels.find(p => p.id === panel2Id);
            if (panel1 && panel2) {
                const temp = { ...panel1 };
                panel1.action = panel2.action;
                panel1.title = panel2.title;
                panel2.action = temp.action;
                panel2.title = temp.title;
            }
        };

        // Close panel
        const closePanel = (panelId) => {
            const panel = state.panels.find(p => p.id === panelId);
            if (panel && panelId !== 1) {
                panel.action = null;
                panel.title = '';
                panel.active = false;

                // If closing last active panel, switch to single mode
                const activePanels = state.panels.filter(p => p.action !== null);
                if (activePanels.length <= 1) {
                    disable();
                }
            }
        };

        // Maximize panel (go to single view with this panel)
        const maximizePanel = (panelId) => {
            const panel = state.panels.find(p => p.id === panelId);
            if (panel && panel.action) {
                // Move this panel's action to panel 1
                state.panels[0].action = panel.action;
                state.panels[0].title = panel.title;
                disable();

                // Execute the action
                if (panel.action.type) {
                    action.doAction(panel.action);
                }
            }
        };

        return {
            state,
            enable,
            disable,
            toggle,
            setActivePanel,
            openInPanel,
            openInNewWindow,
            openRecordInNewWindow,
            openActionInNewWindow,
            openMenuInNewWindow,
            cloneToNewWindow,
            getPanelLayout,
            swapPanels,
            closePanel,
            maximizePanel,
        };
    },
};

registry.category("services").add("splitScreen", splitScreenService);
