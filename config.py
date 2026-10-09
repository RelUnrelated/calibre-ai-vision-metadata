# __license__   = 'GPL v3'
# __copyright__ = '2026, RelUnrelated <dan@relunrelated.com>'
from calibre.utils.config import JSONConfig

prefs = JSONConfig('plugins/metamanga')
CURRENT_SCHEMA_VERSION = 1.0

def migrate_config_if_required():
    # Copy legacy settings once; never overwrite an existing MetaManga config.
    if not prefs:
        legacy_prefs = JSONConfig('plugins/ai_vision_metadata')
        if legacy_prefs:
            with prefs:
                prefs.update(legacy_prefs)

    # Fetch the version, default to 0.9 if it doesn't exist yet
    schema_version = prefs.get('schema_version', 0.9)
    
    if schema_version < 1.0:
        # If upgrading from the 0.9 beta, set the new version
        # (In the future, logic here will inject new keys safely)
        prefs['schema_version'] = CURRENT_SCHEMA_VERSION

# Run this immediately when the file is loaded
migrate_config_if_required()
