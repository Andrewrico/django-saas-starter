import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "rename_project.py"
spec = importlib.util.spec_from_file_location("rename_project", SCRIPT)
rename = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rename)


@pytest.fixture
def tree(tmp_path):
    (tmp_path / "README.md").write_text("# Django SaaS Starter\nrepo: django-saas-starter\n")
    (tmp_path / "LICENSE").write_text("Django SaaS Starter license text")
    (tmp_path / "CHANGELOG.md").write_text("django-saas-starter history")
    (tmp_path / ".venv").mkdir()
    (tmp_path / ".venv" / "x.txt").write_text("django-saas-starter")
    (tmp_path / "logo.bin").write_bytes(b"\xff\xfe\x00django-saas-starter")
    (tmp_path / "unrelated.txt").write_text("nothing here")
    return tmp_path


def test_dry_run_changes_nothing(tree, capsys):
    assert rename.main(["Acme Cloud", "--root", str(tree)]) == 0
    assert "Dry run: 1 file(s)" in capsys.readouterr().out
    assert "Django SaaS Starter" in (tree / "README.md").read_text()


def test_apply_rewrites_only_safe_files(tree):
    assert rename.main(["Acme Cloud", "--apply", "--root", str(tree)]) == 0
    assert (tree / "README.md").read_text() == "# Acme Cloud\nrepo: acme-cloud\n"
    assert "Django SaaS Starter" in (tree / "LICENSE").read_text()
    assert "django-saas-starter" in (tree / "CHANGELOG.md").read_text()
    assert "django-saas-starter" in (tree / ".venv" / "x.txt").read_text()
    assert b"django-saas-starter" in (tree / "logo.bin").read_bytes()


@pytest.mark.parametrize("args", [["!!!"], ["Django SaaS Starter"], ["Ok", "--slug", "Bad Slug"], [" "]])
def test_rejects_invalid_names(tree, args, capsys):
    assert rename.main([*args, "--root", str(tree)]) == 2
    assert "error" in capsys.readouterr().err


def test_slugify():
    assert rename.slugify("  Acme  Cloud! ") == "acme-cloud"
