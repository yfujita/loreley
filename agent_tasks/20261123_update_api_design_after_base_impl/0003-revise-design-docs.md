# 0003 P2・P3 設計書 D・A・B・C の改訂

作成: 2026-11-23(メインエージェント)

## 実施内容

### P2: D の改訂(document-writer。agent a7066500ee69189bc)

`admin/admin-api-module-structure-v0.1.md` を直接改訂した(0001 の 4 節 P2 の 1〜12)。`git diff --stat c0b6e40` で D 以外・`apps/` に変更がないことを確認した。

- 冒頭(版・HO-1〜HO-51・関連 HO を HO-39・HO-48・HO-49・HO-51 に・改訂履歴・「実装との関係」)、関連文書の表(`apps/api/` の行)
- 1章、2.1(図・注)、3章、4.1、4.2(見出し「`server`・`health`」)、4.11、4.12(新設)、5.9、6章(R1・R2・R3・R5・R9・R10・R11、許可表)、7章(7.1〜7.4)、8章(8.1、8.2 に AAM-K-5 を新設、8.3 の AAM-P-2・P-3・P-14・P-17・P-23、8.4 の AAM-U-2・U-6・U-9、8.7)
- AAM-K-5 の出典は「ユーザー回答(2026-11-23)。0001-work-plan.md の 0 節」。AAM-U-2 は行を残して確定(AAM-K-5 に移した)。AAM-P-23 は新方式に改め、区分欄に経緯を記載。
- writer の報告にある HO-51 内訳の反映先は、メインエージェントが 0001 の P2 と照合した(P4 で実装との突き合わせを行う)。
- 事実確認: FastAPI 0.165.0・Starlette 1.10.0・anyio 4.16.0・uvicorn 0.54.0(`uv.lock`)、`uv run pytest` 310 passed。

### P3: A・B・C の改訂(メインエージェント)

- A(`api-base-design-v0.1.md`):
  - 版の欄、改訂履歴の追記
  - 5.4: BAPI-U-2 の参照を P-d に合わせ、OpenAPI の生成元・422 の宣言・`openapi_url` の明示を追記(P-f)
  - 5.5: 500 変換の保証は応答の開始前の例外に限る(P-f)
  - 7章の層: `server`・`health` を追加
  - 9.2: HO-48(AAM-U-2 は確定。BAPI-U-2 は絞って残る)、HO-51(状態「対応済み」、「確認済み(2026-11-23)」)、HO-51 内訳(確認済みの追記、他文書の表記は更新済み)
  - 10.1「確認していないこと」: OpenAPI の `servers`・`paths` に限定
  - 10.4: BAPI-U-2 を OpenAPI の `servers`・`paths` に絞った
  - 10.3 の BAPI-P-18 の行は、要約の記述が 7章と矛盾しないため変更なし
- B・C: 「HO-1〜HO-50」を「HO-1〜HO-51」にし、改訂履歴に追記(更新日は 2026-11-23 のまま)。
- 残った `HO-1〜HO-50` は、A の改訂履歴・A 253 行(HO-51 の説明)・A 383 行(改訂の記述)・B の改訂履歴の過去の記述のみ(経緯の記録として残す)。

## 判断・設計上の理由

- A 7章の層は D の順序(エントリ → `server` → 機能パッケージ → …)に揃えた(writer の指摘への対応)。
- 更新日はすべて 2026-11-23(もともと同日)。

## 変更したファイル

- `docs/v0.x/system-design/api/admin/admin-api-module-structure-v0.1.md`
- `docs/v0.x/system-design/api/api-base-design-v0.1.md`
- `docs/v0.x/system-design/api/admin/admin-api-v0.1.md`
- `docs/v0.x/system-design/api/admin/admin-api-architecture-v0.1.md`

## 未対応事項・次にやること

- P4(実装との突き合わせ)、P5(grep)、document-reviewer、task-reviewer
- `apps/api/README.md` 冒頭の「実装は D と一部異なる…D を追従改訂するまでは実装を正とする」が古くなった。`apps/` の変更はスコープ外(完了条件 7)のため触らない。最終報告でユーザーに伝え、別途対応を判断してもらう
- mermaid 図(D 2.1・5.9)は描画ツールがなく目視確認のみ
- 範囲外: E・F の「HO-1〜HO-50」、HO-39 の状態、BAPI-U-2 のうち OpenAPI の `servers`・`paths`
