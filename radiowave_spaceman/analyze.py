# BSD 3-Clause License; see https://github.com/jpivarski/radiowave-spaceman/blob/master/LICENSE

from __future__ import absolute_import

import sys

import uncompyle6
import spark_parser


def decorator(argument_name):
    def get_function(function):
        references = set()
        setattr(function, argument_name, references)

        analyze_function(function, references, argument_name)

        return function

    return get_function


class Unknown(object):
    def __repr__(self):
        return "Unknown"

    def __hash__(self):
        return hash(Unknown)

    def __eq__(self, other):
        return other is Unknown or isinstance(other, Unknown)

    def __ne__(self, other):
        return not self == other

    def __add__(self, other):
        return Unknown()


class SymbolTable(object):
    def __init__(self, parent):
        self.parent = parent
        self.symbols = {}

    def __getitem__(self, symbol):
        if symbol in self.symbols:
            return self.symbols[symbol]
        elif self.parent is not None:
            return self.parent[symbol]
        else:
            return None

    def __setitem__(self, symbol, value):
        self.symbols[symbol] = value


class Context(object):
    def __init__(self, argument_name, references, symboltable, indent):
        self.argument_name = argument_name
        self.references = references
        self.symboltable = symboltable
        self.indent = indent

    def copy_with(self, **kwargs):
        argument_name = kwargs.pop("argument_name", self.argument_name)
        references = kwargs.pop("references", self.references)
        symboltable = kwargs.pop("symboltable", self.symboltable)
        indent = kwargs.pop("indent", self.indent)
        return Context(argument_name, references, symboltable, indent)


def analyze_function(function, references, argument_name):
    python_version = float(sys.version[0:3])
    is_pypy = "__pypy__" in sys.builtin_module_names

    parser = uncompyle6.parser.get_python_parser(
        python_version,
        debug_parser=dict(spark_parser.DEFAULT_DEBUG),
        compile_mode="exec",
        is_pypy=is_pypy,
    )

    scanner = uncompyle6.scanner.get_scanner(
        python_version,
        is_pypy=is_pypy,
    )

    tokens, customize = scanner.ingest(
        function.__code__,
        code_objects={},
        show_asm=False,
    )

    parsed = uncompyle6.parser.parse(
        parser,
        tokens,
        customize,
        function.__code__,
    )

    context = Context(argument_name, references, SymbolTable(None), "")
    handle(parsed, context)


handlers = {}


def handle(node, context):
    print(context.indent + node.kind)

    if node.kind in handlers:
        tmp = handlers[node.kind](node, context)
    else:
        tmp = handle_default(node, context)

    print(context.indent + repr(tmp))
    return tmp


def handle_default(node, context):
    output = None
    for subnode in node:
        out = handle(subnode, context.copy_with(indent=context.indent + "    "))
        if out is not None:
            if output is None:
                output = out
            elif output != out:
                output = Unknown()
    return output


def handle_LOAD_NAME(node, context):
    if node.pattr == context.argument_name:
        return ()
    else:
        return None


handlers["LOAD_FAST"] = handle_LOAD_NAME
handlers["LOAD_NAME"] = handle_LOAD_NAME


def handle_attribute(node, context):
    partial_ref = handle(node[0], context)
    if partial_ref is not None:
        ref = partial_ref + (node[1].pattr,)
        context.references.add(ref)
        return ref
    else:
        return None


handlers["attribute"] = handle_attribute
