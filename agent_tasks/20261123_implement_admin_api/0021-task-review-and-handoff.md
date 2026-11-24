# 0021 タスクレビューの結果と、後続への申し送りの集約

日付: 2026-11-24

## タスクレビュー(task-reviewer)の結果

比較基準: 開始 SHA `cedcd56` から HEAD `acbb4b4`。`task-reviewer` が 0000〜0020・実コード・Git 差分・プロジェクト規則を突き合わせた。

**総合判定: Critical なし。差し戻し不要**(STATUS.md の整理と申し送りの転記だけが要対応。本記録と STATUS.md の書き直しで対応した)。

- 要件の充足: 完了条件「Admin API が存在している」、具体的にやること(設計書の確認・Indexer API の確認・Crawler API の確認・実装)、0001 の確定事項、プランの受け入れ基準 ①〜④ をすべて満たす。ルーター定義は 14 本(documents 1・dashboard 1・jobs 2・sources 5・crawl_operations 3・opensearch 1・meta 1)
- プランとの乖離(P5 の分割、R-C の分割、P5a の停止と引き継ぎ、R-C 前半の再レビューの別レビュアーへの切替、`ClientDisconnect` の変更、`servers` の固定、`lock_state` を読む時刻、`SourceSettings` の分離)は、すべて作業記録にあり判断も妥当。範囲外のものの混入なし
- `docs`・`apps/crawler`・`apps/indexer`・`deploy`・`infra`・`apps/api/Dockerfile` の差分なし。静的配信・SPA フォールバックの実装なし。差分は `apps/api` と `agent_tasks` のみ(248 ファイル、+33,197/-142 行)
- 作業記録の連番 0003〜0020 に欠番・重複なし。`0000`〜`0002` は書き換えられていない。テスト件数の推移は連続(310 → 751 → 1096 → 1150 → 1735 → 1936 → 1956 → 2608 → 3032 → 3252 → 3246 → 3389 → 3410)。最終値 3410 は `task-reviewer` の再実行と一致
- レビュー工程(R-A・R-B・R-C と各再再レビュー)はすべて実施され、Critical・Important はすべて解消。省略したレビュー(web-ui-reviewer: Web UI の変更なし、document-reviewer: 設計書を変更しない・README は code-reviewer が確認)の理由はプラン §5 に記録済み。実装担当とレビュアーは分離されていた。作業記録・STATUS.md はメインエージェントのみが作成
- 19 コミットはフェーズ・指摘対応・記録の単位。`.venv`・キャッシュ・`audit/`・生成した OpenAPI JSON・`.env` は含まれていない

### 指摘と対応

| 指摘 | 内容 | 対応 |
| --- | --- | --- |
| I1 | STATUS.md の未解決事項に、手動スモークで未確認の項目の一部が転記されていない。AAM-U-7・BAPI-U-2 が古い表現のまま | 本記録の「結合テストのタスクへの申し送り」に集約し、AAM-U-7・BAPI-U-2 を「確認済み」と「残り」に書き分けた。STATUS.md を書き直した |
| S1 | STATUS.md の「現在の状況」が時系列で乱れ最新が反映されていない | STATUS.md を書き直した |
| S2 | 認証なし・Origin 検査なしの現状が STATUS.md にない | 「既知のリスク」として STATUS.md に記載。PR 説明にも書く |
| S3 | 据え置き・申し送りの一部が STATUS.md に転記されていない | 本記録の「据え置き一覧」に集約し、STATUS.md から参照 |
| S4 | STATUS.md の未解決事項に解消済みの項目が混在 | 「解消済み」を分けた |
| N1〜N3 | 0002 の冒頭の「ユーザー承認待ち」(書き換えない規則のためそのまま。承認は 0003)/ `OPENAPI_ENABLED` を外した 404 は単体テストのみ(0018 に明記)/ 0012 の逸脱(今後は依頼文に「ローカル起動も禁止」と明記する) | 対応不要(記録済み)。N3 は今後の依頼文で反映 |

## 後続への申し送り(集約)

### A. 設計書の追従改訂の申し送り(別タスク)

設計書は本タスクでは変更していない。食い違い・追記したい点は各作業記録の「設計書との食い違い・申し送り」にある。件数と主な内容は次のとおり。別タスクとして起票するか、ユーザー判断が必要(後述「ユーザー判断待ち」)。

| 記録 | 件数 | 主な内容 |
| --- | --- | --- |
| 0004 | 4 | D 4.3 `create_admin_router(deps)` が D 6章の許可表と循環(実装は引数なし)/D 4.7 `AdminApiError` の署名/D 3章 `probes/config.py`・`AdminSettings` の中身/D 4.1 `AdminDependencies` の組み立て関数 |
| 0005 | 5 | D 4.8 `connection.py` は許可リストのラッパー付き `ReadOnlyConnection` を返す/`CountsReader.tab_counts` → `count_for_source`/`responses.py`・`reading.py` の追加/`list_*` の窓の保証は `PageRequest` の `ValueError`/C 3.3 R-3 の `terms` 集計の `size` |
| 0006 | 10 | B に `ErrorCode` ごとの固定文の規定がない(`config_invalid`・`lock_held` 以外の 10 件を実装側で補った)。文言を固定したいなら B へ追記 |
| 0008 | 6 | B 2.2 の単一応答の列挙と EP-12・14 の定義の不一致/`failure_detail` は `failed` のときだけ(B 5.2 と C 5.4 の食い違い)/`cat.shards` の必須項目/改行(`%0A`)入りの `job_id` は 404 `not_found`/未配線の DTO/`ErrorCode` の追従 |
| 0009 | 4 | DTO の null 許容(B の非 null 型を B 2.2 の「読めない値は null」に従い nullable に)/EP-02 の `delete_job` の失敗キー/D 3章にないファイル/`DocumentListResponse.items` は `anyOf` |
| 0010 | 2 | B 2.2 の列挙から EP-12・14 を外す/EP-09 のクエリ違反は依存関係ごとに最初の 1 群のみ返す(B 2.12「違反はすべて返す」との差) |
| 0012 | 3 | **B 11 の AAPI-U-12・AAA-U-4 を「確認済み」に**/`redirect=False` は urllib3 では冗長(害なし)/`config_invalid` 400 は `details` キーを持たない |
| 0013 | 7 | B 2.11 の `SourceSettings`(EP-03・04 は非 null)/`ttl_*` の `field` 名/違反の 2 段返却/`connector_config` の NaN・無限大/`%0A` の `job_id`/`lock_state` を読む時刻/巨大整数の `type` |
| 0014 | 7 | B 2.2 の列挙から EP-13 も外す/`HttpHealthProbe.check(url)`/`Connection: close`/`web` の空ファイル/R9 の AST 検査/`checked_at` の扱い/`AdminProbes` |
| 0015 | 3 | **D 5.0 の `lock_state` を読む時刻をリクエスト先頭から Crawler 応答後へ**(C・B と合わせる)/C 8.5 に Crawler 失敗の WARNING を追記/C 11章に DNS の扱いを追記 |
| 0017 | 7 | D 4.12(c) の実装形(`app.openapi` の差し替え・`servers` の固定)と `ClientDisconnect` の確定/B 8.1 の EP-13 の 400/`ttl_*` の OpenAPI 型(`integer \| null`)/`ErrorResponse.error.code` は `str`/`create_admin_app` の `openapi_enabled` ほか |
| 0019 | 2 | `app.py` の `app.openapi` の再試行方針(失敗が続けば毎回伝播する)を D 4.12(c) に反映/Dockerfile のコメント(下記 C) |

### B. 結合テストのタスクへの申し送り(手動スモークで未確認の項目。0018)

- **AAA-U-1〜3(クエリの意味)は部分的に確認**: R-3(`last_crawl`・`last_completed_at`)・R-9(`document_count`)・`tab_counts`・一覧の `total`・EP-10 の `latest_for_source` は実データで期待どおり。並べ替えの順序・`terms` の `size`・`top_hits` は 1 ソース・数ジョブでは十分に確認できていない。AAA-U-2(`mget`/`msearch` の応答の形・`ids` クエリ・スレッド間共有)・AAA-U-3(`refresh_interval`・`max_result_window`)も同様
- **AAA-U-7**(同時実行上限 16/4/8 などの実測)、**AAA-U-10**(期限後に残るスレッドの数と時間): 未実測
- **実行中ジョブの取消(EP-07)・実ロックの解放(EP-08)・EP-06 の `lock_in_use`・`stalled=true`・`lease_expired` などのロック状態**: クロールが約 3 秒で完了するため意図的に作れず未確認。単体テスト(偽物・ローカル HTTP スタブ)では確認済み
- **`force_delete=true`**(EP-05・06): 未実行(削除の実機確認は `source_delete` のみ)
- **EP-12 の `relocating` の `node` 表記、複数ノード・複数シャードの `cat.*` の列**: 単一ノード・数索引のみ
- **AAPI-U-7**(`ids` クエリの `_id` と `document_id` の一致): `skipped` の行が 0 件で `existence` を実機で見られていない
- **ページングの窓 10,000 の実データ**、**OpenSearch の部分失敗(一部シャード障害)**、**`ClientDisconnect` の実機**: 未確認(単体テストのみ)
- **BAPI-U-2 の残り**: `servers`・`paths` は確認済み(0017。`servers` を固定・`paths` はマウント位置を含まない相対パス)。**入れ子のマウントと `FastAPI(root_path=…)` は未検証**
- **AAM-U-7**: 前半(`openapi_export` が外部接続なしで書き出せる)は 0017 で確認済み。後半(E の型生成の手順との整合)はフロントエンドのタスク(FARC)の事項

### C. 据え置き一覧(軽微。必要になったら対応)

- `tests/infrastructure/opensearch/test_secret_output.py` の `.invalid` 名前解決への依存(0007)。`tests/conftest.py` の `host.endswith(".invalid")` は末尾ドット付き・素の `invalid` を拾わない(0016)。`test_http_client.py` の実 DNS 1 件は意図的(0015)
- `job_queries.get_job` の失敗集約の整理(文字列キーと可変の辞書)・`brief_fields` の型付け(0010)
- `RegisterSourceBody(UpdateSourceBody)` の継承の向き、操作の列挙値と呼び出しメソッドの手書き対応(`source_commands`・`crawl_commands`)、`routes.ROUTE_TEMPLATES` がテストからしか使われない(0015。R8 の 6 経路検査の目印として維持)
- `openapi_enabled` の持ち方が二重(`AdminSettings` と `create_admin_app` の引数)(0019)
- `packaging` が `pyproject.toml` に明示されていない(`pytest` の必須依存として `uv.lock` に入っており実害なし)(0019・0020)
- `test_blocking_isolation.py` は `run('probe', …)` の区分取り違えを検出しない(relay 単体が検出する)(0019・0020)
- Protocol 整合テストが `inspect._ParameterKind`・`_is_protocol` に依存(Python 3.12 前提。更新時に `typing.is_protocol` へ)(0011)
- `search_index_reader` の `count_by_source` を `parse_uncounted_search` にする案(0007。現状は安全)
- **`apps/api/Dockerfile` 11 行目のコメント「現時点の `api` は基盤だけ」が古い**: HO-36 で Dockerfile に触るときに直す(0019)
- **`tzdata` の上限 `<2027`**: 2027 年に見直す(0017)
- `ttl_days`・`ttl_seconds` の OpenAPI 型は `integer | null`(実行時は明示的な `null` を `type` で拒否する。B 2.4)。必要なら `json_schema_extra` などで絞る(0017)
- OpenAPI JSON のコミット先・Hey API 側の読み込み(`servers` の扱い)はフロントエンドのタスク(FARC-P-6)

### D. 既知のリスク(設計どおり。対策は別タスクの判断)

認証なしの `api` が破壊的操作(データソースの削除ジョブ、ロック解放、クロール起動、取消)を公開する(HO-40)。本文なしの POST(EP-05・06・07)は `Origin` を問わず処理される(0013 のテストで確認。HO-41)。EP-03 は JSON の `Content-Type` が必要、EP-04・08 は CORS 未許可で届かない。DNS rebinding なら全 EP が対象。README 第 2 章に記載済み。**信頼できるネットワークにだけ公開すること**。PR 説明にも書く。

## 完了チェックリスト(task-workflow.md)

- [x] プランが作業記録として残り、ユーザーの承認を得ている(0002、承認は 0003)
- [x] すべての作業に作業記録がある(0003〜0021)
- [x] プランで指定されたレビュー(レビューフェーズ・タスクレビューフェーズ)を実施している。省略したレビューの理由はプラン §5 に記録(web-ui-reviewer・document-reviewer)
- [x] 未対応事項を最新の作業記録に書いている(本記録の申し送り A〜D)
- [x] STATUS.md が最新の作業記録と一致している(状態・最新作業記録・次のアクション・未解決事項)

## 未対応事項・次にやること

- PR の作成(ユーザーの確認が要る。1 本か 2 本か。ブランチ `feature/implement-admin-api` の開始 SHA からの 20 コミット(本記録の更新を含む)・249 ファイル・約 33,000 行の追加。うち `apps/api` は 226 ファイル)
- 設計書の追従改訂を別タスクとして起票するか(ユーザー判断)
- 結合テストのタスクの起票(申し送り B)
