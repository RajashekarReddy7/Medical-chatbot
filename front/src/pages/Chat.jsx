import { useState, useRef, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import "../styles/chat.css";
import doctorImg from "../assets/doctor.jpg";
import userPlaceholder from "../assets/user.png";
import {
  Home,
  FileText,
  Activity,
  LogOut,
  X,
  ChevronRight,
  Sun,
  Moon,
} from "lucide-react";

export default function Chat() {
  const navigate = useNavigate();
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [toast, setToast] = useState("");
  const [isTyping, setIsTyping] = useState(false);
  const [chatHistory, setChatHistory] = useState([]);
  const [activeChat, setActiveChat] = useState(null);
  const [showSidebar, setShowSidebar] = useState(false);
  const [selectedSummary, setSelectedSummary] = useState(null);
  const [theme, setTheme] = useState("light");
  const [showProfile, setShowProfile] = useState(false);
  const [userData, setUserData] = useState({});
  const inputRef = useRef(null);
  const token = localStorage.getItem("token");

  if (!token) navigate("/");

  // ===== Fetch chat summaries =====
  useEffect(() => {
    fetch("http://127.0.0.1:8000/api/summaries", {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((res) => res.json())
      .then((data) => setChatHistory(data.history || []))
      .catch((err) => console.error("❌ Error fetching summaries:", err));
  }, []);

  // ===== Fetch user details =====
  useEffect(() => {
    fetch("http://127.0.0.1:8000/api/me", {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((res) => res.json())
      .then((data) => setUserData(data))
      .catch(() => console.log("⚠ Unable to fetch user profile"));
  }, []);

  // ===== Theme toggle effect =====
  useEffect(() => {
    document.body.className =
      theme === "dark" ? "dark-mode smooth-transition" : "smooth-transition";
  }, [theme]);

  const appendMessage = (msg, role = "bot") => {
    setMessages((prev) => [...prev, { msg, role }]);
    setTimeout(() => {
      const chat = document.getElementById("chat");
      if (chat) chat.scrollTop = chat.scrollHeight;
    }, 50);
  };

  const sendMessage = async () => {
    if (!input.trim()) return;
    appendMessage(input, "user");
    setInput("");
    setIsTyping(true);

    try {
      const res = await fetch("http://127.0.0.1:8000/api/chat", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          session_id: "sess-" + Math.random().toString(36).slice(2, 9),
          message: input,
        }),
      });

      const data = await res.json();
      setIsTyping(false);

      appendMessage(data.reply || "No response received.", "bot");

      // ===== TRIAGE BADGE (KEEP ORIGINAL FUNCTIONALITY) =====
      if (data.triage) {
        let badgeClass =
          data.triage.level.toLowerCase() === "emergency"
            ? "emergency"
            : data.triage.level.toLowerCase() === "urgent"
            ? "urgent"
            : "routine";

        appendMessage(
          `<div class="triage-badge ${badgeClass}">
            <strong>${data.triage.level}</strong> — ${data.triage.reason}
          </div>`,
          "bot"
        );
      }
    } catch {
      setIsTyping(false);
      appendMessage("❌ Failed to send message.", "bot");
    }
  };

  // ===== SUMMARY GENERATOR =====
  const generateSummary = async () => {
    appendMessage("<div class='meta'>🧠 Generating case summary...</div>", "meta");

    try {
      const res = await fetch("http://127.0.0.1:8000/api/generate_summary", {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });

      const data = await res.json();

      appendMessage(
        `<div class='summary-box'>
          <h3>🧾 <strong>Case Summary:</strong></h3>
          <div>${data.summary}</div>
        </div>`,
        "bot"
      );

      setToast("✅ Summary generated successfully!");
    } catch {
      appendMessage("❌ Failed to generate summary.", "bot");
    }
  };

  // ===== DIAGNOSIS GENERATOR =====
  const generateDiagnosis = async () => {
    appendMessage("<div class='meta'>Analyzing conversation for possible diagnoses...</div>", "meta");

    try {
      const res = await fetch("http://127.0.0.1:8000/api/generate_diagnosis", {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });

      const data = await res.json();

      const formattedDiagnosis = (data.diagnosis || "")
        .split("\n")
        .filter(Boolean)
        .map((line) => `<div>${line}</div>`)
        .join("");

      appendMessage(
        `<div class='diagnosis-box'>
          <h3>🩻 <strong>Diagnoses:</strong></h3>
          <div>${formattedDiagnosis || "No diagnosis generated."}</div>
        </div>`,
        "bot"
      );

      setToast("✅ Diagnosis generated successfully!");
    } catch {
      appendMessage("❌ Failed to generate diagnosis.", "bot");
    }
  };

  const showToast = (msg) => {
    setToast(msg);
    setTimeout(() => setToast(""), 4000);
  };

  return (
    <div className="chat-page smooth-transition">
      
      {/* ===== NAVBAR ===== */}
      <nav className="blue-navbar smooth-transition">
        <div className="nav-left">
          <h1 className="brand">
            <Activity className="brand-icon" />
            Care Companion
          </h1>

          <button onClick={() => navigate("/home")}>
            <Home size={18} /> Home
          </button>

          {/* FIXED: Summary fetch (not redirect) */}
          <button onClick={generateSummary}>
            <FileText size={18} /> Summary
          </button>

          {/* FIXED: Diagnosis fetch (not redirect) */}
          <button onClick={generateDiagnosis}>
            <Activity size={18} /> Diagnosis
          </button>
        </div>

        {/* ===== PROFILE SECTION ===== */}
        <div className="profile-section smooth-transition">
          <img
            src={userPlaceholder}
            alt="User Profile"
            className="profile-avatar hoverable"
            onClick={() => setShowProfile(true)}
            title="View Profile"
          />

          <span className="profile-name">You</span>

          <button
            className="theme-toggle-btn hoverable"
            onClick={() => setTheme(theme === "light" ? "dark" : "light")}
          >
            {theme === "light" ? <Moon size={18} /> : <Sun size={18} />}
          </button>

          <button
            className="logout-btn hoverable"
            onClick={() => {
              localStorage.removeItem("token");
              navigate("/");
            }}
          >
            <LogOut size={16} /> Logout
          </button>
        </div>
      </nav>

      {/* ===== Profile Modal ===== */}
      {showProfile && (
        <div className="profile-modal" onClick={() => setShowProfile(false)}>
          <div className="profile-card" onClick={(e) => e.stopPropagation()}>
            <button className="close-modal" onClick={() => setShowProfile(false)}>
              <X size={18} />
            </button>
            <img src={userPlaceholder} alt="User" className="profile-avatar-large" />
            <h3>{userData.email || "User"}</h3>
            <p><strong>Status:</strong> Active</p>
            <p><strong>Joined:</strong> {new Date().toLocaleDateString()}</p>
          </div>
        </div>
      )}

      {/* ===== Floating Sidebar Button ===== */}
      <button className="toggle-sidebar-btn" onClick={() => setShowSidebar(true)}>
        <ChevronRight size={20} />
      </button>

      {/* ===== Sidebar ===== */}
      <div className={`history-sidebar ${showSidebar ? "open" : ""}`}>
        <div className="sidebar-header">
          <h3><ChevronRight size={18}/> Summaries</h3>
          <button onClick={() => setShowSidebar(false)} className="close-btn">
            <X size={18} />
          </button>
        </div>

        <div className="sidebar-list">
          {chatHistory.length === 0 ? (
            <p className="no-history">No summaries yet</p>
          ) : (
            chatHistory.map((chat) => (
              <div
                key={chat._id}
                className={`sidebar-item hoverable`}
                onClick={() => navigate(`/summary/${chat._id}`)}
              >
                <p>{chat.summary_text.slice(0, 60)}...</p>
                <span>{new Date(chat.timestamp).toLocaleDateString()}</span>
              </div>
            ))
          )}
        </div>
      </div>

      {/* ===== Chat Section ===== */}
      <div className="chat-container">
        <div className="avatar-section">
          <img src={doctorImg} alt="Doctor" />
          <h2>Dr. Cura</h2>
          <p>Your trusted AI healthcare assistant.</p>
        </div>

        <div className="chat-section">
          <div id="chat">
            {messages.map((m, i) => (
              <div
                key={i}
                className={`message ${m.role}`}
                dangerouslySetInnerHTML={{ __html: m.msg }}
              ></div>
            ))}

            {isTyping && (
              <div className="message bot typing">
                <div className="dot"></div>
                <div className="dot"></div>
                <div className="dot"></div>
              </div>
            )}
          </div>

          <div id="input-area">
            <input
              id="input"
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && sendMessage()}
              placeholder="Describe your symptoms..."
            />
            <button id="send" onClick={sendMessage}>
              ➤
            </button>
          </div>
        </div>
      </div>

      {toast && <div className="toast show">{toast}</div>}
    </div>
  );
}
