# 🐾 Vet Expense Tracker

A receipt-scanning expense tracking app built for veterinary clinics. Upload a receipt photo, and the app extracts vendor, date, amount, and auto-categorizes the expense.

## Features

- 📸 **Receipt Upload** — Drag & drop or click to upload receipt images
- 🔍 **OCR Extraction** — Automatically reads vendor, date, total, and line items
- 🏷️ **Auto-Categorization** — Smart categorization for vet clinic expenses
- 📊 **Dashboard** — Visual overview with spending trends and category breakdowns
- 📋 **Reports** — Generate reports by category, date, or vendor
- 💾 **Export** — Download expenses as CSV

## Categories

Medical Supplies, Pharmaceuticals, Equipment & Maintenance, Utilities, Office Supplies, Cleaning Supplies, Food & Nutrition, Marketing & Advertising, Insurance, Professional Services, Rent & Facilities, Staff & Payroll, Other

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Install Tesseract OCR (required for receipt scanning)
# Ubuntu/Debian:
sudo apt-get install tesseract-ocr

# macOS:
brew install tesseract

# Run the app
python app.py
```

Open http://localhost:5000 in your browser.

## Mobile-Friendly

The app is fully responsive — staff can upload receipts directly from their phones.

## Tech Stack

- **Backend:** Python + Flask
- **Database:** SQLite (no setup needed)
- **OCR:** Tesseract (pytesseract)
- **Frontend:** Bootstrap 5 + Chart.js
- **Icons:** Bootstrap Icons

## Project Structure

```
vet-expense-tracker/
├── app.py              # Flask backend + API
├── requirements.txt    # Python dependencies
├── templates/
│   └── index.html      # Main dashboard UI
├── static/
│   └── app.js          # Frontend JavaScript
├── uploads/            # Receipt images storage
└── expenses.db         # SQLite database (auto-created)
```

## API Endpoints

- `POST /api/upload` — Upload receipt image
- `GET /api/expenses` — List expenses (with filters)
- `POST /api/expenses` — Add expense
- `PUT /api/expenses/:id` — Update expense
- `DELETE /api/expenses/:id` — Delete expense
- `GET /api/dashboard` — Dashboard summary data
- `GET /api/reports` — Generate reports
- `GET /api/export` — Export as CSV
- `GET /api/categories` — List categories
