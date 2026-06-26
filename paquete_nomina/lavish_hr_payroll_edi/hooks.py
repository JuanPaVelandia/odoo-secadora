# -*- coding: utf-8 -*-
import logging
import os
import re

_logger = logging.getLogger(__name__)

MODULE = 'lavish_hr_payroll_edi'

# (xml file relative to module, target ORM model)
DATA_FILES = [
    ('data/hr_accrued_rule_data.xml', 'hr.accrued.rule'),
    ('data/hr_deduct_rule_data.xml', 'hr.deduct.rule'),
]


def _adopt_existing_records(cr, file_path, model):
    """SQL-only adoption: avoids depending on ORM registry, which may not yet
    have the model fully set up during pre_init_hook when there is a clash
    of `_name` between the legacy module and this one."""
    if not os.path.isfile(file_path):
        return 0
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    pattern = re.compile(
        r'<record\s+id="([^"]+)"\s+model="' + re.escape(model) + r'">.*?<field\s+name="code">([^<]+)</field>',
        re.DOTALL,
    )
    table = model.replace('.', '_')
    cr.execute(
        "SELECT 1 FROM information_schema.tables WHERE table_name = %s",
        (table,),
    )
    if not cr.fetchone():
        return 0
    adopted = 0
    for xmlid, code in pattern.findall(content):
        cr.execute(f"SELECT id FROM {table} WHERE code = %s LIMIT 1", (code,))
        row = cr.fetchone()
        if not row:
            continue
        rec_id = row[0]
        cr.execute(
            "SELECT 1 FROM ir_model_data WHERE module = %s AND name = %s",
            (MODULE, xmlid),
        )
        if cr.fetchone():
            continue
        cr.execute(
            "INSERT INTO ir_model_data "
            "(module, name, model, res_id, noupdate, create_date, write_date) "
            "VALUES (%s, %s, %s, %s, FALSE, NOW(), NOW())",
            (MODULE, xmlid, model, rec_id),
        )
        adopted += 1
    return adopted


def pre_init_hook(env):
    """Adopt existing rows of hr.accrued.rule / hr.deduct.rule under this module's
    xmlids, so the data XML loader UPDATEs instead of trying to INSERT and hitting
    the UNIQUE(code) constraint."""
    module_path = os.path.dirname(__file__)
    total = 0
    for relative_path, model in DATA_FILES:
        adopted = _adopt_existing_records(
            env.cr, os.path.join(module_path, relative_path), model,
        )
        if adopted:
            _logger.info("[%s.pre_init_hook] adopted %d existing %s record(s)", MODULE, adopted, model)
        total += adopted
    if total:
        _logger.info("[%s.pre_init_hook] total adopted: %d", MODULE, total)
