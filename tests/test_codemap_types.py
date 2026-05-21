import pytest

from app_classifier.codemap.types import CodeMap, FileNode, FunctionNode


def _make_simple_graph():
    # a.py imports b.py imports c.py
    return CodeMap(
        files={
            "a.py": FileNode(path="a.py", language="python",
                             imports=["b.py"], imported_by=[], is_entry_point=True),
            "b.py": FileNode(path="b.py", language="python",
                             imports=["c.py"], imported_by=["a.py"], is_entry_point=False),
            "c.py": FileNode(path="c.py", language="python",
                             imports=[], imported_by=["b.py"], is_entry_point=False),
        },
        functions={},
        entry_points=["a.py"],
    )


def test_impact_of_file_transitive():
    g = _make_simple_graph()
    # If I change c.py, both b.py (direct) and a.py (transitive) are affected.
    assert g.impact_of("c.py", transitive=True) == ["a.py", "b.py"]


def test_impact_of_file_one_hop():
    g = _make_simple_graph()
    assert g.impact_of("c.py", transitive=False) == ["b.py"]


def test_impact_of_returns_empty_for_unknown_target():
    g = _make_simple_graph()
    assert g.impact_of("nonexistent.py") == []


def test_impact_of_handles_cycle():
    """a → b → c → a cycle must not infinite-loop. Visited-set required."""
    cyclic = CodeMap(
        files={
            "a.py": FileNode(path="a.py", language="python",
                             imports=["b.py"], imported_by=["c.py"], is_entry_point=False),
            "b.py": FileNode(path="b.py", language="python",
                             imports=["c.py"], imported_by=["a.py"], is_entry_point=False),
            "c.py": FileNode(path="c.py", language="python",
                             imports=["a.py"], imported_by=["b.py"], is_entry_point=False),
        },
        functions={},
        entry_points=[],
    )
    # Each file is impacted by changing any other in the cycle, target excluded.
    assert sorted(cyclic.impact_of("a.py", transitive=True)) == ["b.py", "c.py"]


def test_impact_of_function_target():
    """`file:function` target walks the call-graph and folds up to file impact."""
    g = CodeMap(
        files={
            "a.py": FileNode(path="a.py", language="python",
                             imports=[], imported_by=[], is_entry_point=True),
            "b.py": FileNode(path="b.py", language="python",
                             imports=[], imported_by=[], is_entry_point=True),
        },
        functions={
            "a.py:helper": FunctionNode(file="a.py", name="helper", line=1,
                                         calls=[], called_by=["b.py:caller"]),
            "b.py:caller": FunctionNode(file="b.py", name="caller", line=1,
                                         calls=["a.py:helper"], called_by=[]),
        },
        entry_points=["a.py", "b.py"],
    )
    # Changing a.py:helper impacts b.py (where caller lives).
    assert g.impact_of("a.py:helper", transitive=True) == ["b.py"]
