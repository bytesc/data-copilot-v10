"""AST review gate for LLM-generated execution code (sandbox layer 1).

The generated code is parsed into a syntax tree and every import, call, attribute
access and name is checked against a whitelist. Anything suspicious is reported
with a line number and the code is NOT executed (the caller returns the message to
the LLM through the existing ``code_exe_error`` retry loop).

This is a "doorman", not a cryptographic boundary: it stops slips of the hand and
the obvious 90% of malicious intent, while the child process (layer 2), the
whitelisted namespace (layer 3), the resource limits (layer 4) and the narrow
output channel (layer 5) provide the real, defence-in-depth guarantees.
"""

import ast


# Root modules generated code must never be able to import: process/OS/network
# escape hatches plus the project's own privileged modules (which would otherwise
# hand back ``engine``, config secrets and other privileged objects).
BLOCKED_MODULE_ROOTS = {
    # process / OS / filesystem
    "os", "sys", "subprocess", "shutil", "pathlib", "glob", "tempfile",
    "fileinput", "fcntl", "pty", "tty", "termios", "select",
    "selectors", "signal", "mmap", "posix", "nt", "winreg", "msvcrt",
    "platform", "sysconfig", "site", "runpy", "code", "codeop", "pkgutil",
    "importlib", "imp", "builtins", "__builtin__", "gc", "inspect",
    # network
    "socket", "socketserver", "ssl", "http", "httplib", "urllib", "urllib2",
    "urllib3", "requests", "ftplib", "telnetlib", "smtplib", "poplib",
    "imaplib", "xmlrpc", "webbrowser", "asyncio",
    # concurrency / execution
    "multiprocessing", "threading", "concurrent", "resource", "ctypes",
    # serialization / persistence
    "pickle", "cPickle", "marshal", "shelve", "dbm", "sqlite3", "xml",
    # project modules (privileged objects live here)
    "agent", "utils", "config", "data_access", "main", "front", "mcpserver",
    "doc_workspace", "vue_front",
}

# Deny-by-default: generated code may only import these roots. The executore
# injects exactly this set into ``func`` so legitimate generated code keeps
# working, while any other import is rejected.
ALLOWED_MODULE_ROOTS = {
    "pandas", "numpy", "matplotlib", "seaborn", "PIL",
    "math", "json", "re", "datetime", "textwrap", "random", "collections",
    "io", "functools", "itertools", "statistics", "decimal", "fractions",
    "uuid", "string", "copy", "typing", "warnings", "numbers",
}

# Builtins that are escape hatches or interactive blockers.
BLOCKED_CALL_NAMES = {
    "eval", "exec", "compile", "__import__", "open", "input", "breakpoint",
    "globals", "locals", "vars", "getattr", "setattr", "delattr",
    "exit", "quit", "help", "memoryview", "copyright", "credits", "license",
}

# Dunder attributes used to climb from a value back to its globals/builtins and
# escape the whitelist namespace.
BLOCKED_ATTRS = {
    "__globals__", "__builtins__", "__subclasses__", "__bases__", "__base__",
    "__mro__", "__class__", "__code__", "__closure__", "__loader__",
    "__reduce__", "__reduce_ex__", "__getattribute__", "__setattr__",
    "__delattr__", "__init_subclass__", "__subclasshook__", "__mro_entries__",
    "__dict__", "func_globals", "func_code", "gi_frame", "cr_frame",
    "f_globals", "f_builtins", "f_locals", "tb_frame", "im_func", "im_self",
}

# Bare names that expose interpreter internals directly.
BLOCKED_NAMES = {
    "__builtins__", "__loader__", "__spec__", "__package__", "__import__",
}


class PolicyViolation(Exception):
    """Raised when a non-obvious policy failure should abort review.

    ``kind`` is a stable machine-readable code (``syntax_error`` when the code
    cannot even be parsed, ``policy_violation`` otherwise) so the caller can
    record and act on the failure type instead of parsing the message text.
    """

    def __init__(self, message, kind="policy_violation"):
        super().__init__(message)
        self.kind = kind


class _ViolationVisitor(ast.NodeVisitor):
    def __init__(self):
        self.violations = []

    def _add(self, node, message):
        self.violations.append(f"line {getattr(node, 'lineno', '?')}: {message}")

    def _check_module(self, name, node):
        root = name.split(".")[0]
        if not name:
            self._add(node, "empty module name is not allowed")
        elif root in BLOCKED_MODULE_ROOTS or (root.startswith("_") and root != "_"):
            self._add(node, f"importing module '{name}' is not allowed")
        elif root not in ALLOWED_MODULE_ROOTS:
            self._add(node, f"importing module '{name}' is not allowed")

    def visit_Import(self, node):
        for alias in node.names:
            self._check_module(alias.name, node)
        self.generic_visit(node)

    def visit_ImportFrom(self, node):
        if node.level and node.level > 0:
            self._add(node, "relative imports are not allowed")
        else:
            self._check_module(node.module or "", node)
        self.generic_visit(node)

    def visit_Call(self, node):
        func = node.func
        if isinstance(func, ast.Name) and func.id in BLOCKED_CALL_NAMES:
            self._add(node, f"calling '{func.id}()' is not allowed")
        elif isinstance(func, ast.Attribute) and func.attr in BLOCKED_CALL_NAMES:
            self._add(node, f"calling '{func.attr}()' is not allowed")
        self.generic_visit(node)

    def visit_Attribute(self, node):
        if node.attr in BLOCKED_ATTRS:
            self._add(node, f"accessing attribute '{node.attr}' is not allowed")
        self.generic_visit(node)

    def visit_Name(self, node):
        if node.id in BLOCKED_NAMES:
            self._add(node, f"using name '{node.id}' is not allowed")
        self.generic_visit(node)


def validate(code):
    """Return a list of human-readable policy violations (empty when clean).

    Raises :class:`PolicyViolation` when the code cannot even be parsed, so a
    syntax error is reported through the same ``code_exe_error`` path.
    """
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        raise PolicyViolation(
            f"generated code is not valid Python (line {exc.lineno}): {exc.msg}",
            kind="syntax_error",
        ) from exc

    visitor = _ViolationVisitor()
    visitor.visit(tree)
    return visitor.violations
