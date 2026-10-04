# Documentation & Developer Notes

## Project Overview
**student-expense-tracker** is a full-stack financial tracking application tailored for students. It enables tracking daily expenses, setting category budgets (e.g., Food, Books, Rent, Leisure), visualizing spending patterns with analytics, and managing financial health throughout academic terms.

## System Architecture
- **Backend**: Django 6.1 + Django REST Framework running Python. Configured with `django-environ`, `django-cors-headers`, and MySQL client support.
- **Frontend**: React 18/19 built with Vite, React Router (`react-router-dom`), Axios for API interactions, and Recharts for data visualization.
- **Database**: Configured for MySQL with fallback support for local SQLite development.

## API Endpoints
- `GET /api/health/`: Service health check.

## Directory Structure
- `/backend`: Django project (`config`), `core` app, virtual environment, and settings.
- `/frontend`: React application created with Vite.
- `/docs`: Architecture, setup instructions, and developer documentation.
