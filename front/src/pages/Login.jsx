import { useState } from "react";
import { useNavigate } from "react-router-dom";
import "../styles/login.css";
// NOTE: Reverting to 'User' as 'Mail' might not be available in your lucide-react version.
import { Eye, EyeOff, User, Lock } from "lucide-react"; 
import loginImage from "../assets/doctor1.jpg"; // Reverting to the existing image file name

export default function Login() {
  const navigate = useNavigate();
  const [isLogin, setIsLogin] = useState(true);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);

  const toggleForm = () => setIsLogin(!isLogin);

  const handleSubmit = async (e) => {
    e.preventDefault();

    if (!email || !password) {
      alert("Please fill all fields");
      return;
    }

    try {
      if (isLogin) {
        const formData = new URLSearchParams();
        formData.append("username", email);
        formData.append("password", password);

        const res = await fetch("/login", {
          method: "POST",
          headers: { "Content-Type": "application/x-www-form-urlencoded" },
          body: formData,
        });

        const data = await res.json();
        if (data.access_token) {
          localStorage.setItem("token", data.access_token);
          navigate("/chat");
        } else {
          alert("Login failed");
        }
      } else {
        const res = await fetch("/register", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ email, password }),
        });

        if (res.ok) {
          alert("✅ Registered successfully. Please log in now.");
          setIsLogin(true);
        } else {
          const err = await res.json();
          alert("⚠ " + (err.detail || "Registration failed"));
        }
      }
    } catch (error) {
      alert("❌ " + error.message);
    }
  };

  return (
    <div className="auth-wrapper">
      <div className="auth-left">
        <img src={loginImage} alt="Healthcare background" className="login-image" />
      </div>

      <div className="auth-right">
        <div className="login-card">
          <div className="login-header">
            {/* CareBot Logo and text */}
            <div className="carebot-logo">
              <svg
                xmlns="http://www.w3.org/2000/svg"
                width="24"
                height="24"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
                className="heart-icon"
              >
                <path d="M19 14c1.49-1.46 3-3.21 3-5.5A5.5 5.5 0 0 0 16.5 3c-1.76 0-3 .5-4.5 2-1.5-1.5-2.74-2-4.5-2A5.5 5.5 0 0 0 2 8.5c0 2.3 1.5 4.05 3 5.5l7 7Z" />
              </svg>
              <span>Care Companion</span>
            </div>
            <h2>{isLogin ? "Welcome Back" : "Create Account"}</h2>
            <p className="subtitle">
              {isLogin
                ? "Login to continue your healthcare journey"
                : "Register to start your healthcare journey"}
            </p>
          </div>

          <form onSubmit={handleSubmit}>
            <div className="input-group">
              <User className="input-icon" /> {/* Using User icon for email */}
              <input
                type="email"
                placeholder="Email address"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
              />
            </div>

            <div className="input-group">
              <Lock className="input-icon" />
              <input
                type={showPassword ? "text" : "password"}
                placeholder="Password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
              <span
                className="eye-toggle"
                onClick={() => setShowPassword(!showPassword)}
                aria-label={showPassword ? "Hide password" : "Show password"}
              >
                {showPassword ? <EyeOff /> : <Eye />}
              </span>
            </div>

            <button type="submit">{isLogin ? "Login" : "Register"}</button>
          </form>

          <p className="toggle" onClick={toggleForm}>
            {isLogin
              ? <>Don’t have an account? <span>Register here</span></>
              : <>Already have an account? <span>Login here</span></>}
          </p>
        </div>
      </div>
  </div>
 );
}
