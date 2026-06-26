# -*- coding: utf-8 -*-
import logging
import re
import unicodedata

from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)


def _normalize_city_name(name):
    if isinstance(name, dict):
        name = next((v for v in name.values() if v), "")
    name = (name or "").strip()
    if not name:
        return ""
    name = unicodedata.normalize("NFKD", name)
    name = "".join(c for c in name if not unicodedata.combining(c))
    name = name.upper()
    name = re.sub(r"[^A-Z0-9 ]+", " ", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name


def _get_edi_code(city):
    for field_name in ("l10n_co_edi_code", "code_dian", "code"):
        if hasattr(city, field_name):
            value = getattr(city, field_name)
            if value:
                return str(value).strip()
    return ""


def _select_master(cities):
    # Prefer city with DIAN code, then zipcode, then lowest id.
    def score(city):
        result = 0
        if _get_edi_code(city):
            result += 100
        if hasattr(city, "zipcode") and city.zipcode:
            result += 10
        return result

    return sorted(cities, key=lambda c: (-score(c), c.id))[0]


def _merge_city_data(master, dup):
    updates = {}
    for field_name in ("zipcode", "l10n_co_edi_code", "code_dian", "code", "code_zip"):
        if hasattr(master, field_name) and hasattr(dup, field_name):
            if not getattr(master, field_name) and getattr(dup, field_name):
                updates[field_name] = getattr(dup, field_name)
    if updates:
        master.write(updates)


def _relink_many2one(env, model, field_name, master_id, dup_id):
    try:
        table = env[model]._table
    except Exception:
        return
    env.cr.execute("SELECT to_regclass(%s)", (table,))
    if not env.cr.fetchone()[0]:
        return
    env.cr.execute(
        """
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = %s
          AND column_name = %s
        """,
        (table, field_name),
    )
    if not env.cr.fetchone():
        return
    env.cr.execute(
        f'UPDATE "{table}" SET "{field_name}" = %s WHERE "{field_name}" = %s',
        (master_id, dup_id),
    )


def _relink_many2many(env, relation_table, column1, column2, master_id, dup_id):
    env.cr.execute("SELECT to_regclass(%s)", (relation_table,))
    if not env.cr.fetchone()[0]:
        return
    env.cr.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = %s
          AND column_name IN (%s, %s)
        """,
        (relation_table, column1, column2),
    )
    columns = {row[0] for row in env.cr.fetchall()}
    if column1 not in columns or column2 not in columns:
        return
    # Insert merged pairs first to avoid losing links when a unique pair exists.
    env.cr.execute(
        f'''
        INSERT INTO "{relation_table}" ("{column1}", "{column2}")
        SELECT "{column1}", %s
        FROM "{relation_table}"
        WHERE "{column2}" = %s
        ON CONFLICT DO NOTHING
        ''',
        (master_id, dup_id),
    )
    env.cr.execute(
        f'DELETE FROM "{relation_table}" WHERE "{column2}" = %s',
        (dup_id,),
    )


def _cleanup_known_conflicts(env, master_id, dup_id):
    # Avoid unique(city_id, ciiu_id) conflicts.
    if "lavish.ica.tariffs" in env:
        env.cr.execute(
            """
            DELETE FROM lavish_ica_tariffs t
            USING lavish_ica_tariffs keep
            WHERE t.city_id = %s
              AND keep.city_id = %s
              AND keep.ciiu_id = t.ciiu_id
              AND keep.id <> t.id
            """,
            (dup_id, master_id),
        )
    # Avoid unique(name, city_id) conflicts.
    if "res.city.neighborhood" in env:
        env.cr.execute(
            """
            DELETE FROM res_city_neighborhood n
            USING res_city_neighborhood keep
            WHERE n.city_id = %s
              AND keep.city_id = %s
              AND keep.name = n.name
              AND keep.id <> n.id
            """,
            (dup_id, master_id),
        )


def merge_duplicate_cities(env):
    country = env["res.country"].search([("code", "=", "CO")], limit=1)
    if not country:
        return 0

    cities = env["res.city"].sudo().search([("country_id", "=", country.id)])
    if not cities:
        return 0

    # Preload fields referencing res.city (many2one + many2many)
    m2o_fields = env["ir.model.fields"].sudo().search([
        ("relation", "=", "res.city"),
        ("ttype", "=", "many2one"),
        ("store", "=", True),
    ])
    m2m_fields = env["ir.model.fields"].sudo().search([
        ("relation", "=", "res.city"),
        ("ttype", "=", "many2many"),
    ])

    # Group by state + code when available, fallback to normalized name.
    groups_by_code = {}
    groups_by_name = {}
    for city in cities:
        state_id = city.state_id.id or 0
        code = _normalize_city_name(_get_edi_code(city))
        name = _normalize_city_name(city.name)
        if code:
            groups_by_code.setdefault((state_id, code), []).append(city)
        if name:
            groups_by_name.setdefault((state_id, name), []).append(city)

    merged_count = 0
    processed_dup_ids = set()
    all_groups = list(groups_by_code.values()) + list(groups_by_name.values())

    for group in all_groups:
        group = [c for c in group if c.id not in processed_dup_ids]
        if len(group) < 2:
            continue

        master = _select_master(group)
        for dup in group:
            if dup.id == master.id:
                continue

            _merge_city_data(master, dup)
            _cleanup_known_conflicts(env, master.id, dup.id)

            for field in m2o_fields:
                _relink_many2one(env, field.model, field.name, master.id, dup.id)

            for field in m2m_fields:
                relation_table = field.relation_table or field.relation
                column1 = field.column1
                column2 = field.column2
                if relation_table and column1 and column2:
                    _relink_many2many(env, relation_table, column1, column2, master.id, dup.id)

            dup.unlink()
            processed_dup_ids.add(dup.id)
            merged_count += 1

    return merged_count


def post_init_hook(env):
    """Post-installation hook to merge duplicate cities."""
    merged_count = merge_duplicate_cities(env)
    _logger.info("City merge hook finished. Merged duplicate cities: %s", merged_count)
