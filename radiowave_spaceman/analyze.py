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


class SymbolTable(object):
    def __init__(self, parent):
        self.parent = parent
        self.symbols = {}

    def __len__(self):
        return len(self.symbols)

    def __contains__(self, symbol):
        if symbol in self.symbols:
            return True
        elif self.parent is not None:
            return symbol in self.parent
        else:
            return False

    def __getitem__(self, symbol):
        if symbol in self.symbols:
            return self.symbols[symbol]
        elif self.parent is not None:
            return self.parent[symbol]
        else:
            return None

    def __setitem__(self, symbol, value):
        self.symbols[symbol] = value

    def __delitem__(self, symbol):
        del self.symbols[symbol]

    def __iter__(self):
        return iter(self.symbols)


class Context(object):
    def __init__(self, references, symboltable, previous_passes):
        self.references = references
        self.symboltable = symboltable
        self.previous_passes = previous_passes

    def copy_with(self, **kwargs):
        references = kwargs.pop("references", self.references)
        symboltable = kwargs.pop("symboltable", self.symboltable)
        previous_passes = kwargs.pop("previous_passes", self.previous_passes)
        return Context(references, symboltable, previous_passes)


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

    symboltable = SymbolTable(None)
    symboltable[argument_name] = ()

    previous_passes = set()
    while len(symboltable) > 0:
        current_pass = set(symboltable)

        handle(parsed, Context(references, symboltable, previous_passes))

        for symbol in current_pass:
            del symboltable[symbol]
        previous_passes.update(current_pass)


handlers = {}


def handle(node, context):
    if node.kind in handlers:
        return handlers[node.kind](node, context)
    else:
        return handle_default(node, context)


def handle_default(node, context):
    output = None
    for subnode in node:
        out = handle(subnode, context)
        if out is not None:
            if output is None:
                output = out
            elif output != out:
                output = Unknown()
    return output


def handle_LOAD_NAME(node, context):
    if node.pattr in context.symboltable:
        return context.symboltable[node.pattr]
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


def handle_assign(node, context):
    ref = handle(node[0], context)
    if ref is not None:
        if len(node[1]) == 1:
            symbol = node[1][0].pattr
            if symbol not in context.previous_passes:
                context.symboltable[symbol] = ref
        else:
            context.references.add(ref + (Unknown(),))
    return None


handlers["assign"] = handle_assign
