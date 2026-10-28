"""Add the function that decodes an event's canonical bytes into JSON.

Postgres only allows immutable expressions in generated columns, and the
built-in ``convert_from`` is marked stable because its result can depend on the
encoding argument. With the encoding fixed to UTF-8 the result depends only on
the input bytes, so this wrapper is declared immutable.
"""

from django.db import migrations

FORWARD = """
CREATE OR REPLACE FUNCTION ledger_document(canonical bytea) RETURNS jsonb
LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE
AS $$ SELECT convert_from(canonical, 'UTF8')::jsonb $$;
"""

REVERSE = "DROP FUNCTION IF EXISTS ledger_document(bytea);"


class Migration(migrations.Migration):
    initial = True
    operations = [migrations.RunSQL(FORWARD, REVERSE)]
