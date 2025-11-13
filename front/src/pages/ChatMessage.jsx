import React from 'react';
import '../styles/ChatPage.css';

function ChatMessage({ message }) {
  return (
    <div className={`message ${message.sender}`}>
      {message.sender === 'bot' && (
        <img 
          src="https://ui-avatars.com/api/?name=Dr+AI&size=35&background=0066FF&color=fff&rounded=true"
          alt="Doctor"
          className="message-avatar"
        />
      )}
      <div className="message-bubble">
        <p>{message.text}</p>
        <span className="message-time">{message.timestamp}</span>
      </div>
    </div>
  );
}

export default ChatMessage;
