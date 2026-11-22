# 20261113_upgrade_opensearch

## 背景・目的

Indexerおよびdeployで使用しているOpenSearchが古い。
最新に更新する。

## 要件

### 現状(As-Is)

- opensearch-py>=2.8,<4
- opensearch 2.19.7

### あるべき姿(To-Be)

- opensearch-py 3系の現時点での最新(3.2?)
- opensearch 現時点での最新をデフォルトにする（3.9.0）

### 具体的にやること

- indexerのopensearch-pyの更新
- composeのopensearchのバージョン更新
- indexerのintegration testを通す

## 対象範囲

- indexer
- deploy


## 完了条件

- [ ] indexerのintegration testが通る

## 成果物

- 変更したコード

