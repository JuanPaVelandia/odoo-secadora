# -*- coding: utf-8 -*-
"""
Builders para generar HTML de reportes de nómina usando Bootstrap 5.3.3
Patrón Builder + Template Method para reutilización
Usa clases nativas de Bootstrap 5.3.3 e iconos de Bootstrap Icons
"""

from typing import List, Optional, Dict, Any


class BaseHTMLBuilder:
    """
    Builder base para generar HTML con Bootstrap 5.3.3
    Usa CDN de Bootstrap para estilos nativos
    """

    # Link a Bootstrap 5.3.3 (se puede cambiar a archivos locales en producción)
    BOOTSTRAP_CDN = """
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.min.css">
    """

    # Estilos personalizados adicionales
    CUSTOM_STYLES = """
    <style>
        .payroll-report {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            font-size: 0.95rem;
            line-height: 1.6;
        }
        .payroll-card {
            border-radius: 0.5rem;
            box-shadow: 0 0.125rem 0.25rem rgba(0,0,0,.075);
            margin-bottom: 1.5rem;
        }
        .calculation-steps {
            background-color: #f8f9fa;
            border-left: 4px solid #0d6efd;
            padding: 1rem;
            border-radius: 0.25rem;
        }
        .calculation-steps ol {
            margin-bottom: 0;
            padding-left: 1.5rem;
        }
        .calculation-steps li {
            margin-bottom: 0.5rem;
        }
        .result-highlight {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 1.5rem;
            border-radius: 0.5rem;
            text-align: center;
        }
        .result-value {
            font-size: 2rem;
            font-weight: 700;
            margin: 0.5rem 0;
        }
        .icon-badge {
            display: inline-flex;
            align-items: center;
            gap: 0.5rem;
        }
    </style>
    """

    def __init__(self, use_cdn: bool = True):
        """
        Inicializa el builder

        Args:
            use_cdn: Si usar CDN de Bootstrap (True) o archivos locales (False)
        """
        self.parts = []
        self.use_cdn = use_cdn

    def add_bootstrap(self) -> 'BaseHTMLBuilder':
        """Añade enlaces a Bootstrap CSS y Icons"""
        if self.use_cdn:
            self.parts.append(self.BOOTSTRAP_CDN)
        else:
            # Usar archivos locales del módulo
            local_bootstrap = """
            <link href="/lavish_hr_employee/static/lib/bootstrap/bootstrap.min.css" rel="stylesheet">
            <link rel="stylesheet" href="/lavish_hr_employee/static/lib/bootstrap-icons/bootstrap-icons.css">
            """
            self.parts.append(local_bootstrap)

        self.parts.append(self.CUSTOM_STYLES)
        return self

    def add_html(self, html: str) -> 'BaseHTMLBuilder':
        """Añade HTML personalizado"""
        self.parts.append(html)
        return self

    def build(self) -> str:
        """Construye y retorna el HTML completo"""
        return f'<div class="payroll-report container-fluid">{"".join(self.parts)}</div>'


class ProvisionHTMLBuilder(BaseHTMLBuilder):
    """
    Builder especializado para reportes de provisiones
    Usa Bootstrap 5.3.3 y Bootstrap Icons
    """

    NOMBRES = {
        'vacaciones': 'VACACIONES',
        'prima': 'PRIMA DE SERVICIOS',
        'cesantias': 'CESANTÍAS',
        'intereses': 'INTERESES SOBRE CESANTÍAS'
    }

    FORMULAS = {
        'vacaciones': 'Base × 4.17%',
        'prima': 'Base × 8.33%',
        'cesantias': 'Base × 8.33%',
        'intereses': 'Base Cesantías × 12%'
    }

    ICONOS = {
        'vacaciones': 'bi-calendar-check',
        'prima': 'bi-cash-coin',
        'cesantias': 'bi-piggy-bank',
        'intereses': 'bi-graph-up-arrow'
    }

    def __init__(self, provision_type: str, use_cdn: bool = True):
        super().__init__(use_cdn)
        self.provision_type = provision_type
        self.nombre = self.NOMBRES.get(provision_type, provision_type.upper())
        self.formula = self.FORMULAS.get(provision_type, '')
        self.icono = self.ICONOS.get(provision_type, 'bi-calculator')
        self.add_bootstrap()

    def add_header(self, periodo: str) -> 'ProvisionHTMLBuilder':
        """Añade encabezado de provisión con icono"""
        html = f"""
        <div class="alert alert-info border-start border-4 border-info mb-3">
            <div class="d-flex align-items-center mb-2">
                <i class="bi {self.icono} fs-3 me-3 text-info"></i>
                <h4 class="mb-0 fw-bold">{self.nombre}</h4>
            </div>
            <hr class="my-2">
            <div class="row small">
                <div class="col-md-6">
                    <i class="bi bi-calendar3 me-1"></i><strong>Periodo:</strong> {periodo}
                </div>
                <div class="col-md-6">
                    <i class="bi bi-calculator me-1"></i><strong>Fórmula:</strong> {self.formula}
                </div>
            </div>
        </div>
        """
        self.parts.append(html)
        return self

    def add_steps_table(self, steps: List[Dict[str, str]]) -> 'ProvisionHTMLBuilder':
        """
        Añade tabla de pasos de cálculo con estilos Bootstrap 5.3.3

        Args:
            steps: Lista de dicts con keys 'concepto' y 'valor'
        """
        rows = "\n".join([
            f'<tr><td><i class="bi bi-check-circle text-success me-2"></i>{step["concepto"]}</td>'
            f'<td class="text-end fw-semibold">{step["valor"]}</td></tr>'
            for step in steps
        ])

        html = f"""
        <div class="card payroll-card border-0 mb-3">
            <div class="card-body p-0">
                <table class="table table-sm table-hover mb-0">
                    <thead class="table-light">
                        <tr>
                            <th class="fw-semibold"><i class="bi bi-list-ul me-2"></i>Concepto</th>
                            <th class="text-end fw-semibold"><i class="bi bi-currency-dollar me-2"></i>Valor</th>
                        </tr>
                    </thead>
                    <tbody>{rows}</tbody>
                </table>
            </div>
        </div>
        """
        self.parts.append(html)
        return self

    def add_result(self, total: str, applied: bool = True) -> 'ProvisionHTMLBuilder':
        """Añade resultado final con diseño moderno"""
        if applied:
            alert_class = 'alert-success'
            icon = 'bi-check-circle-fill'
            status_text = 'APLICADO'
            badge_class = 'bg-success'
        else:
            alert_class = 'alert-warning'
            icon = 'bi-exclamation-triangle-fill'
            status_text = 'NO APLICADO'
            badge_class = 'bg-warning'

        html = f"""
        <div class="{alert_class} border-0 shadow-sm">
            <div class="d-flex justify-content-between align-items-center">
                <div>
                    <div class="d-flex align-items-center mb-2">
                        <i class="bi {icon} fs-4 me-2"></i>
                        <h5 class="mb-0 fw-bold">Total {self.nombre}</h5>
                    </div>
                    <div class="result-value display-4">{total}</div>
                </div>
                <div>
                    <span class="badge {badge_class} fs-6 px-3 py-2">
                        <i class="bi bi-info-circle me-1"></i>{status_text}
                    </span>
                </div>
            </div>
        </div>
        """
        self.parts.append(html)
        return self


class SocialSecurityHTMLBuilder(BaseHTMLBuilder):
    """
    Builder para logs de seguridad social y conceptos de nómina
    Usa Bootstrap 5.3.3 y Bootstrap Icons
    """

    def __init__(self, use_cdn: bool = True):
        super().__init__(use_cdn)
        self.add_bootstrap()

    def add_header(self, titulo: str, periodo: str, aplicado: bool) -> 'SocialSecurityHTMLBuilder':
        """Añade encabezado del concepto con iconos Bootstrap"""
        if aplicado:
            alert_class = 'alert-info'
            icon = 'bi-info-circle-fill'
            badge_class = 'bg-success'
            status = 'APLICADO'
        else:
            alert_class = 'alert-warning'
            icon = 'bi-exclamation-triangle-fill'
            badge_class = 'bg-danger'
            status = 'NO APLICADO'

        html = f"""
        <div class="{alert_class} border-start border-4 mb-3">
            <div class="d-flex justify-content-between align-items-start">
                <div class="flex-grow-1">
                    <div class="d-flex align-items-center mb-1">
                        <i class="bi {icon} fs-5 me-2"></i>
                        <h5 class="mb-0 fw-bold">{titulo}</h5>
                    </div>
                    <p class="mb-0 small text-muted">
                        <i class="bi bi-calendar-range me-1"></i>Periodo: {periodo}
                    </p>
                </div>
                <div class="ms-3">
                    <span class="badge {badge_class} rounded-pill px-3 py-2">
                        <i class="bi bi-patch-check me-1"></i>{status}
                    </span>
                </div>
            </div>
        </div>
        """
        self.parts.append(html)
        return self

    def add_description(self, descripcion: str) -> 'SocialSecurityHTMLBuilder':
        """Añade descripción del cálculo con icono"""
        html = f"""
        <div class="mb-3">
            <p class="mb-0 fst-italic text-secondary">
                <i class="bi bi-chat-left-text me-2"></i>{descripcion}
            </p>
        </div>
        """
        self.parts.append(html)
        return self

    def add_steps_list(self, pasos: List[str]) -> 'SocialSecurityHTMLBuilder':
        """Añade lista de pasos del cálculo con estilo Bootstrap 5.3.3"""
        if not pasos:
            return self

        items = "\n".join([
            f'<li class="mb-2"><i class="bi bi-arrow-right-circle text-primary me-2"></i>{paso}</li>'
            for paso in pasos
        ])

        html = f"""
        <div class="calculation-steps mb-3">
            <div class="d-flex align-items-center mb-2">
                <i class="bi bi-calculator fs-5 text-primary me-2"></i>
                <strong class="text-primary">Pasos del cálculo:</strong>
            </div>
            <ol class="mb-0">{items}</ol>
        </div>
        """
        self.parts.append(html)
        return self

    def add_details_table(self, detalles: List[Dict[str, Any]]) -> 'SocialSecurityHTMLBuilder':
        """
        Añade tabla de detalles con estilos Bootstrap 5.3.3

        Args:
            detalles: Lista de dicts con keys 'campo', 'valor', opcionalmente 'highlight'
        """
        rows = []
        for detalle in detalles:
            if detalle.get('highlight'):
                row_class = 'table-primary fw-semibold'
                icon = '<i class="bi bi-star-fill text-warning me-2"></i>'
            else:
                row_class = ''
                icon = '<i class="bi bi-dot me-2"></i>'

            rows.append(
                f'<tr class="{row_class}">'
                f'<td>{icon}{detalle["campo"]}</td>'
                f'<td class="text-end fw-semibold">{detalle["valor"]}</td></tr>'
            )

        html = f"""
        <div class="card payroll-card border-0 mb-3">
            <div class="card-body p-0">
                <table class="table table-sm table-striped mb-0">
                    <tbody>{"".join(rows)}</tbody>
                </table>
            </div>
        </div>
        """
        self.parts.append(html)
        return self


class LeaveHTMLBuilder(BaseHTMLBuilder):
    """
    Builder para reportes de vacaciones y ausencias
    Usa Bootstrap 5.3.3 y Bootstrap Icons
    """

    def __init__(self, use_cdn: bool = True):
        super().__init__(use_cdn)
        self.add_bootstrap()

    def add_leave_header(self, tipo: str, periodo: str) -> 'LeaveHTMLBuilder':
        """Añade encabezado de vacaciones con icono"""
        html = f"""
        <div class="alert alert-info border-start border-4 border-info mb-3">
            <div class="d-flex align-items-center">
                <i class="bi bi-calendar-heart fs-3 text-info me-3"></i>
                <div>
                    <h5 class="mb-1 fw-bold">{tipo}</h5>
                    <p class="mb-0 small">
                        <i class="bi bi-clock-history me-1"></i>Periodo: {periodo}
                    </p>
                </div>
            </div>
        </div>
        """
        self.parts.append(html)
        return self

    def add_leave_summary(self, summary: Dict[str, str]) -> 'LeaveHTMLBuilder':
        """
        Añade resumen de vacaciones con iconos

        Args:
            summary: Dict con información de días disponibles, tomados, etc.
        """
        # Mapeo de iconos según el tipo de información
        icon_map = {
            'días disponibles': 'bi-calendar-check',
            'días tomados': 'bi-calendar-x',
            'días pendientes': 'bi-calendar-plus',
            'saldo': 'bi-wallet2',
            'total': 'bi-calculator'
        }

        items = []
        for key, value in summary.items():
            key_lower = key.lower()
            icon = next((v for k, v in icon_map.items() if k in key_lower), 'bi-info-circle')
            items.append(
                f'<tr>'
                f'<td><i class="bi {icon} text-primary me-2"></i>{key}</td>'
                f'<td class="text-end fw-semibold">{value}</td>'
                f'</tr>'
            )

        items_html = "\n".join(items)

        html = f"""
        <div class="card payroll-card border-0 mb-3">
            <div class="card-header bg-light border-0">
                <h6 class="mb-0 fw-semibold">
                    <i class="bi bi-list-check me-2"></i>Resumen
                </h6>
            </div>
            <div class="card-body p-0">
                <table class="table table-sm mb-0">
                    <tbody>{items_html}</tbody>
                </table>
            </div>
        </div>
        """
        self.parts.append(html)
        return self
