# 0007 ゲート4 の承認(2026-11-26)

- 日付: 2026-11-26
- 対象: 0006 の 6 章(G4-1〜G4-7)。ユーザーが `AskUserQuestion` で回答(2 回)
- 区分: 以降、v0.2 の新規の判断は「承認済みの案(ゲート4。2026-11-26)」、ユーザー指示の反映は「確定(ユーザー指示 2026-11-26。0003)」とする

## 1. 回答

| ID | 確認事項 | 回答 |
| --- | --- | --- |
| G4-1 | 配信方式の変更と Nginx 方針(FARC-P-40〜42)を承認済みの案にする | **承認** |
| G4-2 | `api` のホスト publish(`127.0.0.1:8080`)を残すか | **`web` 経由に一本化**(推奨「残す」とは異なる選択)。→ 2 章 |
| G4-3 | Vue Router 5.5.1、Node 下限 `^22.22.2 \|\| ^24.15.0 \|\| >=26`、jsdom 31、OpenAPI JSON・生成コードのコミット維持 | **承認** |
| G4-4 | 前提タスク A と B+C の 2 本、EP-13 の `web` 判定は `HttpHealthCheck` による HTTP 確認(案 (a)) | **承認** |
| G4-5 | Nginx 由来の失敗: 書き込みの 502・504・通信断は結果不明、読み取りは 1 回だけ再試行。1 MiB 超の 413 は `client_max_body_size` を `api` の上限より少し大きくして `api` の JSON 400 を出させる。Nginx の `error_page` で JSON は返さない | **承認** |
| G4-6 | DLG-4 の `force_delete`/`rewrite_mode` が null のときは false として送り、「記録なし(なしとして実行)」と表示 | **承認** |
| G4-7 | 0006 の 1.4 の事実の訂正・拡張と、FARC-P-44・45、FMOD-P-34・35 を一括承認 | **一括承認** |

承認の範囲: 0006 の 1〜5 章(1.1〜1.4 の変更点、2 章の新規案、3 章の前提タスク、4 章の章立て、5 章の U の状態)。G4-2 は下の 2 章で 0006 の該当箇所を置き換える。

## 2. G4-2(`web` 経由に一本化)で 0006 から変わる点

`api` を compose でホストに publish せず、ブラウザ・開発・IT のすべてが `web`(Nginx)経由、または自前の上書きで接続する。

| 対象 | 0006 の案 | 本記録での変更 |
| --- | --- | --- |
| FARC-P-42(公開範囲) | `web` と `api` の両方を `127.0.0.1` のみ publish | **`web` だけを `127.0.0.1` に publish する。`api` は compose の `ports` を持たず、内部ネットワークのサービス名(`api:8080`)だけで到達できる**。認証なしの破壊的操作の入口が 1 つになる(HO-40・41 の注意書きは `web` に対して適用)。区分: 承認済みの案(ゲート4) |
| FARC-P-19(開発プロキシ) | `/api` → `127.0.0.1:8080`(維持) | **変更: 開発サーバーの `/api` の転送先は、compose で起動した `web` の公開ポート(`http://127.0.0.1:<WEB_HOST_PORT>`)を既定とする**(`api` に直接つながらない)。転送先は dev 専用の環境変数で上書きできる(名前は実装で決める)。つまり開発は「`web`・`api`・OpenSearch・Crawler・Indexer を compose で起動し、Vite の dev サーバーから `web` 経由で `api` を使う」。`web` に配るのは本番ビルドの `dist/` で、dev サーバーの HMR は Vite が持つ |
| 結合テスト(IT。`tests/integration/api/support.py:39`、`scripts/run-api-integration-test.sh`、`compose.test.yaml`) | `api` の publish を残すので変更不要 | **IT 用の上書き `compose.test.yaml` が `api` を `127.0.0.1:8080` に publish する**(Crawler と同じく診断・テスト用の上書き。本番用の `compose.yaml` には書かない)。`/app/web` の fixtures の mount は C で不要になる。変更は前提タスク B+C に含める |
| 前提タスク B+C | — | 上の 3 点(`api` の `ports` を `compose.yaml` から外す、IT の上書きで publish、dev プロキシの転送先)を追加。`compose.yaml` 冒頭の「公開範囲」の注意書きと `deploy/compose/README.md`・`apps/api/README.md` の更新も含める |
| `web` の起動順 | `depends_on: api`(`service_healthy`) | 同じ(`web` のヘルスチェックの手段は実装時確認) |
| `API_HOST_PORT` | 維持 | 本番用の `compose.yaml` では不要になる(IT の上書きだけが使う)。`WEB_HOST_PORT` を新設(既定値は 8080・8000・8001・9200 と重ならない値。実装時に決める) |

## 3. 確定した設計判断の一覧(P4・P5 が従うもの)

0006 の 1・2 章(G4-2 は上記 2 章で置き換え)と、0004・0005 が正。要点:

- 配信: `web`(Nginx)が `/admin/` を配信し `/api/` を `api` へプロキシ。FARC-K-4・FMOD-K-4 を更新(確定。ユーザー指示)。FARC-P-2・P-20 を変更。FARC-P-19 は dev プロキシの転送先を `web` の公開ポートに変更
- 新規の `-P-`: FARC-P-40(Nginx 配信方針)・41(`/api/` プロキシ)・42(公開範囲。上記 2 章)・43(Nginx 由来の失敗)・44(実行時エラーの正規化)・45(生成・ビルド設定)・46(DLG-4 の null)、FMOD-P-34(`admin/api` の正規化・パス値検証)・35(ルート直下の設定ファイルの追加)
- 変更: FARC-P-30・4(Vue Router 5.5.1)、FARC-P-3(Node 下限)、FARC-P-21(jsdom 31)、FARC-P-4(固定範囲の具体化)。維持: FARC-P-6(コミット)
- 事実の訂正・拡張: 0006 の 1.4
- U の状態: 0006 の 5 章
- 前提タスク: A(OpenAPI の型・docstring)、B+C(`web` コンテナ・compose・`api` の `web` プローブ置換・IT の追従)

## 4. A 9 章へ転記する G4 の表(P6 で使う)

上の 1 章の表(G4-1〜G4-7。G4-2 は「`web` 経由に一本化」と 2 章の影響を併記する)。

## 5. 次にやること

P4(E v0.2)と P5(F v0.2)を `document-writer` で並列に開始する。共通の依頼文を scratchpad に置き、各回はそれを参照する。
