"""`admin/openapi_export.py`(型生成の入力の書き出し。A 5.4・AAM-P-16・AAM-U-7)。

外部に接続しないこと(ネットワークを禁止した上で成功する・環境変数の設定がなくても動く)、
出力が安定していること(2 回の出力が一致)、書き出しは `OPENAPI_ENABLED` と関係なくできること。
"""

import copy
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from loreley_api.admin import create_admin_app
from loreley_api.admin.openapi_export import (
    _Unconnected,
    build_openapi_schema,
    main,
    render_openapi_json,
)
from tests.admin.factories import make_admin_dependencies
from tests.fakes.clock import FixedClock
from tests.fakes.in_memory_readers import InMemoryReaders
from tests.fakes.inline_runner import InlineRunner
from tests.openapi_structure import iter_operations, structure_problems

SOURCE_DIRECTORY = Path(__file__).resolve().parents[2] / "src"


def test_it_writes_a_valid_openapi_json_without_any_network_access(
    tmp_path: Path, forbid_network_connections: None
) -> None:
    output_path = tmp_path / "openapi.json"

    main([str(output_path)])

    written = json.loads(output_path.read_text(encoding="utf-8"))
    assert written["openapi"].startswith("3.")
    assert structure_problems(written) == []
    assert len(list(iter_operations(written))) == 14  # EP-01〜14


def test_two_exports_are_identical_and_the_format_is_stable(tmp_path: Path) -> None:
    first, second = tmp_path / "first.json", tmp_path / "second.json"

    main([str(first)])
    main([str(second)])

    text = first.read_text(encoding="utf-8")
    assert text == second.read_text(encoding="utf-8")
    assert text.endswith("}\n")
    assert text.startswith('{\n  "components"')  # キーを並べ替え、インデントは 2
    parsed = json.loads(text)
    assert text == json.dumps(parsed, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def test_the_export_matches_the_openapi_of_an_app_built_with_fakes() -> None:
    """書き出しの依存(どこにもつながらない代役)は、OpenAPI の内容を変えない。"""
    deps = make_admin_dependencies(InMemoryReaders(), FixedClock(), InlineRunner())
    with_fakes = create_admin_app(deps).openapi()

    assert build_openapi_schema() == with_fakes


def test_the_unconnected_stand_in_fails_if_anything_uses_it() -> None:
    """代役が使われたら(OpenAPI の生成がサービスを呼んだら)、黙って通らず失敗する。"""
    with pytest.raises(RuntimeError, match="does not connect anywhere"):
        _Unconnected().list_sources()


def test_the_unconnected_stand_in_hides_dunder_attributes_but_fails_on_the_others() -> None:
    """ダンダー名の探索(`copy` など)は `AttributeError`(存在しない)で返し、それ以外は失敗する。"""
    unconnected = _Unconnected()

    assert not hasattr(unconnected, "__deepcopy__")
    assert copy.copy(unconnected) is not None  # `__copy__` の探索で `RuntimeError` にならない
    with pytest.raises(RuntimeError, match="does not connect anywhere"):
        unconnected.name  # noqa: B018


def test_the_export_does_not_depend_on_the_openapi_enabled_setting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """公開の既定が無効でも、有効でも、書き出しは同じ(AAM-P-16)。"""
    disabled = render_openapi_json()
    monkeypatch.setenv("LORELEY_API_OPENAPI_ENABLED", "true")

    assert render_openapi_json() == disabled


def run_export_in_a_clean_process(output_path: Path) -> subprocess.CompletedProcess[str]:
    """設定の環境変数を 1 つも渡さない別プロセスで、`python -m` の入口を実行する。"""
    environment = {
        name: value
        for name, value in os.environ.items()
        if not name.startswith(("LORELEY_", "OPENSEARCH_", "CRAWLER_", "INDEXER_"))
    }
    environment["PYTHONPATH"] = str(SOURCE_DIRECTORY)
    return subprocess.run(
        [sys.executable, "-m", "loreley_api.admin.openapi_export", str(output_path)],
        env=environment,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


def test_the_module_entry_point_needs_no_required_settings(tmp_path: Path) -> None:
    """`python -m loreley_api.admin.openapi_export <出力パス>`。必須の環境変数がなくても動く。"""
    output_path = tmp_path / "openapi.json"

    completed = run_export_in_a_clean_process(output_path)

    assert completed.returncode == 0, completed.stderr
    assert json.loads(output_path.read_text(encoding="utf-8")) == build_openapi_schema()
    assert completed.stdout == ""


def test_the_entry_point_requires_the_output_path_argument() -> None:
    with pytest.raises(SystemExit) as exit_info:
        main([])

    assert exit_info.value.code == 2


def test_the_export_writes_nothing_but_the_given_file(tmp_path: Path) -> None:
    output_path = tmp_path / "openapi.json"

    main([str(output_path)])

    assert [path.name for path in tmp_path.iterdir()] == ["openapi.json"]


def test_the_exported_json_has_the_request_bodies_and_the_common_error_schema(
    tmp_path: Path,
) -> None:
    """型生成の入力として、`requestBody` と 400 の共通スキーマが JSON に出ている。"""
    output_path = tmp_path / "openapi.json"
    main([str(output_path)])
    written: dict[str, Any] = json.loads(output_path.read_text(encoding="utf-8"))

    register = written["paths"]["/sources"]["post"]
    assert register["requestBody"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/RegisterSourceBody"
    }
    assert "422" not in register["responses"]
    assert "ErrorResponse" in written["components"]["schemas"]
