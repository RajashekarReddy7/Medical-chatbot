import React from "react";
import { useNavigate } from "react-router-dom";
import { Heart, Shield, Clock, Brain, LogIn } from "lucide-react";
import "../styles/HomePage.css";
import loginImage from "../assets/doctor1.jpg"; 

function HomePage() {
  const navigate = useNavigate();

  return (
    <div className="homepage">
      {/* ===== HEADER ===== */}
      <header className="homepage-header">
        <div className="logo-container">
          <Heart className="logo-icon" />
          <h1 className="logo-text">Care Companion</h1>
        </div>

        <div className="header-buttons">
          <button
            className="header-login-btn"
            onClick={() => navigate("/login")}
          >
            <LogIn size={16} /> Login
          </button>

          {/* ❌ Removed Register Button */}
        </div>
      </header>

      {/* Spacer */}
      <div className="nav-spacer"></div>

      {/* ===== HERO SECTION ===== */}
      <section className="hero-section">
        <div className="hero-content">
          <h2 className="hero-title">Your AI Healthcare Assistant, 24/7</h2>
          <p className="hero-subtitle">
            Get instant medical guidance from our intelligent chatbot
          </p>

          {/* 🔥 Start Conversation → ALWAYS go to login page */}
          <button className="cta-button" onClick={() => navigate("/login")}>
            Start Conversation
          </button>
        </div>

        <div className="hero-image">
          <img
            src={loginImage}
            alt="Healthcare illustration"
          />
        </div>
      </section>

      {/* ===== FEATURES SECTION ===== */}
      <section className="features-section">
        <div className="feature-card">
          <Shield className="feature-icon" />
          <h3>Emergency Support</h3>
          <p>Quick response for urgent medical queries</p>
        </div>

        <div className="feature-card">
          <Clock className="feature-icon" />
          <h3>24/7 Availability</h3>
          <p>Healthcare guidance anytime you need</p>
        </div>

        <div className="feature-card">
          <Brain className="feature-icon" />
          <h3>AI-Powered</h3>
          <p>Smart diagnosis and health recommendations</p>
        </div>
      </section>

      {/* ===== FOOTER ===== */}
      <footer className="footer">
        © {new Date().getFullYear()} Care Companion AI — Your Trusted Digital Health Assistant
      </footer>
    </div>
  );
}

export default HomePage;
