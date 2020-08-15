# BSD 3-Clause License; see https://github.com/jpivarski/radiowave-spaceman/blob/master/LICENSE

from __future__ import absolute_import

import sys
# import inspect

import uncompyle6
import spark_parser


def decorator(argument_name):
    """
    Attaches an attribute named by "argument_name" to the decorated function,
    which is a function that searches for references to that argument.

    See the unit tests for examples.
    """

    def get_function(function):
        def get_references():
            references = set()
            analyze_function(function, references, argument_name, ())
            return references

        setattr(function, argument_name, get_references)

        return function

    return get_function


class SymbolTable(object):
    """
    Mapping from symbol name to references/partial references.

    SymbolTables are chained: if a symbol is not found in this table, it defers
    to its parent (until reaching the root table). The chain of SymbolTables
    represents lexically nested scopes.

    References can be set to "None" to shadow symbols in the parent's scope.
    """

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
    """
    Grab-bag of data required by each parsing tree handler.

    (Better than maintaining long argument lists.)
    """

    def __init__(self, references, symboltable, previous_passes, closure):
        self.references = references
        self.symboltable = symboltable
        self.previous_passes = previous_passes
        self.closure = closure


def analyze_function(function, references, argument_name, argument_ref):
    """
    Entry point for analyzing a function.

    This calls "analyze_code" to do most of its work, but if you have a function
    object, rather than just a code object, you get closure data (symbols that
    surround the function's definition and may be passed into the function)
    and it is necessary to make a nested SyntaxTable because Python functions
    have nested scope.

    (In Python, ONLY functions have nested scope. If this were C, we'd have to
    make a nested SyntaxTable in every if and for loop.)
    """

    ### fails if any cells have not been filled yet
    # closurevars = inspect.getclosurevars(function)
    # closure = dict(closurevars.globals)
    # closure.update(closurevars.nonlocals)

    closure = dict(function.__globals__)
    if function.__closure__ is not None:
        for var, cell in zip(function.__code__.co_freevars, function.__closure__):
            try:
                closure[var] = cell.cell_contents
            except ValueError:
                pass   # the cell has not been filled yet, so ignore it

    symboltable = SymbolTable(None)
    symboltable[argument_name] = argument_ref

    analyze_code(function.__code__, closure, symboltable, references, False, set())


def analyze_code(code, closure, symboltable, references, single_pass, previous_passes):
    """
    This function uses uncompyle6 to parse the Python bytecode, resulting in a
    parsing tree (forerunner of an abstract syntax tree or AST).

    This parsing tree is passed to "handle", which recursively walks over it.

    A single-pass is used for nested functions, multiple passes for the top-level.
    """

    # this block is all uncompyle6
    python_version = float(sys.version[0:3])
    is_pypy = "__pypy__" in sys.builtin_module_names
    parser = uncompyle6.parser.get_python_parser(
        python_version,
        debug_parser=dict(spark_parser.DEFAULT_DEBUG),
        compile_mode="exec",
        is_pypy=is_pypy,
    )
    scanner = uncompyle6.scanner.get_scanner(python_version, is_pypy=is_pypy)
    tokens, customize = scanner.ingest(code, code_objects={}, show_asm=False)
    parsed = uncompyle6.parser.parse(parser, tokens, customize, code)

    # single pass for nested functions and lambdas because they're already part
    # of the multi-pass run on the top-level function
    if single_pass:
        handle(parsed, Context(references, symboltable, previous_passes, closure))

    # multiple passes over the function to handle cases like test_4, in which a
    # symbol may be used lexically BEFORE the assignment that associates it with
    # a watched symbol
    else:
        previous_passes = set()
        while len(symboltable) > 0:
            current_pass = set(symboltable)

            handle(parsed, Context(references, symboltable, previous_passes, closure))

            # only search for symbols we haven't searched for before
            for symbol in current_pass:
                del symboltable[symbol]
            previous_passes.update(current_pass)


handlers = {}


def handle(node, context):
    """
    Recursive function for analyzing one parsing tree node.

    This function dispatches to specialized handlers, with a default.

    Returns None or a reference/partial reference.
    """

    if node.kind in handlers:
        return handlers[node.kind](node, context)
    else:
        return handle_default(node, context)


def handle_default(node, context):
    """
    Default handler for any parsing tree node kind.

    Most specialized handlers also call this function to recurse through a
    node's children.
    """

    results = set()
    for subnode in node:
        result = handle(subnode, context)
        if result is not None:
            results.add(result)

    if len(results) == 1:
        return list(results)[0]
    else:
        return None


def handle_LOAD_NAME(node, context):
    if node.pattr in context.symboltable:
        return context.symboltable[node.pattr]
    else:
        return None


handlers["LOAD_NAME"] = handle_LOAD_NAME
handlers["LOAD_FAST"] = handle_LOAD_NAME
handlers["LOAD_DEREF"] = handle_LOAD_NAME


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
    return None


handlers["assign"] = handle_assign


def handle_call(node, context):
    if node.kind == "call":
        argnodes = node[1:-1]
        kwnames = [None] * len(argnodes)

    elif node.kind == "call_kw36":
        argnodes = node[1:-2]
        kwnames = node[-2].pattr
        kwnames = [None] * (len(argnodes) - len(kwnames)) + list(kwnames)

    argvalues = [handle(argnode, context) for argnode in argnodes]
    args = []
    kwargs = {}
    for name, value in zip(kwnames, argvalues):
        if name is None:
            args.append(value)
        else:
            kwargs[name] = value

    if node[0].kind == "expr":
        if node[0][0].kind == "LOAD_GLOBAL" or node[0][0].kind == "LOAD_DEREF":
            function_name = node[0][0].pattr
            if function_name in context.closure:
                function = context.closure[function_name]

                ### the inspect module, with its version-dependent interface,
                ### is not strictly needed here: the code below works, too
                # signature = inspect.signature(function)
                # try:
                #     binding = signature.bind(*args, **kwargs)
                # except TypeError:
                #     pass
                # else:
                #     for name, ref in binding.arguments.items():
                #         analyze_function(function, context.references, name, ref)

                code = function.__code__
                for pos, name in enumerate(code.co_varnames[:code.co_argcount]):
                    if name in kwargs:
                        ref = kwargs[name]
                    elif pos < len(args):
                        ref = args[pos]
                    else:
                        continue
                    analyze_function(function, context.references, name, ref)

    return handle_default(node, context)


handlers["call"] = handle_call
handlers["call_kw36"] = handle_call


def handle_mkfunc(node, context):
    if node[0].kind == "LOAD_CODE":
        codenode = node[0]
    else:
        codenode = node[1]

    code = codenode.attr
    symboltable = SymbolTable(context.symboltable)
    for name in code.co_varnames[:code.co_argcount]:
        symboltable[name] = None

    analyze_code(
        code,
        context.closure,
        symboltable,
        context.references,
        True,
        context.previous_passes)
    return None


handlers["mkfunc"] = handle_mkfunc


def handle_mklambda(node, context):
    if node[0].kind == "LOAD_LAMBDA":
        lambdanode = node[0]
    else:
        lambdanode = node[1]

    code = lambdanode.attr
    symboltable = SymbolTable(context.symboltable)
    for name in code.co_varnames[:code.co_argcount]:
        symboltable[name] = None

    analyze_code(
        code,
        context.closure,
        symboltable,
        context.references,
        True,
        context.previous_passes)
    return None


handlers["mklambda"] = handle_mklambda
