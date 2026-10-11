import React, { useState, useEffect, useRef } from 'react';
import { chatService, authService } from '../api';
import './ChatWidget.css';

const SUGGESTION_CHIPS = [
  'How much did I spend on food?',
  'Can I afford ₹500 this weekend?',
  "What's my cash runway date?",
  'Log ₹150 for Chai & Samosa',
  "What's my financial health score?",
];

export default function ChatWidget() {
  const [isOpen, setIsOpen] = useState(false);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [initialLoaded, setInitialLoaded] = useState(false);
  const messagesEndRef = useRef(null);

  const isAuthenticated = authService.isAuthenticated();

  // Scroll to bottom
  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    if (isOpen) {
      scrollToBottom();
    }
  }, [messages, isOpen, loading]);

  // Load history on mount or when opened
  useEffect(() => {
    if (isAuthenticated && isOpen && !initialLoaded) {
      loadHistory();
    }
  }, [isOpen, isAuthenticated]);

  const loadHistory = async () => {
    try {
      const history = await chatService.getHistory();
      if (history && history.length > 0) {
        setMessages(history);
      } else {
        // Welcome message if new chat
        setMessages([
          {
            role: 'assistant',
            content:
              "👋 Hi! I'm your **Claude AI Copilot**. I have live access to your bank statements, spending categories, runway forecast, goals, and health score.\n\nAsk me anything or tap one of the chips below!",
          },
        ]);
      }
      setInitialLoaded(true);
    } catch (err) {
      console.warn('Could not load chat history:', err);
    }
  };

  const handleSend = async (messageText) => {
    const textToSend = (messageText || input).trim();
    if (!textToSend || loading) return;

    // Optimistically add user message
    const userMsg = {
      role: 'user',
      content: textToSend,
      created_at: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, userMsg]);
    setInput('');
    setLoading(true);

    try {
      const res = await chatService.sendMessage(textToSend);
      const assistantMsg = {
        role: 'assistant',
        content: res.reply,
        tool_calls: res.tools_executed,
        created_at: res.created_at || new Date().toISOString(),
      };
      setMessages((prev) => [...prev, assistantMsg]);
    } catch (err) {
      console.error('Chat request failed:', err);
      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          content: '⚠️ Sorry, I encountered an issue processing your request. Please try again.',
        },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const handleClearHistory = async () => {
    if (!window.confirm('Clear your conversation history?')) return;
    try {
      await chatService.clearHistory();
      setMessages([
        {
          role: 'assistant',
          content: '🧹 Chat history cleared. How can I assist you with your campus finances today?',
        },
      ]);
    } catch (err) {
      console.error('Failed to clear history:', err);
    }
  };

  if (!isAuthenticated) return null;

  return (
    <div className="chat-widget-wrapper" id="chat-widget-container">
      {/* Floating Trigger Button */}
      {!isOpen && (
        <button
          type="button"
          className="chat-floating-btn animate-pulse-glow"
          onClick={() => setIsOpen(true)}
          id="btn-open-chat-widget"
          title="Open AI Financial Copilot"
        >
          <span className="chat-btn-icon">✨</span>
          <span className="chat-btn-label">AI Copilot</span>
          <span className="pulse-indicator"></span>
        </button>
      )}

      {/* Slide-up Chat Panel */}
      {isOpen && (
        <div className="chat-panel glass-panel animate-scale-up" id="chat-panel-modal">
          {/* Header */}
          <div className="chat-header">
            <div className="chat-header-info">
              <div className="bot-avatar">🤖</div>
              <div>
                <h4 className="chat-title">Claude Copilot</h4>
                <div className="chat-status">
                  <span className="status-dot-online"></span>
                  <span>claude-sonnet-4-6 • Function Calling</span>
                </div>
              </div>
            </div>

            <div className="chat-header-actions">
              <button
                type="button"
                className="btn-chat-header-action"
                onClick={handleClearHistory}
                title="Clear conversation"
                id="btn-clear-chat"
              >
                🗑️
              </button>
              <button
                type="button"
                className="btn-chat-header-action"
                onClick={() => setIsOpen(false)}
                title="Close chat"
                id="btn-close-chat"
              >
                ✕
              </button>
            </div>
          </div>

          {/* Messages Container */}
          <div className="chat-messages-scroll" id="chat-messages-container">
            {messages.map((msg, idx) => (
              <div
                key={idx}
                className={`chat-bubble-row ${msg.role === 'user' ? 'row-user' : 'row-assistant'}`}
              >
                {msg.role === 'assistant' && <div className="bubble-avatar">🤖</div>}

                <div className="bubble-body">
                  {/* Tool execution badge */}
                  {msg.tool_calls && msg.tool_calls.length > 0 && (
                    <div className="tool-badges-list">
                      {msg.tool_calls.map((tc, tIdx) => (
                        <div key={tIdx} className="tool-executed-chip">
                          <span className="tool-chip-icon">⚡</span>
                          <span>Called: {tc.tool}()</span>
                        </div>
                      ))}
                    </div>
                  )}

                  {/* Message Content */}
                  <div className="bubble-content-text">
                    {msg.content.split('\n').map((line, lIdx) => (
                      <p key={lIdx} className="message-paragraph">
                        {renderFormattedText(line)}
                      </p>
                    ))}
                  </div>
                </div>
              </div>
            ))}

            {/* Typing Indicator */}
            {loading && (
              <div className="chat-bubble-row row-assistant animate-fade-in">
                <div className="bubble-avatar">🤖</div>
                <div className="typing-indicator-box">
                  <div className="typing-dot"></div>
                  <div className="typing-dot"></div>
                  <div className="typing-dot"></div>
                  <span className="typing-text">Calling tools & analyzing finances...</span>
                </div>
              </div>
            )}

            <div ref={messagesEndRef} />
          </div>

          {/* Suggestion Chips */}
          <div className="chips-container" id="chat-suggestion-chips">
            {SUGGESTION_CHIPS.map((chip, idx) => (
              <button
                key={idx}
                type="button"
                className="chip-suggestion-btn"
                onClick={() => handleSend(chip)}
                disabled={loading}
              >
                {chip}
              </button>
            ))}
          </div>

          {/* Input Form */}
          <form
            onSubmit={(e) => {
              e.preventDefault();
              handleSend();
            }}
            className="chat-input-bar"
          >
            <input
              type="text"
              placeholder="Ask Copilot (e.g. 'Can I afford ₹500?')..."
              value={input}
              onChange={(e) => setInput(e.target.value)}
              disabled={loading}
              autoFocus
              id="input-chat-message"
            />
            <button
              type="submit"
              disabled={!input.trim() || loading}
              className="btn-chat-send"
              id="btn-send-chat"
              title="Send message"
            >
              ➤
            </button>
          </form>
        </div>
      )}
    </div>
  );
}

// Simple bold / bullet markdown parser
function renderFormattedText(text) {
  if (!text) return null;
  // Replace **bold** with strong
  const parts = text.split(/(\*\*[^*]+\*\*)/g);
  return parts.map((part, index) => {
    if (part.startsWith('**') && part.endsWith('**')) {
      return <strong key={index}>{part.slice(2, -2)}</strong>;
    }
    return part;
  });
}
