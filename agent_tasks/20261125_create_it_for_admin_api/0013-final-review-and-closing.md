# 0013 最終確認・タスクレビューの結果と完了整理

日付: 2026-11-25

## test-reviewer による AIT-30 の再確認(0012 の対応の確認。コミット 5c6da23 の前)

- 前回 Important(AIT-30 の `terms` の `size` の検出力)は**解消**。Critical・Important の新規指摘なし
- 確認された点: フィクスチャが「`crawl` のジョブ記録と文書を持つ登録済みソース」を 11 件以上にする(`-k test_30` 単独実行でも成立。削除済みソースは `loreley-sources` との積集合で除外)、アサート 3 つが独立計算・api 応答の両側で 10 超を要求、独立計算は OpenSearch 直読みで空・同じ誤りで通らない、`size` が 10 に退行すれば 1 件欠けて落ちる設計、AIT-91 の変更に問題なし、`OpenSearchProbe` の追加メソッドは読み取りのみで直接書き込みの範囲は AIT-41・51 のまま、結果文書の AIT-30・AAA-U-1 の記述は実コードと一致
- Suggestion 1 件: 下限が 11 ちょうどなので `size` が 10 以外の固定値(20・50 など)に退行した場合は検出できない。**対応**: 結果文書 7 章に 1 文追記(コミット 5c6da23)。コード側の増強(補いのクロール増。1 回約 11 秒)は見送り
- Nitpick 1 件: AIT-30 の件数ログが素の `print`(`observed()` を使っていない)。変更しない

## task-reviewer の結果(比較基準 55dce2f..HEAD)

**総合判定: 軽微な修正で完了可。差し戻し不要**(Critical なし、Important 1 件)。要件の完了条件 5 項目をすべて満たし、0001 の確定事項とプラン承認時の 3 点は守られ、スコープ外の混入なし(差分は `agent_tasks/`・`deploy/compose/`・`scripts/`・`tests/integration/`・`docs/v0.x/test-results/` のみ。`apps/`・設計書・`infra/` は変更なし)。連番 0000〜0012 に欠番・重複なし、既存の作業記録の書き換えなし、サブエージェントによる `agent_tasks` 配下への書き込みは監査ログ上なし。OpenSearch への直接書き込みは承認範囲(AIT-41・51)に収まる。

| 指摘 | 対応 |
| --- | --- |
| I: 最後の再確認(test-reviewer の AIT-30)と 5c6da23 が作業記録・STATUS にない | 本記録(0013)に記録し、STATUS.md を最新化した |
| S: 0011・0012 の変更(`scripts/run-crawler-integration-test.sh` の固定、`compose.test.yaml` のコメント、`support.py` のリファクタ、結果文書の大幅な書き直し)に対する code-reviewer の再レビュー・document-reviewer の再々レビューが省略されている | **省略する**。理由: code-reviewer の指摘は Suggestion のみ(Critical・Important なし)で、その Suggestion に対応しただけ。実行系スクリプトの変更は Crawler IT(14 passed)と api IT(連続 2 回 23 passed、後続で 2 回さらに 23 passed)の再実行で動作を確認した。document-reviewer は再レビューで前回 Important 7 件の解消を確認済みで、その後の変更は再レビューの Suggestion・Nitpick への対応と実行結果の追記のみ(プラン 9 章の「Critical・Important が解消するまで」の条件を満たす)。結果文書の事実は作業記録・実行ログと突き合わせてある |
| S: AAA-U-1 を「確認済み」としているが size 退行の検出は実機で未確認 | 判定を **「一部確認」** に変更した(4.4)。根拠と限界(`size` を 10 に固定して落ちることの実機確認はしていない。固定値の退行は検出できない。数百件以上は未検証)は併記。実機確認(`apps/api` を一時的に変更して落ちることを見る)は `apps/` を変更しない方針のためしていない。必要ならユーザー判断 |
| N: 結果文書の句点・古い数値、compose.yaml の断定調 | 4.6 の文の位置と句点を直した(7・8 回目の段落に Crawler IT 再実行の記述を戻した)、ログ本数を「確認時の本数」と明記、4.6 導入文に 9・10 回目を追記、`compose.yaml` 冒頭コメントに「(設計書の記述。実機未確認)」を追記 |

## 完了チェックリスト(task-workflow.md)

- [x] プランが作業記録として残り、ユーザーの承認を得ている(0002、承認は 0003)
- [x] すべての作業に作業記録がある(0003〜0013)
- [x] プランで指定されたレビュー(code-reviewer・test-reviewer・document-reviewer、task-reviewer)を実施し、Critical・Important は解消。省略したレビューの理由を記録(web-ui-reviewer: Web UI の変更なし、プラン §8。code-reviewer・document-reviewer の再々レビュー: 上表)
- [x] 未対応事項を最新の作業記録に書いている(下記)
- [x] STATUS.md が最新の作業記録と一致している

## 未対応事項・ユーザー判断が必要な事項

- **PR の作成**(ユーザー確認が要る)。説明に書く点: 認証なしの api(HO-40・41)のリスクと、127.0.0.1 限定の公開、IT の実行は約 9 分でホストをスリープさせないこと(`caffeinate -i`)、開発用 compose では `web` が `abnormal` に見えること(HO-36 未対応)、実行前に 9200・8000・8001・8080 が空いていること、既存の Crawler・Indexer IT と同時に実行できないこと
- **設計書追従改訂タスクの起票**: api-base-design 9.2 の HO-34・35・40・41・43・44・45 の状態更新、HO-40 の文言(`:ro` のマウントだけ)の見直し(結果文書 9 章)
- **AIT-30 の `size` 退行検出の実機確認**をするか(`apps/api` を一時変更して落ちることを確認する。しない場合は「一部確認」のまま)
- 据え置き: `apps/api/Dockerfile` の古いコメント(「現時点の `api` は基盤だけ…」)を HO-36 で直す、shellcheck 未導入で未実施、スクリプトの重複(3 本。共通ライブラリ化しない方針)
- 未検証事項の一覧は結果文書 7 章(AAA-U-7・10、EP-09 の複数ページ、10,000 件窓、一部シャード障害、複数ノード `cat.*`、`ClientDisconnect`、入れ子マウント・`root_path`、`stalled`・`lease_expired`、実 Crawler が書いたスキップ記録、`summary_pending`、`size_hint`、EP-07 の終了通知送信前の取消、`web` が mount なしで `abnormal` になること など)
