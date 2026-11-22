# 0016 tests 配下をモジュール別に整理

## きっかけ(ユーザーの追加指示)

「tests 配下に Indexer 用のテストが直下に置かれていて、後から別モジュールを追加するとごちゃごちゃになりそう。tests 配下を整理してほしい」。軽微な追加指示としてプランは作り直さず対応した(task-workflow「途中の追加指示」)。

## 実施内容

`tests/integration/` 直下にあった Indexer 用の資材をすべて `tests/integration/indexer/` へ移した(`git mv`。履歴は rename として残る)。

- 移動: `conftest.py` / `support.py` / `test_*.py`(6 ファイル)/ `samples/` / `compose.test.yaml` / `pyproject.toml` / `uv.lock` / `README.md` / `results/`(gitignore 済みのログ)
- 削除して再作成: `.venv` `.pytest_cache`(venv は移動できないため。`uv run` が再作成した)
- 以後、別モジュールは `tests/integration/{モジュール名}/` に同じ形(自己完結した uv プロジェクト)で追加する。`tests/e2e/` は要件定義の構成案どおり別に置く

### パスの更新(`tests/integration` → `tests/integration/indexer`)

- `scripts/run-indexer-integration-test.sh`(`uv run --project`、pytest の対象、compose ファイル、results ディレクトリ、コメント)
- `tests/integration/indexer/` 内: `README.md`(`../../docs` → `../../../docs` のリンク補正を含む)、`conftest.py`(STACK_HINT)、`compose.test.yaml`(コメント)、`samples/README.md`
- `deploy/compose/README.md`、`apps/indexer/README.md`、`docs/v0.x/test-results/indexer-integration.md`
- `.gitignore`: `tests/integration/*/.venv/` などモジュールに依らないパターンに変更

### 変更していないもの

- 過去の作業記録(0001〜0015)と STATUS.md 内の旧パスの記述: 作業記録は書き換えない決まりのため、当時のパスのまま
- テストコード・compose・Indexer の中身(パス文字列以外)。`support.py` は `Path(__file__).parent / "samples"` のため修正不要

## 検証

- `scripts/run-indexer-integration-test.sh` を移動後に実行: **40 passed in 13.33s、終了コード 0**、`loreley-it` のコンテナ・ボリューム・ネットワークの残りなし(ログ `tests/integration/indexer/results/pytest-20261113-035742.log`)
- `ruff check tests/integration/indexer`: All checks passed
- `bash -n` でスクリプトの構文確認。`uv.lock` に差分なし
- `.gitignore` が `tests/integration/indexer/results/` を無視することを `git check-ignore` で確認

## 注意・未対応

- `docs/v0.x/test-results/indexer-integration.md` の過去の実行(④⑤など)の記述は、パス表記だけ新しい場所に更新されている(実行時は旧パス)。内容・結果は同じ
- 未コミット(コミットの指示なし)。移動は `git mv` 済みでステージされている
- 未解決事項・ユーザー判断待ちは 0015 から変わらない
