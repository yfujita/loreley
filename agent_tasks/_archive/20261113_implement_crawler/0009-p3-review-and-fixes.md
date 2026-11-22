# 0009 P3 のレビューと修正

日付: 2026-11-14 / 実施: code-reviewer・test-reviewer(各2〜3回)、code-implementer(修正)/ 記録・再検証: メインエージェント
レビュー対象: P3 で追加した `connectors/`・`documents/` と対応テスト(`apps/crawler/` は未コミット。比較基準 HEAD `061dc7b196f67a689e0d834eb676ce356d6cdb34`)

## 1. 1回目のレビュー結果(ともに「軽微な修正で可」、Critical なし)

### code-reviewer(Suggestion 3、Nitpick 3)と対応

| 指摘 | 対応 |
| --- | --- |
| glob の `**` を離して多数並べると正規表現の照合が指数的に遅い | まず `max_double_stars`(既定4)で対応 → 3回目のレビューで `*` の多用にも爆発することが判明し、**正規表現をやめて照合を置き換え**(§3)。`max_double_stars` は削除 |
| 取得の後処理(`len`・`sha256`・表示用置換)が例外変換の外 | 後処理も `converting_unexpected_errors(DOCUMENT)` の中に。`isinstance(content, bytes)` 検査も追加。不正な戻り値6種のテスト |
| 想定外の例外の変換が `from error` で元の例外(ファイル名 repr・値)を残し、`logger.exception` 経由で生のパスや設定値がログに出うる(R11) | 5箇所を `from None` に統一(分類済み errno 変換も。元の `OSError` のファイル名 repr は制御文字を含みえて行偽造できるため)。診断に必要な情報(型名・errno 名・エスケープ済みパス)は説明文に残る。`__suppress_context__` が真で traceback に出ない。ログ出力(`traceback.format_exception`・`caplog`)で SENTINEL と偽造行が出ないことをテスト |
| Nitpick: 定数の重複、`_next_item` の型検査の可読性、`Completed` 後の `next()` | `_EPOCH` に一本化、`_check_shape(item)` に切り出し、`DocumentEnumeration` が `Completed` を保持し以降は Connector を呼ばず `Completed` を返す |

### test-reviewer(Important 4、Suggestion 9、Nitpick 7。175変異中25件が生存、うち15件がテスト不足)と対応

| 指摘 | 対応 |
| --- | --- |
| I1 列挙側のパス NFC 化が未検証 | NFD 名のディレクトリ・ファイルで NFC の exclude/include が効くテスト(名前を保てない FS では skip) |
| I2 多セグメントの exclude がルート相対パス全体に当たることが未検証 | `*.md`(`sub/a.md` が残る)、`docs/*.tmp.md` のテスト |
| I3 `scandir` を閉じること(CFS-P-12)が未検証 | `ScriptedFsOps` に開いている数の記録(明示的な `__enter__`/`__exit__` のクラス。ジェネレータ形式の `contextmanager` だと参照が尽きて閉じてしまい検出できなかったため改修)。10階層で同時に開くのは1つ、終了時・失敗後・close 後は0 |
| I4 サイズだけの変更検出(#17)が未検証 | フック内で `write_bytes` 後に `os.utime` で mtime を戻し、サイズだけが変わった状態を作る |
| S1〜S9、Nitpick | 説明文に本文が入らないこと、読み取り上限の off-by-one(`bytes_read == max_bytes+1`)、open フラグの完全一致、errno 否定側(`ENAMETOOLONG`・`EISDIR`・`ENXIO`・`ENOMEDIUM`)、root 失敗を `follow_symlinks` 両方で、FIFO テストに `run_with_deadline`、DOTALL・`st_dev`・設定値検証、弱いアサーションの強化、close 後の `next`、日本語・絵文字の名前、自己同値テストの削除、JSON の注記修正、`skip_unless_linux` を能力判定 `create_names_or_skip` に 等を対応 |

## 2. 2回目のレビュー

- code-reviewer: 前回の指摘6件はすべて解消。「指摘なし」
- test-reviewer: 前回の Important 4件は解消(変異60件中55件検出、残り5件は等価または軽微)。「軽微な修正で可」。**新規 Important R1**: `max_double_stars` は `**` だけを数えるため、1セグメント内に `*` を並べたパターン(`*a*a*a*a*a*a*b` を `'a'*60+'c'` に照合で、6組1.8秒、10組超で戻らない)の ReDoS を防げていない。時間テストも `**` だけを見ていて誤った安心を与える。S10: Linux で能力判定の skip が黙って起きうる

## 3. 3回目の修正と再レビュー

### R1 への対応: glob 照合の置き換え(`connectors/filesystem/patterns.py` を書き直し)

- 個数上限の追加は設計書にない設定値を増やすため、**照合そのものをバックトラックの爆発しない実装に置き換えた**。セグメント内の `*`・`?` は貪欲な2ポインタ法(最後の `*` の位置だけに戻る)、セグメント間は「到達しうるパスのセグメント位置の集合」を持ち、`**`(ゼロ個以上の空でないセグメント)は位置を進める。末尾の `**` は即一致。`GlobPattern(segments).matches(nfc_relative_path)`。
- `max_double_stars` を削除(`FileSystemSettings`・`find_pattern_violation`・config.py・テスト)。`**` が単独セグメントでないもの・隣り合う `**` の拒否(FS 設計書 2.2)は残る。
- 挙動(FS 2.3 の11行の表、NFC 化、改行を含む名前、`*`・`?` が `/` に当たらない)は不変。
- 実装担当の差分テスト: 旧正規表現実装と比較して 2,669,340 組(網羅 2,069,340+ランダム 600,000)で不一致 0。リポジトリには、独立した素朴な再帰実装との突き合わせ(15,000組超)と61件の固定ケース表を残した。
- 性能(実測): `("*a"*30)+"*b"` vs 60/255 文字 0.03〜0.05 ms、`**/a/` 204組(1021バイト)vs 深さ200 約13.5 ms。テスト閾値 0.5秒(実測の10倍以上の余裕)。旧実装は `*a` 6組で2.0秒、7組で13.6秒。

### code-reviewer の再々レビュー(マッチャに絞る): 「可」(指摘なし)

- 照合の正しさ(FS 2.3 の表26ケース、`**` の末尾・途中、`_skip_segments`・`covered_up_to`、前提の「空でないセグメント」を検証・列挙側が満たす)を確認。
- **独立した素朴な実装(メモ化再帰)と設計書 2.3 の正規表現変換との差分テスト**を自分で書いて比較: 網羅 193,120組+ランダム 200,000組、**不一致 0**。
- 時間計算量は多項式。実測: `*a` 500組 vs 255文字 0.000秒、`**` と `*a` 交互(995バイト)vs 2000セグメント(3999バイト)0.51秒、`**/a` 170組 vs 2000セグメント 0.27秒。
- **Suggestion(対応しない。記録のみ)**: 細工した最悪に近い入力(1024バイトのパターンと4096バイトのパス)で 0.2〜0.5 秒/件/パターン。100パターンを細工し名前も特殊な形に揃えた場合に限り影響し、管理者が自分で設定する値で MVP は認証なしのため通常運用では起きない。必要になれば (a) パスのセグメント数がパターンの `**` 以外のセグメント数に満たなければ即 `False`、(b) `max_pattern_bytes` の既定値を下げる、を検討。

### その他の修正

- S10: 環境変数 `LORELEY_REQUIRE_LINUX_NAMES=1` のとき、`create_names_or_skip` は skip せず `pytest.fail`(それ以外は従来どおり skip)。macOS で `=1` を付けると該当3件が失敗することを確認。**README(P9)に記載する**
- 改行テストを、ファイル名・ディレクトリ名の改行を実際に検証する形に修正。取得の説明文テストの `or` 連結を3テストに分割。`close()` 後の `next()`(完了後は保持した `Completed`、未完了で close ならストリームの `RuntimeError` を `connector_internal_error` として保持)をテストで固定

## 4. 検証結果(メインが再実行、`apps/crawler`)

```
$ uv run pytest -q           -> 1488 passed, 3 skipped in 10.20s(P3 実装直後 1395 → 1446 → 1488)
$ uv run ruff check          -> All checks passed!
$ uv run ruff format --check -> 126 files already formatted
$ uv lock --check            -> Resolved 39 packages
```

- skip 3件(macOS・uid 501): 非 UTF-8 名、大文字小文字だけが違う名前、NFC/NFD の併存(skip メッセージに実測の理由 `Illegal byte sequence`/`File exists`)。
- **Linux での実行(skip の3件が Linux で検証される根拠)**: Docker 20.10.13、`python:3.12-slim-bookworm`、`pip install pytest` のみ、リポジトリは `:ro` マウントしてコンテナ内の `/tmp/w` にコピー、`--rm`。実装担当のスクリプトを scratchpad の `docker-run.sh` に置いた(リポジトリには入れていない)。内容:
  ```
  set -e
  python -m venv /opt/v >/dev/null
  /opt/v/bin/pip install -q pytest >/dev/null 2>&1
  rm -rf /tmp/w && mkdir /tmp/w && cp -R /work/src /work/tests /work/pyproject.toml /tmp/w/
  chmod -R a+rwX /tmp/w
  # root で pytest、続けて useradd -m tester → su tester で pytest(-p no:cacheprovider -rs tests/connectors tests/documents tests/architecture)
  ```
  実行コマンド: `docker run --rm -e LORELEY_REQUIRE_LINUX_NAMES=1 -v "$PWD":/work:ro -v <scratchpad>/docker-run.sh:/run.sh:ro python:3.12-slim-bookworm sh /run.sh`(`apps/crawler` で)。
  結果(実装担当の最終実行): **非 root(uid 1000)840 passed・skip 0**(Linux 専用テストと権限エラーのテストを全て含む)、root 835 passed・5 skipped(権限エラーのテスト5件)。test-reviewer も2回目のレビューで独自に再実行し、非 root で skip 0 を確認(538 passed、変更前の範囲)。
- メインは、Docker コンテナ・不要なプロセス・`.bak` の残りがないこと、`git status` が `apps/crawler/` のみであることを確認。

## 5. 0008 の記述の訂正

0008 §4 の「スレッド・スリープなし」は不正確。`tests/connectors/filesystem/support.py` の `run_with_deadline` は daemon スレッドと `join(10)` を使う(FIFO を開いて戻らない退行をハングでなく失敗にするため)。`sleep` は使っておらず、順序の待ちに時間を使うテストはない。

## 6. 設計書の改版依頼リスト(提案。P3 分)

1. **FS 設計書 2.3・9.1・9.2**: 実装が正規表現を使わなくなった。2.3 の「正規表現への変換」、9.1 の「NFC にして正規表現にコンパイル」、9.2 の「`re.fullmatch` で照合」は実装と食い違う。意味(2.3 の表の11行)は変わらないので、「意味を満たせば実装方式は問わない」と書き換えるか、「照合は多項式時間のアルゴリズム(正規表現のバックトラックを使わない。照合は中断できず Job Runner が止まるため)。セグメント内は貪欲な2ポインタ法、セグメント間は到達位置の集合」に改める。あわせて 2.2 の隣り合う `**` の拒否理由に「照合の負荷」を残すか見直す(現実装は隣り合う `**` も照合でき、拒否理由は意味の一意性のみ)。
2. **interface 3.2・6.1**: 想定外の例外の変換では元の例外を連鎖に残さない(`from None`。分類済み errno 変換も同じ)。R11 の根拠: `OSError` のファイル名 repr(未加工のパス)や値の repr が `logger.exception` でログに出ないようにするため。必要な情報は説明文(型名・errno 名・エスケープ済みパス)が持つ。トレードオフ: 元の例外の発生箇所(ファイル・行)は失われる。診断が必要なら P6 の `crawl` が `traceback.extract_tb(error.__context__.__traceback__)` から「ファイル名:行番号:関数名」だけを出す方法がある(code-reviewer の任意提案)。
3. **module 4.7(`documents`)**: 取得の包みは、Connector の戻り値の検査と後処理も `connector_internal_error`(document)の変換範囲に含める。列挙の包みは `Completed` を受けた後は Connector を呼ばず `Completed` を返す。列挙の包みの結果は3種(`EnumeratedDocument`・`InvalidExternalId`・`Completed`)と `EnumerationTooLargeError`(0008 §3)。
4. **FS 設計書 10章**: テスト実行環境の注意を「OS の名前ではなく、実際に作成できるかで判定する」に直し、`LORELEY_REQUIRE_LINUX_NAMES=1` で Linux 専用のテストを失敗扱いにできることを書く。
5. (0008 §8)FS エンコーディングの確認を `FsOps` 経由で `create` に置いたこと(CFS-P-22 の選択)。

## 7. 持ち越し・未対応事項

- 実機でしか確認できない項目(0008 §7): NFS/SMB・Docker バインドマウントでのマウント外れの errno と症状、集合 T の妥当性、`st_ino` の信頼性、ブロッキング I/O 中のスレッド挙動、実運用イメージの FS エンコーディング、`:ro` マウント。
- 照合の最悪入力での絶対時間(0.2〜0.5 秒/件/パターン。§3)は許容として記録。

## 8. 次のアクション

P4(`sources`・`jobs/records`・`jobs/locks`)を `code-implementer` に依頼する。**0007 §4 の申し送り(sort は `document_id` で終える、`pit_expired` は `with scan` 全体をやり直す、リトライ後の `AlreadyExists`/`Conflict` は所有者を読み直す、`Conflict` は記録なしも含む、`StoreUnexpectedResponseError` の扱い)と、0008 §6(P6 向け)を依頼に含める。**
