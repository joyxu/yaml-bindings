#!/usr/bin/env python3

import sys
import os
basedir = os.path.dirname(__file__)
import yaml
sys.path.insert(0, os.path.join(basedir, "jsonschema-draft6"))
import jsonschema
import argparse
import glob
import dtschema

def item_generator(json_input, lookup_key):
    if isinstance(json_input, dict):
        for k, v in json_input.items():
            if k == lookup_key:
                if isinstance(v, str):
                    yield [v]
                else:
                    yield v
            else:
                for child_val in item_generator(v, lookup_key):
                    yield child_val
    elif isinstance(json_input, list):
        for item in json_input:
            for item_val in item_generator(item, lookup_key):
                yield item_val

def get_select_schema(schema):
    '''Get a schema to be used in select tests.

    If the provided schema has a 'select' property, then use that as the select schema.
    If it has a compatible property, then create a select schema from that.
    If it has neither, then return a match-nothing schema
    '''
    compatible_list = [ ]
    if "select" in schema.keys():
        return schema["select"]

    if not 'properties' in schema.keys():
        return {"not": {}}

    if not 'compatible' in schema['properties'].keys():
        return {"not": {}}

    for l in item_generator(schema['properties']['compatible'], 'enum'):
        compatible_list.extend(l)

    for l in item_generator(schema['properties']['compatible'], 'const'):
        compatible_list.extend(l)

    compatible_list = list(set(compatible_list))

    return { 'required': ['compatible'],
             'properties': {'compatible': {'contains': {'enum': compatible_list}}}}

class schema_group():
    def __init__(self):
        self.schemas = list()
        for filename in glob.iglob("schemas/**/*.yaml", recursive=True):
            self.load_binding_schema(filename)

    def load_binding_schema(self, filename):
        try:
            schema = dtschema.load_schema(filename)
        except yaml.YAMLError as exc:
            print(filename + ": ignoring, error parsing file")
            return

        # Check that the validation schema is valid
        try:
            dtschema.DTValidator.check_schema(schema)
        except jsonschema.SchemaError as exc:
            print(filename + ": ignoring, error in schema '%s'" % exc.path[-1])
            #print(exc.message)
            return

        # $validator and $select_validator are special properties that cache the
        # validator objects so the object doesn't need to be recreated on every node.
        schema["$validator"] = dtschema.DTValidator(schema)
        schema["$select_validator"] = jsonschema.Draft6Validator(get_select_schema(schema))
        self.schemas.append(schema)

        schema["$filename"] = filename
        print(filename + ": loaded")

    def check_node(self, dt, node, path):
        node_matched = False
        for schema in self.schemas:
            if schema['$select_validator'].is_valid(node):
                node_matched = True
                errors = sorted(schema['$validator'].iter_errors(node), key=lambda e: e.path)
                if (errors):
                    for error in errors:
                        print("node '%s': in %s: %s (from %s)" %
                              (path, list(error.path), error.message, schema["$filename"]))
        if not node_matched:
            print(node)
            print("node %s: failed to match any schema with compatible(s) %s" % (path, node["compatible"]))

    def check_subtree(self, dt, subtree, path="/"):
        self.check_node(dt, subtree, path)
        for name,value in subtree.items():
            if type(value) == dict:
                self.check_subtree(dt, value, '/'.join([path,name]))

    def check_trees(self, dt):
        """Check the given DT against all schemas"""
        for subtree in dt:
            self.check_subtree(dt, subtree)

if __name__ == "__main__":
    sg = schema_group()

    ap = argparse.ArgumentParser()
    ap.add_argument("yamldt", type=str,
                    help="Filename of YAML encoded devicetree input file")
    args = ap.parse_args()


    testtree = yaml.load(open(args.yamldt).read())
    sg.check_trees(testtree)
