"""Schema changes: connect as the owner role, which is the only role allowed to run DDL.

The API and workers never load this module, so they never hold the owner's
credentials (docs/threat-model.md).
"""

import dj_database_url

from config.env import ConfigurationError
from config.settings.base import ENV
from config.settings.local import *

if ENV.db_owner_url is None:
    raise ConfigurationError("DB_OWNER_URL is required to run migrations")
DATABASES = {"default": dj_database_url.parse(ENV.db_owner_url.get_secret_value())}
