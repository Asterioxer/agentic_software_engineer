from __future__ import annotations

from pathlib import Path

from app.codegraph import CodeGraph


def test_codegraph_python_indexing(tmp_path: Path) -> None:
    # Setup simulated modular codebase
    auth_py = tmp_path / "auth.py"
    auth_py.write_text(
        "class AuthManager:\n"
        "    def login(self, user: str) -> bool:\n"
        "        return True\n"
        "\n"
        "def verify_token(token: str) -> bool:\n"
        "    return bool(token)\n",
        encoding="utf-8",
    )

    api_py = tmp_path / "api.py"
    api_py.write_text(
        "from auth import AuthManager, verify_token\n"
        "\n"
        "def handle_request():\n"
        "    mgr = AuthManager()\n"
        "    return mgr.login('admin')\n",
        encoding="utf-8",
    )

    test_py = tmp_path / "test_api.py"
    test_py.write_text(
        "import api\n\ndef test_handle():\n    assert api.handle_request()\n",
        encoding="utf-8",
    )

    graph = CodeGraph(tmp_path).build()
    summary = graph.summary()
    assert summary["files_indexed"] == 3
    assert summary["definitions_count"] >= 4

    # Test symbol finding
    syms = graph.find_symbol("verify_token")
    assert len(syms) == 1
    assert syms[0]["file_path"] == "auth.py"
    assert syms[0]["kind"] == "function"

    # Test blast radius on auth.py:
    # api.py depends on auth.py, test_api.py depends on api.py
    radius = graph.get_blast_radius("auth.py")
    assert "api.py" in radius.direct_dependents
    assert "test_api.py" in radius.transitive_dependents
    assert "test_api.py" in radius.affected_tests
    assert radius.total_impacted_files >= 2
    assert radius.impact_level in ("MEDIUM", "HIGH")


def test_codegraph_js_ts_indexing(tmp_path: Path) -> None:
    lib_ts = tmp_path / "logger.ts"
    lib_ts.write_text(
        "export function logMessage(msg: string): void {\n  console.log(msg);\n}\n",
        encoding="utf-8",
    )

    app_tsx = tmp_path / "app.tsx"
    app_tsx.write_text(
        "import { logMessage } from './logger';\n"
        "\n"
        "export const App = () => {\n"
        "  logMessage('running');\n"
        "  return null;\n"
        "};\n",
        encoding="utf-8",
    )

    graph = CodeGraph(tmp_path).build()
    syms = graph.find_symbol("logMessage")
    assert len(syms) == 1
    assert syms[0]["file_path"] == "logger.ts"

    radius = graph.get_blast_radius("logger.ts")
    assert "app.tsx" in radius.direct_dependents


def test_codegraph_isolated_file(tmp_path: Path) -> None:
    solo = tmp_path / "standalone.py"
    solo.write_text("x = 1\n", encoding="utf-8")

    graph = CodeGraph(tmp_path).build()
    radius = graph.get_blast_radius("standalone.py")
    assert radius.direct_dependents == []
    assert radius.transitive_dependents == []
    assert radius.affected_tests == []
    assert radius.impact_level == "LOW"
