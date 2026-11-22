# 0004 P0: `/healthz` 追加のための設計書改版

日付: 2026-11-13 / 実施: document-writer(作成・修正)、document-reviewer(レビュー2回)/ 記録: メインエージェント

## 1. 実施した作業

ユーザー決定(0003 §1: 「`/healthz` を追加する」。完了条件9の起動確認方法への回答)を、CM-U-5・CAPI-U-9(ヘルスチェックの要否)の解消として設計書に反映した。新版を新規作成(旧版は無変更)。

## 2. 変更したファイル(`docs/v0.x/system-design/crawler/`、すべて新規)

- `crawler-api-v0.3.md`: CAPI-K-9(確定)・CAPI-P-19(案)を追加、CAPI-U-9 を解消(番号は残す)。1章・3.1・4.7(ヘルスチェック。契約外の案)・5.1・5.2 を更新
- `crawler-module-structure-v0.4.md`: CM-K-11(確定)・CM-P-27(案)を追加、CM-U-5 を解消(番号は残す)。1章、4.1(`api` の責務・API 担当表)、5.7、7.1、7.2、7.6、7.7 を更新
- `crawler-architecture-v0.3.md`: 10章の起動順の直後にヘルスチェックの項目を追記、13.8 横断一覧の CAPI-U-9・CM-U-5 を「解消」に。CA-K は追加しない(確定の記録先は CM-K-11・CAPI-K-9)
- `crawler-design-decisions-v0.3.md`: 3章に確定の行を追加、5章の「決めてはいけない」から CM-U-5・CAPI-U-9 を外した(P8 で実装する方針と矛盾し、実装者を誤誘導するため改版が必須だった)、10章の参照先を新版に

architecture・decisions を改版した理由は上記のとおり。connector 配下の v0.2 文書は CM-U-5・CAPI-U-9 に言及していないため未改版。

## 3. 確定・案の区分(重要)

- **確定**: 「Crawler にヘルスチェック用の API を置く」だけ。出典はユーザー回答(2026-11-13、0003 §1)。
- **案のまま**(CAPI-P-19 / CM-P-27): `GET /healthz` というパス・メソッド、応答の形(Indexer に倣い `{"status": "ok"}` を出発点)、`api` が担当機能(`jobs`・`sources`)を呼ばず受付開始後に 200 を返す動作、Admin API の契約外の運用上の API という位置づけ(1章の6 API に数えない)、起動順を変えないこと、Dockerfile の `HEALTHCHECK` は `apps/indexer/Dockerfile` に倣う(`--start-period` を十分に取る。導出。値は実装時)。
- 導出として明記: 200 は「受付が始まった」ことだけを示す(OpenSearch・Indexer の到達性や Job Runner・ハートビートの生存は示さない)。回復完了前は接続できない。回復に時間がかかりうるため compose のヘルスチェックには猶予が要る(値は決めていない)。
- 他の未決・案(CA-U-14、CAPI-U-1〜8・10、CM-U-1〜4・6・8・9、CAPI-P-1〜18、CM-P-1〜26 など)は変更・確定していない。

検討して採らなかった案: architecture 13.2 に CA-K を追加する案(ユーザー回答は CM-U-5・CAPI-U-9 に対するもので、記録先は CM-K-11・CAPI-K-9 に統一)。

## 4. レビュー結果と対応

### 1回目(document-reviewer): 軽微な修正で可(Critical なし)

| 重要度 | 指摘 | 対応 |
| --- | --- | --- |
| Important | 「`GET /healthz` を置く」を確定とする文言が「パス・メソッドは案」と矛盾 | 確定を「ヘルスチェック用の API を置く」に直し、パス・メソッド等は案と明記(修正済み) |
| Important | 確定行に導出・案(契約外、起動順を変えない)が混入 | 確定行は「置く」に絞り、案側(CAPI-P-19 / CM-P-27)へ移動(修正済み) |
| Suggestion | 出典の文脈(要否の回答か起動確認方法の回答か) | 出典欄に質問の文脈を追記(修正済み) |
| Suggestion | Dockerfile の `HEALTHCHECK` の扱いが文書間でそろっていない | api 4.7・CAPI-P-19・CM-P-27・architecture 10章に案として追記、module 7.7 の参照先を整理(修正済み) |
| Nitpick ×3 | 担当機能の範囲の表記、module 5.7 の指示先、作業記録パスの繰り返し | 修正済み |

方針: パスまで確定にするかの追加確認はユーザーにしていない(確定は「置く」だけ。ユーザー回答の原文は「`/healthz` を追加する」)。パスを確定したい場合は後から昇格できる。

### 2回目(同じ document-reviewer): 指摘なし

前回の7件はすべて解消。Nitpick 2件は任意で、**対応しない**(実害なし。本文で位置づけは「案」と明記済み):
- api 4.7 見出し・module 1章入力欄の「契約外」注記の不統一
- api 5.1 に Indexer の `--start-period=120s` の根拠が無い(module 7.1 には記載済み)

旧版が無変更で、無関係な変更がないことを `git status` と diff で確認済み。

## 5. 0002 への反映(0003 §2 のとおり)

- P8: `GET /healthz`(案: CM-P-27)を実装し、200 の応答・担当機能を呼ばない・回復完了前は応答しないテストを置く
- P9: Dockerfile に `HEALTHCHECK`(`apps/indexer/Dockerfile` に倣う。`--start-period` を十分に取る。値は実装時に決める)

## 6. 環境確認(P1 開始前)

- 開始時点の HEAD: `061dc7b196f67a689e0d834eb676ce356d6cdb34`(P1〜P2 レビューの比較基準)
- uv 0.13.8、Docker 20.10.13 が使える。

## 7. 未対応事項・次のアクション

- 設計書 v0.2〜新版のユーザー承認、decisions 4章の10件の最終確定はユーザー判断待ちのまま
- 次: P1(基盤・`common`・依存ルール検査)を `code-implementer` に依頼
