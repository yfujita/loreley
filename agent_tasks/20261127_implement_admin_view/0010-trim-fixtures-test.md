# 0010 フィクスチャのテスト(fixtures.test.ts)の削減

作成日: 2026-11-28 / 工程: 実施(フェーズ 5 の前の整理。ユーザーの指示)
ブランチ: `feature/implement-admin-view`

## 1. 背景と指示

0009 の 5 章で、既存テストの削減候補を挙げ、ユーザーに判断を求めた。回答: 「`fixtures.test.ts` の削減のみ、フェーズ 5 の前に実施」。`dependencyRules.test.ts`・`dependencyMatrix.test.ts`・E2E の大きい 3 本・`describeError.test.ts` は今回は触らない(フェーズ 5 以降は 0009 の方針を適用するのみ)。

## 2. 実施内容(メインエージェントが直接実施。テストの 1 ファイルのみの変更)

`apps/web/tests/support/fixtures/fixtures.test.ts`: 780 行・74 件 → 397 行・30 件。

- **残したもの**(画面側のテストでは検出しにくい、または複数の画面・E2E が前提にする不変条件):
  - dashboard: 全フィクスチャで 8 コンポーネントが固定の順。状態の組み合わせ
  - opensearch: クラスタ集計とシャード一覧の整合(シャードを全件持つ 5 種)、red 系の未割り当てプライマリ数、truncated、`many` の並び・null・10 桁
  - sourceList/sourceDetails: 未実行とキーあり失敗の区別、行単位の unavailable、ロック 7 状態とジョブ記録、ttl・しきい値の境界、unavailable のキー、EP-03・04 の型の違い
  - jobList/jobDetails: 取消可否、再実行の可否と理由、stalled・フラグ unavailable、warnings の変則要素、削除ジョブの現在値(J-E10)
  - documents: 4 タブの判別キー、skipped 系、件数の境界(empty・countsUnavailable・overWindow)
  - lockRefusals: code・status・retryable、EP-06 だけが持つ `requested`・`options_applied`、lock_state と既存ジョブの組み合わせ、番兵のリース期限
  - releaseLockResponses
- **削ったもの**: 値をそのまま写すだけの確認(meta、`allNormal` 以外の個別の状態、`statusNull`・`neverCrawled` などの単純な null、`jobAccepted`・`cancelJobResponses`、`summaryPending`、同じ性質の `it` の分割)。関連する画面テスト・E2E が同じ状態を見る。

## 3. 検証

| 項目 | 結果 |
| --- | --- |
| `typecheck`・`lint`・`format:check` | 成功 |
| `npm run test` | 116 ファイル 1948 件成功(1992 → 1948。所要 86 秒)|
| E2E・build・`gen:api:check` | 未実行(テストのみの変更で、実装・フィクスチャ本体は未変更のため) |

レビュー(test-reviewer・変異試験)は省略した。理由: 削除と統合のみで新しい検証ロジックはなく、残した確認は元の記述の移植である。フィクスチャ本体は変えていない。

## 4. 未対応・申し送り

- 本コミットは**ローカルのみ**で push していない(PR #27 の再レビューが済んだ直後で、差分を増やさないため)。次の PR のブランチで一緒に push する。
- 他の削減候補(依存ルールのテスト 2 本・E2E 3 本・`describeError.test.ts`)は未実施。フェーズ 5 以降は 0009 5 章の方針を依頼・レビューに含める。
- 次: フェーズ 5(S1・S2 と DLG-1/2/5。0007 の申し送りを含む)。
