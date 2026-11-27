import { resolve } from 'node:path'

import { ESLint } from 'eslint'

/** apps/web。リポジトリ直下から `--root apps/web` で実行しても、このファイルの位置から決まる。 */
export const WEB_DIR = resolve(import.meta.dirname, '../..')

/** 実際の eslint.config.js を読む ESLint(依存ルールのテストが、設定そのものを検査するため)。 */
export const eslint = new ESLint({ cwd: WEB_DIR })
