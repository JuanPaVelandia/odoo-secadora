# -*- coding: utf-8 -*-
"""Migracion 18.0.1.1: alinea codigos de hr.deduct.rule con XSD DIAN V1.0.6.

Renombres aplicados:
  Pension              -> FondoPension
  Embargo              -> EmbargoFiscal
  PlanComplementario   -> PlanComplementarios
  Sindicato            -> Sindicatos
  FondoSubsistencia    -> FondoSP (la subsistencia es atributo DeduccionSub
                                   del nodo FondoSP, no codigo independiente)

El XML de data tiene noupdate=1, por lo que la actualizacion del modulo no
sobreescribe los codigos existentes. Aqui forzamos el cambio via SQL.
"""

def migrate(cr, version):
    if not version:
        return

    rename_map = {
        'Pension': 'FondoPension',
        'Embargo': 'EmbargoFiscal',
        'PlanComplementario': 'PlanComplementarios',
        'Sindicato': 'Sindicatos',
        'FondoSubsistencia': 'FondoSP',
    }
    for old_code, new_code in rename_map.items():
        cr.execute(
            "UPDATE hr_deduct_rule SET code = %s WHERE code = %s",
            (new_code, old_code),
        )
