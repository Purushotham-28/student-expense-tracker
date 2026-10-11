import React, { useState, useEffect, useRef } from 'react';
import { chatService } from '../api';
import './ChatPage.css';

const SUGGESTIONS = [
  'How much did I spend on food this month?',
  'Can I afford ₹500 this weekend?',
  'When will my money run out at current burn rate?',
  'What is my financial health score and tips?',
  'Log expense: ₹180 for Campus Canteen lunch under Food',
  'What if I reduce Food spending by 30%?',
];

export default function ChatPage() {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [fetchingHistory, setFetchingHistory] = useState(true);
  const messagesEndRef = useRef(null);

  useEffect(() => {
    let isMounted = true;
    chatService
      .getHistory()
      .then((history) => {
        if (isMounted) {
          if (Array.isArray(history) && history.length > 0) {
            setMessages(history);
          } else {
            setMessages([
              {
                id: 'welcome',
                role: 'assistant',
                content:
                  "Hello! I am your AI Campus Financial Copilot powered by Claude. I have direct access to your real spending data, runway forecasts, savings goals, and health scores.\n\nAsk me questions like \"How much did I spend on food?\" or tell me to log an expense!",
                created_at: new Date().toISOString(),
              },
            ]);
          }
        }
      })
      .catch((err) => {
        console.warn('Could not load chat history:', err);
      })
      .finally(() => {
        if (isMounted) setFetchingHistory(false);
      });

    return () => {
      isMounted = false;
    };
  }, []);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading]);

  const handleSend = async (textToSend) => {
    const text = (textToSend || input).trim();
    if (!text || loading) return;

    setInput('');
    const tempUserMsg = {
      id: `user-${Date.now()}`,
      role: 'user',
      content: text,
      created_at: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, tempUserMsg]);
    setLoading(true);

    try {
      const data = await chatService.sendMessage(text);
      const assistantMsg = {
        id: `asst-${Date.now()}`,
        role: 'assistant',
        content: data.reply,
        tool_calls: data.tools_executed,
        created_at: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, assistantMsg]);
    } catch (err) {
      console.error('Chat error:', err);
      setMessages((prev) => [
        ...prev,
        {
          id: `err-${Date.now()}`,
          role: 'assistant',
          content: 'Sorry, I encountered an issue processing your request. Please try again.',
          created_at: new Date().toISOString(),
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
          id: 'welcome-fresh',
          role: 'assistant',
          content: 'Chat history cleared. How can I help you today?',
          created_at: new Date().toISOString(),
        },
      ]);
    } catch (err) {
      console.error('Failed to clear history:', err);
    }
  };

  return (
    <div className="chat-page-container" id="ai-chat-page">
      <div className="page-header" style={{ marginBottom: '1rem' }}>
        <div>
          <h2 className="page-title">AI Financial Copilot</h2>
          <p className="page-description">
            Grounded budgeting guidance with Claude function calling and live database access.
          </p>
        </div>
        <button
          type="button"
          onClick={handleClearHistory}
          className="btn-secondary"
          style={{ fontSize: '0.82rem', padding: '0.45rem 0.85rem' }}
          id="btn-clear-chat-history"
        >
          🗑️ Clear History
        </button>
      </div>

      <div className="chat-page-card glass-panel">
        {/* Suggestion Chips */}
        <div className="chat-chips-scroll">
          {SUGGESTIONS.map((chip, idx) => (
            <button
              key={idx}
              type="button"
              className="chat-suggestion-chip"
              onClick={() => handleSend(chip)}
              disabled={loading}
            >
              💡 {chip}
            </button>
          ))}
        </div>

        {/* Message Thread */}
        <div className="chat-thread-area">
          {fetchingHistory ? (
            <div style={{ textAlign: 'center', padding: '2rem', color: '#94a3b8' }}>
              Loading conversation history...
            </div>
          ) : (
            messages.map((msg) => (
              <div
                key={msg.id || msg.created_at}
                className={`chat-bubble-wrap ${msg.role === 'user' ? 'bubble-user' : 'bubble-assistant'}`}
              >
                <div className="chat-bubble-avatar">
                  {msg.role === 'user' ? '👤' : '✨'}
                </div>
                <div className="chat-bubble-content">
                  <div className="chat-bubble-text">{msg.content}</div>

                  {msg.tool_calls && msg.tool_calls.length > 0 && (
                    <div className="chat-tools-pill-group">
                      {msg.tool_calls.map((t, idx) => (
                        <span key={idx} className="tool-pill">
                          ⚡ {t.tool || t.name || 'executed_tool'}
                        </span>
                      ))}
                    </div>
                  )}

                  <span className="chat-bubble-time">
                    {msg.created_at ? new Date(msg.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : ''}
                  </span>
                </div>
              </div>
            ))
          )}

          {loading && (
            <div className="chat-bubble-wrap bubble-assistant">
              <div className="chat-bubble-avatar">✨</div>
              <div className="chat-bubble-content">
                <div className="typing-indicator-dots">
                  <span></span>
                  <span></span>
                  <span></span>
                </div>
              </div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>

        {/* Input Bar */}
        <form
          className="chat-input-bar"
          onSubmit={(e) => {
            e.preventDefault();
            handleSend();
          }}
        >
          <input
            type="text"
            className="chat-text-input"
            placeholder="Ask about your budget, runway, goals, or log an expense..."
            value={input}
            onChange={(e) => setInput(e.target.value)}
            disabled={loading}
            id="chat-page-input"
          />
          <button
            type="submit"
            className="chat-send-btn"
            disabled={loading || !input.trim()}
            id="btn-chat-page-send"
          >
            {loading ? 'Thinking...' : 'Send →'}
          </button>
        </form>
      </div>
    </div>
  );
}
