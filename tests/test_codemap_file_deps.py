from pathlib import Path

import pytest

from app_classifier.codemap.file_deps import (
    extract_imports, build_file_graph, detect_entry_points,
)

FIX = Path(__file__).parent / "fixtures"


# ── Per-language extraction ──

def test_python_extracts_relative_and_package_imports(tmp_path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "a.py").write_text(
        "from .b import x\nimport os\nfrom pkg.c import y\n"
    )
    (tmp_path / "pkg" / "b.py").write_text("")
    (tmp_path / "pkg" / "c.py").write_text("")
    imports = extract_imports(tmp_path / "pkg" / "a.py", tmp_path)
    assert "pkg/b.py" in imports
    assert "pkg/c.py" in imports
    assert "os" not in imports  # external dropped


def test_js_extracts_relative_imports(tmp_path):
    (tmp_path / "a.js").write_text(
        "import {x} from './b';\nconst y = require('./c.js');\nconst z = await import('./d');"
    )
    (tmp_path / "b.js").write_text("")
    (tmp_path / "c.js").write_text("")
    (tmp_path / "d.js").write_text("")
    imports = extract_imports(tmp_path / "a.js", tmp_path)
    assert "b.js" in imports
    assert "c.js" in imports
    assert "d.js" in imports


def test_go_extracts_module_internal_imports():
    root = FIX / "go_service"
    imports = extract_imports(root / "main.go", root)
    # main.go imports github.com/example/svc/handler — resolved to handler.go
    assert "handler.go" in imports


def test_ruby_extracts_require_relative():
    root = FIX / "ruby_sinatra"
    imports = extract_imports(root / "app.rb", root)
    assert "helpers.rb" in imports
    # `require 'sinatra'` is external — must not appear
    assert "sinatra.rb" not in imports


def test_java_extracts_package_imports():
    root = FIX / "java_spring"
    controller = root / "src/main/java/com/example/Controller.java"
    imports = extract_imports(controller, root)
    # Controller imports com.example.Util — must resolve to Util.java.
    assert any(path.endswith("Util.java") for path in imports)
    # External imports (org.springframework.*) must be dropped — no false positives.
    for path in imports:
        assert "annotation" not in path
        assert "springframework" not in path


def test_php_extracts_require_and_use(tmp_path):
    (tmp_path / "a.php").write_text(
        "<?php\nrequire_once 'b.php';\ninclude 'c.php';\nuse App\\Helpers;\n"
    )
    (tmp_path / "b.php").write_text("<?php ?>")
    (tmp_path / "c.php").write_text("<?php ?>")
    imports = extract_imports(tmp_path / "a.php", tmp_path)
    assert "b.php" in imports
    assert "c.php" in imports


# ── Graph builder ──

def test_build_file_graph_transposes_edges(tmp_path):
    (tmp_path / "a.py").write_text("from b import x")
    (tmp_path / "b.py").write_text("")
    graph = build_file_graph(tmp_path)
    assert graph["a.py"].imports == ["b.py"]
    assert graph["b.py"].imported_by == ["a.py"]
    assert graph["a.py"].imported_by == []


def test_build_file_graph_skips_excluded_dirs(tmp_path):
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "lib.js").write_text("export {}")
    (tmp_path / "app.js").write_text("import x from './node_modules/lib';")
    graph = build_file_graph(tmp_path)
    assert "node_modules/lib.js" not in graph
    assert "app.js" in graph


def test_detect_entry_points_zero_in_degree(tmp_path):
    (tmp_path / "a.py").write_text("from b import x")
    (tmp_path / "b.py").write_text("")
    graph = build_file_graph(tmp_path)
    eps = detect_entry_points(graph, tmp_path)
    assert "a.py" in eps  # 0 importers
    assert "b.py" not in eps


def test_detect_entry_points_framework_markers(tmp_path):
    (tmp_path / "shared.py").write_text("def x(): pass")
    (tmp_path / "main.py").write_text(
        "from shared import x\nif __name__ == '__main__':\n    x()"
    )
    (tmp_path / "imports_main.py").write_text("import main")
    graph = build_file_graph(tmp_path)
    eps = detect_entry_points(graph, tmp_path)
    # main.py is imported, but the if __name__ marker makes it an entry point too
    assert "main.py" in eps
