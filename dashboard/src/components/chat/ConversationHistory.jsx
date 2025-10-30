import React, { useState, useEffect } from 'react'
import { X, MessageCircle, Calendar, Clock } from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card'
import { Button } from '../ui/button'
import { ScrollArea } from '../ui/scroll-area'
import { Badge } from '../ui/badge'
import api from '../../lib/api'

const ConversationHistory = ({ isOpen, onClose, onSelectConversation }) => {
  const [conversations, setConversations] = useState([])
  const [loading, setLoading] = useState(false)
  const [selectedConversation, setSelectedConversation] = useState(null)
  const [messages, setMessages] = useState([])

  // Load conversations when opened
  useEffect(() => {
    if (isOpen) {
      loadConversations()
    }
  }, [isOpen])

  const loadConversations = async () => {
    setLoading(true)
    try {
      const response = await api.getConversations()
      if (response.success) {
        setConversations(response.conversations || [])
      }
    } catch (error) {
      console.error('Error loading conversations:', error)
    } finally {
      setLoading(false)
    }
  }

  const loadConversationMessages = async (conversationId) => {
    try {
      const response = await api.getConversation(conversationId)
      if (response.success) {
        setMessages(response.messages || [])
        setSelectedConversation(conversationId)
      }
    } catch (error) {
      console.error('Error loading conversation messages:', error)
    }
  }

  const formatDate = (dateString) => {
    const date = new Date(dateString)
    const now = new Date()
    const diffTime = Math.abs(now - date)
    const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24))

    if (diffDays === 1) return 'Today'
    if (diffDays === 2) return 'Yesterday'
    if (diffDays <= 7) return `${diffDays} days ago`
    return date.toLocaleDateString()
  }

  const formatTime = (dateString) => {
    return new Date(dateString).toLocaleTimeString([], { 
      hour: '2-digit', 
      minute: '2-digit' 
    })
  }

  const handleSelectConversation = (conversation) => {
    onSelectConversation(conversation)
    onClose()
  }

  if (!isOpen) return null

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 bg-black/50 flex items-center justify-center z-50"
      onClick={onClose}
    >
      <motion.div
        initial={{ scale: 0.9, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        exit={{ scale: 0.9, opacity: 0 }}
        className="bg-background border rounded-lg shadow-lg w-full max-w-4xl h-[80vh] m-4"
        onClick={(e) => e.stopPropagation()}
      >
        <Card className="h-full">
          <CardHeader className="border-b">
            <div className="flex items-center justify-between">
              <CardTitle className="flex items-center gap-2">
                <MessageCircle className="w-5 h-5" />
                Conversation History
              </CardTitle>
              <Button variant="ghost" size="sm" onClick={onClose}>
                <X className="w-4 h-4" />
              </Button>
            </div>
          </CardHeader>

          <CardContent className="p-0 h-[calc(100%-80px)]">
            <div className="grid grid-cols-1 md:grid-cols-2 h-full">
              {/* Conversations List */}
              <div className="border-r">
                <div className="p-4 border-b">
                  <h3 className="font-semibold text-sm">Recent Conversations</h3>
                </div>
                
                <ScrollArea className="h-[calc(100%-60px)]">
                  {loading ? (
                    <div className="p-4 text-center text-muted-foreground">
                      Loading conversations...
                    </div>
                  ) : conversations.length === 0 ? (
                    <div className="p-4 text-center text-muted-foreground">
                      No conversations found
                    </div>
                  ) : (
                    <div className="p-2 space-y-2">
                      {conversations.map((conversation) => (
                        <motion.div
                          key={conversation.id}
                          whileHover={{ scale: 1.02 }}
                          whileTap={{ scale: 0.98 }}
                          className={`p-3 rounded-lg border cursor-pointer transition-colors ${
                            selectedConversation === conversation.id
                              ? 'bg-primary/10 border-primary'
                              : 'hover:bg-muted/50'
                          }`}
                          onClick={() => loadConversationMessages(conversation.id)}
                        >
                          <div className="flex items-center justify-between mb-2">
                            <Badge variant="outline" className="text-xs">
                              {conversation.mode}
                            </Badge>
                            <span className="text-xs text-muted-foreground">
                              {formatTime(conversation.created_at)}
                            </span>
                          </div>
                          
                          <div className="flex items-center gap-2 text-xs text-muted-foreground">
                            <Calendar className="w-3 h-3" />
                            {formatDate(conversation.created_at)}
                          </div>
                        </motion.div>
                      ))}
                    </div>
                  )}
                </ScrollArea>
              </div>

              {/* Messages Preview */}
              <div>
                <div className="p-4 border-b">
                  <h3 className="font-semibold text-sm">
                    {selectedConversation ? 'Messages' : 'Select a conversation'}
                  </h3>
                </div>
                
                <ScrollArea className="h-[calc(100%-60px)]">
                  {selectedConversation ? (
                    <div className="p-4 space-y-4">
                      {messages.map((message, index) => (
                        <div
                          key={message.id || index}
                          className={`flex ${
                            message.role === 'user' ? 'justify-end' : 'justify-start'
                          }`}
                        >
                          <div
                            className={`max-w-[80%] p-3 rounded-lg ${
                              message.role === 'user'
                                ? 'bg-primary text-primary-foreground'
                                : 'bg-muted'
                            }`}
                          >
                            <p className="text-sm">{message.content}</p>
                            <p className="text-xs opacity-70 mt-1">
                              {formatTime(message.timestamp)}
                            </p>
                          </div>
                        </div>
                      ))}
                      
                      {messages.length > 0 && (
                        <div className="pt-4 border-t">
                          <Button
                            onClick={() => handleSelectConversation(
                              conversations.find(c => c.id === selectedConversation)
                            )}
                            className="w-full"
                          >
                            Continue This Conversation
                          </Button>
                        </div>
                      )}
                    </div>
                  ) : (
                    <div className="flex items-center justify-center h-full text-muted-foreground">
                      <div className="text-center">
                        <MessageCircle className="w-12 h-12 mx-auto mb-4 opacity-50" />
                        <p>Select a conversation to view messages</p>
                      </div>
                    </div>
                  )}
                </ScrollArea>
              </div>
            </div>
          </CardContent>
        </Card>
      </motion.div>
    </motion.div>
  )
}

export default ConversationHistory

