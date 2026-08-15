import { ref, reactive, computed } from 'vue'
import {
  thinkStream, actionStream, actStream, observeStream,
  logUserInput, generateDocumentStream, fetchGeneratedFiles,
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

  function parseThinkResult(events) {
    for (const event of events) {
      if (event.type === 'done') {
        if (event.plan_result) return event.plan_result
        return parsePlanJson(event.content || '')
      }
    }
    return { description: '', todo: [] }
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

  function parseActionResult(events) {
    for (const event of events) {
      if (event.type === 'done' && event.action_result) {
        return event.action_result
      }
    }
    return { action: null, error: 'No action result' }
  }

  function parseActResult(events) {
    const parsed = {
      selected_fields: null,
      selected_functions: null,
      function_solved: false,
      full_code: '',
      full_ans: '',
      exec_error: null,
      solved_ans: '',
      needs_user_input: false,
      choices: [],
      paused: false,
      completed: false,
      db_context: null,
      func_context: null,
      search_result: null,
      explore_plan: '',
    }
    for (const event of events) {
      const sub = event.sub_phase || ''
      const etype = event.type || ''
      const content = event.content || ''
      const result = event.result

      if (etype === 'done' && result && typeof result === 'object') {
        if (sub === 'explore_schema' || sub === 'explore_functions') {
          parsed.search_result = content
          parsed.db_context = result.db_context || parsed.db_context
          parsed.func_context = result.func_context || parsed.func_context
          parsed.explore_plan = result.explore_plan || parsed.explore_plan
          if (result.selected_fields != null) parsed.selected_fields = result.selected_fields
          if (result.selected_functions != null) parsed.selected_functions = result.selected_functions
        } else if (sub === 'output_text' || sub === 'summary' || sub === 'completion') {
          parsed.full_ans = result.text || content
          if (result.paused) parsed.paused = true
          if (result.completed) parsed.completed = true
        } else if (sub === 'exec') {
          parsed.full_code = result.code || ''
          parsed.full_ans = result.exec_result || ''
          parsed.exec_error = result.error || null
          if (result.solved_ans) parsed.solved_ans = result.solved_ans
        } else if (sub === 'ask_question') {
          parsed.full_ans = result.text || content
          if (result.needs_user_input) parsed.needs_user_input = true
        } else if (sub === 'ask_choice') {
          parsed.full_ans = result.text || content
          parsed.choices = result.choices || []
          if (result.needs_user_input) parsed.needs_user_input = true
        }
      } else if (etype === 'chunk' || etype === 'code_chunk') {
        if (sub === 'output_text' || sub === 'summary' || sub === 'completion') {
          parsed.full_ans += content
        }
        if (sub === 'exec') {
          parsed.full_ans += content
          parsed.exec_error = null
        }
      } else if (sub === 'code' && event.sub_type === 'code_complete') {
        parsed.full_code = content
      } else if (sub === 'code' && etype === 'solved') {
        parsed.solved_ans = content
        parsed.function_solved = true
      } else if (sub === 'exec' && event.sub_type === 'code_exe_error') {
        parsed.exec_error = content
      }
    }
    return parsed
  }

  function parseObserveResult(events) {
    for (const event of events) {
      if (event.type === 'done') {
        if (event.plan_result) return event.plan_result
        return parsePlanJson(event.content || '')
      }
    }
    return { description: '', todo: [] }
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
        if (actResult.solved_ans) {
          conversationHistory.value.push({
            role: 'assistant', type: 'act', action: 'solved', solved_ans: actResult.solved_ans,
          })
        }
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

  async function collectSSEEvents(gen) {
    const events = []
    for await (const event of gen) {
      events.push(event)
    }
    return events
  }

  async function runThinkPhase() {
    const label = cycleIndex.value === 1 ? 'THINK - Planning' : `THINK - Planning (Cycle ${cycleIndex.value})`
    const msgId = Date.now()
    addMessage('stream', 'think', { label, content: '', streaming: true, msgId })

    const events = []
    let rawPlan = ''
    const gen = thinkStream({
      question: question.value,
      conversation_history: conversationHistory.value,
      session_id: sessionId.value,
    })
    for await (const event of gen) {
      events.push(event)
      if (event.type === 'chunk') {
        rawPlan += event.content
        updateStreamingMessage(msgId, rawPlan)
      } else if (event.type === 'done') {
        const doneContent = event.content || ''
        if (doneContent && !rawPlan) rawPlan = doneContent
        updateStreamingMessage(msgId, rawPlan, false)
      } else if (event.type === 'error') {
        updateStreamingMessage(msgId, event.content, false, true)
      }
    }

    const result = parseThinkResult(events)
    finalizeThinkMessage(msgId, rawPlan, result)
    conversationHistory.value.push({ role: 'assistant', type: 'think', content: rawPlan })
    return { result, rawPlan }
  }

  async function runActionPhase() {
    const msgId = Date.now()
    const label = `ACTION - Decide (Cycle ${cycleIndex.value})`
    addMessage('stream', 'action_decision', { label, content: '', streaming: true, msgId })

    const events = []
    let rawDecision = ''
    const gen = actionStream({
      question: question.value,
      conversation_history: conversationHistory.value,
      cycle_index: cycleIndex.value,
      session_id: sessionId.value,
    })
    for await (const event of gen) {
      events.push(event)
      if (event.type === 'chunk') {
        rawDecision += event.content
        updateStreamingMessage(msgId, rawDecision)
      } else if (event.type === 'done') {
        updateStreamingMessage(msgId, rawDecision, false)
      } else if (event.type === 'error') {
        updateStreamingMessage(msgId, event.content, false, true)
      }
    }

    finalizeDecisionMessage(msgId, rawDecision)
    conversationHistory.value.push({ role: 'assistant', type: 'action_decision', content: rawDecision })
    return parseActionResult(events)
  }

  async function runActPhase(action, fullQuestion, actionResult) {
    if (FRONTEND_ACTIONS.has(action)) {
      return handleFrontendAction(action, actionResult)
    }

    const label = `ACT - ${action} (Cycle ${cycleIndex.value})`
    const msgId = Date.now()
    addMessage('stream', 'act', {
      label,
      action,
      content: '',
      streaming: true,
      msgId,
      subPhases: [],
    })

    const events = []
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
      },
    })

    for await (const event of gen) {
      events.push(event)
      const sub = event.sub_phase || ''
      const etype = event.type || ''
      const content = event.content || ''

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
      } else if (etype === 'error') {
        updateStreamingSubPhase(msgId, currentSubPhase, content, false, true)
      }
    }

    if (currentSubContent) {
      addSubPhaseToMessage(msgId, currentSubPhase, currentSubContent)
    }

    const parsed = parseActResult(events)
    finalizeActMessage(msgId, action, parsed)

    if (parsed.selected_fields != null) {
      conversationHistory.value.push({
        role: 'assistant', type: 'act', action: 'explore_schema', selected_fields: parsed.selected_fields,
      })
    }
    if (parsed.selected_functions != null) {
      conversationHistory.value.push({
        role: 'assistant', type: 'act', action: 'explore_functions', selected_functions: parsed.selected_functions,
      })
    }
    if (parsed.search_result) {
      conversationHistory.value.push({
        role: 'assistant', type: 'act', action, search_result: parsed.search_result,
      })
    }
    if (parsed.full_ans && !parsed.exec_error && parsed.full_code) {
      conversationHistory.value.push({
        role: 'assistant', type: 'act', action: 'generate_and_execute',
        code: parsed.full_code, result: parsed.full_ans,
      })
    } else if (parsed.exec_error) {
      conversationHistory.value.push({
        role: 'assistant', type: 'act', action: 'generate_and_execute',
        error: parsed.exec_error, code: parsed.full_code || undefined,
      })
    } else if (parsed.full_ans && FRONTEND_ACTIONS.has(action)) {
      conversationHistory.value.push({
        role: 'assistant', type: 'act', action, text: parsed.full_ans,
      })
    }

    return parsed
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
    const label = `OBSERVE - Review (Cycle ${cycleIndex.value})`
    const msgId = Date.now()
    addMessage('stream', 'observe', { label, content: '', streaming: true, msgId })

    const events = []
    let rawReview = ''
    const gen = observeStream({
      question: question.value,
      conversation_history: conversationHistory.value,
      cycle_index: cycleIndex.value,
      session_id: sessionId.value,
    })
    for await (const event of gen) {
      events.push(event)
      if (event.type === 'chunk') {
        rawReview += event.content
        updateStreamingMessage(msgId, rawReview)
      } else if (event.type === 'done') {
        updateStreamingMessage(msgId, rawReview, false)
      } else if (event.type === 'error') {
        updateStreamingMessage(msgId, event.content, false, true)
      }
    }

    const result = parseObserveResult(events)
    finalizeObserveMessage(msgId, rawReview, result)
    conversationHistory.value.push({ role: 'assistant', type: 'observe', content: rawReview })
    return { result, rawReview }
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

  function finalizeThinkMessage(msgId, content, result) {
    const idx = messages.value.findIndex(m => m.msgId === msgId)
    if (idx !== -1) {
      messages.value[idx].content = content
      messages.value[idx].streaming = false
      messages.value[idx].planResult = result
      messages.value[idx].phase = 'think'
    }
  }

  function finalizeDecisionMessage(msgId, content) {
    const idx = messages.value.findIndex(m => m.msgId === msgId)
    if (idx !== -1) {
      messages.value[idx].content = content
      messages.value[idx].streaming = false
      messages.value[idx].phase = 'action_decision'
    }
  }

  function finalizeActMessage(msgId, action, parsed) {
    const idx = messages.value.findIndex(m => m.msgId === msgId)
    if (idx !== -1) {
      messages.value[idx].streaming = false
      messages.value[idx].parsed = parsed
      if (parsed.attempts?.length) {
        messages.value[idx].attempts = parsed.attempts
      }
    }
  }

  function finalizeObserveMessage(msgId, content, result) {
    const idx = messages.value.findIndex(m => m.msgId === msgId)
    if (idx !== -1) {
      messages.value[idx].content = content
      messages.value[idx].streaming = false
      messages.value[idx].planResult = result
      messages.value[idx].phase = 'observe'
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
    conversationHistory.value = sessionData.conversation_history || []
    cycleIndex.value = sessionData.cycle_count || 0

    addMessage('system', 'resume', {
      content: `Session restored: \`${sessionId.value}\`\nOriginal question: ${question.value}\nCycles completed: ${cycleIndex.value}`,
    })

    for (const entry of conversationHistory.value) {
      renderHistoryEntry(entry)
    }

    try {
      const files = await fetchGeneratedFiles(sessionId.value)
      generatedFiles.value = files
    } catch {
      generatedFiles.value = []
    }
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
      const plan = parsePlanJson(entry.content || '')
      addMessage('assistant', 'think', { content: entry.content, planResult: plan, collapsed: true })
    } else if (entryType === 'action_decision') {
      addMessage('assistant', 'action_decision', { content: entry.content, collapsed: true })
    } else if (entryType === 'observe') {
      const plan = parsePlanJson(entry.content || '')
      addMessage('assistant', 'observe', { content: entry.content, planResult: plan, collapsed: true })
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
        collapsed: true,
      })
    } else if (entryType === 'document') {
      addMessage('assistant', 'document', { content: entry.content })
    }
  }

  async function generateDocument() {
    const docMsgId = Date.now()
    addMessage('stream', 'document', {
      label: 'Generating Document...',
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
          downloadUrlMd: event.download_url_md || event.download_url || '',
          downloadUrlDocx: event.download_url_docx || '',
          completedParts: [...completedParts],
        })
        generatedFiles.value.push({
          id: docMsgId,
          title: outlineData?.title || 'Document',
          downloadUrlMd: event.download_url_md || event.download_url || '',
          downloadUrlDocx: event.download_url_docx || '',
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
    reset,
    serverUrl,
  }
}