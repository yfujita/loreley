# 0013 connectors を独立したモジュールにする(module-structure v0.3)

- 日付: 2026-11-13
- 種別: 途中の追加指示への対応(軽微。プランは作り直さない。設計の置き場の変更で、仕様は変えない)

## 指示(ユーザー)

Crawler の設計書で、Connector が `infrastructure` 配下にあるが、独立したモジュールにしたい。理由は、データソースへの単純な接続以外に、クロール対象の管理など複雑な処理を持つから。Connector が他のデータソースにアクセスする際に必要があれば `infrastructure` を使う構成が自然。

## 実施した作業

`crawler-module-structure-v0.2.md` を複製して v0.3 を作り、`connectors` を `infrastructure` の外へ出した(既存の版は変更しない運用)。`crawler-design-decisions` は module-structure の参照先と方針の 1 行だけが変わるため v0.2 を作った。

主な変更(module-structure v0.3):

- `connectors` をアプリケーション機能の層の独立したモジュール(ディレクトリ `connectors/`)にした。`infrastructure` は `opensearch`・`indexer_client` の 2 モジュールになった(1章、2.1 の図・凡例、3章)
- 4.10: 役割に「クロール対象の管理など複雑な処理を持つ」ことを追記。依存先を「データソース(外部)。必要があれば `infrastructure` を使う。`opensearch`・`indexer_client`・他のアプリケーション機能には依存しない」に変更
- 依存ルール: R2(外部アクセスの担当を、`infrastructure` は OpenSearch・Indexer、`connectors` はデータソースに分けた)、R3(アプリケーション機能どうしの依存を 6 本から 9 本に。`sources`・`crawl`・`documents` → `connectors` を追加。`connectors` は葉)、R4(`api`・`scheduler` が `connectors` を import しない)、R5(`infrastructure` の 2 モジュールは互いに依存しない。`connectors` は `opensearch`・`indexer_client`・他の機能を import しない)
- 7.2 に CM-K-10(確定)を追加。7.3 の CM-P-1・CM-P-7、7.4 の CM-U-8、7.6 の対応表を更新

変更したファイル:

- 新規: `docs/v0.x/system-design/crawler/crawler-module-structure-v0.3.md`
- 新規: `docs/v0.x/system-design/crawler/crawler-design-decisions-v0.2.md`(2章に方針 #15、3章に確定の 1 行、参照先を module v0.3 に)
- 新規: 本作業記録。更新: `STATUS.md`

## 判断・設計上の理由

- **確定の範囲**: ユーザーの指示は「置き場(独立したモジュール)」と「必要なら `infrastructure` を使う依存の向き」。これを CM-K-10 として確定にし、具体の依存ルール(R2〜R5)・内部構成・R3 の本数は案のままにした(既存の方針: 確定はユーザーが言ったことだけ)
- **層**: `connectors` はアプリケーション機能の層に置いた(R1 の層の順は変えない)。Indexer の構成との違いは 3章と 4.10 に明記した
- **`connectors` から `infrastructure` への依存**: MVP の FileSystem は OS 呼び出しを `connectors/filesystem/` 内の `FsOps`(CM-P-9)にまとめていて足りるので、`infrastructure` を使わない。図には「必要になったときだけ」の点線で示した。Web で HTTP クライアントなどが要るときに、`infrastructure` に置くか `web/` 内に持つかは Web の設計で決める(CM-U-8 に追記)。ユーザーの要件にない `infrastructure` の部品(データソース用)は新設していない(要件にない機能を追加しない)
- **`connectors` が `opensearch`・`indexer_client` を使わない**: interface 1.4(Connector は Indexer・ジョブ・ロックを知らない)を、R5 の import 検査の対象にした
- **他の設計書は変更不要**: architecture・interface・FS・Web・crawler-api に `connectors` の置き場の記述はない(grep で確認)。版は v0.2 のまま
- **節番号**: 4.10 は参照が多いため、節の順(4.8・4.9 が infrastructure、4.10 が `connectors`)は変えていない

## 検証

- v0.3 内に旧構成の記述(`infrastructure/connectors`、「3 モジュール」、「6 本」)が残っていないことを grep で確認した(「6 本から 9 本」の変更記録を除く)
- `document-reviewer` による独立レビュー: 結果は下記「レビュー結果」

## 未対応事項・次にやること

- 設計書はユーザー未承認の案を含む(承認は従来どおり未)
- mermaid(サブグラフへの点線エッジ)は未レンダリング(既知の限界と同じ)
- 実装タスク(`20261113_implement_crawler`)が参照する設計書の版は、module-structure v0.3・decisions v0.2 になる。実装タスクの要件・STATUS の参照先は本作業では変更していない

## レビュー結果

document-reviewer(独立レビュー)の指摘と対応:

- 旧構成の記述の残存、R3 の「9 本」と図のエッジ数、循環依存、R1・R4・R9 との整合: 問題なし。mermaid の構文も妥当
- 重要 1: 「分割はすべて案・確定は引用だけ」と CM-K-10 が矛盾 → v0.3 の冒頭・読み方・7.2 に CM-K-10 の例外を明記した
- 重要 2: 確定の範囲がユーザーの発言を超えていた(`opensearch`・`indexer_client` に依存しないことまで確定扱い) → CM-K-10 の確定を「独立したモジュールにすること、必要があれば `infrastructure` を使うこと」に絞り、依存しないことは interface 1.4 と R5 からの導出(案)と明記した(v0.3 の CM-K-10・冒頭・1章、decisions の #15・3章)
- 重要 3: v0.3 の関連文書表が decisions v0.1 を指していた → decisions-v0.2 に直した
- 重要 4: 図の `conn -.-> L3` が R5 と読み違えやすい → ラベルと凡例を「データソース用の部品が要るときだけ。`opensearch`・`indexer_client` は不可」に直した
- 提案: 「クロール対象の管理」の範囲が未定義 → 4.10 に想定(FS は包含・除外パターンの適用と走査)と `sources`・`documents` との切り分けを案として書き、CM-U-8 に残した。「MVP で `infrastructure` を使わない」は案と明記した
- 軽微: 凡例の「使うこと」を「使ってよい」に、decisions の「ほかは変更していない」を「参照先の更新を除き」に直した

修正後の再レビューは省略した(文言の限定・追記のみで、構成・依存は変えていないため)。
