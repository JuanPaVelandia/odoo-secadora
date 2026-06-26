import logging
import xmltodict
from datetime import date, time, datetime
from num2words import num2words

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)