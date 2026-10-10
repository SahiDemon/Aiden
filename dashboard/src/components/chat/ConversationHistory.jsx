import React, { useState, useEffect } from 'react'
import { History, MessageSquare, ArrowRight } from 'lucide-react'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '../ui/dialog'
import api from '../../lib/api'

export default function ConversationHistory({ isOpen, onClose, onSelectConversation }) {
  const [conversations, setConversations] = useState([])
  const [selected, setSelected] = useState(null)
  const [messages, setMessages] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  useEffect(() => {
    if (!isOpen) return
    let active = true
    setLoading(true)
    api.getConversations().then(result => { if (active) setConversations(result.conversations || []) })
      .catch(err => { if (active) setError(err.message) })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [isOpen])
  useEffect(() => {
    if (!selected) return
    let active = true
    setMessages([]); setLoading(true); setError('')
    api.getConversation(selected.id).then(result => { if (active) setMessages(result.messages || []) })
      .catch(err => { if (active) setError(err.message) })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [selected])
  return <Dialog open={isOpen} onOpenChange={open => { if (!open) onClose() }}><DialogContent className="history-dialog"><DialogHeader><DialogTitle className="flex items-center gap-2"><History size={19} />Conversation history</DialogTitle><DialogDescription>Revisit your previous conversations with Aiden.</DialogDescription></DialogHeader>{error && <p role="alert" className="inline-error">{error}</p>}<div className="history-layout"><nav aria-label="Past conversations">{!conversations.length && !loading && <p className="history-empty">Your conversations will appear here.</p>}{conversations.map(conversation => <button className={selected?.id === conversation.id ? 'selected' : ''} key={conversation.id} onClick={() => setSelected(conversation)}><MessageSquare size={16} /><span>{new Date(conversation.created_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}<small>{new Date(conversation.created_at).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })} · {conversation.mode}</small></span><ArrowRight size={14} /></button>)}</nav><section className="history-preview">{loading ? <p role="status" className="history-empty">Loading conversation…</p> : selected ? <>{messages.map((message, index) => <article key={message.id || index}><strong>{message.role === 'user' ? 'You' : 'Aiden'}</strong><p>{message.content}</p></article>)}{!messages.length && <p className="history-empty">No saved messages in this conversation.</p>}{messages.length > 0 && <button className="history-open" onClick={() => { onSelectConversation(selected); onClose() }}>Continue conversation <ArrowRight size={16} /></button>}</> : <p className="history-empty">Select a conversation to read it.</p>}</section></div></DialogContent></Dialog>
}

