"""Kiem chung MAY cho viec tach chat/session.py thanh package.

Test thong thuong khong bat duoc loi cat file: mot ten quen import chi no khi
chay dung nhanh do, va mot ham bi sot chi lo khi co ai goi. Hai check duoi lam
viec ma so test pass khong lam duoc.

Check 1 (unbound name) da bat duoc `time` thieu trong memory.py ngay lan tach
dau -- truoc do 506/508 test van xanh.
"""
from __future__ import annotations

import ast
import builtins
import importlib
import pathlib

import pytest

PKG = pathlib.Path(__file__).resolve().parents[1] / "src" / "acne_llm" / "chat" / "session"
MODULES = sorted(p.name for p in PKG.glob("*.py"))


def _unbound_names(path: pathlib.Path) -> list[str]:
    """Ten duoc DOC trong module nhung khong he duoc bind o do."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    bound: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                bound.add((alias.asname or alias.name).split(".")[0])
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            bound.add(node.name)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            bound.add(node.id)
        elif isinstance(node, ast.arg):
            bound.add(node.arg)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            bound.add(node.name)
    used = {
        n.id for n in ast.walk(tree)
        if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)
    }
    return sorted(used - bound - set(dir(builtins)))


@pytest.mark.parametrize("module_name", MODULES)
def test_khong_ten_nao_bi_quen_import(module_name: str):
    missing = _unbound_names(PKG / module_name)
    assert not missing, f"{module_name} doc ten chua bind: {missing}"


def test_moi_ten_trong_all_deu_import_duoc_tu_goc_cu():
    """13+ cho dang `from .session import X`. __all__ la hop dong voi chung."""
    session = importlib.import_module("acne_llm.chat.session")
    missing = [name for name in session.__all__ if not hasattr(session, name)]
    assert not missing, f"__all__ hua nhung khong co: {missing}"


def test_moi_submodule_import_doc_lap_duoc():
    """Bat import vong: neu models <-> memory vong nhau thi cho nay no."""
    for module_name in MODULES:
        if module_name == "__init__.py":
            continue
        importlib.import_module(f"acne_llm.chat.session.{module_name[:-3]}")


def test_production_session_package_does_not_export_in_memory_store():
    session = importlib.import_module("acne_llm.chat.session")

    assert not hasattr(session, "SessionStore")
    assert not hasattr(session, "get_session_store")
    assert importlib.util.find_spec("acne_llm.chat.session.memory") is None


def test_test_helper_returns_independent_stores():
    from tests.helpers import get_session_store

    assert get_session_store() is not get_session_store()
