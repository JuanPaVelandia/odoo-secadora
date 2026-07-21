{
    "name": "Páramo Agro Costing",
    "summary": "Costeo agroindustrial: activo biológico (1425) → arroz seco (1430) → derivados",
    "version": "0.1.0",
    "category": "Accounting/Agriculture",
    "author": "PARAMO LABS",
    "website": "https://paramo.digital",
    "license": "OPL-1",
    "depends": [
        "mail",           # chatter + tracking en la cosecha
        "stock_account",  # valoración perpetua + COGS
        "mrp",            # molienda + subproductos (costeo conjunto)
        "analytic",       # planes Punto Operativo / Cosecha
    ],
    "data": [
        "security/ir.model.access.csv",
        "data/analytic_plans.xml",
        "views/paramo_punto_operativo_views.xml",
        "views/paramo_cosecha_views.xml",
        "views/cosecha_close_views.xml",
        "views/mrp_bom_views.xml",
        "views/menus.xml",
    ],
    "application": True,
    "installable": True,
}
