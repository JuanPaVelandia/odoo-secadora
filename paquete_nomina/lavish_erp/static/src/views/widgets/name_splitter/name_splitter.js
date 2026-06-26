/** @odoo-module **/

import { Component } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardWidgetProps } from "@web/views/widgets/standard_widget_props";

/**
 * Widget que divide un nombre completo en sus partes
 * Funciona sin llamar al servidor, actualiza los campos directamente
 */
export class NameSplitterButton extends Component {
    static template = "lavish_erp.NameSplitterButton";
    static props = {
        ...standardWidgetProps,
    };

    setup() {
        this.notification = useService("notification");
    }

    get isVisible() {
        if (!this.props.record) return false;
        const data = this.props.record.data;
        // Visible si: hay nombre Y no hay first_name ni first_lastname Y no es empresa
        return data.name && !data.first_name && !data.first_lastname && !data.is_company;
    }

    /**
     * Divide el nombre completo en partes
     */
    splitName() {
        const record = this.props.record;
        const fullName = record.data.name || '';

        if (!fullName.trim()) {
            this.notification.add("No hay nombre para dividir", { type: "warning" });
            return;
        }

        const parts = this._splitHispanicName(fullName);

        // Actualizar campos directamente en el registro
        record.update({
            first_name: parts.first_name,
            second_name: parts.second_name,
            first_lastname: parts.first_lastname,
            second_lastname: parts.second_lastname,
        });

        this.notification.add("Nombre dividido correctamente", { type: "success" });
    }

    /**
     * Algoritmo para dividir nombres hispanos
     * Formato esperado: APELLIDO1 APELLIDO2 NOMBRE1 NOMBRE2
     * o: NOMBRE1 NOMBRE2 APELLIDO1 APELLIDO2
     */
    _splitHispanicName(fullName) {
        // Limpiar y normalizar
        const cleaned = fullName.trim().toUpperCase().replace(/\s+/g, ' ');
        const words = cleaned.split(' ').filter(w => w.length > 0);

        const result = {
            first_name: '',
            second_name: '',
            first_lastname: '',
            second_lastname: ''
        };

        if (words.length === 0) return result;

        // Preposiciones y conectores comunes en apellidos hispanos
        const connectors = ['DE', 'DEL', 'LA', 'LAS', 'LOS', 'Y', 'E', 'VAN', 'VON', 'DI', 'DA'];

        // Unir palabras con conectores
        const mergedWords = [];
        let i = 0;
        while (i < words.length) {
            if (connectors.includes(words[i]) && i + 1 < words.length) {
                // Unir conector con siguiente palabra
                let compound = words[i];
                i++;
                while (i < words.length && connectors.includes(words[i])) {
                    compound += ' ' + words[i];
                    i++;
                }
                if (i < words.length) {
                    compound += ' ' + words[i];
                    mergedWords.push(compound);
                    i++;
                }
            } else {
                mergedWords.push(words[i]);
                i++;
            }
        }

        const count = mergedWords.length;

        // Detectar si el formato es APELLIDOS NOMBRES o NOMBRES APELLIDOS
        // Heuristica: si la primera palabra parece apellido comun, asumir APELLIDOS NOMBRES
        const commonLastnames = ['GARCIA', 'RODRIGUEZ', 'MARTINEZ', 'LOPEZ', 'GONZALEZ',
            'HERNANDEZ', 'PEREZ', 'SANCHEZ', 'RAMIREZ', 'TORRES', 'FLORES', 'RIVERA',
            'GOMEZ', 'DIAZ', 'REYES', 'MORALES', 'JIMENEZ', 'RUIZ', 'ALVAREZ', 'ROMERO',
            'CASTILLO', 'VARGAS', 'CASTRO', 'ORTIZ', 'MENDOZA', 'GUTIERREZ', 'ROJAS'];

        const firstIsLastname = commonLastnames.some(ln => mergedWords[0]?.startsWith(ln));

        if (count === 1) {
            // Solo una palabra: asumimos que es el primer nombre
            result.first_name = mergedWords[0];
        } else if (count === 2) {
            if (firstIsLastname) {
                // APELLIDO NOMBRE
                result.first_lastname = mergedWords[0];
                result.first_name = mergedWords[1];
            } else {
                // NOMBRE APELLIDO
                result.first_name = mergedWords[0];
                result.first_lastname = mergedWords[1];
            }
        } else if (count === 3) {
            if (firstIsLastname) {
                // APELLIDO1 APELLIDO2 NOMBRE o APELLIDO NOMBRE1 NOMBRE2
                result.first_lastname = mergedWords[0];
                result.second_lastname = mergedWords[1];
                result.first_name = mergedWords[2];
            } else {
                // NOMBRE APELLIDO1 APELLIDO2
                result.first_name = mergedWords[0];
                result.first_lastname = mergedWords[1];
                result.second_lastname = mergedWords[2];
            }
        } else if (count >= 4) {
            if (firstIsLastname) {
                // APELLIDO1 APELLIDO2 NOMBRE1 NOMBRE2
                result.first_lastname = mergedWords[0];
                result.second_lastname = mergedWords[1];
                result.first_name = mergedWords[2];
                result.second_name = mergedWords.slice(3).join(' ');
            } else {
                // NOMBRE1 NOMBRE2 APELLIDO1 APELLIDO2
                result.first_name = mergedWords[0];
                result.second_name = mergedWords[1];
                result.first_lastname = mergedWords[2];
                result.second_lastname = mergedWords.slice(3).join(' ');
            }
        }

        return result;
    }
}

export const nameSplitterButton = {
    component: NameSplitterButton,
    extractProps: ({ attrs }) => ({}),
};

registry.category("view_widgets").add("name_splitter_button", nameSplitterButton);
