import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import "../styles/summaryView.css";
import { ArrowLeft } from "lucide-react";

export default function SummaryView() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [summaryData, setSummaryData] = useState(null);
  const [loading, setLoading] = useState(true);
  const token = localStorage.getItem("token");

  useEffect(() => {
    if (!token) {
      navigate("/");
      return;
    }

    fetch(`http://127.0.0.1:8000/api/summaries/${id}`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((res) => res.json())
      .then((data) => {
        setSummaryData(data);
        setLoading(false);
      })
      .catch((err) => {
        console.error("❌ Failed to fetch summary:", err);
        setLoading(false);
      });
  }, [id]);

  if (loading) return <div className="summary-loading">Loading summary...</div>;

  if (!summaryData)
    return (
      <div className="summary-error">
        <p>⚠ Summary not found.</p>
        <button onClick={() => navigate("/chat")}>Back to Chat</button>
      </div>
    );

  return (
    <div className="summary-view-page">
      <nav className="summary-nav">
        <button className="back-btn" onClick={() => navigate("/chat")}>
          <ArrowLeft size={18} /> Back to Chat
        </button>
        <h2>🧾 Case Summary</h2>
      </nav>

      <div className="summary-content-card">
        <h3>Summary</h3>
        <p>{summaryData.summary_text}</p>

        <h3>Conversation</h3>
        <div className="conversation-box">
          {summaryData.conversation?.map((m, i) => (
            <div key={i} className={`msg ${m.role}`}>
              <strong>{m.role === "doctor" ? "🩺 Doctor:" : "🧍 Patient:"}</strong>{" "}
              {m.message}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
