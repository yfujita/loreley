# 0009 PR #27 のユーザーレビューへの対応

作成日: 2026-11-28 / 工程: 実施(PR #27 のレビュー指摘への修正。フェーズ 5 の前)
ブランチ: `feature/implement-admin-view` / 対象 PR: https://github.com/yfujita/loreley/pull/27
比較基準: `7e0ef0c`(0008 のコミット)/ 修正コミット: `8b27622`・テスト整理のコミット(本記録の直前)

## 1. ユーザーのレビュー結果(Request Changes 推奨。Critical 0・Important 2・Minor 2)

| # | 区分 | 指摘 | 確認結果(メインエージェントがコードで確認) |
| --- | --- | --- | --- |
| 1 | Important | 不正な成功応答が正常データとして扱われる(`validateResponseBody` は空でない JSON オブジェクトしか見ない。例: Dashboard が `{"status":"ok"}` → `dashboardViewModel.ts:216` の `data.components.map` が実行時例外。Query 層は成功扱いでエラー表示に載らない。O1 の `indices`・`nodes`・`shards` も同様) | **妥当**。`client.ts` と `dashboardViewModel.ts:216` で確認 |
| 2 | Important | HTTP 204 がレスポンス検証を迂回する(生成クライアントは 204 で `responseValidator` を呼ばず `{}` を成功として返す。`client.gen.ts:120`。Admin API は 204 を返さない。テストでも許容していた) | **妥当**。管理操作で、結果不明なのに成功通知を出す恐れ。生成クライアントの `interceptors.response`(`client.gen.ts:103`)は 204 の判定より前に走る |
| 3 | Minor | O1 の stale 中も、未割り当てプライマリの警告が「現在の状態」として出る | **妥当**。stale 中は文言を切り替える(通常は「…があります」、stale は「前回取得時に…ありました」) |
| 4 | Minor | J2 のポーリング: 前回 `running` のジョブが 404 になっても、前回データが残るため継続する | **妥当**。404(`job_not_found` など)で停止、network・timeout・5xx では継続 |
| 補足 | 懸念 | コード量(約 4.4 万行。テスト約 2.2 万行・生成物とロック約 1.1 万行・実装約 1 万行)。テストが多く保守コストが気になる | 修正必須ではないが、今後の方針に反映(5 章) |

レビューは静的レビュー(GitHub の差分・主要コード・設計書。実機・テストの独立実行はなし)。アーキテクチャの方向性・責務分離・書き込み操作の自動再送の禁止・`networkMode: 'always'`・タイムアウト・依存ルールの静的解析などは評価された。「API の異常応答の処理を修正すれば、現在のアーキテクチャのままフェーズ 5 以降へ進んでよい」。

## 2. 対応(コミット `8b27622` + テスト整理のコミット)

- **指摘 1・2(同じ根本原因なので 1 つの修正)**: 新ライブラリは足さず、`admin/api/responseShapes.ts`(EP ごとの最小限の形の表と検査関数。手書き)を追加し、`client.ts` の `interceptors.response` に `validateSuccessResponse` を追加した。生成 SDK が渡す `options.url`(展開前のパステンプレート)と `request.method` で表を引く。204・205 は `invalid_response`(status 204/205)にする(生成コードは未編集)。満たさなければ throw → 既存の error interceptor(`toApiError`)が status 付き `invalid_response` にする。
  - 検査する項目は「画面の描画と管理操作の成功判定に使う項目」(必須キー・配列・型・`|null` はキーの存在)に限る(全項目の厳密検証=スキーマの完全生成はしない)。OpenAPI の 2xx 16 件(14 EP)すべてに表のエントリがある。EP-14(`/meta`)は全項目が nullable で検査項目なし(空・非オブジェクトは既存の `responseValidator` が拒否)。検査は値を見ず、エラーメッセージ・診断に値を含めない。
  - **契約テスト**(`responseShapes.contract.test.ts`)が OpenAPI の `required`・型・null 許容・配列と表の整合を固定する(全 2xx に表のエントリがあり余分もない、204・205 の宣言がない、EP-11 の `anyOf` は 4 型すべてで成り立つ、`shards[].node` の null とキー欠落の区別)。
  - 既存テストで必須項目が足りない成功スタブ(`{ ok: true }` など)を返していたものは、生成型で `satisfies` したフィクスチャに置き換えた(テストを緩めていない)。D1・O1 に「形の合わない 2xx でも実行時例外にならず、既存のエラー表示になる」テストを追加。
- **指摘 3**: stale 中のタイトルを「前回取得時に未割り当てのプライマリシャードがありました」(単一インデックスは本文に前回の取得時点であることと現在の状態が確認できていないことを書く。複数も同様)に切り替え、通常時は変更なし。
- **指摘 4**: `jobDetailRefetchInterval` が `query.state.error` を `describeError(...).notFound` で判定し、`job_not_found`・`not_found`・`invalid_request`(400。ID の形式違反は再取得しても変わらない)で停止。network・timeout・5xx・HTML の 502 では継続。

## 3. 設計との差異(設計書は改訂しない。Q2)

- **response interceptor を追加**: E 5.3・F 3.3 は「interceptor は 2 つ(request・error)」だが、request・response・error の 3 つになった。冪等性の判定は従来どおり error interceptor の登録で行う(3 つを同じ関数内で続けて登録する)。
- **二重パース**: interceptor が `response.clone().text()` を JSON パースし、生成クライアントも後で読み直す。インデックス 1,000 件・シャード 10,000 件(約 850KB)で検査だけが約 190ms(Node・jsdom の実測。ブラウザは未測定)。通常規模では問題なし。規模が問題になったら、検査結果のキャッシュかパース済みの値を `responseValidator` に渡す方式に寄せる。
- **表にない EP・パースできない本文はここでは通す**(後者は生成クライアントが SyntaxError にする)。新しい EP を追加して表に書き忘れると、契約テストが落ちる。

## 4. 検証

| 項目 | 結果 |
| --- | --- |
| `gen:api:check`・`typecheck`・`lint`・`format:check`・`build` | 成功 |
| `npm run test` | 116 ファイル 1992 件成功(3 回連続。所要 81〜97 秒) |
| `npm run test:e2e` | 178 件成功 |
| `docker build` | 成功(8b27622 時点。テスト整理は `apps/web` のテストのみの変更) |
| `code-reviewer`(再レビュー) | **可**(Critical・Important なし。正常応答の誤検出は読んだ範囲で見つからない) |
| `test-reviewer`(再レビュー) | Critical・Important なし。OpenAPI の変異 19 件のうち、設計上検出しない 1 件(表にない必須キーの追加)を除いて検出。実装の変異 36 件に実害のある生存なし |
| **実 API での確認**(専用 compose 環境。0003 3 章の事前確認・後始末つき) | 登録・更新・クロール起動・ジョブ取消・ロック解放・削除と各 GET を実 Admin API に実行し、**採取した 32 件の実応答が、表の全 14 EP の検査をすべて通った(誤検出 0 件)**。確認した形は dashboard・cluster(1 ノード・7 インデックス)・meta・sources(空/1 件/削除後)・jobs・job 詳細(queued〜succeeded・取消後)・documents(4 タブ)・登録/更新/クロール受付/取消/ロック解放(`released:false`)/削除受付。**ただし EP-11 の文書一覧は 4 タブとも 0 件だった**ため、各行型(`skipped` など)の要素の検査は実データでは通っていない(フェーズ 8 の実機確認で確認する)。環境は後始末済み(別プロジェクトのコンテナ・ボリュームには触れていない) |

## 5. コード量・テスト量について(ユーザーの懸念)

- **現状の内訳**: PR #27 は 334 ファイル・約 4.4 万行(追加)。テスト約 2.2 万行・生成物とロックファイル約 1.1 万行・実装約 1 万行。Vitest 1992 件(1 回の実行 81〜97 秒。ファイルごとの jsdom 環境の起動が約 4 割、インポートが約 2 割)、Playwright 178 件(約 3 分)。
- **ユーザーのレビューで示された方針(フェーズ 5 以降に適用)**:

  | テスト対象 | 方針 |
  | --- | --- |
  | 管理操作の安全性・API 契約・エラー処理・状態遷移 | 厳密に検証 |
  | 純関数 | 境界値を中心に |
  | UI の内部実装 | 過度に固定しない |
  | CSS・細かな表示文言 | 重要な仕様に限定 |
  | E2E | 主要なユーザー操作を優先 |

  テスト件数を増やすことより、仕様変更時に変更が少なくて済むことを重視する。依頼文・レビュー依頼にこの方針を含める(今回の修正から適用済み)。
- **今回の整理**: 重複したテスト(契約テストの重複項目・`client.test.ts` の再検証・O1 の stale 文言 3 件)を削り、全 EP の誤形 2xx を 1 本の表にまとめた(差し引き −35 行)。
- **既存テストの削減候補(未実施。ユーザーの判断待ち)**: 行数の多いファイル — `tests/support/dependencyRules.test.ts`(1026 行)・`dependencyMatrix.test.ts`(451 行)=依存ルールの検査(静的解析の設定の回帰テスト。価値は高いが量は多い)、`tests/support/fixtures/fixtures.test.ts`(780 行)=フィクスチャ自体の「名前の主張」の検証(フィクスチャ(テストデータ)のテストで、重複度が高い。削減の第一候補)、E2E `opensearch.spec.ts`(810)・`shell.spec.ts`(770)・`dashboard.spec.ts`(631)、`describeError.test.ts`(783)。

## 6. 未対応事項・申し送り

- 検査対象外のもの: EP-02 の `lock`・`last_crawl` など nullable で、画面側が null を許容して読む項目。ネストの 2 段目以降。`status` などの列挙値(未知値の中立表示は各画面の責務)。画面実装で新たに必須の項目が増えたら `responseShapes.ts` に足す(契約テストが OpenAPI との整合を見る)。
- 検証失敗時の診断は `status` だけで、どの項目が原因かは残らない(`ResponseShapeError` は項目のパスを持つが `toApiError` が破棄する。PII を含まない設計の帰結)。本番で OpenAPI と実 API のずれが起きたとき調査が難しくなりうる。開発時だけ `console.warn` を出す案があるが未実施(フェーズ 10 の実機確認・IT で実 API の応答が検査を通ることを確認する方針)。
- 実 API での EP-11 の要素検査は、フェーズ 8 で確認する。

## 7. 次のアクション

- 修正を PR #27 に push する(ユーザーのレビューへの対応。0008 の「PR ごとに指示を受けて push」の例外=同じ PR への修正)。ユーザーが再レビューする。
- ユーザーの判断: 既存テストの削減(`fixtures.test.ts` ほか)を、フェーズ 5 の前に行うか、フェーズ 5 以降の実装で方針を適用していくか。
- 再レビュー後、フェーズ 5(S1・S2・DLG-1/2/5)に進む(0007 の申し送りを含む)。
