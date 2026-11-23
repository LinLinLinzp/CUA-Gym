import { byPosition, geometryOf } from './data/model.js'

export function indexPreviews(pages, layers) {
  const firstPages = new Map()
  for (const page of Array.isArray(pages) ? pages : []) {
    if (!page?.fileId || !page.id) continue
    const current = firstPages.get(page.fileId)
    if (!current || byPosition(page, current) < 0) firstPages.set(page.fileId, page)
  }
  const previews = new Map()
  for (const layer of Array.isArray(layers) ? layers : []) {
    if (!layer?.id || firstPages.get(layer.fileId)?.id !== layer.pageId) continue
    if (!previews.has(layer.fileId)) previews.set(layer.fileId, [])
    previews.get(layer.fileId).push(layer)
  }
  for (const layers of previews.values()) layers.sort(byPosition)
  return previews
}

export function Preview({ layers = [], compact }) {
  const artwork = layers.slice(0, 64).map((layer) => ({ layer, box: geometryOf(layer) }))
  if (!artwork.length) return <div className={'preview preview-blank' + (compact ? ' swatch' : '')} aria-hidden="true"><span>◇</span></div>

  const left = Math.min(...artwork.map(({ box }) => box.x))
  const top = Math.min(...artwork.map(({ box }) => box.y))
  const width = Math.max(...artwork.map(({ box }) => box.x + box.width)) - left
  const height = Math.max(...artwork.map(({ box }) => box.y + box.height)) - top
  const ratio = 9 / 16
  const scale = Math.min(80 / width, 80 * ratio / height)
  const centerX = left + width / 2
  const centerY = top + height / 2
  return <div className={'preview' + (compact ? ' swatch' : '')} aria-hidden="true">
    <div className="preview-sheet">
      {artwork.map(({ layer, box }) => <span key={layer.id} className={'preview-layer ' + (layer.kind === 'text' ? 'preview-text' : '')}
        style={{ left: 50 + (box.x - centerX) * scale + '%',
          top: 50 + (box.y - centerY) * scale / ratio + '%',
          width: box.width * scale + '%', height: box.height * scale / ratio + '%',
          backgroundColor: layer.fill || undefined }}>
        {!compact && layer.text}
      </span>)}
    </div>
  </div>
}
