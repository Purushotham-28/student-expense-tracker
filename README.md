# Student Expense Tracker

Student Expense Tracker is a modern full-stack web application engineered to give university and college students full visibility and control over their finances. By categorizing everyday spending across essentials like tuition, rent, groceries, and leisure, the platform helps students manage tight semester budgets, track recurring subscriptions, and spot unhealthy spending trends before they impact academic goals.

The architecture pairs a high-performance Django REST Framework backend with a responsive, component-driven React and Vite frontend. Built with modern security and development workflows in mind, the backend manages MySQL data persistence, environment-driven configurations via django-environ, and origin-restricted CORS headers, while the frontend leverages React Router for seamless navigation and Recharts for interactive financial visualizations and budget analytics.

---

## Getting Started Locally

### Prerequisites
- **Python 3.11+** installed
- **Node.js 20+** and **npm** installed
- **MySQL Server** (optional for local SQLite fallback)

---

### Backend Setup (Django)

1. **Navigate to the backend directory**:
   ```bash
   cd backend
   ```

2. **Activate the virtual environment**:
   - On Windows:
     ```bash
     .\venv\Scripts\activate
     ```
   - On Linux/macOS:
     ```bash
     source venv/bin/activate
     ```

3. **Install dependencies** (if setting up fresh):
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment variables**:
   Copy `.env.example` from the root directory to `.env` in the root or `backend/` and update your MySQL credentials:
   ```bash
   cp ../.env.example ../.env
   ```

5. **Run database migrations**:
   ```bash
   python manage.py migrate
   ```

6. **Start the Django development server**:
   ```bash
   python manage.py runserver
   ```
   The backend API will be available at `http://127.0.0.1:8000/`. You can verify API health at `http://127.0.0.1:8000/api/health/`.

---

### Frontend Setup (React + Vite)

1. **Navigate to the frontend directory**:
   ```bash
   cd frontend
   ```

2. **Install npm dependencies**:
   ```bash
   npm install
   ```

3. **Start the Vite development server**:
   ```bash
   npm run dev
   ```
   The frontend application will be running at `http://localhost:5173/`.

---

## Project Structure

```text
student-expense-tracker/
├── backend/
│   ├── config/          # Django project configuration & settings
│   ├── core/            # Core app (APIs, models, views)
│   ├── manage.py        # Django management script
│   └── requirements.txt # Python dependencies
├── frontend/
│   ├── src/             # React application source code
│   ├── package.json     # Node.js dependencies & scripts
│   └── vite.config.js   # Vite configuration
├── docs/
│   └── notes.md         # Developer documentation and notes
├── .env.example         # Template for environment variables
├── .gitignore           # Git ignore rules for Python, Node, & secrets
└── README.md            # Project documentation & local setup instructions
```
