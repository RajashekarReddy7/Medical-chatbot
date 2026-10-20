# 🩺 CareBot AI — Medical Chatbot with Triage, Summary & Diagnosis  
A full-stack medical AI assistant built using **FastAPI**, **Ollama + Mistral-7B**, **React**, and **MongoDB**.  
This project provides intelligent medical conversations, automated triage, case summaries, diagnosis suggestions, and personalized health planning.

---

## 🚀 Project Overview

CareBot AI is an **AI-powered medical consultation assistant** that interacts with patients, understands symptoms, evaluates urgency, and provides medically guided responses.

### ✔ Features:
- 🧠 **AI Doctor Agent** (powered by Mistral-7B via Ollama)  
- 🚨 **Automated Triage Classification** (Emergency / Urgent / Routine / Normal)  
- 📄 **Case Summary Generator**  
- 🩻 **Differential Diagnosis Prediction**  
- 🗂️ **Chat History + Summaries stored in MongoDB**  
- 👤 **User Authentication (JWT-based)**  
- 🎨 **Modern React UI with theme toggle**  
- 💬 **Real-time chat interface**  
- 📊 **Health Data Planner** (Personalized recommendations)

---

## 🎯 Problem Statement

Many patients struggle to:
- Understand whether symptoms are **serious or routine**  
- Communicate clearly with doctors  
- Receive **immediate triage guidance**  
- Maintain medical history or summaries  
- Understand possible diagnosis options  

---

## 💡 Our Solution

We built a **multi-agent medical chatbot**:

1️⃣ **Doctor Agent (LLM)**  
Understands symptoms, asks clarifying questions, responds empathetically.

2️⃣ **Symptom Extractor**  
Extracts structured medical symptoms from patient text.

3️⃣ **Triage Engine**  
Classifies urgency based on red-flags.

4️⃣ **Guideline Verifier**  
Cross-checks triage using medical rules.

5️⃣ **Summary & Diagnosis Agents**  
Generate case summaries and provide differential diagnosis.

6️⃣ **Health Planner Agent**  
Produces personalized medical recommendations.

---

## 🏗️ Tech Stack

### **Frontend**
- ⚛️ React  
- 🎨 Custom CSS + Lucide Icons  
- 🔄 React Router  
- ⚡ Vite (build tool)

### **Backend**
- 🚀 FastAPI (ASGI, async, fast for LLMs)  
- 🔐 JWT Authentication  
- 🧵 Multithreading (via `run_in_threadpool` for LLM calls)

### **AI Layer**
- 🧠 Ollama (local LLM runtime)  
- 💬 Mistral-7B model  
- 🩺 Custom prompt engineering for medical tone  
- 🔎 Agents: doctor, triage, extractor, summary, diagnosis, health planner

### **Database**
- 🍃 MongoDB (NoSQL — ideal for chat histories & dynamic documents)

---

## 🔧 Installation Guide

### 1️⃣ **Clone the Repository**
```bash
git clone https://github.com/RajashekarReddy7/Medical-chatbot
cd Medical-chatbot

# Create Virtual Environment
python -m venv venv

# Activate Virtual Environment
# Windows:
venv\Scripts\activate
# Mac/Linux:
# source venv/bin/activate

# Install backend dependencies
pip install -r requirements.txt

# Pull the Mistral model (Ollama must be installed)
ollama pull mistral

# Start MongoDB (local or Atlas)
# Default URL: mongodb://localhost:27017

# Run FastAPI backend
uvicorn main:app --reload


# Navigate to frontend folder
cd front

# Install dependencies
npm install

# Start frontend
npm run dev

---

## 🔎 Guideline verification (RAG)

Doctor-agent advice can be checked against official guideline PDFs (NICE/WHO) with source citations, explicit
"insufficient evidence" handling and rule-based emergency escalation. See [`rag/README.md`](rag/README.md) for
setup (needs Python 3.10–3.12), ingestion, API examples, tests, evaluation and known limitations.
This is an educational prototype, not clinically validated.
