"""check_ui.py: find import and call mismatches between app.py and the ui/ modules.
Run from the project root:   python check_ui.py
"""
import ast
import importlib
import inspect
import logging
import pathlib
import sys
import warnings

sys.path.insert(0, ".")
logging.disable(logging.CRITICAL)
warnings.filterwarnings("ignore")

files = [pathlib.Path("app.py")] + sorted(pathlib.Path("ui").glob("*.py"))
problems, modules = [], {}


def load(name):
    if name not in modules:
        try:
            modules[name] = importlib.import_module(name)
        except Exception as e:
            modules[name] = None
            problems.append(f"cannot import module {name}: {type(e).__name__}: {e}")
    return modules[name]


for path in files:
    if not path.exists():
        problems.append(f"{path} is missing")
        continue
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    local = {}                                         # local name -> imported object

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.module.split(".")[0] == "ui":
            mod = load(node.module)
            if mod is None:
                continue
            for alias in node.names:
                if alias.name == "*":
                    continue
                if not hasattr(mod, alias.name):
                    problems.append(f"{path}:{node.lineno}: '{alias.name}' does not exist in {node.module}")
                else:
                    local[alias.asname or alias.name] = getattr(mod, alias.name)

    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in local:
            obj = local[node.func.id]
            if not callable(obj):
                continue
            if any(isinstance(a, ast.Starred) for a in node.args) or any(k.arg is None for k in node.keywords):
                continue
            try:
                sig = inspect.signature(obj)
            except (TypeError, ValueError):
                continue
            try:
                sig.bind(*[None] * len(node.args), **{k.arg: None for k in node.keywords})
            except TypeError as e:
                problems.append(f"{path}:{node.lineno}: {node.func.id}(...) does not match its definition: {e}")

# one known trap: the old landing page unpacks a pair from render_search(), the new one returns a bool
landing = pathlib.Path("ui/landing.py")
if landing.exists() and "render_search" in landing.read_text(encoding="utf-8"):
    problems.append("ui/landing.py still uses render_search: it is the OLD landing file. "
                    "Replace it with the new version (search now lives in app.py).")

if problems:
    print(f"\n{len(problems)} problem(s) found:\n")
    for p in problems:
        print("  -", p)
    sys.exit(1)
print(f"\nOK: {len(files)} files checked, every import and call matches.")