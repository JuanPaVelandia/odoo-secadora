# -*- coding: utf-8 -*-
import logging

from odoo import SUPERUSER_ID, api
from odoo.addons.lavish_erp.hooks import merge_duplicate_cities

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return

    env = api.Environment(cr, SUPERUSER_ID, {})
    merged_count = merge_duplicate_cities(env)
    _logger.info("Post-migrate city merge finished. Merged duplicate cities: %s", merged_count)
