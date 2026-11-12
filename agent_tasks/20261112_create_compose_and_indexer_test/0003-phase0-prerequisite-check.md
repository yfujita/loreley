# 0003 フェーズ0: 前提確認

日付: 2026-11-12
実施者: メインエージェント
基準コミット: `c59fea7`(作業ツリーの変更は `.obsidian/workspace.json`(本タスク外)と本タスクのディレクトリのみ)

## 実施内容

ホストで Docker・docker compose・uv・ポート・ネットワークを確認した。

## 確認結果

| 項目 | 結果 | 備考 |
| --- | --- | --- |
| Docker | 20.10.13(Docker Desktop)。デーモン起動済み | CPU 2、メモリ約 4.1GB(4125892608 B) |
| docker compose | **v2.3.3**(古い) | `up` に `--wait` はあるが **`--wait-timeout` は無い**(追加は v2.18 以降) |
| ホストの CPU | x86_64 | OpenSearch の amd64 イメージで足りる(arm64 確認は不要) |
| ポート 9200・8000 | 空き | |
| ネットワーク | OK | Docker Hub のイメージ取得(`hello-world`)と Docker Hub API(opensearch のタグ一覧)に到達できた |
| Python | 3.13.4(pyenv)、3.11、pip あり | `apps/indexer` は `>=3.12,<3.13` を要求。ただし Indexer はコンテナ内で動くので、ホストの Python に制約はない |
| **uv** | **未インストール** | `brew` はある。イメージのビルドは Dockerfile 内で uv を入れるためホストの uv は不要。ホストで必要なのは結合テストの実行と、`apps/indexer` の単体テストを再実行するとき |

## プランへの影響

1. **`--wait-timeout 300` は使えない**(compose v2.3.3)。フェーズ 3・5 では次のいずれかにする。
   - `up -d --build` のあと、スクリプトで indexer の health と `opensearch-init` の終了コードを自前でポーリングし、上限時間を自分で持つ。
   - 先に `up --wait` が one-shot の init 終了で失敗しないかを実機で確かめる(v2.3.3 では終了済みコンテナがあると `--wait` が失敗する既知の挙動があり得る)。
   - いずれも 0002 のリスク表の「`up --wait` が one-shot init で失敗する場合は自前の待機に切り替え、理由を記録・報告」に該当する。0001 Q3 の `up --wait` からの逸脱になる場合は、記録して報告する。
2. **`service_completed_successfully`** は compose v2.3.3 で使えるかをフェーズ 3 で確認する(使えなければ代替を検討し、報告)。
3. **uv が無い**: 結合テストの実行環境の作り方をユーザーに確認する(下記)。フェーズ 1〜3 は uv なしで進められる。
4. メモリ約 4GB・2 CPU なので、OpenSearch のヒープ 512m の既定は妥当。ほかの重いコンテナを同時に動かさない前提を README に書く。

## 判断・未対応事項

- Docker は使えるため `blocked` にはしない(プランの 5 のとおり)。
- uv の扱い(インストール or 代替)はユーザーに確認する。回答前でもフェーズ 1〜3 は進める。
- 次: フェーズ 1(OpenSearch スキーマ定義)を `code-implementer` に依頼する。
