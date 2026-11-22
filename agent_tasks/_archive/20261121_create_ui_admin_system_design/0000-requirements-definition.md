# 20261121_create_ui_admin_design

## 背景・目的

Admin画面の機能を設計する。
既存のProduct Designおよび各コンポーネントの設計を踏まえ、Admin画面に必要な機能を整理し、機能設計書を作成する。

## 要件

### 現状(As-Is)

Admin画面を作ることは決まっているが詳細は未定。

### あるべき姿(To-Be)

Admin画面の機能が明確になっている
既存設計で決定済みの機能を整理するとともに、不足している機能を洗い出し、MVPで実装する機能と将来拡張する機能を区別する。

今の所私が考えている候補は以下。

- Crawler設定の管理
- Crawlerの起動/停止/実行状態の参照
- Loreleyダッシュボード
  - 各コンポーネントの起動状態を表示。落ちたりしていないか。
- OpenSearchダッシュボード
  - OpenSearchのクラスタ状態が参照できる。cerebroのようなUIが理想。機能拡張はあるかもしれないが、当初はクラスタ状態、インデックス状態（シャード配置状態やドキュメント件数）が確認できればいい。

### 具体的にやること

- プロジェクト全体の把握
- Admin画面の機能のリストアップ
- Admin画面機能設計書の作成 

## 対象範囲

- 機能面での設計

## スコープ外

- 詳細設計
  - 画面の詳細設計は不要
  - UIデザイン
  - API設計
  - 技術スタックの選定

## 完了条件

- [ ] admin画面の機能の設計が完成している

## 成果物

- `docs/v0.x/system-design/ui-admin/ui-admin-functions-v0.X.md`

## 補足・参考情報

- Product設計: `docs/v0.x/product-design`
- Crawler設計: `docs/v0.x/system-design/crawler`
- Indexer設計: `docs/v0.x/system-design/indexer`