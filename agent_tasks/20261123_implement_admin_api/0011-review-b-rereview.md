# 0011 レビュー R-B 再レビューの結果

日付: 2026-11-24

## 結果

比較基準 `d681ae8..5dc68c4`(指摘対応コミット)。`test-reviewer` が再レビュー(Important I1・I2 の解消確認)。`code-reviewer` は R-B で Important なし、`src` の変更も Nitpick の 14 行のみのため再レビュー不要と判断した。

- **test-reviewer: 指摘なし**(Critical 0 / Important 0 / Suggestion 1 / Nitpick 2)
  - I1・I2 は実質的に解消。HEAD の複製でのミューテーション 5 件(`_judge_after_confirmation` (a) を狭める、`refreshed_job` を `if False:`、EP-01・02 側の `job_fields` を `('status',)`、EP-10 の `job_fields`、EP-10 の `brief` 再構築を落とす)をすべて検出。`job_queries.py:137-138` の行カバレッジの穴も塞がった
  - S1・S2・S4・S5・S6 は意味のあるアサーションを持つ(Protocol 整合、R7 の相対 import、非既定索引名の配線、ヘルパー集約)。`on_nth_call` の移動に副作用なし
  - pytest 1956 passed。逆順・シャッフル(seed 777・4242)でも 1956 passed。順序依存・グローバル状態の汚染・フレークなし

## 判断(Suggestion・Nitpick)

- S-a(Protocol 整合テストが `inspect._ParameterKind`・`_is_protocol` の非公開 API に依存): 3.12 固定の現状は許容。Python を上げるときに `typing.is_protocol` へ置き換える(コメントで 3.12 前提と明記するのは P5 の取り込み分に含める)
- N-a(`known_operations` の有無が fake ごとに異なる): P5 で Crawler の fake を足すときに同様の `OPERATIONS` を持たせて打ち間違いを防ぐ
- N-b(成功パスのアクセスログ確認): P7 のスモークで確認(0010 のとおり)

## 結論

R-B の Critical・Important はすべて解消。P5 に進む。

## 次にやること

- P5(書き込み系 EP-03〜08・Crawler 中継)。最初に Crawler の実 API と B 9.2 を突き合わせる。`SourceSettings` の共用の扱いを判断する
