"""Tests for the pyproject.toml parser."""

from __future__ import annotations

from pathlib import Path

from packages.sca.models import PinStyle
from packages.sca.parsers.pyproject import parse


def _write(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "pyproject.toml"
    p.write_text(body, encoding="utf-8")
    return p


def test_pep621_dependencies(tmp_path: Path) -> None:
    body = """\
[project]
name = "demo"
version = "0.1.0"
dependencies = [
    "django==4.2.7",
    "requests~=2.31",
    "click",
]

[project.optional-dependencies]
dev = ["pytest>=7"]
"""
    deps = {(d.name, d.scope): d for d in parse(_write(tmp_path, body))}
    assert deps[("django", "main")].pin_style is PinStyle.EXACT
    assert deps[("requests", "main")].pin_style is PinStyle.TILDE
    assert deps[("click", "main")].pin_style is PinStyle.WILDCARD
    assert deps[("pytest", "optional")].pin_style is PinStyle.RANGE


def test_poetry_string_and_dict_specs(tmp_path: Path) -> None:
    body = """\
[tool.poetry.dependencies]
python = "^3.10"
django = "^4.2"
requests = { version = ">=2.31,<3", optional = true }
internal = { path = "../internal" }
fork = { git = "https://github.com/u/r.git", tag = "v1.0" }

[tool.poetry.dev-dependencies]
pytest = "~7.4.0"

[tool.poetry.group.docs.dependencies]
sphinx = "*"
"""
    by_name = {d.name: d for d in parse(_write(tmp_path, body))}
    assert "python" not in by_name  # Poetry's project-python constraint
    assert by_name["django"].pin_style is PinStyle.CARET
    assert by_name["django"].version == "4.2"
    assert by_name["requests"].pin_style is PinStyle.RANGE
    assert by_name["internal"].pin_style is PinStyle.PATH
    assert by_name["fork"].pin_style is PinStyle.GIT
    assert by_name["fork"].version == "v1.0"
    assert by_name["pytest"].scope == "dev"
    assert by_name["pytest"].pin_style is PinStyle.TILDE
    assert by_name["sphinx"].scope == "dev"
    assert by_name["sphinx"].pin_style is PinStyle.WILDCARD


def test_pdm_dev_dependencies(tmp_path: Path) -> None:
    body = """\
[tool.pdm.dev-dependencies]
test = ["pytest>=7", "pytest-cov"]
lint = ["ruff>=0.1"]
"""
    deps = parse(_write(tmp_path, body))
    by_name = {d.name: d for d in deps}
    assert by_name["pytest"].scope == "dev"
    assert by_name["ruff"].scope == "dev"


def test_pep735_dependency_groups(tmp_path: Path) -> None:
    body = """\
[dependency-groups]
lint = ["ruff==0.15.12"]
test = ["pytest==9.1.1", "pytest-cov>=7"]
docs = ["sphinx~=7.0"]
"""
    by_name = {d.name: d for d in parse(_write(tmp_path, body))}
    assert by_name["ruff"].scope == "dev"
    assert by_name["ruff"].pin_style is PinStyle.EXACT
    # ``test``/``tests`` map to the test scope, not blanket-dev — hygiene
    # buckets cross-manifest comparisons by scope.
    assert by_name["pytest"].scope == "test"
    assert by_name["pytest-cov"].scope == "test"
    assert by_name["sphinx"].scope == "dev"
    assert by_name["sphinx"].pin_style is PinStyle.TILDE


def test_pep735_group_name_scope_mapping(tmp_path: Path) -> None:
    body = """\
[dependency-groups]
main = ["requests==2.34.2"]
runtime = ["urllib3==2.7.0"]
tests = ["pytest==9.1.1"]
whatever = ["mypy==2.1.0"]
"""
    by_name = {d.name: d for d in parse(_write(tmp_path, body))}
    assert by_name["requests"].scope == "main"
    assert by_name["urllib3"].scope == "main"
    assert by_name["pytest"].scope == "test"
    assert by_name["mypy"].scope == "dev"


def test_pep735_include_group_is_skipped(tmp_path: Path) -> None:
    # ``{include-group = "..."}`` is a group reference, not a dep. It must
    # not become a Dependency row; the referenced group is parsed on its
    # own key.
    body = """\
[dependency-groups]
lint = ["ruff==0.15.12"]
dev = [{include-group = "lint"}, "mypy==2.1.0"]
"""
    deps = parse(_write(tmp_path, body))
    names = sorted(d.name for d in deps)
    assert names == ["mypy", "ruff"]


def test_pep735_malformed_group_value_is_skipped(tmp_path: Path) -> None:
    # A group whose value isn't a list (operator typo) must not abort the
    # parse — the well-formed sibling group still yields rows.
    body = """\
[dependency-groups]
broken = "ruff==0.15.12"
lint = ["mypy==2.1.0"]
"""
    by_name = {d.name: d for d in parse(_write(tmp_path, body))}
    assert "ruff" not in by_name
    assert by_name["mypy"].scope == "dev"


def test_tool_uv_dev_dependencies(tmp_path: Path) -> None:
    body = """\
[tool.uv]
dev-dependencies = ["ruff==0.15.12", "mypy==2.1.0"]
"""
    by_name = {d.name: d for d in parse(_write(tmp_path, body))}
    assert by_name["ruff"].scope == "dev"
    assert by_name["mypy"].scope == "dev"


def test_tool_uv_resolver_steering_tables_are_not_deps(tmp_path: Path) -> None:
    # constraint-/override-dependencies steer resolution; nothing installs
    # them. Emitting them would inflate the dep surface with phantom rows.
    body = """\
[tool.uv]
dev-dependencies = ["ruff==0.15.12"]
constraint-dependencies = ["urllib3<3"]
override-dependencies = ["werkzeug==2.3.0"]
"""
    names = sorted(d.name for d in parse(_write(tmp_path, body)))
    assert names == ["ruff"]


def test_raptor_own_manifest_shape(tmp_path: Path) -> None:
    """Lock the shape of RAPTOR's own pyproject.toml.

    RAPTOR scans itself weekly (.github/workflows/sca-self-bump.yml). If
    this parser stops seeing any of these tables, the self-scan goes blind
    on that surface and the bump silently stops proposing fixes for it —
    a failure that exits 0. Keep this test in lockstep with the real
    manifest.
    """
    body = """\
[project]
name = "raptor"
requires-python = ">=3.10"
dependencies = [
    "requests==2.34.2",
    "tomli==2.3.0 ; python_version < '3.11'",
]

[project.optional-dependencies]
web = ["beautifulsoup4==4.15.0"]
smt = ["z3-solver==4.15.4.0"]

[dependency-groups]
lint = ["ruff==0.15.12"]
types = ["mypy==2.1.0"]
test = ["pytest==9.1.1"]
dev = [
    {include-group = "lint"},
    {include-group = "types"},
    {include-group = "test"},
]

[tool.uv]
package = false
"""
    deps = parse(_write(tmp_path, body))
    by_name = {d.name: d for d in deps}

    # Runtime pins stay `main` + EXACT — the "no loose deps" policy is
    # what harden re-asserts on every weekly bump.
    assert by_name["requests"].scope == "main"
    assert by_name["requests"].pin_style is PinStyle.EXACT
    # Marker-guarded runtime dep is still a main-scope exact pin.
    assert by_name["tomli"].scope == "main"
    assert by_name["tomli"].pin_style is PinStyle.EXACT

    # Extras land in `optional`, groups in dev/test.
    assert by_name["beautifulsoup4"].scope == "optional"
    assert by_name["z3-solver"].scope == "optional"
    assert by_name["ruff"].scope == "dev"
    assert by_name["mypy"].scope == "dev"
    assert by_name["pytest"].scope == "test"

    # Every declared dep is visible, and the include-group refs and
    # `[tool.uv]` config keys produced no phantom rows.
    assert sorted(by_name) == [
        "beautifulsoup4", "mypy", "pytest", "requests", "ruff",
        "tomli", "z3-solver",
    ]
    assert all(d.pin_style is PinStyle.EXACT for d in deps)


def test_build_system_requires(tmp_path: Path) -> None:
    body = """\
[build-system]
requires = ["setuptools>=61", "wheel"]
build-backend = "setuptools.build_meta"
"""
    deps = parse(_write(tmp_path, body))
    by_name = {d.name: d for d in deps}
    assert by_name["setuptools"].scope == "build"
    assert by_name["setuptools"].pin_style is PinStyle.RANGE
    assert by_name["wheel"].scope == "build"


def test_combined_pep621_plus_poetry_block(tmp_path: Path) -> None:
    # A real-world hybrid: PEP 621 [project] + Poetry tool table.
    body = """\
[project]
name = "demo"
dependencies = ["django==4.2.7"]

[tool.poetry.dependencies]
requests = "^2.31"
"""
    deps = parse(_write(tmp_path, body))
    by_name = {d.name: d for d in deps}
    assert by_name["django"].pin_style is PinStyle.EXACT
    assert by_name["requests"].pin_style is PinStyle.CARET


def test_poetry_multi_constraint_list(tmp_path: Path) -> None:
    body = """\
[tool.poetry.dependencies]
foo = [
    { version = "^1.0", python = ">=3.10" },
    { version = "^0.9", python = "<3.10" },
]
"""
    deps = parse(_write(tmp_path, body))
    assert len(deps) == 1
    d = deps[0]
    assert d.name == "foo"
    assert d.pin_style is PinStyle.CARET
    assert d.parser_confidence.level == "medium"


def test_pep503_normalisation(tmp_path: Path) -> None:
    body = """\
[project]
dependencies = ["Foo_Bar.Baz==1.0"]
"""
    deps = parse(_write(tmp_path, body))
    assert deps[0].name == "foo-bar-baz"
    assert deps[0].purl == "pkg:pypi/foo-bar-baz@1.0"


def test_malformed_toml_returns_empty(tmp_path: Path) -> None:
    p = tmp_path / "pyproject.toml"
    p.write_text("[project\nname = bad", encoding="utf-8")
    assert parse(p) == []


def test_empty_pyproject_returns_empty(tmp_path: Path) -> None:
    p = tmp_path / "pyproject.toml"
    p.write_text("", encoding="utf-8")
    assert parse(p) == []
