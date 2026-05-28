const GENERIC_TYPE_VALUES = new Set([
  '',
  'entity',
  'upload',
  'node',
  'naturalobject',
  'unknown',
  'unknown_source',
  'null',
  'undefined',
  '未分类',
  '未识别类型'
])

const EMPTY_TYPE_VALUES = new Set([
  '',
  'unknown',
  'unknown_source',
  'null',
  'undefined',
  '未分类',
  '未识别类型'
])

const GENERIC_SOURCE_VALUES = new Set([
  '',
  'unknown',
  'unknown_source',
  'null',
  'undefined'
])

const RENDER_EDGE_TYPES = new Set([
  'arc',
  'cubic',
  'cubic-horizontal',
  'cubic-radial',
  'cubic-vertical',
  'edge',
  'line',
  'loop',
  'polyline',
  'quadratic'
])

const NODE_SOURCE_TYPE_FIELDS = [
  'type',
  'raw_type',
  'source_type',
  'original_type',
  'entity_type_from_source',
  'data_type',
  'entity_type',
  'display_type',
  'category'
]

function normalizeText(value) {
  return String(value ?? '').trim()
}

function normalizeLower(value) {
  return normalizeText(value).toLowerCase()
}

function isMeaningfulType(value) {
  const normalized = normalizeLower(value)
  return Boolean(normalized) && !GENERIC_TYPE_VALUES.has(normalized)
}

function isNonEmptyType(value) {
  const normalized = normalizeLower(value)
  return Boolean(normalized) && !EMPTY_TYPE_VALUES.has(normalized)
}

function isMeaningfulSource(value) {
  const normalized = normalizeLower(value)
  return Boolean(normalized) && !GENERIC_SOURCE_VALUES.has(normalized)
}

function collectLayers(source) {
  if (!source || typeof source !== 'object') return []

  const layers = []
  const seen = new Set()
  const queue = [source]

  while (queue.length > 0 && layers.length < 32) {
    const current = queue.shift()
    if (!current || typeof current !== 'object' || seen.has(current)) continue

    seen.add(current)
    layers.push(current)

    const nextLayers = [
      current.data,
      current.properties,
      current.original,
      current.raw,
      current.h,
      current.t,
      current.raw?.h,
      current.raw?.t,
      current.data?.raw,
      current.data?.h,
      current.data?.t,
      current.data?.raw?.h,
      current.data?.raw?.t
    ]

    for (const next of nextLayers) {
      if (next && typeof next === 'object' && !seen.has(next)) {
        queue.push(next)
      }
    }
  }

  return layers
}

function pickFirstMeaningfulField(layers, fieldName) {
  for (const layer of layers) {
    const value = layer?.[fieldName]
    if (isMeaningfulType(value)) return normalizeText(value)
  }
  return ''
}

function pickMeaningfulLabel(layers) {
  for (const layer of layers) {
    const labels = layer?.labels
    if (!Array.isArray(labels)) continue

    for (const label of labels) {
      if (isMeaningfulType(label)) return normalizeText(label)
    }
  }

  return ''
}

function collectFieldValues(layers, fieldNames) {
  return layers.flatMap((layer) => fieldNames.map((fieldName) => layer?.[fieldName]))
}

function collectRelationTypeValues(source, values = [], seen = new Set()) {
  if (!source || typeof source !== 'object' || seen.has(source)) return values

  seen.add(source)
  values.push(
    source.relationTypes,
    source.relation_types,
    source.relation_type,
    source.data?.relationTypes,
    source.data?.relation_types,
    source.data?.relation_type,
    source.properties?.type,
    source.properties?.relation_type,
    source.raw?.r?.type,
    source.r?.type
  )

  // GraphCanvas edges also carry `type`, but that field is the G6 renderer type there.
  if ((source.source_id || source.target_id || !source.data) && !isRenderEdgeType(source.type)) {
    values.push(source.type)
  }

  const relatedSources = [
    source.original,
    source.raw,
    source.data?.original,
    source.data?.originals,
    source.originals,
    source.relationships
  ]

  for (const relatedSource of relatedSources) {
    if (Array.isArray(relatedSource)) {
      relatedSource.forEach((item) => collectRelationTypeValues(item, values, seen))
    } else {
      collectRelationTypeValues(relatedSource, values, seen)
    }
  }

  return values
}

function isRenderEdgeType(value) {
  return RENDER_EDGE_TYPES.has(normalizeLower(value))
}

function inferNodeTypeFromText(source) {
  const layers = collectLayers(source)
  const text = layers
    .flatMap((layer) => [
      layer?.name,
      layer?.title,
      layer?.label,
      layer?.description,
      layer?.summary,
      layer?.abstract,
      layer?.content,
      layer?.display_type,
      layer?.entity_type,
      layer?.type,
      layer?.category,
      layer?.graph_type
    ])
    .filter(Boolean)
    .map(normalizeLower)
    .join(' ')

  if (!text) return ''

  if (
    text.includes('gibberellic acid') ||
    text.includes('hormone') ||
    text.includes('substance') ||
    text.includes('compound') ||
    text.includes('ga')
  ) {
    return text.includes('substance') || text.includes('compound') ? 'compound' : 'concept'
  }

  if (
    text.includes('rg') ||
    text.includes('nf-kb') ||
    text.includes('regulation') ||
    text.includes('regulatory')
  ) {
    return 'concept'
  }

  if (
    text.includes('fusion protein') ||
    text.includes('protein') ||
    text.includes('蛋白')
  ) {
    return 'protein'
  }

  if (
    text.includes('chromatin immunoprecipitation') ||
    text.includes('chip') ||
    text.includes('method') ||
    text.includes('analysis') ||
    text.includes('technique') ||
    text.includes('rna-seq') ||
    text.includes('transcriptome') ||
    text.includes('expression')
  ) {
    return 'method'
  }

  if (
    text.includes('pathway') ||
    text.includes('biosynthesis') ||
    text.includes('regulation')
  ) {
    return 'pathway'
  }

  if (
    text.includes('metabolome') ||
    text.includes('metabolomic') ||
    text.includes('metabolite') ||
    text.includes('compound') ||
    text.includes('flavonoid')
  ) {
    return text.includes('metabolite') || text.includes('compound') ? 'metabolite' : 'data'
  }

  if (
    text.includes('marker') ||
    text.includes('snp') ||
    text.includes('indel') ||
    text.includes('kasp') ||
    text.includes('caps')
  ) {
    return 'marker'
  }

  if (
    text.includes('crop') ||
    text.includes('millet') ||
    text.includes('rice') ||
    text.includes('wheat') ||
    text.includes('maize') ||
    text.includes('sorghum') ||
    text.includes('organism') ||
    text.includes('species')
  ) {
    return 'organism'
  }

  if (
    /(^|\W)(gene|genes)(\W|$)/.test(text) ||
    /(^|\W)oswrky\d+/i.test(text) ||
    /(^|\W)si\d+/i.test(text) ||
    text.includes('基因')
  ) {
    return 'gene'
  }

  if (text.includes('concept')) return 'concept'

  return ''
}

export function normalizeBusinessType(raw) {
  if (!isMeaningfulType(raw)) return ''

  const normalized = normalizeLower(raw)
  if (normalized === 'substance') return 'compound'
  if (normalized === 'chemical') return 'compound'
  if (normalized === 'hormone') return 'concept'
  if (normalized === 'pathway regulation') return 'regulation'
  if (normalized === 'relationship') return 'relation'

  return normalizeText(raw)
}

export function formatBusinessTypeForDisplay(type) {
  const normalized = normalizeBusinessType(type)
  return normalized
}

export function getBusinessType(source) {
  return getNodeInferredType(source)
}

export function normalizeTypeValues(values) {
  const rawValues = Array.isArray(values) ? values : [values]
  const splitValues = rawValues.flatMap((value) => {
    if (Array.isArray(value)) return normalizeTypeValues(value)

    return String(value ?? '')
      .split(/\s*\/\s*|[;,|、]+/)
      .map((item) => item.trim())
      .filter(Boolean)
  })

  return Array.from(new Set(splitValues.filter(isNonEmptyType)))
}

export function getNodeSourceType(source) {
  if (!source || typeof source !== 'object') return ''

  const values = normalizeTypeValues(
    collectFieldValues(collectLayers(source), NODE_SOURCE_TYPE_FIELDS)
  )

  return values[0] || ''
}

export function getNodeDisplayType(source) {
  if (!source || typeof source !== 'object') return ''

  const sourceType = getNodeSourceType(source)
  if (sourceType) return sourceType

  const labels = getNodeGraphLabels(source)
  if (labels.length > 0) return labels[0]

  return getNodeInferredType(source)
}

export function getNodeGraphLabels(source) {
  if (!source || typeof source !== 'object') return []

  const labels = collectLayers(source).flatMap((layer) =>
    Array.isArray(layer?.labels) ? layer.labels : []
  )

  return normalizeTypeValues(labels).filter(isMeaningfulType)
}

export function getNodeInferredType(source) {
  if (!source || typeof source !== 'object') return ''

  const layers = collectLayers(source)
  const directValue =
    pickFirstMeaningfulField(layers, 'display_type') ||
    pickFirstMeaningfulField(layers, 'entity_type') ||
    pickFirstMeaningfulField(layers, 'type') ||
    pickFirstMeaningfulField(layers, 'category') ||
    pickMeaningfulLabel(layers) ||
    pickFirstMeaningfulField(layers, 'graph_type')

  if (directValue) return formatBusinessTypeForDisplay(directValue)

  return formatBusinessTypeForDisplay(inferNodeTypeFromText(source))
}

export function getDisplayTags(source) {
  return getNodeGraphLabels(source)
}

export function getRelationDisplayType(edge) {
  return getRelationSourceTypes(edge)[0] || ''
}

export function getRelationDisplayTypes(edge) {
  return getRelationSourceTypes(edge)
}

export function getRelationSourceTypes(edge) {
  const sourceTypes = normalizeTypeValues(collectRelationTypeValues(edge))
    .map((value) => normalizeText(value))
    .filter(Boolean)

  return Array.from(new Set(sourceTypes))
}

export function getSourceDisplayValue(source) {
  if (!source || typeof source !== 'object') return ''

  const layers = collectLayers(source)
  const keys = ['kg_source', 'source_file', 'source', 'file', 'chunk_source', 'graph_source', 'dataset']

  for (const key of keys) {
    for (const layer of layers) {
      const value = layer?.[key]
      if (isMeaningfulSource(value)) return normalizeText(value)
    }
  }

  return ''
}
