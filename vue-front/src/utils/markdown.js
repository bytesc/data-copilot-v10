import { marked } from 'marked'

marked.setOptions({
  breaks: true,
  gfm: true,
})

export function renderMarkdown(text) {
  if (!text) return ''
  return marked.parse(text)
}

export function renderMarkdownInline(text) {
  if (!text) return ''
  return marked.parseInline(text)
}