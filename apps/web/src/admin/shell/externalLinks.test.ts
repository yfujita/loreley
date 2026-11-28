import { describe, expect, it } from 'vitest'

import { externalLinks, toSafeExternalUrl } from './externalLinks'

describe('externalLinks(AF-20。外部リンクの定義表)', () => {
  it('MVP は OpenSearch Dashboards 1 件で、URL の取得元は /meta の dashboards_url', () => {
    expect(externalLinks).toHaveLength(1)
    expect(externalLinks[0]).toMatchObject({
      id: 'opensearch-dashboards',
      label: 'OpenSearch Dashboards',
      source: 'dashboards',
    })
  })
})

describe('toSafeExternalUrl(設定の URL を、リンクにしてよいか)', () => {
  it.each([
    ['http://localhost:5601', 'http://localhost:5601'],
    [
      'https://dashboards.example.internal/app/home',
      'https://dashboards.example.internal/app/home',
    ],
  ])('http・https は、設定された値のままリンクにする: %s', (value, expected) => {
    expect(toSafeExternalUrl(value)).toBe(expected)
  })

  it.each([
    null,
    '',
    'localhost:5601',
    '/relative/path',
    'javascript:alert(1)',
    'data:text/html,<script>1</script>',
    'ftp://example.com',
    'not a url',
  ])('それ以外(未設定・相対・javascript: など)は null: %j', (value) => {
    expect(toSafeExternalUrl(value)).toBeNull()
  })
})
