# SmartSchool - Elite NaCCA School Management SaaS

A production-grade, multi-tenant school management ecosystem designed for the future of Ghanaian education. Refactored for extreme scale, performance, and **Sasu AI 2.0** integration.

## 🚀 Elite Tier Showcase (Live Features)

- **Sasu AI 2.0 (Voice & Text):** The industry's first **Whisper-integrated** school assistant. Handles WhatsApp voice notes in **Twi, Pidgin, and English**, explaining NaCCA grades and checking student balances with cultural intelligence.
- **Predictive Analytics Hub:** An advanced early warning system that scans institutional data to identify **Academic Risk** (dropout detection) and **Financial Flow** forecasting.
- **Progressive Web App (PWA):** Installs as a native app on Android/iOS with **Offline-First** architecture and a custom 'SmartSchool' premium icon.
- **Migration War Room:** High-speed bulk data ingestion pipeline with a dynamic **Topology Mapper** for transitioning 10-year legacy histories with zero downtime.
- **Digital Marketplace:** Integrated e-commerce engine for schools to sell uniforms, books, and canteen credits with **Paystack** checkout.
- **QR Identity Infrastructure:** Secure, bulk-generated student ID cards with encrypted QR codes for instant morning roll-call and parent SMS alerts.

## 🏛️ System Architecture (Production Ready)

- **Platform Governance:** Built-in **Super Admin SaaS Dashboard** to monitor and toggle premium features (AI, PWA, Marketplace) per tenant.
- **Performance Engine:** Complex grading and ranking moved to **PostgreSQL Materialized Views** for sub-second terminal report rendering.
- **Audit Governance:** Immutable system tracking of every grade change, fee deletion, and AI-triggered event.
- **Security:** Strict compliance with the **Ghana Data Protection Act (Act 843)** using multi-tenant partitioning and PII masking.

## 🛠️ Core Modules

- **NaCCA Academic Logic** - Automatic grading and descriptors based on latest NaCCA assessment standards.
- **Financial Engine** - Full ledger with Paystack integration, automated invoicing, and digital receipts.
- **Parent Portal** - Secure access to track student performance trends, attendance, and fee status.
- **Smart SMS Hub** - Multi-channel alerting (Arkesel/Hubtel) for attendance landmarks and fee reminders.

## 💻 Tech Stack

- **Backend:** Python / Flask (Elite Blueprint Architecture)
- **AI Core:** OpenAI Whisper (Voice) & Groq Llama 3 (Reasoning)
- **Database:** PostgreSQL 15+ (With Materialized Views & B-Tree Composite Indexing)
- **Frontend:** Vanilla HTML5, CSS3 (Premium Glassmorphism), JavaScript (ES6+), PWA Service Workers
- **Analytics:** Pandas & OpenPyXL for the 'War Room' ingestion pipeline

---

## ⚙️ Setup & Installation

### Prerequisites
- Python 3.10+
- PostgreSQL 15+
- OpenAI API Key (for Voice AI)
- Groq API Key (for Agentic Reasoning)

### Rapid Deployment
1. **Clone the repository:**
   ```bash
   git clone https://github.com/sasusavage/SMS.git
   cd School
   ```

2. **Initialize Environment:**
   Create a `.env` file from the example:
   ```bash
   cp .env.example .env
   ```

3. **Install Performance Dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Production Data Provisioning:**
   Initialize the database, materialize views, and seed elite tenants:
   ```bash
   python reseed_db_final.py
   ```

5. **Launch:**
   ```bash
   python app.py
   ```

---

## 📈 SaaS Subscription Tiers

| Feature | Basic (₵1,000/yr) | Standard (₵2,500/yr) | Elite (₵6,000/yr) |
|---------|-------------------|----------------------|-------------------|
| **Enrollment/Attendance** | ✅ | ✅ | ✅ |
| **Finance Engine** | ❌ | ✅ | ✅ |
| **NaCCA Reports** | ❌ | ✅ | ✅ |
| **Sasu AI 2.0 (Voice)** | ❌ | ❌ | ✅ |
| **Predictive Analytics** | ❌ | ❌ | ✅ |
| **Digital Market** | ❌ | ❌ | ✅ |

---

Built for **NaCCA Excellence** - Modern, High-Performance, and AI-First.
© 2026 SmartSchool SaaS | Designed by Antigravity
