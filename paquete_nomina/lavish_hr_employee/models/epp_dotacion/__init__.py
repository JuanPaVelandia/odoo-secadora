# -*- coding: utf-8 -*-
# Orden importante: hr.epp.batch debe cargarse antes de hr.epp.request
from . import hr_employee_location
from . import hr_epp_item_type
from . import hr_epp_size
from . import hr_epp_provider_agreement
from . import hr_epp_configuration
from . import hr_epp_configuration_improved
from . import hr_epp_batch
from . import hr_epp_batch_stock
from . import hr_epp_dotacion
from . import hr_epp_request
from . import wizard_epp_batch_generate
