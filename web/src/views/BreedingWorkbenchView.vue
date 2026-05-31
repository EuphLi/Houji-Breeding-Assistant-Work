<template>
  <div class="breeding-workbench-page">
    <div class="workbench-body">
      <section class="config-panel">
        <div class="panel-intro">
          <h2>输入配置</h2>
          <p>
            左侧维护固定证据流程输入。选择文件后会先上传到 YuXi 工作区，再由后端使用服务端路径进入正式多组学育种分析链路。
          </p>
        </div>

        <div v-if="uploadedFileList.length" class="uploaded-files-card">
          <div class="uploaded-files-title">已上传文件</div>
          <div class="uploaded-files-list">
            <div v-for="item in uploadedFileList" :key="item.key" class="uploaded-file-item">
              <div class="uploaded-file-main">
                <span class="uploaded-file-label">{{ item.label }}</span>
                <span class="uploaded-file-name">{{ item.name }}</span>
                <span class="uploaded-file-status" :class="item.status">{{ item.statusLabel }}</span>
              </div>
              <code v-if="item.serverPath" class="uploaded-file-path">{{ item.serverPath }}</code>
            </div>
          </div>
        </div>

        <a-collapse v-model:activeKey="activePanels" ghost class="breeding-collapse">
          <a-collapse-panel key="reference" header="参考基因组">
            <div class="field-grid single-column-grid">
              <div class="field-item">
                <label class="field-label">参考基因组</label>
                <div
                  class="file-input-row"
                  :class="{ dragging: dragState.reference_genome }"
                  @dragover.prevent="dragState.reference_genome = true"
                  @dragleave.prevent="dragState.reference_genome = false"
                  @drop.prevent="handleFileDrop('reference_genome', $event)"
                >
                  <div class="file-input-control">
                    <a-input v-model:value="form.reference_genome" :disabled="running" />
                    <a-button
                      size="small"
                      :disabled="running"
                      @click="openFilePicker('reference_genome')"
                    >
                      添加文件
                    </a-button>
                  </div>
                  <input
                    :ref="(el) => registerFileInput('reference_genome', el)"
                    class="hidden-file-input"
                    type="file"
                    @change="handleSingleFileChange('reference_genome', $event)"
                  />
                </div>
              </div>

              <div class="field-item">
                <label class="field-label">基因组注释</label>
                <div
                  class="file-input-row"
                  :class="{ dragging: dragState.genome_gff }"
                  @dragover.prevent="dragState.genome_gff = true"
                  @dragleave.prevent="dragState.genome_gff = false"
                  @drop.prevent="handleFileDrop('genome_gff', $event)"
                >
                  <div class="file-input-control">
                    <a-input v-model:value="form.genome_gff" :disabled="running" />
                    <a-button
                      size="small"
                      :disabled="running"
                      @click="openFilePicker('genome_gff')"
                    >
                      添加文件
                    </a-button>
                  </div>
                  <input
                    :ref="(el) => registerFileInput('genome_gff', el)"
                    class="hidden-file-input"
                    type="file"
                    @change="handleSingleFileChange('genome_gff', $event)"
                  />
                </div>
              </div>

              <div class="field-item">
                <label class="field-label">基因功能注释</label>
                <div
                  class="file-input-row"
                  :class="{ dragging: dragState.function_annotation }"
                  @dragover.prevent="dragState.function_annotation = true"
                  @dragleave.prevent="dragState.function_annotation = false"
                  @drop.prevent="handleFileDrop('function_annotation', $event)"
                >
                  <div class="file-input-control">
                    <a-input v-model:value="form.function_annotation" :disabled="running" />
                    <a-button
                      size="small"
                      :disabled="running"
                      @click="openFilePicker('function_annotation')"
                    >
                      添加文件
                    </a-button>
                  </div>
                  <input
                    :ref="(el) => registerFileInput('function_annotation', el)"
                    class="hidden-file-input"
                    type="file"
                    @change="handleSingleFileChange('function_annotation', $event)"
                  />
                </div>
              </div>
            </div>
            <p class="hint-text">输出说明：无输出</p>
          </a-collapse-panel>

          <a-collapse-panel key="transcriptome" header="转录组">
            <div class="field-grid single-column-grid">
              <div class="field-item">
                <label class="field-label">RNA-seq Reads</label>
                <div
                  class="file-input-row"
                  :class="{ dragging: dragState.rnaseq_reads }"
                  @dragover.prevent="dragState.rnaseq_reads = true"
                  @dragleave.prevent="dragState.rnaseq_reads = false"
                  @drop.prevent="handleFileDrop('rnaseq_reads', $event, true)"
                >
                  <div class="file-input-control">
                    <a-input v-model:value="form.rnaseq_reads" :disabled="running" />
                    <a-button
                      size="small"
                      :disabled="running"
                      @click="openFilePicker('rnaseq_reads')"
                    >
                      添加文件
                    </a-button>
                  </div>
                  <input
                    :ref="(el) => registerFileInput('rnaseq_reads', el)"
                    class="hidden-file-input"
                    type="file"
                    multiple
                    accept=".fq,.fastq,.gz"
                    @change="handleMultiFileChange('rnaseq_reads', $event)"
                  />
                </div>
                <div v-if="selectedFiles.rnaseq_reads.length" class="file-chip-list">
                  <span
                    v-for="item in selectedFiles.rnaseq_reads"
                    :key="item.name"
                    class="file-chip"
                  >
                    {{ item.name }}
                  </span>
                </div>
              </div>

              <div class="field-item">
                <label class="field-label">数据标签</label>
                <div
                  class="file-input-row"
                  :class="{ dragging: dragState.sample_map }"
                  @dragover.prevent="dragState.sample_map = true"
                  @dragleave.prevent="dragState.sample_map = false"
                  @drop.prevent="handleFileDrop('sample_map', $event)"
                >
                  <div class="file-input-control">
                    <a-input v-model:value="form.sample_map" :disabled="running" />
                    <a-button
                      size="small"
                      :disabled="running"
                      @click="openFilePicker('sample_map')"
                    >
                      添加文件
                    </a-button>
                  </div>
                  <input
                    :ref="(el) => registerFileInput('sample_map', el)"
                    class="hidden-file-input"
                    type="file"
                    @change="handleSingleFileChange('sample_map', $event)"
                  />
                </div>
              </div>

              <div class="field-item">
                <label class="field-label">流程说明</label>
                <div class="file-input-row file-output-row">
                  <div class="file-output-note">
                    <span>固定转录组流程由后端执行，不接受前端上传流程说明文件。</span>
                  </div>
                </div>
              </div>

              <div class="field-item">
                <label class="field-label">差异显著基因结果</label>
                <div class="file-input-row file-output-row">
                  <div class="file-output-note">
                    <span><code>significant_de_genes.tsv</code> 只作为后端固定流程输出展示，不作为用户上传输入。</span>
                  </div>
                </div>
              </div>
            </div>
            <p class="hint-text">
              输入：<code>fq/*.fq.gz</code>、<code>sampleName_clientId.txt</code>、<code>genome.fa</code>、<code>genome.gff</code>；
              输出：后端固定流程生成 <code>significant_de_genes.tsv</code>
            </p>
          </a-collapse-panel>

          <a-collapse-panel key="metabolome" header="代谢组">
            <div class="field-grid single-column-grid">
              <div class="field-item">
                <label class="field-label">代谢含量</label>
                <div
                  class="file-input-row"
                  :class="{ dragging: dragState.metabolome_tsv }"
                  @dragover.prevent="dragState.metabolome_tsv = true"
                  @dragleave.prevent="dragState.metabolome_tsv = false"
                  @drop.prevent="handleFileDrop('metabolome_tsv', $event)"
                >
                  <div class="file-input-control">
                    <a-input v-model:value="form.metabolome_tsv" :disabled="running" />
                    <a-button
                      size="small"
                      :disabled="running"
                      @click="openFilePicker('metabolome_tsv')"
                    >
                      添加文件
                    </a-button>
                  </div>
                  <input
                    :ref="(el) => registerFileInput('metabolome_tsv', el)"
                    class="hidden-file-input"
                    type="file"
                    @change="handleSingleFileChange('metabolome_tsv', $event)"
                  />
                </div>
              </div>

              <div class="field-item">
                <label class="field-label">已验证文献证据（可选）</label>
                <div
                  class="file-input-row"
                  :class="{ dragging: dragState.literature_evidence_path }"
                  @dragover.prevent="dragState.literature_evidence_path = true"
                  @dragleave.prevent="dragState.literature_evidence_path = false"
                  @drop.prevent="handleFileDrop('literature_evidence_path', $event)"
                >
                  <div class="file-input-control">
                    <a-input v-model:value="form.literature_evidence_path" :disabled="running" />
                    <a-button
                      size="small"
                      :disabled="running"
                      @click="openFilePicker('literature_evidence_path')"
                    >
                      添加文件
                    </a-button>
                  </div>
                  <input
                    :ref="(el) => registerFileInput('literature_evidence_path', el)"
                    class="hidden-file-input"
                    type="file"
                    @change="handleSingleFileChange('literature_evidence_path', $event)"
                  />
                </div>
              </div>
            </div>
            <p class="hint-text">输出说明：无输出</p>
          </a-collapse-panel>

          <a-collapse-panel key="trait" header="性状输入">
            <div class="field-grid">
              <div class="field-item full-width">
                <label class="field-label">性状输入</label>
                <a-input
                  v-model:value="form.trait"
                  size="large"
                  placeholder="请输入性状描述"
                  :disabled="running"
                />
              </div>
            </div>
            <p class="hint-text">这里是性状描述，不是文件上传，也不是标签选择。</p>
          </a-collapse-panel>

          <a-collapse-panel key="question" header="用户问题">
            <div class="field-grid">
              <div class="field-item full-width">
                <label class="field-label">用户问题</label>
                <a-textarea
                  v-model:value="form.user_question"
                  :rows="5"
                  :disabled="running"
                  placeholder="请输入你的育种问题，例如：给出一些育种建议"
                />
              </div>
            </div>
            <p class="hint-text">
              当前页面走固定证据流程 + LLM 证据整合分析，不依赖模型自主决定是否调用正式主工具。
            </p>

            <div class="action-row">
              <a-button type="primary" size="large" :loading="running" @click="handleSubmit">
                提交给智能体
              </a-button>
              <a-button size="large" :disabled="running" @click="handleReset">重置</a-button>
            </div>
          </a-collapse-panel>
        </a-collapse>
      </section>

      <section class="result-panel">
        <div class="panel-intro result-header">
          <div>
            <h2>智能体输出 / 育种建议</h2>
            <p>以下结果由智能体根据用户问题、性状输入和多组学证据生成。</p>
          </div>
        </div>

        <div class="chain-card">
          <div class="chain-card-top">
            <div class="chain-title">工具调用链</div>
            <div v-if="displayStatus" class="inline-status">
              <span class="status-label">状态</span>
              <span class="status-pill" :class="`status-${displayStatus.tone}`">
                {{ displayStatus.label }}
              </span>
            </div>
          </div>
          <div v-if="result.toolName" class="chain-meta">
            <span>tool: {{ result.toolName }}</span>
          </div>
          <div v-if="showSoftTimeoutActions" class="soft-timeout-actions">
            <div class="soft-timeout-text">
              智能体仍在执行，可能是模型或工具调用较慢。你可以继续等待或停止本次运行。
            </div>
            <div class="soft-timeout-buttons">
              <a-button type="primary" size="small" @click="handleContinueWaiting"
                >继续等待</a-button
              >
              <a-button size="small" danger @click="handleStopRun">停止本次运行</a-button>
            </div>
          </div>
          <div v-if="visibleToolChain.length" class="chain-list">
            <span v-for="item in visibleToolChain" :key="item.name" class="chain-chip">
              {{ item.label }}
            </span>
          </div>
          <div v-else class="result-block-body">
            {{ running ? '等待智能体调用工具' : '暂无工具调用记录' }}
          </div>
        </div>

        <a-alert
          v-if="errorMessage"
          type="error"
          show-icon
          :message="errorMessage"
          class="result-alert"
        />
        <div class="result-shell">
          <a-spin :spinning="running && !softTimeoutState.awaitingDecision" :tip="spinTip">
            <template v-if="result.markdown">
              <div class="result-block-grid">
                <div class="result-block downloads-card">
                  <div class="result-block-title">下游可复用结果</div>
                  <div class="download-list">
                    <button type="button" class="download-card" @click="downloadSignificantDeg">
                      <span class="download-name">significant_de_genes.tsv</span>
                      <span class="download-desc">下载差异显著基因结果</span>
                    </button>
                    <button type="button" class="download-card" @click="downloadMetabolome">
                      <span class="download-name">metabolome_raw_3372.tsv</span>
                      <span class="download-desc">下载代谢组占位结果</span>
                    </button>
                    <button
                      type="button"
                      class="download-card"
                      :disabled="!result.markdown"
                      @click="downloadAdviceMarkdown"
                    >
                      <span class="download-name">育种建议</span>
                      <span class="download-desc">下载当前 breeding_advice.md</span>
                    </button>
                  </div>
                </div>
              </div>

              <div class="markdown-card">
                <MarkdownContentViewer :content="result.markdown" />
              </div>

              <div v-if="literatureCards.length" class="result-block literature-card">
                <div class="result-block-title">文献依据</div>
                <div class="literature-list">
                  <div v-for="item in literatureCards" :key="item.citation_id || item.title" class="literature-item">
                    <div class="literature-doi">
                      {{ item.doi ? `DOI: ${item.doi}` : item.pmid ? `PMID: ${item.pmid}` : '未提供 DOI/PMID' }}
                    </div>
                    <div class="literature-title">{{ item.title || '未提供标题' }}</div>
                    <div class="literature-source">source: {{ item.source || '-' }}</div>
                    <div class="literature-quote">
                      {{ item.quoted_sentence || item.abstract_sentence || '未提供原句/摘要句' }}
                    </div>
                  </div>
                </div>
              </div>

              <a-collapse v-if="claimTraceRows.length" ghost class="diagnostic-collapse">
                <a-collapse-panel key="claim-trace" header="逐句来源追溯">
                  <div class="claim-trace-list">
                    <div v-for="row in claimTraceRows" :key="row.claim_id || row.text" class="claim-trace-item">
                      <div class="claim-text">{{ row.text }}</div>
                      <div class="claim-source-meta">
                        <span>{{ (row.citation_ids || []).join(', ') || 'uncited' }}</span>
                        <span>{{ row.source_status || '-' }}</span>
                      </div>
                      <div v-if="row.sources?.length" class="claim-source-list">
                        <div v-for="source in row.sources" :key="source.citation_id" class="claim-source-item">
                          <div>{{ source.metadata?.title || source.metadata?.gene_id || source.citation_id }}</div>
                          <div>
                            {{ source.metadata?.doi ? `DOI: ${source.metadata.doi}` : source.metadata?.pmid ? `PMID: ${source.metadata.pmid}` : source.citation_id }}
                          </div>
                          <div>{{ source.metadata?.quoted_sentence || source.text }}</div>
                        </div>
                      </div>
                    </div>
                  </div>
                </a-collapse-panel>
              </a-collapse>

              <div class="markdown-download-footer">
                <a-button
                  type="primary"
                  size="large"
                  :disabled="!result.markdown"
                  @click="downloadAdviceMarkdown"
                >
                  下载育种建议 Markdown
                </a-button>
              </div>
            </template>
            <a-empty
              v-else
              description="提交问题后，这里会显示由后端 Tool / Agent 生成的育种建议结果。"
            />

            <a-collapse v-if="hasDiagnostics" ghost class="diagnostic-collapse">
              <a-collapse-panel key="diagnostics" header="运行诊断信息">
                <div class="diagnostic-grid">
                  <div class="diagnostic-item">
                    <span>thread_id</span><code>{{ runDiagnostics.threadId || '-' }}</code>
                  </div>
                  <div class="diagnostic-item">
                    <span>run_id</span><code>{{ runDiagnostics.runId || '-' }}</code>
                  </div>
                  <div class="diagnostic-item">
                    <span>run_status</span><code>{{ runDiagnostics.runStatus || '-' }}</code>
                  </div>
                  <div class="diagnostic-item">
                    <span>elapsed_seconds</span><code>{{ runDiagnostics.elapsedSeconds }}</code>
                  </div>
                  <div class="diagnostic-item">
                    <span>polling_count</span><code>{{ runDiagnostics.pollingCount }}</code>
                  </div>
                  <div class="diagnostic-item">
                    <span>last_history_message_role</span
                    ><code>{{ runDiagnostics.lastHistoryMessageRole || '-' }}</code>
                  </div>
                  <div class="diagnostic-item">
                    <span>parsed_tool_calls</span><code>{{ diagnosticsToolCalls }}</code>
                  </div>
                  <div class="diagnostic-item">
                    <span>soft_timeout_reached</span
                    ><code>{{ String(runDiagnostics.softTimeoutReached) }}</code>
                  </div>
                  <div class="diagnostic-item">
                    <span>hard_timeout_reached</span
                    ><code>{{ String(runDiagnostics.hardTimeoutReached) }}</code>
                  </div>
                  <div class="diagnostic-item">
                    <span>trait</span><code>{{ businessSummary.trait || '-' }}</code>
                  </div>
                  <div class="diagnostic-item">
                    <span>question</span><code>{{ businessSummary.question || '-' }}</code>
                  </div>
                  <div class="diagnostic-item">
                    <span>data_source</span><code>{{ businessSummary.data_source || businessSummary.evidence_level || '-' }}</code>
                  </div>
                  <div class="diagnostic-item">
                    <span>transcriptome_pipeline_status</span><code>{{ businessSummary.transcriptome_pipeline_status || '-' }}</code>
                  </div>
                  <div class="diagnostic-item">
                    <span>transcriptome_input_status</span><code>{{ businessSummary.transcriptome_input_status || '-' }}</code>
                  </div>
                  <div class="diagnostic-item">
                    <span>transcriptome_path_exists</span><code>{{ String(Boolean(businessSummary.transcriptome_path_exists)) }}</code>
                  </div>
                  <div class="diagnostic-item">
                    <span>metabolome_path_exists</span><code>{{ String(Boolean(businessSummary.metabolome_path_exists)) }}</code>
                  </div>
                  <div class="diagnostic-item">
                    <span>metabolome_preview_available</span><code>{{ String(Boolean(businessSummary.metabolome_preview_available)) }}</code>
                  </div>
                  <div class="diagnostic-item">
                    <span>background_literature_count</span><code>{{ businessSummary.background_literature_count ?? '-' }}</code>
                  </div>
                  <div class="diagnostic-item">
                    <span>literature_card_count</span><code>{{ businessSummary.literature_card_count ?? '-' }}</code>
                  </div>
                  <div class="diagnostic-item">
                    <span>citation_backend</span><code>{{ businessSummary.citation_backend || '-' }}</code>
                  </div>
                  <div class="diagnostic-item">
                    <span>llamaindex_available</span><code>{{ String(Boolean(businessSummary.llamaindex_available)) }}</code>
                  </div>
                  <div class="diagnostic-item">
                    <span>pipeline_log_path</span><code>{{ businessSummary.pipeline_log_path || '-' }}</code>
                  </div>
                  <div class="diagnostic-item">
                    <span>transcriptome_result_path</span><code>{{ businessSummary.transcriptome_result_path || '-' }}</code>
                  </div>
                  <div class="diagnostic-item">
                    <span>uploaded_file_count</span><code>{{ businessSummary.uploaded_file_count ?? 0 }}</code>
                  </div>
                  <div class="diagnostic-item full-span">
                    <span>submitted_reference_genome_path</span><code>{{ businessSummary.submitted_reference_genome_path || businessSummary.reference_genome_path || '-' }}</code>
                  </div>
                  <div class="diagnostic-item full-span">
                    <span>submitted_genome_gff_path</span><code>{{ businessSummary.submitted_genome_gff_path || businessSummary.genome_gff_path || '-' }}</code>
                  </div>
                  <div class="diagnostic-item full-span">
                    <span>submitted_metabolome_path</span><code>{{ businessSummary.submitted_metabolome_path || businessSummary.metabolome_path || '-' }}</code>
                  </div>
                  <div class="diagnostic-item full-span">
                    <span>submitted_sample_map_path</span><code>{{ businessSummary.submitted_sample_map_path || businessSummary.sample_map_path || '-' }}</code>
                  </div>
                  <div class="diagnostic-item full-span">
                    <span>submitted_rnaseq_read_paths</span><code>{{ (businessSummary.submitted_rnaseq_read_paths || []).join(', ') || '-' }}</code>
                  </div>
                  <div class="diagnostic-item full-span">
                    <span>upload_root</span><code>{{ businessSummary.submitted_upload_root || businessSummary.upload_root || '-' }}</code>
                  </div>
                </div>
              </a-collapse-panel>
            </a-collapse>
          </a-spin>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup>
// 这个文件在链路中的作用：
// 1. 收集育种工作台左侧多组学输入和用户问题；
// 2. 调用 breeding_workbench_api.js 创建 YuXi Thread 和 Agent Run；
// 3. 展示工具链、最终 markdown、结构化追溯信息和下载入口。
//
// 它是“/breeding-workbench 页面层”，不直接执行后端 Tool，也不自己拼最终育种建议。

import { computed, onMounted, reactive, ref } from 'vue'
import { message } from 'ant-design-vue'
import { storeToRefs } from 'pinia'
import { breedingWorkbenchApi } from '@/apis'
import { createWorkspaceDirectory, uploadWorkspaceFile } from '@/apis/workspace_api'
import MarkdownContentViewer from '@/components/MarkdownContentViewer.vue'
import { useAgentStore } from '@/stores/agent'
import {
  DEFAULT_SMOKE_BREEDING_CONTEXT,
  REQUIRED_BREEDING_FIELDS,
  downloadMarkdown,
  downloadTsv
} from '@/utils/breedingWorkbench'

const DEFAULT_FORM = { ...DEFAULT_SMOKE_BREEDING_CONTEXT }
const DEFAULT_DATA_DIR = DEFAULT_SMOKE_BREEDING_CONTEXT.data_dir
const DEFAULT_TRAIT = DEFAULT_SMOKE_BREEDING_CONTEXT.trait
const DEFAULT_QUESTION = DEFAULT_SMOKE_BREEDING_CONTEXT.user_question
const TOOL_LABELS = {
  omics_breeding_analysis_run: '多组学育种分析',
  smoke_flavonoid_breeding_advice: 'Smoke 黄酮育种建议',
  breeding_reference_prepare: '参考基因组准备',
  breeding_transcriptome_deg: '转录组差异分析',
  breeding_metabolome_prepare: '代谢组准备',
  breeding_literature_evidence: '文献证据读取',
  breeding_advice_generate: '育种建议生成',
  breeding_validation_plan: '验证计划生成'
}
const TERMINAL_RESULT_STATUSES = new Set([
  'completed',
  'completed_with_warnings',
  'succeeded',
  'failed',
  'cancelled',
  'interrupted',
  'error'
])

const agentStore = useAgentStore()
const { selectedAgentId, selectedAgentConfigId } = storeToRefs(agentStore)

/*
 * 状态变量区
 * */
// 这些状态是工作台页面的最小运行现场：
// - form: 左侧输入面板内容
// - running：当前是否正在执行智能体
// - result: 当前可展示结果
// - runDiagnostics: 轮询过程中记录的 thread/run 诊断信息
// - softTimeoutState: 软超时后继续等待或停止的交互状态
const form = reactive({ ...DEFAULT_FORM })
const activePanels = ref(['reference', 'transcriptome', 'metabolome', 'trait', 'question'])
const running = ref(false)
const currentMode = ref('')
const errorMessage = ref('')
const softTimeoutDecisionResolver = ref(null)
const activeSubmissionId = ref('')
const uploadBatchId = ref(`breeding-workbench-${Date.now()}`)
const result = reactive({
  status: 'idle',
  markdown: '',
  frontendPayload: null,
  toolCalls: [],
  toolChain: [],
  visibleToolChain: [],
  toolName: '',
  guardPassed: null,
  outputFiles: []
})
const uploadedServerPaths = reactive({
  upload_root: '',
  uploaded_file_count: 0,
  reference_genome_path: '',
  genome_gff_path: '',
  annotation_path: '',
  transcriptome_result_path: '',
  metabolome_path: '',
  literature_evidence_path: '',
  sample_map_path: '',
  rnaseq_read_paths: []
})
const uploadState = reactive({
  reference_genome: [],
  genome_gff: [],
  function_annotation: [],
  transcriptome_result_path: [],
  rnaseq_reads: [],
  sample_map: [],
  usage_doc: [],
  metabolome_tsv: [],
  literature_evidence_path: []
})
const runDiagnostics = reactive({
  threadId: '',
  runId: '',
  requestId: '',
  runStatus: '',
  elapsedSeconds: 0,
  pollingCount: 0,
  lastHistoryMessageRole: '',
  parsedToolCalls: [],
  softTimeoutReached: false,
  hardTimeoutReached: false
})
const softTimeoutState = reactive({
  reached: false,
  awaitingDecision: false,
  hardReached: false
})

const selectedFiles = reactive({
  reference_genome: [],
  genome_gff: [],
  function_annotation: [],
  transcriptome_result_path: [],
  rnaseq_reads: [],
  sample_map: [],
  usage_doc: [],
  metabolome_tsv: [],
  literature_evidence_path: []
})

const dragState = reactive({
  reference_genome: false,
  genome_gff: false,
  function_annotation: false,
  rnaseq_reads: false,
  sample_map: false,
  metabolome_tsv: false,
  literature_evidence_path: false
})

const fileInputRefs = new Map()

// 这个计算属性在页面渲染状态提示时被调用。
// 输入是真实 run 状态和超时状态；输出是给用户看的状态文案。
// 它属于“页面解释当前 Run 进度”的步骤，不参与业务判断。
const frontendPayload = computed(() => result.frontendPayload || null)
const businessSummary = computed(() => frontendPayload.value?.summary || {})
const literatureCards = computed(
  () =>
    frontendPayload.value?.literature_panel?.cards ||
    frontendPayload.value?.literature_cards ||
    result.frontendPayload?.literature_cards ||
    []
)
const claimTraceRows = computed(
  () => frontendPayload.value?.claim_trace_panel?.rows || result.frontendPayload?.claim_trace || []
)
const uploadRootVirtualPath = computed(() => `/breeding-workbench/${uploadBatchId.value}`)
const uploadedFileList = computed(() =>
  Object.entries(uploadState)
    .flatMap(([field, items]) =>
      (items || []).map((item, index) => ({
        key: `${field}-${index}-${item.serverPath || item.name}`,
        field,
        label:
          {
            reference_genome: '参考基因组',
            genome_gff: '基因组注释',
            function_annotation: '功能注释',
            transcriptome_result_path: '差异显著基因结果',
            rnaseq_reads: 'RNA-seq Reads',
            sample_map: '数据标签',
            usage_doc: '流程说明',
            metabolome_tsv: '代谢含量',
            literature_evidence_path: '已验证文献证据'
          }[field] || field,
        name: item.name,
        serverPath: item.serverPath,
        status: item.status || 'uploaded',
        statusLabel: item.status === 'uploading' ? '上传中' : item.status === 'error' ? '上传失败' : '已上传'
      }))
    )
    .filter(Boolean)
)

const displayStatus = computed(() => {
  const runStatus = String(runDiagnostics.runStatus || result.status || '')
    .trim()
    .toLowerCase()
  const hasCompletedResult = Boolean(
    frontendPayload.value || (result.markdown || '').includes('分析流程已完成')
  )

  if (hasCompletedResult) {
    return { label: '已完成', tone: 'success' }
  }

  if (['completed', 'completed_with_warnings', 'succeeded'].includes(runStatus)) {
    return { label: '已完成', tone: 'success' }
  }
  if (['failed', 'error', 'failed_guard'].includes(runStatus)) {
    return { label: '运行失败', tone: 'failed' }
  }
  if (['cancelled', 'interrupted'].includes(runStatus)) {
    return { label: '已取消', tone: 'failed' }
  }
  if (softTimeoutState.hardReached) {
    return { label: '智能体执行时间过长，请检查后端 run 状态或重试', tone: 'failed' }
  }
  if (['running', 'pending', 'queued'].includes(runStatus) || running.value) {
    return { label: '运行中', tone: 'running' }
  }
  if (!runStatus || runStatus === 'idle') return null
  return { label: runStatus, tone: 'running' }
})

// 这个计算属性在结果区展示工具链时被调用。
// 输入是 API 层整理好的 toolChain；输出是带中文标签的可视化链路。
// 这里只展示结构化 tool call。
const visibleToolChain = computed(() => {
  return (result.visibleToolChain || result.toolChain || [])
    .filter((item) => item?.name === 'omics_breeding_analysis_run')
    .filter((item) => !item?.inferred)
    .map((item) => ({
      name: item.name,
      label: TOOL_LABELS[item.name] || item.name
    }))
})

const spinTip = computed(() => '智能体正在分析并调用工具，请稍候...')
const showSoftTimeoutActions = computed(() => {
  const runStatus = String(runDiagnostics.runStatus || result.status || '')
    .trim()
    .toLowerCase()
  return (
    running.value && softTimeoutState.awaitingDecision && !TERMINAL_RESULT_STATUSES.has(runStatus)
  )
})
const hasDiagnostics = computed(
  () =>
    !!(
      runDiagnostics.threadId ||
      runDiagnostics.runId ||
      runDiagnostics.pollingCount ||
      result.markdown
    )
)
const diagnosticsToolCalls = computed(() =>
  runDiagnostics.parsedToolCalls.length ? runDiagnostics.parsedToolCalls.join(', ') : '-'
)

/*
 * 文件输入相关函数
 * 添加文件按钮 → openFilePicker → 触发隐藏 input
 * 选择文件/拖拽文件 → updateFieldFiles → 把文件名写入 form
 * 当前工作台文件选择主要是演示和上下文描述，真实后端执行仍依赖服务器挂载路径下的 smoke 数据包
 * TODO：后续如果要支持用户上传真实文件，需要新增上传接口和后端文件落盘逻辑。
 * */

// 这个函数在模板中的隐藏 input 挂载/卸载时被调用。
// 输入是字段 key 和 DOM 元素；输出是更新本地 ref 映射。
// 页面通过它把“点击按钮”转成“打开真实文件选择器”。
const registerFileInput = (key, el) => {
  if (el) {
    fileInputRefs.set(key, el)
  } else {
    fileInputRefs.delete(key)
  }
}

const openFilePicker = (key) => {
  fileInputRefs.get(key)?.click()
}

const normalizeFileName = (file) => String(file?.name || '').trim().toLowerCase()

const validateFilesForField = (key, files) => {
  const normalizedFiles = Array.from(files || []).filter(Boolean)
  if (!normalizedFiles.length) return { files: normalizedFiles, error: '' }

  if (key === 'rnaseq_reads') {
    const invalidFile = normalizedFiles.find((file) => {
      const name = normalizeFileName(file)
      return !(
        name.endsWith('.fq') ||
        name.endsWith('.fastq') ||
        name.endsWith('.fq.gz') ||
        name.endsWith('.fastq.gz')
      )
    })
    if (invalidFile) {
      const invalidName = invalidFile.name || '未知文件'
      if (normalizeFileName(invalidFile) === 'read_counts.tsv') {
        return {
          files: [],
          error: 'read_counts.tsv 不是 FASTQ reads，也不是最终 significant_de_genes.tsv，请改为上传 fq/*.fq.gz 或 fq 文件夹。'
        }
      }
      return {
        files: [],
        error: `${invalidName} 不是 FASTQ reads。RNA-seq Reads 仅接受 .fq/.fastq/.fq.gz/.fastq.gz 文件。`
      }
    }
  }

  return { files: normalizedFiles, error: '' }
}

// 这个函数在用户选择文件或拖拽文件后被调用。
// 输入是字段 key、FileList 和是否多文件；输出是更新页面可见文件名。
// 当前第一版不会把文件真正上传到后端，只把文件名写进上下文发给 Agent。
const updateFieldFiles = (key, files, multiple = false) => {
  const normalizedFiles = Array.from(files || []).map((file) => ({
    name: file.name,
    size: file.size,
    type: file.type
  }))
  selectedFiles[key] = normalizedFiles
  dragState[key] = false

  if (multiple) {
    form[key] =
      normalizedFiles.length > 0 ? normalizedFiles.map((file) => file.name).join(', ') : ''
  } else if (normalizedFiles[0]) {
    form[key] = normalizedFiles[0].name
  }
}

const ensureWorkspaceDirectoryPath = async (targetPath) => {
  const parts = String(targetPath || '/')
    .split('/')
    .filter(Boolean)
  let currentPath = '/'
  let serverPath = ''

  for (const part of parts) {
    try {
      const response = await createWorkspaceDirectory(currentPath, part)
      serverPath = response?.server_path || serverPath
    } catch (error) {
      const detail = String(error?.message || '')
      if (!detail.includes('已存在')) {
        throw error
      }
    }
    currentPath = currentPath === '/' ? `/${part}` : `${currentPath}/${part}`
  }

  return { virtualPath: currentPath, serverPath }
}

const syncUploadedServerPaths = (key, entries) => {
  if (key === 'reference_genome') {
    uploadedServerPaths.reference_genome_path = entries[0]?.serverPath || ''
  } else if (key === 'genome_gff') {
    uploadedServerPaths.genome_gff_path = entries[0]?.serverPath || ''
  } else if (key === 'function_annotation') {
    uploadedServerPaths.annotation_path = entries[0]?.serverPath || ''
  } else if (key === 'transcriptome_result_path') {
    uploadedServerPaths.transcriptome_result_path = entries[0]?.serverPath || ''
  } else if (key === 'metabolome_tsv') {
    uploadedServerPaths.metabolome_path = entries[0]?.serverPath || ''
  } else if (key === 'literature_evidence_path') {
    uploadedServerPaths.literature_evidence_path = entries[0]?.serverPath || ''
  } else if (key === 'sample_map') {
    uploadedServerPaths.sample_map_path = entries[0]?.serverPath || ''
  } else if (key === 'rnaseq_reads') {
    uploadedServerPaths.rnaseq_read_paths = entries.map((item) => item.serverPath).filter(Boolean)
  }

  uploadedServerPaths.uploaded_file_count = Object.values(uploadState).reduce(
    (count, items) => count + (items?.length || 0),
    0
  )
}

const uploadFilesForField = async (key, files, { multiple = false, subdir = '' } = {}) => {
  const { files: normalizedFiles, error } = validateFilesForField(key, files)
  if (error) {
    throw new Error(error)
  }
  if (!normalizedFiles.length) return

  const virtualParent = subdir
    ? `${uploadRootVirtualPath.value}/${subdir}`.replace(/\/+/g, '/')
    : uploadRootVirtualPath.value
  const ensuredDir = await ensureWorkspaceDirectoryPath(virtualParent)
  if (!uploadedServerPaths.upload_root && ensuredDir.serverPath) {
    uploadedServerPaths.upload_root = subdir
      ? ensuredDir.serverPath.replace(/\/fq$/, '')
      : ensuredDir.serverPath
  }

  uploadState[key] = normalizedFiles.map((file) => ({
    name: file.name,
    status: 'uploading',
    serverPath: ''
  }))
  updateFieldFiles(key, normalizedFiles, multiple)

  const uploadedEntries = []
  for (let index = 0; index < normalizedFiles.length; index += 1) {
    const file = normalizedFiles[index]
    const response = await uploadWorkspaceFile(virtualParent, file)
    uploadedEntries.push({
      name: file.name,
      status: 'uploaded',
      serverPath: response?.server_path || '',
      virtualPath: response?.entry?.virtual_path || ''
    })
  }

  uploadState[key] = uploadedEntries
  syncUploadedServerPaths(key, uploadedEntries)
}

const handleSingleFileChange = async (key, event) => {
  try {
    await uploadFilesForField(key, event?.target?.files || [], { multiple: false })
  } catch (error) {
    console.error('Upload failed:', error)
    message.error(error?.message || '文件上传失败。')
  }
  if (event?.target) event.target.value = ''
}

const handleMultiFileChange = async (key, event) => {
  try {
    await uploadFilesForField(key, event?.target?.files || [], { multiple: true, subdir: 'fq' })
  } catch (error) {
    console.error('Upload failed:', error)
    message.error(error?.message || '文件上传失败。')
  }
  if (event?.target) event.target.value = ''
}

const handleFileDrop = async (key, event, multiple = false) => {
  try {
    await uploadFilesForField(key, event?.dataTransfer?.files || [], {
      multiple,
      subdir: multiple ? 'fq' : ''
    })
  } catch (error) {
    console.error('Upload failed:', error)
    message.error(error?.message || '文件上传失败。')
  }
}

// 这个函数在用户点击“重置”或新任务开始前被调用。
// 输入为空；输出是清空上一次运行留下的结果和诊断信息。
const resetResult = () => {
  result.status = 'idle'
  result.markdown = ''
  result.frontendPayload = null
  result.toolCalls = []
  result.toolChain = []
  result.visibleToolChain = []
  result.toolName = ''
  result.guardPassed = null
  result.outputFiles = []
  currentMode.value = ''
  runDiagnostics.threadId = ''
  runDiagnostics.runId = ''
  runDiagnostics.requestId = ''
  runDiagnostics.runStatus = ''
  runDiagnostics.elapsedSeconds = 0
  runDiagnostics.pollingCount = 0
  runDiagnostics.lastHistoryMessageRole = ''
  runDiagnostics.parsedToolCalls = []
  runDiagnostics.softTimeoutReached = false
  runDiagnostics.hardTimeoutReached = false
  softTimeoutState.reached = false
  softTimeoutState.awaitingDecision = false
  softTimeoutState.hardReached = false
  softTimeoutDecisionResolver.value = null
}

const resetFileSelections = () => {
  Object.keys(selectedFiles).forEach((key) => {
    selectedFiles[key] = []
  })
  Object.keys(uploadState).forEach((key) => {
    uploadState[key] = []
  })
  Object.keys(dragState).forEach((key) => {
    dragState[key] = false
  })
  uploadedServerPaths.upload_root = ''
  uploadedServerPaths.uploaded_file_count = 0
  uploadedServerPaths.reference_genome_path = ''
  uploadedServerPaths.genome_gff_path = ''
  uploadedServerPaths.annotation_path = ''
  uploadedServerPaths.transcriptome_result_path = ''
  uploadedServerPaths.metabolome_path = ''
  uploadedServerPaths.literature_evidence_path = ''
  uploadedServerPaths.sample_map_path = ''
  uploadedServerPaths.rnaseq_read_paths = []
  uploadBatchId.value = `breeding-workbench-${Date.now()}`
}

const handleReset = () => {
  Object.assign(form, DEFAULT_FORM)
  errorMessage.value = ''
  resetResult()
  resetFileSelections()
}

// 这个函数在页面初始化和正式提交前被调用。
// 输入为空；输出是保证当前存在可用的默认 Agent 和 AgentConfig。
// 它在链路中的位置是“工作台提交前的最小前置检查”。
const ensureAgentContext = async () => {
  if (!agentStore.isInitialized) {
    await agentStore.initialize()
  }
  if (!selectedAgentId.value || !selectedAgentConfigId.value) {
    throw new Error('当前没有可用的默认智能体或默认配置，请先在对话页或模型配置中确认。')
  }
}

/*
 * 提交前构造上下文
 * */
const buildVisibleQuestion = () => {
  const question = (form.user_question || DEFAULT_QUESTION).trim()
  return question || DEFAULT_QUESTION
}

const buildTrait = () => {
  const trait = (form.trait || DEFAULT_TRAIT).trim()
  return trait || DEFAULT_TRAIT
}

// 这个函数在真正发起 Agent Run 前被调用。
// 输入来自页面表单；输出是发给 API 层的标准上下文字段。
// 这些值描述的是“本次要让 Tool 读取哪些文件/文件名”，不是前端自己做组学分析。
const buildSubmissionContext = () => {
  const hasUploadedBatch = Boolean(uploadedServerPaths.upload_root)
  const resolvePath = (uploadedPath, defaultFilename, { optional = false } = {}) => {
    if (uploadedPath) return uploadedPath
    if (hasUploadedBatch && optional) return ''
    return `${DEFAULT_DATA_DIR}/${defaultFilename}`
  }

  return {
    data_dir: uploadedServerPaths.upload_root || DEFAULT_DATA_DIR,
    upload_root: uploadedServerPaths.upload_root || '',
    uploaded_file_count: uploadedServerPaths.uploaded_file_count || 0,
    reference_genome: (form.reference_genome || '').trim() || DEFAULT_FORM.reference_genome,
    reference_genome_path: resolvePath(
      uploadedServerPaths.reference_genome_path,
      DEFAULT_FORM.reference_genome
    ),
    genome_gff: (form.genome_gff || '').trim() || DEFAULT_FORM.genome_gff,
    genome_gff_path: resolvePath(uploadedServerPaths.genome_gff_path, DEFAULT_FORM.genome_gff),
    function_annotation: (form.function_annotation || '').trim() || DEFAULT_FORM.function_annotation,
    annotation_path: resolvePath(
      uploadedServerPaths.annotation_path,
      DEFAULT_FORM.function_annotation,
      { optional: true }
    ),
    transcriptome_result_path: resolvePath(
      uploadedServerPaths.transcriptome_result_path,
      DEFAULT_FORM.transcriptome_result_path,
      { optional: true }
    ),
    rnaseq_reads: (form.rnaseq_reads || '').trim() || DEFAULT_FORM.rnaseq_reads,
    rnaseq_read_paths:
      uploadedServerPaths.rnaseq_read_paths.length > 0
        ? uploadedServerPaths.rnaseq_read_paths
        : [],
    sample_map: (form.sample_map || '').trim() || DEFAULT_FORM.sample_map,
    sample_map_path: resolvePath(uploadedServerPaths.sample_map_path, DEFAULT_FORM.sample_map),
    usage_doc: '',
    metabolome_tsv: (form.metabolome_tsv || '').trim() || DEFAULT_FORM.metabolome_tsv,
    metabolome_path: resolvePath(uploadedServerPaths.metabolome_path, DEFAULT_FORM.metabolome_tsv),
    literature_evidence_path: resolvePath(
      uploadedServerPaths.literature_evidence_path,
      DEFAULT_FORM.literature_evidence_path,
      { optional: true }
    )
  }
}

// 这个函数在点击提交后首先被调用。
// 输入是当前表单；输出是缺失字段提示或 null。
// 它只做页面级校验，真正的文件存在性和 Tool 输入有效性仍由后端 Tool 检查。
const validateRequiredFields = () => {
  const missing = REQUIRED_BREEDING_FIELDS.find(({ key }) => !(form[key] || '').trim())
  if (!missing) return null
  return `${missing.label}不能为空，请补充后再提交。`
}

// 这些下载函数在用户点击下载卡片时被调用。
// 当前 TSV 下载是工作台演示用占位内容；真正的业务核心仍是右侧展示的最终 markdown 和工具结果。
const downloadSignificantDeg = () => {
  const content = ['gene_id\tstatus', 'candidate_gene_1\tdetected'].join('\n')
  downloadTsv('significant_de_genes.tsv', content)
}

const downloadMetabolome = () => {
  const content = ['compound\tannotation', 'trait_related_metabolite\tmetabolome_raw_3372.tsv'].join(
    '\n'
  )
  downloadTsv('metabolome_raw_3372.tsv', content)
}

const downloadAdviceMarkdown = () => {
  if (!result.markdown) {
    message.warning('请先提交给智能体生成结果。')
    return
  }
  downloadMarkdown('breeding_advice.md', result.markdown)
}

// 这个函数在每轮轮询快照到达页面时被调用。
// 输入是 API 层返回的 diagnostics；输出是同步页面上的 thread/run 诊断区。
// 这些字段帮助你向老师解释：一次任务属于哪个 thread、哪个 run、轮询了多少次、最后一条消息来自谁。
const syncDiagnostics = (diagnostics = {}) => {
  runDiagnostics.threadId = diagnostics.threadId || ''
  runDiagnostics.runId = diagnostics.runId || ''
  runDiagnostics.requestId = diagnostics.requestId || ''
  runDiagnostics.runStatus = diagnostics.runStatus || ''
  runDiagnostics.elapsedSeconds = diagnostics.elapsedSeconds || 0
  runDiagnostics.pollingCount = diagnostics.pollingCount || 0
  runDiagnostics.lastHistoryMessageRole = diagnostics.lastHistoryMessageRole || ''
  runDiagnostics.parsedToolCalls = diagnostics.parsedToolCalls || []
  runDiagnostics.softTimeoutReached = Boolean(diagnostics.softTimeoutReached)
  runDiagnostics.hardTimeoutReached = Boolean(diagnostics.hardTimeoutReached)
  softTimeoutState.reached = Boolean(diagnostics.softTimeoutReached)
  softTimeoutState.hardReached = Boolean(diagnostics.hardTimeoutReached)
  if (!diagnostics.softTimeoutReached) {
    softTimeoutState.awaitingDecision = false
    softTimeoutDecisionResolver.value = null
  }
}

// 这个函数在页面拿到 run snapshot 或最终 payload 时被调用。
// 输入是 API 层快照；输出是更新右侧结果区。
// 页面不自己拼育种建议，而是把后端真实落库的 markdown、工具链和诊断信息同步出来。
const syncResultFromPayload = (payload, { final = false, submissionId = '' } = {}) => {
  if (submissionId && activeSubmissionId.value && submissionId !== activeSubmissionId.value) {
    return
  }

  result.status = payload.status || (final ? 'completed' : result.status || 'running')
  result.markdown = payload.frontendPayload?.answer_markdown || payload.markdown || ''
  result.frontendPayload = payload.frontendPayload || null
  result.toolCalls = payload.toolCalls || []
  result.toolChain = payload.toolChain || []
  result.visibleToolChain = payload.visibleToolChain || []
  result.toolName =
    payload.toolName ||
    (payload.visibleToolChain?.length === 1
      ? payload.visibleToolChain[0]?.name || ''
      : payload.toolChain?.length === 1
        ? payload.toolChain[0]?.name || ''
        : '')
  result.guardPassed =
    typeof payload.frontendPayload?.guard_panel?.passed === 'boolean'
      ? payload.frontendPayload.guard_panel.passed
      : null
  result.outputFiles = payload.outputFiles || result.outputFiles || []
  syncDiagnostics(payload.diagnostics || {})

  const normalizedStatus = String(payload.status || '')
    .trim()
    .toLowerCase()
  if (
    TERMINAL_RESULT_STATUSES.has(normalizedStatus) ||
    payload.frontendPayload?.answer_markdown ||
    payload.markdown
  ) {
    softTimeoutState.awaitingDecision = false
  }
  if (TERMINAL_RESULT_STATUSES.has(normalizedStatus)) {
    running.value = false
    softTimeoutState.reached = false
    softTimeoutState.awaitingDecision = false
    softTimeoutDecisionResolver.value = null
  }

  if (final && !result.markdown) {
    errorMessage.value = '后端运行已结束，但没有返回可渲染的结果内容。'
  }
}

const resolveSoftTimeoutDecision = (decision) => {
  if (typeof softTimeoutDecisionResolver.value === 'function') {
    softTimeoutState.awaitingDecision = false
    const resolver = softTimeoutDecisionResolver.value
    softTimeoutDecisionResolver.value = null
    resolver(decision)
  }
}

const handleContinueWaiting = () => {
  resolveSoftTimeoutDecision('continue')
}

const handleStopRun = () => {
  resolveSoftTimeoutDecision('stop')
}
/* 提交主函数（最重要）
* 调用链：
* 用户点击“提交给智能体”
→ handleSubmit()
→ validateRequiredFields()
→ ensureAgentContext()
→ buildSubmissionContext()
→ breedingWorkbenchApi.runBreedingWorkbench(...)
→ syncResultFromPayload(...)
*  1. 做必填字段校验；
*  2. 清空旧结果并进入 running 状态；
*  3. 构造 trait / question / context；
*  4. 调用 breedingWorkbenchApi.runBreedingWorkbench() 创建 YuXi Thread / Run；
*  5. 通过 onProgress / final payload 把后端结果同步到 result。
*  这里不直接执行后端 Tool，真正的 omics_breeding_analysis_run 在后端 run 链路中执行。
* */
// 这个函数在用户点击“提交给智能体”时被调用。
// 输入是页面表单；输出是右侧最终结果、工具链和结构化展示数据。然后交给：breedingWorkbenchApi.runBreedingWorkbench(...)
// 也就是调用前端 API 层去创建 YuXi 的 Thread / Agent Run
// 它在整条链路中的位置是：
// 1. 收集输入
// 2. 调用 API 层创建 Thread / Run
// 3. 持续接收轮询快照
//
// 这里不直接调用 Tool。真正的 Tool 执行发生在后端 Agent Run 中。
const handleSubmit = async () => {
  // 点击提交后，先检查必填字段有没有空。如果有空字段，就提示用户，并且直接 return，不继续创建 run。
  const validationError = validateRequiredFields()
  if (validationError) {
    errorMessage.value = validationError
    message.warning(validationError)
    return
  }

  // 进入运行状态并清空旧结果
  running.value = true // 表示页面进入“运行中”
  currentMode.value = 'agent'
  errorMessage.value = '' // 清空上一次错误
  resetResult() // 防止旧结果污染新结果
  // 前端自己生成的本次提交 ID，防止旧的轮询 snapshot 回写到当前页面
  const submissionId = `${Date.now()}-${Math.random().toString(36).slice(2)}`
  activeSubmissionId.value = submissionId
  currentMode.value = 'agent'
  result.status = 'running' // 控制按钮 loading、状态提示

  try {
    // 确保 YuXi 默认 Agent 和配置存在，即提交前确认当前页面有可用的 agentId 和 agentConfigId。
    await ensureAgentContext()

    // 构造提交上下文，将页面表单整理成一个统一对象。
    const context = buildSubmissionContext()

    /* 关键代码逻辑
     * handleSubmit() 不直接调用后端 Tool，而是调用 breedingWorkbenchApi.runBreedingWorkbench() 创建 YuXi Thread / Agent Run。
     * 真正的 Tool 执行发生在后端 Agent Run 中。
     * 把页面输入交给 API 层，由 API 层负责创建 Thread / Run，由 API 层负责轮询后端状态，由 API 层不断通过 onProgress 回传 snapshot
     * */
    const payload = await breedingWorkbenchApi.runBreedingWorkbench({
      agentId: selectedAgentId.value,
      agentConfigId: selectedAgentConfigId.value,
      // 用户输入信息
      trait: buildTrait(),
      question: buildVisibleQuestion(),
      // 页面上其他输入文件的集合
      context,
      title: `育种工作台：${buildVisibleQuestion().slice(0, 16) || DEFAULT_QUESTION}`,
      normalWaitMs: breedingWorkbenchApi.NORMAL_WAIT_MS,
      hardTimeoutMs: breedingWorkbenchApi.HARD_TIMEOUT_MS,
      // 后端还没完全结束时，API 层每轮轮询拿到一个 snapshot，就调用 onProgress，把中间状态实时同步到页面。
      onProgress: async (snapshot) => {
        syncResultFromPayload(snapshot, { submissionId })
      },
      // 运行时间过长，软超时判断，让页面显示“继续等待 / 停止本次运行”。
      onSoftTimeout: async (snapshot) => {
        syncResultFromPayload(snapshot, { submissionId })
        softTimeoutState.awaitingDecision = true
        return await new Promise((resolve) => {
          softTimeoutDecisionResolver.value = resolve
        })
      }
    })

    // 结果同步  负责把 API 返回的结果写入页面：右侧 Markdown、工具链、guard 状态、诊断信息都来自 API 层返回的 payload
    syncResultFromPayload(
      {
        ...payload,
        toolName: payload.toolChain?.length === 1 ? payload.toolChain[0]?.name || '' : '',
        outputFiles:
          payload.finalMessageSource === 'tool' && payload.markdown ? ['以下为工具返回结果'] : []
      },
      { final: true, submissionId }
    )
  } catch (error) {
    // 前端表现层错误判断
    console.error('Breeding workbench run failed:', error)
    const isStopped = error?.message === '已停止本次运行。'
    result.status = isStopped ? 'cancelled' : 'failed'
    errorMessage.value = error?.message || '育种工作台调用失败。'
    if (isStopped) {
      message.warning(errorMessage.value)
    } else {
      message.error(errorMessage.value)
    }
  } finally {
    // 无论成功还是失败都会执行：清除当前 submissionId、软超时等待状态，running = false，停止按钮 loading 和页面 spin
    if (activeSubmissionId.value === submissionId) {
      activeSubmissionId.value = ''
    }
    softTimeoutState.awaitingDecision = false
    softTimeoutDecisionResolver.value = null
    running.value = false
  }
}

// 页面加载时先确认默认 Agent 环境是否可用。
onMounted(async () => {
  try {
    await ensureAgentContext()
  } catch (error) {
    errorMessage.value = error?.message || '初始化育种工作台失败。'
  }
})
</script>

<style scoped lang="less">
.breeding-workbench-page {
  min-height: 100%;
  user-select: text;
  background:
    radial-gradient(circle at top right, rgba(125, 196, 180, 0.16), transparent 30%),
    linear-gradient(180deg, #f4faf8 0%, var(--gray-0) 100%);
}

.workbench-body {
  display: grid;
  grid-template-columns: minmax(320px, 390px) minmax(0, 1fr);
  gap: 20px;
  padding: 20px var(--page-padding) 28px;
}

.panel-intro {
  margin-bottom: 14px;

  h2 {
    margin: 0 0 8px;
    color: var(--gray-1000);
    font-size: 20px;
    font-weight: 600;
  }

  p {
    margin: 0;
    color: var(--gray-600);
    line-height: 1.7;
  }
}

.uploaded-files-card {
  margin-bottom: 16px;
  padding: 14px 16px;
  border: 1px solid var(--gray-100);
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.92);
}

.uploaded-files-title {
  margin-bottom: 10px;
  color: var(--gray-900);
  font-size: 14px;
  font-weight: 600;
}

.uploaded-files-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.uploaded-file-item {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.uploaded-file-main {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}

.uploaded-file-label {
  color: var(--gray-700);
  font-size: 12px;
}

.uploaded-file-name {
  color: var(--gray-1000);
  font-size: 13px;
  font-weight: 500;
}

.uploaded-file-status {
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 12px;

  &.uploaded {
    background: rgba(31, 158, 134, 0.12);
    color: #167d73;
  }

  &.uploading {
    background: rgba(59, 130, 246, 0.12);
    color: #2563eb;
  }

  &.error {
    background: rgba(239, 68, 68, 0.12);
    color: #dc2626;
  }
}

.uploaded-file-path {
  color: var(--gray-700);
  font-size: 12px;
  word-break: break-all;
}

.breeding-collapse {
  :deep(.ant-collapse-item) {
    margin-bottom: 12px;
    border: 1px solid var(--gray-100);
    border-radius: 18px;
    overflow: hidden;
    background: rgba(255, 255, 255, 0.94);
    box-shadow: 0 12px 36px rgba(19, 31, 23, 0.05);
  }

  :deep(.ant-collapse-header) {
    align-items: center;
    padding: 18px 20px !important;
    color: var(--gray-1000);
    font-size: 16px;
    font-weight: 600;
  }

  :deep(.ant-collapse-content-box) {
    padding: 0 20px 20px !important;
  }
}

.field-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.single-column-grid {
  grid-template-columns: 1fr;
}

.field-item {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 14px;
  border: 1px solid var(--gray-100);
  border-radius: 14px;
  background: linear-gradient(180deg, var(--gray-0) 0%, #f8fcfb 100%);

  &.full-width {
    grid-column: 1 / -1;
  }
}

.field-label {
  color: var(--gray-700);
  font-size: 13px;
  font-weight: 500;
}

.file-input-row {
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-width: 0;

  &.dragging {
    :deep(.ant-input-affix-wrapper),
    :deep(.ant-input) {
      border-color: #1f9e86;
      box-shadow: 0 0 0 2px rgba(31, 158, 134, 0.12);
      background: rgba(220, 244, 238, 0.68);
    }
  }

  :deep(.ant-btn) {
    user-select: none;
  }

  :deep(.ant-input-affix-wrapper),
  :deep(.ant-input) {
    min-width: 0;
  }
}

.file-input-control {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;

  :deep(.ant-btn) {
    flex: 0 0 auto;
  }

  :deep(.ant-input-affix-wrapper),
  :deep(.ant-input) {
    flex: 1 1 auto;
    min-width: 0;
  }
}

.file-output-row {
  padding: 10px 12px;
  border: 1px dashed var(--gray-200);
  border-radius: 12px;
  background: var(--gray-0);
}

.file-output-note {
  color: var(--gray-700);
  font-size: 13px;
  line-height: 1.6;
}

.hidden-file-input {
  display: none;
}

.hint-text,
.hint-text,
.chain-chip,
.compliance-label,
.literature-doi,
.literature-quote,
.download-name,
.download-desc,
.result-block-body,
.artifact-pill {
  user-select: text;
}

.file-chip-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 2px;
}

.file-chip {
  display: inline-flex;
  align-items: center;
  padding: 5px 10px;
  border-radius: 999px;
  background: #edf7f4;
  color: #167d73;
  font-size: 12px;
}

.hint-text {
  margin: 14px 0 0;
  color: var(--gray-600);
  line-height: 1.65;
}

.action-row {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-top: 18px;

  :deep(.ant-btn-primary),
  :deep(.ant-btn) {
    user-select: none;
  }

  :deep(.ant-btn-primary) {
    border-color: #1b8f7a;
    background: linear-gradient(135deg, #1f9e86 0%, #167d73 100%);
  }
}

.chain-card,
.result-shell {
  padding: 18px 20px;
  border: 1px solid var(--gray-100);
  border-radius: 20px;
  background: rgba(255, 255, 255, 0.94);
  box-shadow: 0 14px 40px rgba(19, 31, 23, 0.06);
}

.chain-card {
  margin-bottom: 16px;
}

.chain-card-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 10px;
}

.chain-title {
  color: var(--gray-900);
  font-size: 14px;
  font-weight: 600;
}

.chain-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 10px;
  color: var(--gray-600);
  font-size: 12px;
}

.inline-status {
  display: flex;
  align-items: center;
  gap: 8px;
}

.status-label {
  color: var(--gray-600);
  font-size: 12px;
}

.status-pill {
  display: inline-flex;
  align-items: center;
  padding: 5px 10px;
  border-radius: 999px;
  border: 1px solid var(--gray-100);
  background: var(--gray-0);
  font-size: 12px;
  user-select: text;
}

.status-idle {
  color: var(--gray-700);
}

.status-running {
  border-color: rgba(26, 145, 118, 0.2);
  color: #15795f;
}

.status-success {
  border-color: rgba(38, 166, 91, 0.24);
  color: #217a3d;
}

.status-failed {
  border-color: rgba(233, 84, 84, 0.24);
  color: #c64646;
}

.chain-list {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.soft-timeout-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
  padding: 12px 14px;
  border: 1px solid rgba(235, 177, 49, 0.24);
  border-radius: 14px;
  background: rgba(255, 248, 226, 0.92);
}

.soft-timeout-text {
  flex: 1 1 320px;
  color: #8d6200;
  line-height: 1.6;
}

.soft-timeout-buttons {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.chain-chip {
  display: inline-flex;
  align-items: center;
  padding: 7px 12px;
  border-radius: 999px;
  background: color-mix(in srgb, #1f9e86 14%, white);
  color: #187764;
  font-size: 13px;
}

.result-alert {
  margin-bottom: 16px;
}

.result-block-grid {
  display: grid;
  grid-template-columns: minmax(240px, 0.9fr) minmax(340px, 1.2fr) minmax(240px, 0.9fr);
  gap: 12px;
  margin-bottom: 16px;
}

.result-block {
  padding: 14px;
  border: 1px solid var(--gray-100);
  border-radius: 16px;
  background: linear-gradient(180deg, var(--gray-0) 0%, #f8fcfb 100%);
}

.result-block-title {
  margin-bottom: 10px;
  color: var(--gray-900);
  font-size: 14px;
  font-weight: 600;
}

.result-block-body {
  color: var(--gray-600);
  line-height: 1.7;
}

.compliance-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.compliance-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.compliance-label {
  color: var(--gray-800);
  font-size: 13px;
}

.compliance-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 500;

  .status-dot {
    width: 8px;
    height: 8px;
    border-radius: 999px;
    background: currentColor;
  }

  &.passed {
    background: rgba(46, 174, 96, 0.14);
    color: #27784a;
  }

  &.missing {
    background: rgba(235, 177, 49, 0.16);
    color: #a26a06;
  }
}

.literature-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.literature-item {
  padding: 12px;
  border: 1px solid rgba(31, 158, 134, 0.14);
  border-radius: 12px;
  background: rgba(237, 247, 244, 0.65);
}

.literature-doi {
  margin-bottom: 6px;
  color: #136e63;
  font-size: 13px;
  font-weight: 600;
  word-break: break-all;
}

.literature-title {
  margin-bottom: 6px;
  color: var(--gray-800);
  font-size: 12px;
  line-height: 1.6;
}

.literature-source {
  margin-bottom: 6px;
  color: var(--gray-600);
  font-size: 12px;
}

.literature-quote {
  color: var(--gray-700);
  line-height: 1.7;
}

.claim-trace-list,
.artifact-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.claim-trace-item,
.artifact-item {
  padding: 8px 10px;
  border-radius: 8px;
  background: #f8fafc;
}

.claim-text {
  font-size: 13px;
  line-height: 1.6;
  color: #1f2937;
}

.claim-source-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 6px;
  color: #64748b;
  font-size: 12px;
}

.claim-source-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 8px;
}

.claim-source-item {
  padding: 8px 10px;
  border-radius: 10px;
  background: rgba(237, 247, 244, 0.65);
  color: var(--gray-700);
  font-size: 12px;
  line-height: 1.6;
}

.claim-meta {
  margin-top: 4px;
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  font-size: 12px;
  color: #64748b;
}

.artifact-name {
  display: inline-block;
  margin-right: 8px;
  font-weight: 600;
}

.download-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.download-card {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 12px;
  border: 1px solid var(--gray-100);
  border-radius: 14px;
  background: #fff;
  text-align: left;
  cursor: pointer;
  transition:
    border-color 0.2s ease,
    box-shadow 0.2s ease,
    transform 0.2s ease;
  user-select: none;

  &:hover:not(:disabled) {
    border-color: rgba(31, 158, 134, 0.28);
    box-shadow: 0 8px 20px rgba(17, 80, 67, 0.08);
    transform: translateY(-1px);
  }

  &:disabled {
    cursor: not-allowed;
    opacity: 0.58;
  }
}

.download-name {
  color: var(--gray-900);
  font-size: 13px;
  font-weight: 600;
}

.download-desc {
  color: var(--gray-600);
  font-size: 12px;
  line-height: 1.6;
}

.markdown-card {
  padding-top: 4px;
  user-select: text;

  :deep(.yk-markdown-preview) {
    user-select: text;
  }
}

.markdown-download-footer {
  display: flex;
  justify-content: flex-end;
  margin-top: 18px;

  :deep(.ant-btn) {
    user-select: none;
  }
}

.diagnostic-collapse {
  margin-top: 18px;

  :deep(.ant-collapse-item) {
    border: 1px dashed var(--gray-200);
    border-radius: 14px;
    background: rgba(250, 252, 251, 0.88);
  }

  :deep(.ant-collapse-header) {
    padding: 12px 14px !important;
    color: var(--gray-800);
    font-weight: 600;
  }

  :deep(.ant-collapse-content-box) {
    padding: 0 14px 14px !important;
  }
}

.diagnostic-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px 14px;
}

.diagnostic-item {
  display: flex;
  flex-direction: column;
  gap: 4px;

  &.full-span {
    grid-column: 1 / -1;
  }

  span {
    color: var(--gray-600);
    font-size: 12px;
  }

  code {
    padding: 6px 8px;
    border-radius: 10px;
    background: #f3f7f6;
    color: var(--gray-900);
    font-size: 12px;
    word-break: break-all;
    user-select: text;
  }
}

@media (max-width: 1200px) {
  .workbench-body {
    grid-template-columns: 1fr;
  }

  .result-block-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 860px) {
  .field-grid {
    grid-template-columns: 1fr;
  }

  .diagnostic-grid {
    grid-template-columns: 1fr;
  }

  .file-input-control {
    flex-wrap: wrap;
  }

  .chain-card-top {
    flex-direction: column;
    align-items: flex-start;
  }
}
</style>
