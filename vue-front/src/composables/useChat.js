import { ref, reactive, computed } from 'vue'
import {
  thinkStream, actionStream, actStream, observeStream,
  logUserInput, fetchGeneratedFiles, generateDocumentStream, generateDocumentUnifiedStream,
} from '@/utils/api.js'

export function useChat() {
  const sessionId = ref(generateSessionId())
  const question = ref('')
  const conversationHistory = ref([])
  const cycleIndex = ref(0)
  const isRunning = ref(false)
  const maxCycles = 999
  const awaitingInput = ref(false)
  const inputPrompt = ref('')
  const inputChoices = ref([])
  const isPaused = ref(false)
  const isCompleted = ref(false)

  const messages = ref([])
  const generatedFiles = ref([])

  const serverUrl = ref('http://127.0.0.1:8009')

  function generateSessionId() {
    const now = new Date()
    const ts = now.getFullYear().toString() +
      String(now.getMonth() + 1).padStart(2, '0') +
      String(now.getDate()).padStart(2, '0') +
      String(now.getHours()).padStart(2, '0') +
      String(now.getMinutes()).padStart(2, '0') +
      String(now.getSeconds()).padStart(2, '0')
    const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz'
    let rand = ''
    for (let i = 0; i < 8; i++) {
      rand += chars[Math.floor(Math.random() * chars.length)]
    }
    return ts + rand
  }

  function addMessage(type, phase, data = {}) {
    messages.value.push({
      id: Date.now() + Math.random(),
      type,
      phase,
      ...data,
      timestamp: Date.now(),
    })
  }

  function parsePlanJson(raw) {
    try {
      const result = JSON.parse(raw)
      if (typeof result === 'object' && result !== null) {
        return {
          description: result.description || raw,
          todo: result.todo || [],
        }
      }
    } catch {}
    return { description: raw, todo: [] }
  }

  function parseJsonRaw(raw) {
    raw = raw.trim()
    for (const prefix of ['```json', '```']) {
      if (raw.startsWith(prefix)) raw = raw.slice(prefix.length)
    }
    for (const suffix of ['```']) {
      if (raw.endsWith(suffix)) raw = raw.slice(0, -suffix.length)
    }
    raw = raw.trim()
    try {
      return JSON.parse(raw)
    } catch {
      return {}
    }
  }

function historyToText(history) {
    return history.map(entry => {
      const role = entry.role || ''
      const type = entry.type || ''
      const content = entry.content || ''
      if (role === 'user') {
        return `User: ${content}`
      }
      return `Assistant (${type}): ${content}`
    }).join('\n')
  }

  const FRONTEND_ACTIONS = new Set(['output_text', 'ask_question', 'ask_choice', 'summary_and_pause', 'attempt_completion'])

  async function startChat(questionText) {
    if (isRunning.value) return

    question.value = questionText
    isRunning.value = true
    isCompleted.value = false
    isPaused.value = false
    awaitingInput.value = false
    cycleIndex.value = 0

    addMessage('user', 'question', { content: questionText })
    conversationHistory.value = [{ role: 'user', type: 'question', content: questionText }]

    try {
      await runMainLoop()
    } catch (e) {
      console.error('Chat error:', e)
      addMessage('error', 'system', { content: `Error: ${e.message}` })
    } finally {
      isRunning.value = false
    }
  }

  async function runMainLoop() {
    while (true) {
      if (isCompleted.value || isPaused.value) break

      cycleIndex.value++
      if (cycleIndex.value > maxCycles) {
        addMessage('system', 'warning', { content: 'Reached max cycles.' })
        break
      }

      // Think phase
      await runThinkPhase()
      const fullQuestion = historyToText(conversationHistory.value)

      // Action phase - decide what to do
      const actionResult = await runActionPhase()
      const action = actionResult.action
      if (!action) {
        addMessage('system', 'error', { content: `Action failed: ${actionResult.error || 'unknown'}` })
        break
      }

      // Act phase
      const actResult = await runActPhase(action, fullQuestion, actionResult)
      if (actResult.function_solved) {
        continue
      }

      if (actResult.needs_user_input) {
        awaitingInput.value = true
        inputPrompt.value = actResult.full_ans
        inputChoices.value = actResult.choices || []
        isRunning.value = false
        return
      }

      if (actResult.paused) {
        isPaused.value = true
        isRunning.value = false
        return
      }

      if (actResult.completed) {
        isCompleted.value = true
        isRunning.value = false
        return
      }

      // Observe phase
      await runObservePhase()
    }
  }

  async function runThinkPhase() {
    const msgId = Date.now()
    addMessage('stream', 'think', { label: 'THINK - Planning', content: '', streaming: true, msgId })

    let rawPlan = ''
    const gen = thinkStream({
      question: question.value,
      conversation_history: conversationHistory.value,
      session_id: sessionId.value,
    })
    for await (const event of gen) {
      if (event.type === 'chunk') {
        rawPlan += event.content
        updateStreamingMessage(msgId, rawPlan)
      } else if (event.type === 'done') {
        const doneContent = event.content || ''
        if (doneContent && !rawPlan) rawPlan = doneContent
        updateStreamingMessage(msgId, rawPlan, false)
      } else if (event.type === 'error') {
        updateStreamingMessage(msgId, event.content, false, true)
      } else if (event.type === 'history') {
        handleHistoryEvent(event.history)
      }
    }
    return {}
  }

  async function runActionPhase() {
    const msgId = Date.now()
    addMessage('stream', 'action_decision', { label: 'ACTION - Decide', content: '', streaming: true, msgId })

    let rawDecision = ''
    const gen = actionStream({
      question: question.value,
      conversation_history: conversationHistory.value,
      cycle_index: cycleIndex.value,
      session_id: sessionId.value,
    })
    for await (const event of gen) {
      if (event.type === 'chunk') {
        rawDecision += event.content
        updateStreamingMessage(msgId, rawDecision)
      } else if (event.type === 'done') {
        updateStreamingMessage(msgId, rawDecision, false)
      } else if (event.type === 'error') {
        updateStreamingMessage(msgId, event.content, false, true)
      } else if (event.type === 'history') {
        handleHistoryEvent(event.history)
      }
    }
    const lastAction = [...conversationHistory.value].reverse().find(e => e.type === 'action_decision')
    return lastAction?.content || {}
  }

  async function runActPhase(action, fullQuestion, actionResult) {
    if (FRONTEND_ACTIONS.has(action)) {
      return handleFrontendAction(action, actionResult)
    }

    const msgId = Date.now()
    addMessage('stream', 'act', {
      label: `ACT - ${action}`, action,
      content: '', streaming: true, msgId, subPhases: [],
    })

    let currentSubPhase = null
    let currentSubContent = ''
    const gen = actStream({
      action,
      question: fullQuestion,
      conversation_history: conversationHistory.value,
      session_id: sessionId.value,
      params: {
        tables: [],
        search_keyword: actionResult.keyword || undefined,
        selected_fields: action === 'generate_and_execute' ? { __no_db__: true } : undefined,
        selected_functions: actionResult.funcs || undefined,
        research_guide: actionResult.research_guide || undefined,
        title: actionResult.title || undefined,
      },
    })

    for await (const event of gen) {
      const sub = event.sub_phase || ''
      const etype = event.type || ''
      const content = event.content || ''

      if (event.type === 'history') {
        handleHistoryEvent(event.history)
        continue
      }

      if (sub && sub !== currentSubPhase) {
        if (currentSubContent) {
          addSubPhaseToMessage(msgId, currentSubPhase, currentSubContent)
        }
        currentSubPhase = sub
        currentSubContent = ''
      }

      if ((etype === 'chunk' || etype === 'code_chunk') && event.sub_type !== 'exec_complete') {
        currentSubContent += content
        updateStreamingSubPhase(msgId, currentSubPhase, currentSubContent)
      } else if (etype === 'done') {
        updateStreamingSubPhase(msgId, currentSubPhase, currentSubContent, false)
        if (sub === 'generate_document' && event.download_url_md) {
          addSubPhaseToMessage(msgId, currentSubPhase, currentSubContent)
          setTimeout(() => {
            const idx = messages.value.findIndex(m => m.msgId === msgId)
            if (idx !== -1) messages.value[idx].streaming = false
          })
          generatedFiles.value.push({
            id: msgId,
            title: event.title || 'Document',
            downloadUrlMd: `${serverUrl.value}/tmp_imgs/${event.file_name}.md`,
            downloadUrlDocx: `${serverUrl.value}/tmp_imgs/${event.file_name}.docx`,
            createdAt: Date.now(),
          })
        }
      } else if (etype === 'error') {
        updateStreamingSubPhase(msgId, currentSubPhase, content, false, true)
      }
    }

    if (currentSubContent) {
      addSubPhaseToMessage(msgId, currentSubPhase, currentSubContent)
    }

    return {}
  }

  function handleFrontendAction(action, actionResult) {
    const text = actionResult.text || ''
    const choices = actionResult.choices || []

    const result = {
      selected_fields: null, selected_functions: null,
      function_solved: false, full_code: '', full_ans: text,
      exec_error: null, solved_ans: '',
      needs_user_input: false, choices,
      paused: false, completed: false,
    }

    conversationHistory.value.push({ role: 'assistant', type: 'act', action, text })

    if (action === 'output_text') {
      addMessage('assistant', 'act', { action, text, collapsed: true })
    } else if (action === 'ask_question') {
      addMessage('assistant', 'act', { action, text, collapsed: false })
      result.needs_user_input = true
    } else if (action === 'ask_choice') {
      addMessage('assistant', 'act', { action, text, choices, collapsed: false })
      result.needs_user_input = true
    } else if (action === 'summary_and_pause') {
      addMessage('assistant', 'act', { action, text, collapsed: false })
      result.paused = true
    } else if (action === 'attempt_completion') {
      addMessage('assistant', 'act', { action, text, collapsed: false })
      result.completed = true
    }

    return result
  }

  async function runObservePhase() {
    const msgId = Date.now()
    addMessage('stream', 'observe', { label: 'OBSERVE - Review', content: '', streaming: true, msgId })

    let rawReview = ''
    const gen = observeStream({
      question: question.value,
      conversation_history: conversationHistory.value,
      cycle_index: cycleIndex.value,
      session_id: sessionId.value,
    })
    for await (const event of gen) {
      if (event.type === 'chunk') {
        rawReview += event.content
        updateStreamingMessage(msgId, rawReview)
      } else if (event.type === 'done') {
        updateStreamingMessage(msgId, rawReview, false)
      } else if (event.type === 'error') {
        updateStreamingMessage(msgId, event.content, false, true)
      } else if (event.type === 'history') {
        handleHistoryEvent(event.history)
      }
    }
  }

  function updateStreamingMessage(msgId, content, streaming = true, isError = false) {
    const idx = messages.value.findIndex(m => m.msgId === msgId)
    if (idx !== -1) {
      messages.value[idx].content = content
      messages.value[idx].streaming = streaming
      messages.value[idx].isError = isError
    }
  }

  function updateStreamingSubPhase(msgId, subPhase, content, streaming = true, isError = false) {
    const idx = messages.value.findIndex(m => m.msgId === msgId)
    if (idx !== -1) {
      const msg = messages.value[idx]
      if (!msg.subPhases) msg.subPhases = []
      const existing = msg.subPhases.find(s => s.name === subPhase)
      if (existing) {
        existing.content = content
        existing.streaming = streaming
        existing.isError = isError
      } else {
        msg.subPhases.push({ name: subPhase, content, streaming, isError })
      }
    }
  }

  function addSubPhaseToMessage(msgId, subPhase, content) {
    const idx = messages.value.findIndex(m => m.msgId === msgId)
    if (idx !== -1) {
      const msg = messages.value[idx]
      if (!msg.subPhases) msg.subPhases = []
      const existing = msg.subPhases.find(s => s.name === subPhase)
      if (existing) {
        existing.content = content
        existing.streaming = false
        existing.isError = false
      } else {
        msg.subPhases.push({ name: subPhase, content, streaming: false, isError: false })
      }
    }
  }

  async function submitUserResponse(response) {
    awaitingInput.value = false
    if (inputChoices.value.length > 0) {
      conversationHistory.value.push({ role: 'user', type: 'choice', content: response })
      addMessage('user', 'choice', { content: `Selected: ${response}` })
      await logUserInput(sessionId.value, cycleIndex.value, `User chose: ${response}`)
    } else {
      conversationHistory.value.push({ role: 'user', type: 'response', content: response })
      addMessage('user', 'response', { content: response })
      await logUserInput(sessionId.value, cycleIndex.value, `User response: ${response}`)
    }
    inputChoices.value = []
    inputPrompt.value = ''

    isRunning.value = true
    try {
      await runMainLoop()
    } catch (e) {
      console.error('Chat error:', e)
      addMessage('error', 'system', { content: `Error: ${e.message}` })
    } finally {
      isRunning.value = false
    }
  }

  async function submitPausedInput(input) {
    isPaused.value = false
    const userInput = input || 'continue'
    conversationHistory.value.push({ role: 'user', type: 'input', content: userInput })
    addMessage('user', 'input', { content: userInput, collapsed: true })
    await logUserInput(sessionId.value, cycleIndex.value, `User: ${userInput}`)

    isRunning.value = true
    try {
      await runMainLoop()
    } catch (e) {
      console.error('Chat error:', e)
      addMessage('error', 'system', { content: `Error: ${e.message}` })
    } finally {
      isRunning.value = false
    }
  }

  async function submitNewQuestion(newQuestion) {
    isCompleted.value = false
    question.value = newQuestion
    addMessage('user', 'question', { content: newQuestion })
    conversationHistory.value = [{ role: 'user', type: 'question', content: newQuestion }]
    cycleIndex.value = 0

    isRunning.value = true
    try {
      await runMainLoop()
    } catch (e) {
      console.error('Chat error:', e)
      addMessage('error', 'system', { content: `Error: ${e.message}` })
    } finally {
      isRunning.value = false
    }
  }

  async function resumeSession(sessionData) {
    sessionId.value = sessionData.session_id
    question.value = sessionData.question || ''
    cycleIndex.value = sessionData.cycle_count || 0

    addMessage('system', 'resume', {
      content: `Session restored: \`${sessionId.value}\`\nOriginal question: ${question.value}\nCycles completed: ${cycleIndex.value}`,
    })

    handleHistoryEvent(sessionData.conversation_history || [])

    try {
      const files = await fetchGeneratedFiles(sessionId.value)
      generatedFiles.value = files
    } catch {
      generatedFiles.value = []
    }
  }

  function rebuildMessagesFromHistory(history) {
    messages.value = []
    for (const entry of history) {
      renderHistoryEntry(entry)
    }
  }

  function handleHistoryEvent(history) {
    conversationHistory.value = history
    rebuildMessagesFromHistory(history)
  }

  function renderHistoryEntry(entry) {
    const role = entry.role || ''
    const entryType = entry.type || ''

    if (role === 'user') {
      const utype = entry.type || 'question'
      const content = entry.content || ''
      if (utype === 'choice') {
        addMessage('user', 'choice', { content: `Selected: ${content}`, collapsed: true })
      } else if (utype === 'response' || utype === 'input') {
        addMessage('user', 'input', { content, collapsed: true })
      } else {
        addMessage('user', 'question', { content })
      }
      return
    }

    if (entryType === 'think') {
      const content = entry.content || ''
      const plan = typeof content === 'object' ? content : parsePlanJson(content)
      addMessage('assistant', 'think', { content: typeof content === 'object' ? JSON.stringify(content) : content, planResult: plan, collapsed: true })
    } else if (entryType === 'action_decision') {
      const content = entry.content || ''
      addMessage('assistant', 'action_decision', { content: typeof content === 'object' ? JSON.stringify(content) : content, collapsed: true })
    } else if (entryType === 'observe') {
      const content = entry.content || ''
      const plan = typeof content === 'object' ? content : parsePlanJson(content)
      addMessage('assistant', 'observe', { content: typeof content === 'object' ? JSON.stringify(content) : content, planResult: plan, collapsed: true })
    } else if (entryType === 'act') {
      addMessage('assistant', 'act', {
        action: entry.action,
        text: entry.text,
        code: entry.code,
        result: entry.result,
        error: entry.error,
        solved_ans: entry.solved_ans,
        selected_fields: entry.selected_fields,
        selected_functions: entry.selected_functions,
        search_result: entry.search_result,
        explore_plan: entry.explore_plan,
        attempts: entry.attempts,
        title: entry.title,
        file_name: entry.file_name,
        collapsed: true,
      })
    } else if (entryType === 'document') {
      addMessage('assistant', 'document', { content: entry.content })
    }
  }

  async function generateDocument() {
    const docMsgId = Date.now()
    addMessage('stream', 'document', {
      label: 'Generating Document (Step-by-step)...',
      content: '',
      streaming: true,
      msgId: docMsgId,
      docParts: [],
      docOutline: null,
    })

    const events = []
    let outlineRaw = ''
    let outlineData = null
    let partAccumulator = ''
    let currentPartIdx = -1
    const completedParts = []

    const gen = generateDocumentStream({
      conversation_history: conversationHistory.value,
      session_id: sessionId.value,
    })

    for await (const event of gen) {
      events.push(event)
      const phase = event.phase || ''
      const etype = event.type || ''
      const content = event.content || ''

      if (phase === 'outline') {
        if (etype === 'chunk') {
          outlineRaw += content
          updateDocMessage(docMsgId, { outlineGenerating: outlineRaw })
        } else if (etype === 'done') {
          outlineData = event.outline || {}
          updateDocMessage(docMsgId, { docOutline: outlineData, outlineGenerating: null })
        } else if (etype === 'error') {
          updateDocMessage(docMsgId, { outlineError: content })
        }
      } else if (phase === 'part') {
        const partIdx = event.part_index ?? -1
        if (etype === 'msg') {
          currentPartIdx = partIdx
          partAccumulator = ''
          updateDocMessage(docMsgId, {
            currentPartIdx,
            currentPartHeading: event.heading || `Part ${partIdx + 1}`,
            completedParts: [...completedParts],
          })
        } else if (etype === 'chunk') {
          partAccumulator += content
          updateDocMessage(docMsgId, {
            currentPartIdx,
            currentPartContent: partAccumulator,
            completedParts: [...completedParts],
          })
        } else if (etype === 'done') {
          completedParts.push({
            heading: event.heading || `Part ${partIdx + 1}`,
            content: partAccumulator,
          })
          updateDocMessage(docMsgId, {
            completedParts: [...completedParts],
            currentPartIdx: null,
            currentPartContent: null,
          })
        }
      } else if (phase === 'document' && etype === 'done') {
        updateDocMessage(docMsgId, {
          streaming: false,
          docContent: content,
          downloadUrlMd: `${serverUrl.value}/tmp_imgs/${event.file_name}.md`,
          downloadUrlDocx: `${serverUrl.value}/tmp_imgs/${event.file_name}.docx`,
          completedParts: [...completedParts],
        })
        generatedFiles.value.push({
          id: docMsgId,
          title: outlineData?.title || 'Document',
          downloadUrlMd: `${serverUrl.value}/tmp_imgs/${event.file_name}.md`,
          downloadUrlDocx: `${serverUrl.value}/tmp_imgs/${event.file_name}.docx`,
          createdAt: Date.now(),
        })
      }
    }
  }

  async function generateDocumentUnified() {
    const docMsgId = Date.now()
    addMessage('stream', 'document', {
      label: 'Generating Document...',
      content: '',
      streaming: true,
      msgId: docMsgId,
      docParts: [],
      docOutline: null,
    })

    let fullContent = ''

    const gen = generateDocumentUnifiedStream({
      conversation_history: conversationHistory.value,
      session_id: sessionId.value,
    })

    for await (const event of gen) {
      const phase = event.phase || ''
      const etype = event.type || ''
      const content = event.content || ''

      if (phase === 'act' && etype === 'chunk') {
        fullContent += content
        updateDocMessage(docMsgId, { outlineGenerating: fullContent })
      } else if (phase === 'act' && etype === 'done' && event.file_name) {
        updateDocMessage(docMsgId, {
          streaming: false,
          docContent: content,
          downloadUrlMd: `${serverUrl.value}/tmp_imgs/${event.file_name}.md`,
          downloadUrlDocx: `${serverUrl.value}/tmp_imgs/${event.file_name}.docx`,
        })
        generatedFiles.value.push({
          id: docMsgId,
          title: event.title || 'Document',
          downloadUrlMd: `${serverUrl.value}/tmp_imgs/${event.file_name}.md`,
          downloadUrlDocx: `${serverUrl.value}/tmp_imgs/${event.file_name}.docx`,
          createdAt: Date.now(),
        })
      }
    }
  }

  function updateDocMessage(msgId, updates) {
    const idx = messages.value.findIndex(m => m.msgId === msgId)
    if (idx !== -1) {
      Object.assign(messages.value[idx], updates)
    }
  }

  function reset() {
    messages.value = []
    conversationHistory.value = []
    cycleIndex.value = 0
    isRunning.value = false
    isCompleted.value = false
    isPaused.value = false
    awaitingInput.value = false
    inputPrompt.value = ''
    inputChoices.value = []
    generatedFiles.value = []
    sessionId.value = generateSessionId()
    question.value = ''
  }

  return {
    sessionId,
    question,
    messages,
    generatedFiles,
    isRunning,
    isCompleted,
    isPaused,
    awaitingInput,
    inputPrompt,
    inputChoices,
    cycleIndex,
    startChat,
    submitUserResponse,
    submitPausedInput,
    submitNewQuestion,
    resumeSession,
    generateDocument,
    generateDocumentUnified,
    reset,
    serverUrl,
  }
}