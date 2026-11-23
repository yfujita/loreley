# タスク状態

## 基本情報

- 状態: in_progress
- 現在工程: 実施(P5b 着手前)
- 最終更新: 2026-11-24

- 最新作業記録: 0012-p5a-crawler-client-and-mapping.md

## 現在の状況

プラン(0002)承認済み。P0〜P4 完了、レビュー R-A・R-B 完了(いずれも再レビューで指摘なし)。P5 は 2 段に分け、P5a(Crawler 実 API の突き合わせ・Crawler クライアント・写像・偽物・R8 (d))が完了。ブランチ `feature/implement-admin-api`(開始 SHA `cedcd5667638ec18eaf6ee501963ab356d33ed5f`)。pytest 2608 passed(P5a 検証再実行済み)、コミット済み。
Crawler 実 API と B 9.2 の突き合わせは重大な差なし(0012)。AAPI-U-12・AAA-U-4 は実機で確認済み。
読み取り系 EP-01・02・09・10・11・12・14 は実装済み。次は P5b(サービス・EP-03〜08 のルーター・DTO・配線)。データ削除を中継する高リスクの変更を含む。

## 次のアクション

1. P5b を code-implementer に依頼(`SourceSettings` の共用の判断を含む)
2. P5b 完了後に再検証・作業記録・コミット。P6(EP-13)→ P7(OpenAPI・README・スモーク)→ レビュー R-C → task-reviewer

## 未解決事項

- 9200 を別プロジェクトの Fess が使っている場合のスモーク(P7)は、止めずにユーザー判断を仰ぐ
- `ClientDisconnect` のログ水準は P5 以降で判断
- `tzdata` の直接依存化(P7)、README の Docker 起動例更新(P7)
- AAM-U-7、BAPI-U-2 の残りは実装時に確認
- クエリの意味の実機確認(AAA-U-1〜3、AAPI-U-7)・`cat.*` の実際の列・`relocating` の `node` 表記は P7 スモーク
- `SourceSettings` の共用(EP-03・04 の応答を厳格な型にするか、EP-02 用の nullable 版と分けるか)は P5b で判断
- 設計書追従改訂の申し送り(0012): B 11 の AAPI-U-12・AAA-U-4 を「確認済み」に。`redirect=False` は urllib3 では冗長(害なし)
- 設計書追従改訂の申し送り: 0004(4 件)・0005(5 件)・0006(ErrorCode の固定文 10 件)・0008(6 件)・0009(4 件)・0010(B 2.2 の列挙から EP-12・14 を外す、EP-09 のクエリ違反の返し方)
- 据え置き: `test_secret_output.py` の DNS 依存、`job_queries.get_job` の失敗集約の整理、`brief_fields` の型付け、Protocol 整合テストの非公開 API 依存(Python 更新時)

## ユーザー判断待ち

- なし
