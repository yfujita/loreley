# 0013 PR #26 のレビュー指摘への対応

- 日付: 2026-11-27
- 対象: PR #26(ユーザーが持ち込んだ外部レビュー。Critical 0・Important 1・Suggestion 2)

## 指摘と対応

| 重大度 | 指摘 | 判断・対応 |
| --- | --- | --- |
| Important | 定義した location 以外が `root` 直下の公式イメージの既定ファイル(`/index.html`・`/50x.html`)を 200 で配信する。設計 3.3 は定義外のパスを 404 とする | **妥当。修正**。修正前のイメージで `/index.html`・`/50x.html` が 200 になることを再現してから、`apps/web/nginx/default.conf` に `location / { return 404; }` を追加(より長い location が優先されるため既存の挙動は変わらない)。0005・0009 で確認していたのは `/healthz`・`/favicon.ico`(ファイルがなく 404)だけで、既定ファイルの配信は見落としていた |
| Suggestion | Nginx 経由の結合テストを追加する | **今回は見送り**(レビュー自身もマージ条件にしないとしている)。0012 の申し送り(後続の `tests/integration/<名前>/`)に、回帰対象として `/index.html` の 404 を追加する |
| Suggestion | `compose.yaml:30` の「ホストに publish するのは web だけ」が実態と違う(OpenSearch 9200・Indexer 8000 も 127.0.0.1 に publish) | **妥当。修正**。「Admin View と Admin API のホスト側の入口は web に一本化する」に直した。同じ言い回しの `tests/integration/api/compose.test.yaml` と `apps/api/README.md` も直した(`grep "web だけ"` で確認) |

## 検証

- 修正後のイメージ(`docker build apps/web`)で `nginx -t` OK。一時ネットワークで、`/index.html`・`/50x.html`・`/healthz`・`/favicon.ico`・`/foo/bar` は 404、`/api` は 301(`/api/`)、`/api/x` は 502(`api` なし)、`/admin` 301、`/admin/`・`/admin/sources/xxx`・`/admin/index.html` は 200(`no-cache`)、`/admin/assets/nope.js` は 404、`/` は 302。後始末済み
- `docker compose config` OK(コメントのみの変更)
- IT・実機確認(0008・0009)は再実行していない(変更は未定義パスの 404 のみ。api が見る `/admin/` は 200 のままであることを上で確認)

## 申し送り(0012 への追加)

- Nginx の自動テストの回帰対象に、`/index.html`・`/50x.html` などの未定義パスが 404 になること
- README(`deploy/compose/README.md`)に「定義したパス以外は 404」を追記済み
