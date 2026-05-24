import { useState, useRef, useEffect } from 'react';

interface Props {
  themeColor: string;
  onClose: () => void;
}

interface Message {
  role: 'user' | 'assistant';
  content: string;
}

const SUGGESTIONS = [
  'What is AIMarket Hub?',
  'How do payment channels work?',
  'Explain the plugin system',
  'What desktop apps exist?',
  'How does ACEX work?',
  'What blockchains are supported?',
];

export default function AIAssistant({ themeColor, onClose }: Props) {
  const [messages, setMessages] = useState<Message[]>([
    {
      role: 'assistant',
      content: 'I am the Alien Monitor AI. Ask me anything about the AIMarket ecosystem — hub, contracts, plugins, desktop apps, service mesh, ACEX, SDKs, and more.',
    },
  ]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const chatEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const sendMessage = async (text: string) => {
    if (!text.trim() || loading) return;
    const userMsg: Message = { role: 'user', content: text };
    setMessages((prev) => [...prev, userMsg]);
    setInput('');
    setLoading(true);

    try {
      const res = await fetch('/api/ai/ask', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: text }),
      });
      const data = await res.json();
      setMessages((prev) => [...prev, { role: 'assistant', content: data.answer }]);
    } catch {
      setMessages((prev) => [
        ...prev,
        { role: 'assistant', content: 'Unable to reach the AI. The backend may be offline.' },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage(input);
    }
    if (e.key === 'Escape') onClose();
  };

  return (
    <div
      className="absolute right-4 top-24 z-30 w-96 glass-panel flex flex-col"
      style={{
        borderColor: themeColor + '44',
        boxShadow: `0 0 30px rgba(0,0,0,0.5), 0 0 15px ${themeColor}22`,
        maxHeight: 'calc(100vh - 200px)',
      }}
    >
      {/* Header */}
      <div
        className="flex items-center justify-between px-4 py-3 border-b"
        style={{ borderColor: themeColor + '22' }}
      >
        <div className="flex items-center gap-2">
          <div className="text-sm" style={{ color: themeColor }}>
            &#x25C9;
          </div>
          <span className="text-xs font-semibold tracking-wider" style={{ color: themeColor }}>
            AI ASSISTANT
          </span>
        </div>
        <button
          onClick={onClose}
          className="text-white/40 hover:text-white/80 transition-colors text-lg leading-none"
        >
          ×
        </button>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4 space-y-3" style={{ maxHeight: '400px' }}>
        {messages.map((msg, i) => (
          <div
            key={i}
            className={`text-xs leading-relaxed ${
              msg.role === 'user' ? 'text-right' : 'text-left'
            }`}
          >
            <div
              className={`inline-block px-3 py-2 rounded-lg max-w-[85%] ${
                msg.role === 'user'
                  ? 'text-white'
                  : 'text-white/80'
              }`}
              style={{
                backgroundColor:
                  msg.role === 'user'
                    ? themeColor + '22'
                    : 'rgba(255,255,255,0.04)',
                border: `1px solid ${
                  msg.role === 'user' ? themeColor + '44' : 'rgba(255,255,255,0.06)'
                }`,
              }}
            >
              {msg.content}
            </div>
          </div>
        ))}

        {/* Typing indicator */}
        {loading && (
          <div className="flex items-center gap-1.5 px-2">
            <div className="typing-dot w-1.5 h-1.5 rounded-full" style={{ backgroundColor: themeColor }} />
            <div className="typing-dot w-1.5 h-1.5 rounded-full" style={{ backgroundColor: themeColor }} />
            <div className="typing-dot w-1.5 h-1.5 rounded-full" style={{ backgroundColor: themeColor }} />
          </div>
        )}

        <div ref={chatEndRef} />
      </div>

      {/* Suggestions */}
      {messages.length <= 1 && (
        <div className="px-4 pb-2">
          <div className="flex flex-wrap gap-1.5">
            {SUGGESTIONS.map((s) => (
              <button
                key={s}
                onClick={() => sendMessage(s)}
                className="text-[10px] px-2 py-1 rounded-full transition-colors"
                style={{
                  backgroundColor: themeColor + '0f',
                  border: `1px solid ${themeColor}22`,
                  color: themeColor,
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.backgroundColor = themeColor + '22';
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.backgroundColor = themeColor + '0f';
                }}
              >
                {s}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Input */}
      <div
        className="flex items-center gap-2 px-4 py-3 border-t"
        style={{ borderColor: themeColor + '22' }}
      >
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask about the ecosystem..."
          className="flex-1 bg-transparent border-none outline-none text-xs text-white/90 placeholder:text-white/25 font-mono"
          disabled={loading}
        />
        <button
          onClick={() => sendMessage(input)}
          disabled={loading || !input.trim()}
          className="text-xs px-3 py-1 rounded font-mono transition-all"
          style={{
            backgroundColor: input.trim() ? themeColor + '33' : 'transparent',
            border: `1px solid ${input.trim() ? themeColor : '#ffffff22'}`,
            color: input.trim() ? themeColor : '#ffffff33',
          }}
        >
          SEND
        </button>
      </div>
    </div>
  );
}
