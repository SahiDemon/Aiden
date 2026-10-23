"""Relocated packaging definitions must work outside the repository cwd."""

from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace

import pytest


@pytest.mark.parametrize("filename", ["Aiden.spec", "AidenConsole.spec"])
def test_packaging_resolves_sources_and_assets_from_its_location(monkeypatch, tmp_path, filename):
    root = Path(__file__).resolve().parents[1]
    spec = root / "packaging" / filename
    hooks = ModuleType("PyInstaller.utils.hooks")
    hooks.collect_data_files = lambda _name: []
    hooks.collect_dynamic_libs = lambda _name: []
    monkeypatch.setitem(sys.modules, "PyInstaller.utils.hooks", hooks)
    recorded = {}
    bundle = SimpleNamespace(pure=[], scripts=[], binaries=[], datas=[])

    def analysis(sources, **kwargs):
        recorded["sources"] = sources
        recorded["analysis"] = kwargs
        return bundle

    def executable(*_args, **kwargs):
        recorded["executable"] = kwargs
        return bundle

    monkeypatch.chdir(tmp_path)
    namespace = {"SPECPATH": str(spec.parent), "Analysis": analysis,
                 "PYZ": lambda *_args: bundle, "EXE": executable, "COLLECT": lambda *_args, **_kwargs: bundle}
    exec(compile(spec.read_text(encoding="utf-8"), str(spec), "exec"), namespace)

    assert recorded["sources"] == [str(root / "src" / "main.py")]
    assert recorded["analysis"]["pathex"] == [str(root)]
    for source, destination in recorded["analysis"]["datas"]:
        assert Path(source).is_absolute()
        assert Path(source).is_relative_to(root)
        assert destination in {"config", "dashboard/build", "sounds", "vosk_models", "tools"}
    assert recorded["executable"]["icon"] == [str(root / "overlay" / "public" / "icon.ico")]
