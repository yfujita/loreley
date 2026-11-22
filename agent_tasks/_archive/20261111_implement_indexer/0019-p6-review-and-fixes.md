# 0019 P6 レビューと指摘対応(最終検証を含む)

日付: 2026-11-12 / 対象: 0018(P6)/ レビュー: code-reviewer(Dockerfile)、document-reviewer(README)/ 修正: code-implementer(2回)
比較基準: HEAD c065b9e(`apps/indexer` は未コミットの新規ファイル全体)

## 経緯

0018 の後、(1) メインが `docker build` を実施して成功を確認する際に **R9 違反(起動時の設定エラーで秘密値が標準エラー出力へ出る)** を実機で発見し、(2) code-reviewer(Dockerfile)と document-reviewer(README)のレビューが並行して返った。いずれも指摘を修正した。

## 1. 起動時の設定読み込みエラーによる秘密値の漏洩(R9。メインが発見)

- 症状: `LORELEY_INDEXER_OPENSEARCH_URL` を省略し `LORELEY_INDEXER_OPENSEARCH_PASSWORD=SENTINEL-SECRET-PW` を設定してコンテナを起動すると、pydantic の `ValidationError` が標準エラー出力に `input_value={'http_host': '0.0.0.0', ...': 'SENTINEL-SECRET-PW'}` としてパスワードを出す(`SecretStr` は検証エラーが入力の生の辞書を出すため効かない)。P5 までのテストは起動時の設定読み込みエラー経路を見ていなかった(fake・スタブのみ)
- 修正(code-implementer): `main.py` に `load_settings()` と `describe_settings_errors()` を追加し、`ValidationError` を固定形式の `StartupError` に変換する。メッセージは `invalid settings: <loc>: <type>; ...`(例: `invalid settings: opensearch_url: missing`)で、`errors(include_url=False, include_context=False, include_input=False)` の `loc` と `type` だけを使い、`input`・`ctx`・`msg` は出さない。10件を超えた分は `... and N more`。`raise StartupError` は `except` ブロックの外で行い、入力値を持つ元の例外が `__context__` に残らないようにした(`from None` では `__context__` が残るため)。`config.py` の整合検証4件は `ValueError` から `PydanticCustomError`(検証名付き: `rescan_max_interval_below_min`・`raw_bytes_above_batch_bytes`・`batch_bytes_above_request_body_bytes`・`poll_backoff_max_below_interval`)に変更(文面は従来のまま)。`api/schemas.py` の docstring の `\ud800` を `\\ud800` に直した(Python 3.13 でも `compileall` が通る。docstring のみ)
- テスト: `tests/test_startup_errors.py`(15件。URL 省略+パスワード、範囲外・型不正の値、整合違反、URL にパスワードを埋め込んだ場合。プロセス内と子プロセス `python -m loreley_indexer.main` の両方。stdout/stderr・`str`/`repr`/traceback・`__context__`/`__cause__` を検査。OpenSearch には接続しない失敗経路のみ)。ミューテーション4種(捕捉の除去、`include_input=True`、`str(error)` を出す、`except` 内で raise)はすべて失敗(検出)
- メイン確認: 実プロセスで URL 省略+パスワード設定 → `StartupError: invalid settings: opensearch_url: missing` のみ、センチネルなし
- 判断(ユーザー未承認): 整合検証を `ValueError` から `PydanticCustomError` に変えたこと、エラー表示にフィールド名(小文字)を使い環境変数名にしなかったこと、件数上限10件。見送り: `pydantic_settings.SettingsError`(複合型の環境変数の JSON 解析失敗)は現在の `Settings` に複合型の項目がないため捕捉していない(複合型を足すときは `load_settings` の捕捉対象に加える)

## 2. code-reviewer(Dockerfile・.dockerignore。修正後可。Critical なし、Important 2件)

- 実機確認済み(`docker history`・`docker inspect`・コンテナ実行): ENV/ARG/レイヤーに秘密値なし、`/app` 以下は root 所有で実行ユーザーは書き込めない(例外は uv が作る空の `/app/.venv/.lock` のみ)、venv のステージ間コピーの整合(`pyvenv.cfg`・シェバン・`sys.prefix`)、`.pyc` が実際に読まれる(`COPY --from` で mtime が保たれる)、`importlib.metadata` に依存するコードなし(`PYTHONPATH` 方式で問題なし)、SIGTERM は PID 1 で 0.15秒で正常停止し lifespan の停止処理が走る(tini 不要)、HEALTHCHECK は 503 で例外・終了コード1、uvicorn は lifespan の startup 完了後にソケットを開く
- **Important**: ベースイメージのタグが古い(`python:3.12.11-slim-bookworm` は2025-08-08ビルド。15か月前で固定され CPython・OpenSSL・glibc の更新が入らない)→ **対応**: メインが実機で `python:3.12.16-slim-bookworm` と `python:3.12-slim-bookworm` が同一ダイジェスト `sha256:935c3c5b12357a7e10caa9c1e6ca5692344d97cf229832ef584be2cec9fc03df`(Python 3.12.16、OpenSSL 3.0.22、2026-11-05ビルド)であることを確認し、タグ+ダイジェストで固定。固定日・理由・更新の運用(定期的な再ビルドとタグ・ダイジェストの更新。Renovate/Dependabot は任意)をコメントに記載。**新ベースイメージ(3.12.16)のコンテナ内で全テスト 2098 passed**(実装担当が一時コンテナで確認)
- **Important**: README の `docker run` 例が認証なしの API を全インターフェースに公開する(`-p 8000:8000`)→ **対応**: README を `-p 127.0.0.1:8000:8000` に直し、認証なしの注意を足した。Dockerfile の `HTTP_HOST=0.0.0.0` のコメントにも添えた
- Suggestion(すべて対応): `.dockerignore` を `**/` 付きに、`uv sync --frozen` → `--locked`、コメントの「Docker の secrets」を削除(現在の設定読み込みは secrets/`_FILE` 形式を読めない)、HEALTHCHECK の `--start-period` の根拠の数え方(30×(1+2)=90秒。起動時の整理は複数リクエスト)・ホスト固定(`127.0.0.1`)の注意。**見送り**: uv のハッシュ固定(サプライチェーン。MVP として許容)、空の `/app/.venv/.lock`(0666。実害なし)
- 0018 の判断の妥当性: uv を pip で固定(builder のみ)=妥当、`--no-install-project`+`PYTHONPATH=/app/src`=妥当(hatchling が `uv.lock` に載らない)、HEALTHCHECK の値=妥当(start-period 120秒は目安で上限保証ではない)、`CMD` の単一プロセス=妥当、uid 10001・ホームなし・nologin=妥当

## 3. document-reviewer(README。軽微な修正で可。Critical なし、Important 5件)

- 突き合わせて一致を確認: 設定の表44行を `config.py` と1行ずつ照合(環境変数名・既定・上限・下限・MiB の換算)、整合条件4件、API 一覧(9エンドポイントのパス・メソッド・成功時のステータス・応答の形)、エラー形式と 400/404/409/500/503 の割り当て・各 409 コード名、起動時の整理が終わるまでの全パス 503、起動順・停止の逆順・ワーカーの join 10秒、ログ(ERROR 固定の5ロガー・`describe_origin`・WARNING の形式)、Dockerfile との一致、ID・孤立サロゲート・`content_hash` の規則、`document_id` の算出、仮定義、設計書の節番号
- **Important**: エラー表の `method_not_allowed` が 404 の行にある(実際は 405)→ 行を分けた(404 `crawl_not_found`/`not_found`、405 `method_not_allowed`、その他 `http_error`)
- **Important**: バッチ登録の `failure_type` に `update_conflict` がない/ロック喪失時の部分結果がない → 追加(5種別と Crawler 側の扱いの表。api 3.5・4.3 を実読)
- **Important**: `ratio_threshold`・`min_delete_count` の範囲外リスクが既知の制限にない → 9章を「しきい値・TTL・最小件数の誤設定」に広げ、arch 9.3・9.13(9) に沿って記載。TTL の追加条件を入れていないのはユーザー判断である旨も明記
- **Important**: 認証なしの MVP を外部に晒さない注意がなく、`docker run` の例が実行に足りない(`--network` なしで `http://opensearch:9200` が名前解決できない)→ 1章と Docker の節に追加。例に `-p 127.0.0.1:8000:8000`・`--network`・`--restart unless-stopped`(OpenSearch に到達できないと lifespan が失敗してプロセスが終了するため)を入れた。`--rm` と `--restart` は併用できないため例から `--rm` を外した(実機で確認)
- **Important**: 存在しない「api 4.3 のテストベクタ」への参照 → 「api 4.3 の応答例の `document_id`(`src-docs` + `page-10023` など)と `tests/documents/test_document_id.py` の `API_EXAMPLE_VECTORS`。共有のテストベクタは設計上未決(API-U-7)」に書き換え
- Suggestion(すべて対応): `oversize` の判定条件の訂正、6章冒頭に Crawler の義務の要点(再送は最初と同じ内容でないと 409、未知の `crawl_id` にも 202、受理の確認は Status API)、`last-seen` の `MAX_LAST_SEEN_IDS` 超過は全体 400、整合条件の言い換え、Docker 停止時の終了コード(PID 1 では 0、`--init` など PID 1 でなければ 143)、起動順の参照先(module 5.6)、仮定義表の `extract_failed` の種別の注記
- 注意: README の PID 1 での終了コード0は、code-reviewer が同じイメージで `docker stop` して `ExitCode=0` を確認した実験に基づく(メインは未確認)

## 4. 最終検証(メインが実施)

- `uv run pytest` → **2098 passed**(2回連続。約33秒)。`ruff check` 全通過、`ruff format --check` 191 files already formatted、`uv lock --check` OK
- **`docker build apps/indexer`(0018 の完了条件12)**: 修正後のイメージを再ビルドして成功(イメージサイズ約189MB)。Python 3.12.16、非 root(uid 10001)、`uv` なし、`pytest`・`httpx2`・`ruff` なし(`--no-dev`)、`fastapi`・`loreley_indexer` あり。URL 未設定+パスワードのセンチネルで起動 → 終了コード1、出力は `StartupError: invalid settings: opensearch_url: missing` のみでセンチネル0件、`docker history` にもセンチネル・パスワードなし
- 確認用に作成した Docker イメージ(`loreley-indexer:p6-check`・`p6-check2`・`p6-final`)は削除した。取得したベースイメージ(`python:3.12.16-slim-bookworm`・`python:3.12.11-slim-bookworm`)は残っている
- `git status`: `apps/indexer` と `agent_tasks` 以外の変更なし(`.obsidian/workspace.json` は無関係の既存変更)。**コミットは未実施**(HEAD は c065b9e のまま)

## 完了条件1〜13(0001)の最終状況

0018 の対応表のとおり。変更点: 条件10(ログ)に**起動時の設定エラー経路を追加**(`tests/test_startup_errors.py`)、条件12(docker build)は**実施済み(成功)**。OpenSearch に接続しての実コンテナ起動は未確認(OpenSearch が無い)。条件13(仮値一覧・採用判断の一覧・持ち越し一覧)は 0018 に集約。

## 持ち越し・未対応(0018 からの更新分のみ)

- 実 OpenSearch に接続したコンテナの起動、SIGTERM の終了コード0の実機確認(メインは未確認)、実 uvicorn 経由の `ClientDisconnect`
- uv のハッシュ固定(サプライチェーン)、`/app/.venv/.lock`(0666)
- `pydantic_settings.SettingsError`(複合型の環境変数の JSON 解析失敗)は現在の `Settings` に複合型がないため捕捉していない
- ベースイメージの定期的な更新の運用(Renovate/Dependabot は任意)
- そのほかは 0018 の持ち越し一覧のとおり(U-31、Crawler との突き合わせ、docs への新設定の反映、日本語 PDF、判定時の `MalformedRecordError` が先頭を詰まらせる件 など)

## 次のアクション

タスクレビュー(task-reviewer)を実施し、指摘を反映したうえで、完了報告前にユーザーへ承認未取得の事項(0018 の一覧)を確認する。
