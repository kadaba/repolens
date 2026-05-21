from pathlib import Path

from app_classifier.codemap.py_calls import build_python_function_graph


def test_function_calls_within_file(tmp_path):
    (tmp_path / "m.py").write_text(
        "def helper():\n    return 1\n\n"
        "def caller():\n    return helper()\n"
    )
    g = build_python_function_graph(tmp_path)
    assert "m.py:helper" in g
    assert "m.py:caller" in g
    assert "m.py:helper" in g["m.py:caller"].calls
    assert "m.py:caller" in g["m.py:helper"].called_by


def test_function_calls_across_files(tmp_path):
    (tmp_path / "a.py").write_text("def helper():\n    return 1\n")
    (tmp_path / "b.py").write_text(
        "from a import helper\n\n"
        "def caller():\n    return helper()\n"
    )
    g = build_python_function_graph(tmp_path)
    assert "a.py:helper" in g["b.py:caller"].calls
    assert "b.py:caller" in g["a.py:helper"].called_by


def test_async_function_def_detected(tmp_path):
    (tmp_path / "m.py").write_text(
        "async def fetch():\n    return await api()\n"
    )
    g = build_python_function_graph(tmp_path)
    assert "m.py:fetch" in g


def test_skips_files_with_syntax_errors(tmp_path):
    (tmp_path / "broken.py").write_text("def x(:\n    pass\n")
    (tmp_path / "ok.py").write_text("def y(): pass\n")
    g = build_python_function_graph(tmp_path)
    assert "ok.py:y" in g
    # broken.py simply contributes no functions; not an exception


def test_attribute_calls_unresolved_are_dropped(tmp_path):
    (tmp_path / "m.py").write_text(
        "import os\n\ndef x():\n    return os.path.join('a', 'b')\n"
    )
    g = build_python_function_graph(tmp_path)
    assert "m.py:x" in g
    # os.path.join is external — must not produce false edges
    assert all(":" in c for c in g["m.py:x"].calls)
    assert "os:join" not in g["m.py:x"].calls
