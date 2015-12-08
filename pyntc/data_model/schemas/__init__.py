import os
import json
from jsonschema import RefResolver
from jsonschema import validate as js_validate

CURRENT_DIR = os.path.realpath(os.path.dirname(__file__))

def validate(instance, schema_name, vendor=''):
    schema_filename = '%s.json' % schema_name
    schema_filepath = os.path.join(CURRENT_DIR, vendor, schema_filename)

    with open(schema_filepath) as f:
        schema = json.load(f)

    resolver = RefResolver('file://%s' % schema_filepath, schema)
    js_validate(instance, schema, resolver=resolver)
