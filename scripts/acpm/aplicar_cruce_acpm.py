# Marca como ACPM de finca las facturas identificadas en el cruce con la hoja "ACPM 2025".
# APLICAR=False: simula y deshace. APLICAR=True: guarda.
import json, datetime as dt
APLICAR = False
plan = json.load(open('/tmp/plan_acpm.json'))
AML = env['account.move.line']; Campana = env['finca.campana']
camp = Campana.search([('name', '=', '2025-2026')])
if not camp:
    camp = Campana.create({'name': '2025-2026', 'fecha_inicio': dt.date(2025, 10, 1), 'fecha_fin': dt.date(2026, 9, 30)})
    print('campaña 2025-2026 creada')
n_lineas = 0; gal = 0.0; sin_ana = []
for p in plan:
    lineas = AML.browse(p['lineas']).filtered(lambda l: l.display_type == 'product')
    lineas.write({'acpm_es': True, 'acpm_tipo': 'finca', 'acpm_lugar_id': p['lugar']})
    n_lineas += len(lineas); gal += sum(lineas.mapped('acpm_galones'))
    sin_ana += [l.move_id.name for l in lineas if not l.acpm_analitica_ok]
print('facturas:', len(plan), '| líneas marcadas:', n_lineas, '| galones:', round(gal, 2))
print('sin campaña:', AML.search_count([('acpm_es', '=', True), ('acpm_campana_id', '=', False)]))
print('analítica pendiente en:', sorted(set(sin_ana)) or 'ninguna')
for lugar, g in env['secadora.acpm.compra']._read_group([('tipo', '=', 'finca')], ['lugar_id'], ['galones:sum']):
    print('  ', lugar.name if lugar else '(sin finca)', round(g, 1), 'gal')
if APLICAR:
    env.cr.commit(); print('APLICADO')
else:
    env.cr.rollback(); print('SIMULACIÓN, nada guardado')
