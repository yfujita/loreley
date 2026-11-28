// E2E の dev サーバーの場所。`playwright.config.ts` と各 spec が共有する(ポートの重複定義を避ける)。
// 専用ポート: 手動確認・UI レビュー用の dev サーバー(5173)と衝突させず、既存のサーバーも再利用しない。
export const E2E_PORT = 15173
export const E2E_HOST = `localhost:${E2E_PORT}`
/** 末尾のスラッシュが要る(相対 `goto` が `/admin/` の下に解決されるため)。 */
export const E2E_BASE_URL = `http://${E2E_HOST}/admin/`
