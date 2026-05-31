/**
 * 前端辅助函数层
 * 应用于页面主控的整体辅助逻辑架构：
 * BreedingWorkbenchView.vue
 * │
 * ├── 负责页面输入和结果展示
 * ├── 调用 breedingWorkbenchApi.runBreedingWorkbench()
 * ├── 接收 result.markdown / toolChain / diagnostics
 * │
 * └── 调用 breedingWorkbench.js：
 *     ├── DEFAULT_SMOKE_BREEDING_CONTEXT 初始化默认表单
 *     ├── REQUIRED_BREEDING_FIELDS 做必填校验
 *     ├── extractLiteratureEvidence 解析 legacy DOI 卡片
 *     ├── evaluateBreedingCompliance 提供 legacy 合规检查兜底
 *     ├── downloadMarkdown 下载建议
 *     └── downloadTsv 下载 TSV
 */

// 这个文件在链路中的作用：
// 1. 保存育种工作台 smoke 默认输入上下文；
// 2. 解析最终 markdown 里的 DOI 和引用原句；
// 3. 提供 legacy 页面侧合规检查兜底；
// 4. 提供 Markdown / TSV 下载工具。
//
// 它不负责 Tool 调用，也不负责生成育种建议。
// 可以把它理解为“工作台结果展示的纯前端辅助层”。


/**
 * 默认 smoke 输入
 * 这就是当前工作台的 smoke 示例配置。
 * 仍然强绑定学长给的 Si9g037800 smoke 数据包。
 * TODO：未来多性状扩展时，这里不应该继续写死，而应该来自 TraitProfile 或后端任务配置。
 * */
export const DEFAULT_SMOKE_BREEDING_CONTEXT = {
  data_dir: '/mnt/yuxi-breeding-data/smoke_test_minimal/Si9g037800_smoke_test_minimal',
  reference_genome: 'genome.fa',
  genome_gff: 'genome.gff',
  function_annotation: 'xiaomi_T2T_Annotation.smoke_genes.txt',
  rnaseq_reads: 'fq/*.fq.gz',
  sample_map: 'sampleName_clientId.txt',
  usage_doc: 'USAGE_run_smoke_de_pipeline.md',
  metabolome_tsv: 'metabolome_raw_3372.tsv',
  transcriptome_result_path: 'significant_de_genes.tsv',
  literature_evidence_path: 'verified_literature_evidence.tsv',
  trait: '黄酮相关',
  user_question: '给出一些育种建议'
}

/**
 * 必填字段 用于 validateRequiredFields() 检查页面左侧提交栏不可空字段
 * */
export const REQUIRED_BREEDING_FIELDS = [
  { key: 'reference_genome', label: '参考基因组' },
  { key: 'genome_gff', label: '基因组注释' },
  { key: 'rnaseq_reads', label: 'RNA-seq Reads' },
  { key: 'sample_map', label: '数据标签' },
  { key: 'metabolome_tsv', label: '代谢含量' },
  { key: 'trait', label: '性状输入' },
  { key: 'user_question', label: '用户问题' }
]

const DOI_REGEX = /10\.\d{4,9}\/[^\s，,；;）)\]】"'“”‘’]+/gi

const normalizeQuotedText = (value = '') => value.replace(/^[“"'‘’\s]+|[”"'‘’\s]+$/g, '').trim()
const cleanDoiValue = (value = '') => value.replace(/[，,；;。)\]】>"'“”‘’]+$/g, '').trim()

/**
 * 下载函数  把前端已有文本内容生成浏览器下载文件。
 * */
// 这个函数只负责浏览器下载，不参与任何业务判断。
// 输入是文件名、文本内容和 MIME 类型；输出是触发浏览器下载。
const downloadContent = (filename, content, mimeType) => {
  const blob = new Blob([content], { type: mimeType })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  anchor.click()
  URL.revokeObjectURL(url)
}

/**
 * DOI 和引用原句解析
 * */
// 这个函数在页面拿到最终 markdown 后被调用。
// 输入：最终智能体输出 Markdown
// 输出：文献卡片数组 [{ doi, quote, title }]
// 它在链路中的位置是“前端读取真实最终结果，再从中提取 DOI 和引用原句”。
//
// 这里不允许前端自由编造文献字段，只能从已存在的 markdown 文本中解析。
// 兼容多种标签写法，是因为不同模型或模板可能会把“引用原文”写成不同字段名。
export const extractLiteratureEvidence = (markdown = '') => {
  if (typeof markdown !== 'string' || !markdown.trim()) return []

  const blocks = markdown
    .split(/\n(?=(?:###\s*)?(?:证据|Evidence)\s*\d+)/i)
    .map((item) => item.trim())
    .filter((item) => /(?:证据|Evidence)\s*\d+/i.test(item))

  const parsed = []
  for (const block of blocks) {
    const doiMatch = block.match(/(?:真实\s*)?DOI[：:]\s*(10\.\d{4,9}\/[^\s，,；;）)\]】"'“”‘’]+)/i)
    const quoteMatch = block.match(
      /(?:引用原文|引用原句|quoted_sentence|quote|原文|引用)[：:]\s*([^\n]+)/i
    )
    const doi = cleanDoiValue((doiMatch?.[1] || '').trim())
    const quote = normalizeQuotedText((quoteMatch?.[1] || '').trim())
    const title = (block.match(/(?:文献标题|title)[：:]\s*([^\n]+)/i)?.[1] || '').trim()
    if (!doi || !quote) continue
    parsed.push({ doi, quote, title })
  }

  if (parsed.length > 0) return parsed

  const lines = markdown.split('\n')
  const fallback = []
  for (let index = 0; index < lines.length; index += 1) {
    const doi = cleanDoiValue(
      (lines[index].match(/(?:真实\s*)?DOI[：:]\s*(10\.\d{4,9}\/[^\s，,；;）)\]】"'“”‘’]+)/i)?.[1] || '').trim()
    )
    if (!doi) continue

    let quote = ''
    let title = ''
    for (let inner = index + 1; inner < Math.min(index + 8, lines.length); inner += 1) {
      if (!quote) {
        quote = normalizeQuotedText(
          (
            lines[inner].match(/(?:引用原文|引用原句|quoted_sentence|quote|原文|引用)[：:]\s*([^\n]+)/i)?.[1] || ''
          ).trim()
        )
      }
      if (!title) title = (lines[inner].match(/(?:文献标题|title)[：:]\s*([^\n]+)/i)?.[1] || '').trim()
    }
    if (quote) fallback.push({ doi, quote, title })
  }

  const deduped = []
  const seen = new Set()
  for (const item of fallback) {
    const key = `${item.doi}::${item.quote}`
    if (!item.doi || !item.quote || seen.has(key)) continue
    seen.add(key)
    deduped.push(item)
  }
  return deduped
}

/**
 * Legacy 合规检查
 * */
// 新版 /breeding-workbench 已改为优先使用后端 frontend_payload，不再依赖固定 smoke 文本检查。
// 这里保留空结果，仅兼容 legacy demo 或旧调用方。
export const evaluateBreedingCompliance = () => []

// 这个函数在用户点击下载 breeding_advice.md 时被调用。
// 输入是文件名和 markdown 文本；输出是浏览器下载动作。
export const downloadMarkdown = (filename, content) => {
  downloadContent(filename, content, 'text/markdown;charset=utf-8')
}

// 这个函数在页面下载占位 TSV 时被调用。TODO：后续需要修改为实时读取文件下载
// 输入是文件名和 TSV 文本；输出是浏览器下载动作。
export const downloadTsv = (filename, content) => {
  downloadContent(filename, content, 'text/tab-separated-values;charset=utf-8')
}
