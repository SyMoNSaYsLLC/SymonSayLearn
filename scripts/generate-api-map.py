#!/usr/bin/env python3
"""generate-api-map.py - ONE document mapping every callable surface in the estate.

Endpoint -> the code at the other end -> one line saying what it is. Nothing else.

The one-liners are NOT written here: they are read from the source's own docstring or
the comment immediately above the declaration. So the map cannot drift from the code,
and regenerating it is a check - if a description is wrong, the fix is in the source.

Covers: HTTP endpoints (register + handlers), the C ABI of libsymoneural-api, the Python
API layer, the unit registry, and the operator tools.

  python3 -B tools/generate-api-map.py [-o docs/api/README.md]
"""
import argparse, ast, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # scripts/x -> repo root
# works before and after the runtimes/ reorganisation
APP = next((p for p in (os.path.join(ROOT, "production/runtimes/api/app"),
                        os.path.join(ROOT, "production/runtimes/api/app")) if os.path.isdir(p)), None)
if APP is None:
    sys.exit("FAIL: cannot find the API app tree")
PKG = os.path.join(APP, "symoneural_api")
INC = os.path.join(APP, "include/symoneural")
rel = lambda p: os.path.relpath(p, ROOT)


def first_line(text):
    """First sentence-ish line of a docstring or comment block, flattened."""
    if not text:
        return ""
    for ln in text.strip().splitlines():
        ln = ln.strip().lstrip("*").strip()
        if ln:
            return re.sub(r"\s+", " ", ln)
    return ""


# ----------------------------------------------------------------- C headers
CDECL = re.compile(r"^\s*((?:const\s+)?[A-Za-z_][A-Za-z0-9_ *]*?)\s+(\**)(sym_[a-z0-9_]+)\s*\(([^;]*)\)\s*;")

def c_decls(path):
    """(signature, name, line, one-liner) for every sym_* prototype in a header."""
    out, pending = [], []
    lines = open(path).read().splitlines()
    i = 0
    while i < len(lines):
        ln = lines[i]
        if "/*" in ln and "*/" not in ln:                       # block comment opens
            buf = [ln.split("/*", 1)[1]]
            while i + 1 < len(lines) and "*/" not in lines[i + 1]:
                i += 1; buf.append(lines[i])
            if i + 1 < len(lines):
                i += 1; buf.append(lines[i].split("*/", 1)[0])
            pending = buf
        elif ln.strip().startswith("/*") and "*/" in ln:        # one-line comment
            pending = [ln.strip()[2:ln.strip().rindex("*/") - len(ln.strip())].strip("* ")]
            pending = [re.sub(r"^/\*|\*/$", "", ln.strip()).strip("* ")]
        else:
            m = CDECL.match(ln)
            if m:
                ret, star, name, args = m.groups()
                sig = "%s%s %s(%s)" % (ret.strip(), (" " + star) if star else "", name,
                                       re.sub(r"\s+", " ", args.strip()))
                out.append((sig, name, i + 1, first_line("\n".join(pending))))
                # NOT cleared: in C one comment conventionally heads a group of
                # related prototypes (sym_api_abi_version / _version_string /
                # _strerror share theirs). Clearing here left the 2nd and 3rd
                # of every group with no description.
            elif not ln.strip():
                pending = []
            elif ln.strip() and not ln.strip().startswith("#"):
                pending = []
        i += 1
    return out


def c_enum(path, enum_name):
    """(member, value, trailing comment) rows of a typedef enum."""
    src = open(path).read()
    m = re.search(r"typedef enum \{(.*?)\}\s*%s\s*;" % enum_name, src, re.S)
    if not m:
        return []
    rows = []
    for ln in m.group(1).splitlines():
        mm = re.match(r"\s*([A-Z_0-9]+)\s*=\s*(-?\d+)\s*,?\s*(?:/\*(.*?)\*/)?", ln)
        if mm:
            rows.append((mm.group(1), mm.group(2), (mm.group(3) or "").strip()))
    return rows


# ----------------------------------------------------------------- Python
def py_api(path):
    """Public module-level functions and classes: (kind, signature, line, one-liner)."""
    tree = ast.parse(open(path).read())
    out = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not node.name.startswith("_"):
            args = ast.unparse(node.args)
            ret = " -> " + ast.unparse(node.returns) if node.returns else ""
            out.append(("def", "%s(%s)%s" % (node.name, args, ret), node.lineno,
                        first_line(ast.get_docstring(node))))
        elif isinstance(node, ast.ClassDef) and not node.name.startswith("_"):
            bases = ", ".join(ast.unparse(b) for b in node.bases)
            out.append(("class", "%s(%s)" % (node.name, bases) if bases else node.name,
                        node.lineno, first_line(ast.get_docstring(node))))
    return out


ROUTE = re.compile(r'^@app\.(get|post|put|patch|delete)\("([^"]+)"\)')

def handlers(main_py):
    """method+path -> (handler signature, line, one-liner) for the routes served today."""
    lines = open(main_py).read().splitlines()
    tree = ast.parse("\n".join(lines))
    byline = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            byline[node.lineno] = node
    out = {}
    for i, ln in enumerate(lines):
        m = ROUTE.match(ln.strip())
        if not m:
            continue
        for j in range(i + 2, i + 7):        # tolerate stacked decorators / blank lines
            if j in byline:
                fn = byline[j]
                args = ", ".join(a.arg for a in fn.args.args)
                ret = " -> " + ast.unparse(fn.returns) if fn.returns else ""
                out["%s %s" % (m.group(1).upper(), m.group(2))] = (
                    "%s(%s)%s" % (fn.name, args, ret), j, first_line(ast.get_docstring(fn)))
                break
    return out


def tool_lines():
    """(name, one-liner) for every executable in tools/."""
    out = []
    for n in sorted(os.listdir(os.path.join(ROOT, "work", "tools"))):
        p = os.path.join(ROOT, "work", "tools", n)
        if not os.path.isfile(p) or not os.access(p, os.X_OK):
            continue
        try:
            head = open(p, errors="replace").read(4000)
        except OSError:
            continue
        d = ""
        if n.endswith(".py"):
            try:
                d = first_line(ast.get_docstring(ast.parse(open(p).read())))
            except Exception:
                d = ""
        if not d:
            for ln in head.splitlines()[1:6]:
                if ln.startswith("#") and len(ln) > 3:
                    d = ln.lstrip("# ").strip(); break
        out.append((n, d))
    return out


# ----------------------------------------------------------------- emit
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-o", "--out", default=os.path.join(ROOT, "docs/api/README.md"))
    a = ap.parse_args()

    sys.path.insert(0, APP)
    from symoneural_api import endpoints as ep, units as un

    ep_src = open(os.path.join(PKG, "endpoints.py")).read().splitlines()
    hnd = handlers(os.path.join(PKG, "main.py"))

    def reg_line(e):
        pat = '"%s"' % e.path
        for i, ln in enumerate(ep_src):
            if pat in ln and '"%s"' % e.method in ln:
                return i + 1
        return 0

    o = []
    w = o.append
    w("# The API map\n")
    w("**Generated** by `tools/generate-api-map.py` from the source. Every entry is a real")
    w("declaration with its file and line; every one-line description is the source's own")
    w("docstring or the comment above it. Do not hand-edit — fix the source and regenerate.\n")
    w("One rule: *nothing is built without an assigned endpoint, and no endpoint is listed")
    w("without a state.* `tools/proofs/api.py` asserts it inside the clean-root image.\n")
    w("---\n")

    # 1. HTTP
    w("## 1. HTTP\n")
    w("`pub` no auth · `client` client key · `op` operator token. "
      "**BUILT** = a handler answers today · **DESIGNED** = registered, no handler.\n")
    order = {ep.Namespace.ROOT: 0, ep.Namespace.DIALECT: 1, ep.Namespace.NATIVE: 2,
             ep.Namespace.RESERVED: 3}
    cls = {"PUBLIC_BOOTSTRAP": "pub", "AUTHENTICATED_APPLICATION": "client",
           "OPERATOR_ONLY": "op", "SHARED_AUTH": "auth", "ENTITLEMENT_REQUIRED": "entitled"}
    for ns in sorted({e.namespace for e in ep.REGISTRY}, key=lambda n: order.get(n, 9)):
        w("### `%s`\n" % ns)
        for e in [x for x in ep.REGISTRY if x.namespace == ns]:
            unit = "gateway" if e.unit == ep.GATEWAY else "`%s`:%d" % (e.unit, un.REGISTRY[e.unit].port)
            head = "**`%s %s`** — %s · %s%s · %s" % (
                e.method, e.path, cls.get(str(e.route_class), str(e.route_class)), unit,
                (" → `%s`" % e.worker) if e.worker else "", e.state)
            w(head + "\n")
            k = "%s %s" % (e.method, e.path)
            if k in hnd:
                sig, line, doc = hnd[k]
                w("```python\n# %s:%d\ndef %s\n```" % (rel(os.path.join(PKG, "main.py")), line, sig))
                w(doc or e.note or "—")
            else:
                ln = reg_line(e)
                w("```python\n# %s:%d\nEndpoint(\"%s\", \"%s\", %s, %s, \"%s\", %s%s)\n```" % (
                    rel(os.path.join(PKG, "endpoints.py")), ln, e.method, e.path,
                    str(e.namespace).replace("/", "").upper() or "ROOT",
                    str(e.route_class), e.unit, e.state,
                    (", worker=\"%s\"" % e.worker) if e.worker else ""))
                w(e.note or "registered, no handler yet")
            w("")
    w("### Units with no route\n")
    for n, why in sorted(ep.UNROUTED.items()):
        w("- **`%s`**:%d — %s" % (n, un.REGISTRY[n].port, why))
    w("")

    # 2. C ABI
    w("## 2. C ABI — `libsymoneural-api`\n")
    for h in ("api.h", "gpulock.h", "rack.h", "unit.h"):
        p = os.path.join(INC, h)
        if not os.path.exists(p):
            continue
        decls = c_decls(p)
        if not decls:
            continue
        w("### `%s`\n" % rel(p))
        for sig, name, line, doc in decls:
            w("```c\n// %s:%d\n%s;\n```" % (rel(p), line, sig))
            w(doc or "—")
            w("")
    rows = c_enum(os.path.join(INC, "api.h"), "sym_api_status")
    if rows:
        w("### Status codes\n")
        w("| Code | Value | Meaning |\n|---|---:|---|")
        for m, v, c in rows:
            w("| `%s` | %s | %s |" % (m, v, c or "—"))
        w("")

    # 3. Python
    w("## 3. Python — `symoneural_api`\n")
    for f in sorted(os.listdir(PKG)):
        if not f.endswith(".py") or f == "__init__.py":
            continue
        p = os.path.join(PKG, f)
        api = py_api(p)
        if not api:
            continue
        w("### `%s`\n" % rel(p))
        mod = first_line(ast.get_docstring(ast.parse(open(p).read())))
        if mod:
            w("*%s*\n" % mod)
        for kind, sig, line, doc in api:
            w("```python\n# %s:%d\n%s %s\n```" % (rel(p), line, kind, sig))
            w(doc or "—")
            w("")

    # 4. Units
    w("## 4. Unit registry\n")
    w("| Unit | Port | Resource | Token env | Backing packages |\n|---|---:|---|---|---|")
    for u in un.REGISTRY.values():
        w("| `%s` | %d | %s | `%s` | %s |" % (u.name, u.port, u.resource, u.token_env,
                                              ", ".join("`%s`" % b for b in u.backed_by)))
    w("")

    # 5. Tools
    w("## 5. Operator tools — `tools/`\n")
    for n, d in tool_lines():
        w("- **`tools/%s`** — %s" % (n, d or "—"))
    w("")

    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    open(a.out, "w").write("\n".join(o) + "\n")
    print("wrote %s (%d lines)" % (a.out, len(o) + 1))
    print("  endpoints %d · C decls %d · python modules %d · units %d · tools %d" % (
        len(ep.REGISTRY),
        sum(len(c_decls(os.path.join(INC, h))) for h in os.listdir(INC) if h.endswith(".h")),
        len([f for f in os.listdir(PKG) if f.endswith('.py') and f != '__init__.py']),
        len(un.REGISTRY), len(tool_lines())))


main()
