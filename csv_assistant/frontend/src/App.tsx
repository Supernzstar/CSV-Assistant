import React, { useState, useRef, useEffect } from "react";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { a11yDark } from "react-syntax-highlighter/dist/esm/styles/prism";
import "./App.css";

const API_BASE_URL = "/api";
const MODELS = ["doubao-pro-32k-241215","gpt-3.5-turbo", "gpt-4o", "gpt-4-turbo-preview","claude-sonnet-4-20250514","deepseek-r1","gpt-4.5-preview"];

interface HistoryItem {
  question: string;
  code: string;
  stdout: string;
  explanation: string;
  images: string[];
  model_used?: string; // Add this line
}

function App() {
  const [question, setQuestion] = useState("");
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [selectedModel, setSelectedModel] = useState<string>(MODELS[0]);
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  const [uploadedFileName, setUploadedFileName] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const chatHistoryRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (chatHistoryRef.current) {
      chatHistoryRef.current.scrollTop = chatHistoryRef.current.scrollHeight;
    }
  }, [history]);

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setUploadedFileName(file.name);

    const formData = new FormData();
    formData.append("file", file);
    
    setIsLoading(true);
    try {
      const res = await fetch(`${API_BASE_URL}/upload_csv`, {
        method: "POST",
        body: formData,
      });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Upload failed");
      }
      alert("CSV uploaded and loaded successfully!");
      setHistory([]);
    } catch (error) {
      alert(`Error uploading CSV: ${error instanceof Error ? error.message : "Unknown error"}`);
      setUploadedFileName(null);
    } finally {
      setIsLoading(false);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!question.trim() || isLoading) return;

    setIsLoading(true);
    const currentQuestion = question;
    setQuestion("");

    const tempHistory = [...history, { question: currentQuestion, code: '', stdout: '', explanation: 'Thinking...', images: [] }];
    setHistory(tempHistory);

    try {
      const res = await fetch(`${API_BASE_URL}/ask`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: currentQuestion, model: selectedModel }),
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "API request failed");
      }

      const data = await res.json();
      setHistory([...history, { ...data, question: currentQuestion, model_used: data.model_used }]);
    } catch (error) {
      alert(`Error: ${error instanceof Error ? error.message : "Unknown error"}`);
      setHistory(history);
    } finally {
      setIsLoading(false);
    }
  };

  const handleReset = async () => {
    await fetch(`${API_BASE_URL}/reset`, { method: "POST" });
    setHistory([]);
    setUploadedFileName(null);
  };
  
  return (
    <div className={`app-container ${isSidebarOpen ? 'sidebar-open' : ''}`}>
      <aside className="sidebar">
        <div className="sidebar-header">
          <div className="sidebar-logo">🚀</div>
          <h2 className="sidebar-title">CSV Assistant</h2>
        </div>
        <div className="sidebar-content">
          <label htmlFor="model-select">Model</label>
          <select id="model-select" value={selectedModel} onChange={(e) => setSelectedModel(e.target.value)}>
            {MODELS.map(m => <option key={m} value={m}>{m}</option>)}
          </select>
        </div>
        <div className="sidebar-footer">
            <button onClick={handleReset} className="reset-button">
                <span>🔄</span> Reset Session
            </button>
        </div>
      </aside>

      <div className="main-content">
        <header className="main-header">
            <button className="sidebar-toggle" onClick={() => setIsSidebarOpen(!isSidebarOpen)}>
                <span>{isSidebarOpen ? '‹' : '›'}</span>
            </button>
            <h1>{selectedModel}</h1>
        </header>

        <main className="chat-area" ref={chatHistoryRef}>
          {history.length === 0 && (
              <div className="welcome-message">
                  <h1>CSV Data Assistant</h1>
                  <p>Upload a CSV file and ask questions to analyze your data.</p>
              </div>
          )}
          {history.map((item, index) => (
              <div key={index} className="message-item user-message-item">
                  <div className="message user-message">
                      <div className="avatar user-avatar">You</div>
                      <div className="message-content">
                          <div className="result-block user-block">
                              {item.question}
                          </div>
                      </div>
                  </div>
                  <div className="message assistant-message">
                      <div className="avatar assistant-avatar">🤖</div>
                      <div className="message-content">
                          {item.model_used && <div className="model-tag">Model: {item.model_used}</div>}
                          {item.explanation === 'Thinking...' ? (
                              <div className="loading-spinner-small"></div>
                          ) : (
                              <>
                                  <div className="result-block assistant-block">
                                      {item.code && (
                                          <SyntaxHighlighter language="python" style={a11yDark} customStyle={{ margin: 0 }}>
                                              {item.code}
                                          </SyntaxHighlighter>
                                      )}
                                      {item.stdout && <pre>{item.stdout}</pre>}
                                      <p>{item.explanation}</p>
                                      {item.images && item.images.length > 0 && (
                                          <div className="image-list">
                                              {item.images.map((imgData, imgIndex) => (
                                                  <img key={imgIndex} src={imgData} alt={`Chart ${imgIndex + 1}`} className="chart-image" />
                                              ))}
                                          </div>
                                      )}
                                  </div>
                              </>
                          )}
                      </div>
                  </div>
              </div>
          ))}
        </main>

        <footer className="input-area">
          <form onSubmit={handleSubmit} className="input-form">
            <input
              type="file"
              accept=".csv"
              ref={fileInputRef}
              onChange={handleFileChange}
              hidden
            />
            <button type="button" className="icon-button" onClick={() => fileInputRef.current?.click()} title="Upload CSV">
              <span>📎</span>
            </button>
            {uploadedFileName && (
              <div className="uploaded-file-chip-inline">
                {uploadedFileName}
              </div>
            )}
            <textarea
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              placeholder="Ask a question..."
              disabled={isLoading}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  handleSubmit(e);
                }
              }}
            />
            <button type="submit" disabled={isLoading} className="icon-button send-btn" title="Send">
              <span>➤</span>
            </button>
          </form>
        </footer>
      </div>
    </div>
  );
}

export default App; 