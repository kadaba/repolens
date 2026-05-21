# Code Mapping for Impact Analysis

`map_code()` builds a static dependency graph of your repository for impact analysis — no LLM required.

## What it gives you

```python
from app_classifier import map_code
cm = map_code("./my-repo")

# Files indexed by repo-relative path
print(cm.files["src/auth.py"])
# FileNode(path='src/auth.py', language='python',
#          imports=['src/db.py'], imported_by=['src/api.py', 'src/admin.py'],
#          is_entry_point=False)

# Python-only function graph (best-effort)
print(cm.functions["src/auth.py:verify_token"])
# FunctionNode(file='src/auth.py', name='verify_token', line=42,
#              calls=['src/db.py:get_user'], called_by=['src/api.py:require_auth'])

# Detected entry points (zero-importer files + framework markers)
print(cm.entry_points)
# ['manage.py', 'src/api.py', 'tests/test_auth.py']
```

## Impact analysis

### File-level

```python
# "If I change src/db.py, what files are affected?"
cm.impact_of("src/db.py", transitive=True)
# ['src/admin.py', 'src/api.py', 'src/auth.py']

# One-hop only
cm.impact_of("src/db.py", transitive=False)
# ['src/auth.py']
```

### Function-level (Python only)

```python
# "If I change verify_token, which files break?"
cm.impact_of("src/auth.py:verify_token")
# ['src/api.py']
```

## Coverage

| Language | File deps | Function calls |
|---|---|---|
| Python | ✅ | ✅ (stdlib `ast`) |
| JS / TS | ✅ | ❌ (v0.6.0+) |
| Java | ✅ (Maven layout) | ❌ |
| Go | ✅ (module-aware) | ❌ |
| Ruby | ✅ (`require_relative`) | ❌ |
| PHP | ✅ (`require`/`include`) | ❌ |

External imports (e.g., `import requests`) are recognized and dropped — they don't pollute the intra-repo graph.

## Entry-point detection

A file is flagged as an entry point if:

1. **Nothing imports it** (zero in-degree), **OR**
2. **It has a framework marker**:
   - `if __name__ == "__main__":` (Python)
   - `@app.route`, `@router.get`, `@blueprint.route` (Flask / FastAPI)
   - `@RequestMapping`, `@GetMapping`, `@PostMapping` (Spring)
   - `app.get(...)`, `router.get(...)` (Express)
   - `func main()` (Go)
   - `extends HttpServlet` (Java servlets)

## Recipes

### Pre-merge review: "what does this PR break?"

```python
import subprocess
from app_classifier import map_code

cm = map_code(".")
changed_files = subprocess.check_output(
    ["git", "diff", "--name-only", "main...HEAD"]
).decode().splitlines()

impacted = set()
for f in changed_files:
    impacted.update(cm.impact_of(f))
print(f"Changed: {len(changed_files)} files. Impacts: {len(impacted)} more.")
```

### Refactor safety: "who calls this function?"

```python
cm = map_code(".")
callers = cm.functions["src/db.py:get_user"].called_by
print("Callers of get_user:", callers)
```

### Dead-code detection: "what's never imported AND not an entry point?"

```python
cm = map_code(".")
dead = [
    rel for rel, node in cm.files.items()
    if not node.imported_by and not node.is_entry_point
]
print("Possibly dead:", dead)
```

## Limits

- Regex-based — won't catch dynamic imports (`importlib.import_module(name)`)
- Cross-file Python function resolution requires direct-name imports (`from m import f`); module-attribute calls (`m.f()`) need both the module to resolve and the function to exist in the target
- Cycles handled via a visited-set, but very large graphs (>50k files) may slow down — soft-cap planned for v0.6.0
- Java function-call graph deferred to v0.6.0 (needs tree-sitter or `javac`-driven analysis)
