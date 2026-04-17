"""
Vet Expense Tracker - Receipt OCR + Expense Management
"""

import os
import sqlite3
import json
import re
from datetime import datetime, timedelta
from functools import wraps

from flask import Flask, request, jsonify, send_from_directory, g
from werkzeug.utils import secure_filename
from PIL import Image

try:
    import pytesseract
    HAS_OCR = True
except ImportError:
    HAS_OCR = False
    print("WARNING: pytesseract not available. OCR disabled.")

import boto3

# R2 Cloud Storage Configuration
R2_ENDPOINT = os.environ.get('R2_ENDPOINT_URL', '')
R2_ACCESS_KEY = os.environ.get('R2_ACCESS_KEY_ID', '')
R2_SECRET_KEY = os.environ.get('R2_SECRET_ACCESS_KEY', '')
R2_BUCKET = os.environ.get('R2_BUCKET_NAME', '')
USE_R2 = bool(R2_ENDPOINT and R2_ACCESS_KEY and R2_SECRET_KEY and R2_BUCKET)

s3_client = None
if USE_R2:
    from botocore.config import Config
    s3_client = boto3.client(
        's3',
        endpoint_url=R2_ENDPOINT,
        aws_access_key_id=R2_ACCESS_KEY,
        aws_secret_access_key=R2_SECRET_KEY,
        region_name='auto',
        config=Config(
            connect_timeout=5,
            read_timeout=10,
            retries={'max_attempts': 2}
        )
    )
    print(f"R2 storage enabled: {R2_BUCKET}")

app = Flask(__name__, static_folder='static', template_folder='templates')

# Use /data directory on Render (persistent disk), local otherwise
DATA_DIR = os.environ.get('DATA_DIR', os.path.dirname(__file__))

# Ensure data directory exists
os.makedirs(DATA_DIR, exist_ok=True)

app.config['UPLOAD_FOLDER'] = os.path.join(DATA_DIR, 'uploads')
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max
app.config['DATABASE'] = os.path.join(DATA_DIR, 'expenses.db')

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'bmp', 'webp', 'pdf'}

CATEGORIES = [
    'Medical Supplies',
    'Pharmaceuticals',
    'Equipment & Maintenance',
    'Utilities',
    'Office Supplies',
    'Cleaning Supplies',
    'Food & Nutrition',
    'Marketing & Advertising',
    'Insurance',
    'Professional Services',
    'Rent & Facilities',
    'Staff & Payroll',
    'Other'
]

# Category keywords for auto-detection
def auto_categorize(text):
    """Auto-categorize based on keywords from database."""
    db = sqlite3.connect(app.config['DATABASE'])
    db.row_factory = sqlite3.Row
    cats = db.execute('SELECT name, keywords FROM categories').fetchall()
    db.close()
    
    text_lower = text.lower()
    for cat in cats:
        keywords = json.loads(cat['keywords'] or '[]')
        for keyword in keywords:
            if keyword.lower() in text_lower:
                return cat['name']
    return 'Other'


def get_db():
    """Get database connection."""
    if 'db' not in g:
        g.db = sqlite3.connect(app.config['DATABASE'])
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(exception):
    """Close database connection."""
    db = g.pop('db', None)
    if db is not None:
        db.close()


def init_db():
    """Initialize database tables."""
    db = sqlite3.connect(app.config['DATABASE'])
    db.execute('''
        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            vendor TEXT NOT NULL,
            amount REAL NOT NULL,
            date TEXT NOT NULL,
            category TEXT NOT NULL DEFAULT 'Other',
            description TEXT,
            receipt_image TEXT,
            extracted_text TEXT,
            items TEXT,
            payment_method TEXT DEFAULT 'Unknown',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    ''')
    db.execute('''
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            color TEXT DEFAULT '#6c757d',
            icon TEXT DEFAULT '📁',
            keywords TEXT DEFAULT '[]'
        )
    ''')
    # Add keywords column if it doesn't exist (migration)
    try:
        db.execute('ALTER TABLE categories ADD COLUMN keywords TEXT DEFAULT "[]"')
    except:
        pass
    
    # Insert default categories with keywords
    default_categories = {
        'Medical Supplies': ['syringe', 'bandage', 'gauze', 'glove', 'mask', 'cotton', 'tape', 'catheter', 'iv', 'suture', 'stethoscope', 'thermometer'],
        'Pharmaceuticals': ['medicine', 'drug', 'vaccine', 'antibiotic', 'tablet', 'capsule', 'injection', 'pharmacy', 'pharma', 'prescription', 'dose'],
        'Equipment & Maintenance': ['repair', 'maintenance', 'machine', 'monitor', 'x-ray', 'ultrasound', 'dental', 'surgical', 'anesthesia', 'autoclave'],
        'Utilities': ['electric', 'water', 'gas', 'internet', 'phone', 'utility', 'power', 'energy', 'bill'],
        'Office Supplies': ['paper', 'pen', 'printer', 'ink', 'toner', 'folder', 'stapler', 'clip', 'envelope', 'label'],
        'Cleaning Supplies': ['clean', 'disinfect', 'sanitizer', 'soap', 'detergent', 'bleach', 'mop', 'wipes', 'trash'],
        'Food & Nutrition': ['food', 'feed', 'diet', 'nutrition', 'treat', 'kibble', 'can', 'pet food', 'supplement'],
        'Marketing & Advertising': ['ad', 'advert', 'marketing', 'flyer', 'banner', 'sign', 'social', 'promotion', 'website'],
        'Insurance': ['insurance', 'policy', 'coverage', 'premium', 'liability', 'claim'],
        'Professional Services': ['consult', 'legal', 'accounting', 'audit', 'training', 'license', 'certification', 'cpa', 'lawyer'],
        'Rent & Facilities': ['rent', 'lease', 'mortgage', 'property', 'facility', 'building', 'space'],
        'Staff & Payroll': ['salary', 'wage', 'payroll', 'bonus', 'benefit', 'training', 'staff', 'employee', 'hire'],
        'Other': []
    }
    for cat, keywords in default_categories.items():
        db.execute('INSERT OR IGNORE INTO categories (name, keywords) VALUES (?, ?)', 
                   (cat, json.dumps(keywords)))
    db.commit()
    db.close()


def allowed_file(filename):
    """Check if file extension is allowed."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def extract_text_from_image(image_path):
    """Extract text from image using OCR."""
    if not HAS_OCR:
        return ""
    try:
        img = Image.open(image_path)
        text = pytesseract.image_to_string(img)
        return text.strip()
    except Exception as e:
        print(f"OCR Error: {e}")
        return ""


def parse_receipt_text(text):
    """Parse extracted text to find vendor, date, amount, items."""
    result = {
        'vendor': 'Unknown Vendor',
        'date': datetime.now().strftime('%Y-%m-%d'),
        'amount': 0.0,
        'items': [],
        'category': 'Other'
    }
    
    lines = text.split('\n')
    
    # Find vendor (usually first non-empty line or line with store name)
    for line in lines[:5]:
        line = line.strip()
        if line and len(line) > 3 and not re.match(r'^[\d\s\-\./]+$', line):
            result['vendor'] = line
            break
    
    # Find date patterns
    date_patterns = [
        r'(\d{1,2})[/\-\.](\d{1,2})[/\-\.](\d{2,4})',
        r'(\d{4})[/\-\.](\d{1,2})[/\-\.](\d{1,2})',
        r'(\w+ \d{1,2},? \d{4})',
    ]
    
    for line in lines:
        for pattern in date_patterns:
            match = re.search(pattern, line)
            if match:
                try:
                    if len(match.groups()) == 3:
                        # Try to parse the date
                        parts = match.groups()
                        if len(parts[0]) == 4:  # YYYY-MM-DD
                            date_str = f"{parts[0]}-{parts[1].zfill(2)}-{parts[2].zfill(2)}"
                        else:  # MM/DD/YYYY
                            date_str = f"{parts[2]}-{parts[0].zfill(2)}-{parts[1].zfill(2)}"
                        # Validate date
                        datetime.strptime(date_str, '%Y-%m-%d')
                        result['date'] = date_str
                except:
                    pass
                break
        if result['date'] != datetime.now().strftime('%Y-%m-%d'):
            break
    
    # Find amount (look for TOTAL, AMOUNT, etc.)
    amount_patterns = [
        r'(?:TOTAL|AMOUNT|GRAND TOTAL|SUBTOTAL|BALANCE|DUE)\s*[:\s]*\$?\s*(\d+[.,]\d{2})',
        r'\$\s*(\d+[.,]\d{2})',
        r'(\d+[.,]\d{2})\s*(?:USD|PHP|EUR|GBP)',
    ]
    
    amounts_found = []
    for line in lines:
        for pattern in amount_patterns:
            matches = re.findall(pattern, line, re.IGNORECASE)
            for match in matches:
                try:
                    amount = float(match.replace(',', '.'))
                    amounts_found.append(amount)
                except:
                    pass
    
    if amounts_found:
        # Usually the largest amount is the total
        result['amount'] = max(amounts_found)
    
    # Extract line items (lines with prices)
    item_pattern = r'(.+?)\s+\$?\s*(\d+[.,]\d{2})'
    for line in lines:
        match = re.search(item_pattern, line)
        if match:
            item_name = match.group(1).strip()
            try:
                item_price = float(match.group(2).replace(',', '.'))
                if item_name and len(item_name) > 2:
                    result['items'].append({'name': item_name, 'price': item_price})
            except:
                pass
    
    # Auto-categorize based on vendor name and extracted text
    text_lower = (result['vendor'] + ' ' + text).lower()
    result['category'] = auto_categorize(text_lower)
    
    return result


# ==================== ROUTES ====================

@app.route('/')
def index():
    """Serve main page."""
    return send_from_directory('templates', 'index.html')


@app.route('/static/<path:path>')
def serve_static(path):
    """Serve static files."""
    return send_from_directory('static', path)


@app.route('/api/receipt/<filename>')
def serve_receipt(filename):
    """Serve receipt image from R2 or local storage."""
    if USE_R2 and s3_client:
        try:
            obj = s3_client.get_object(Bucket=R2_BUCKET, Key=f'receipts/{filename}')
            from flask import Response
            return Response(
                obj['Body'].read(),
                mimetype=obj['ContentType'],
                headers={'Content-Disposition': f'inline; filename={filename}'}
            )
        except Exception as e:
            print(f"R2 fetch error: {e}")
    
    # Fallback to local
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)


@app.route('/api/health')
def health_check():
    """Health check with R2 status."""
    r2_error = None
    if USE_R2 and s3_client:
        try:
            s3_client.put_object(
                Bucket=R2_BUCKET,
                Key='_health_check.txt',
                Body=b'ok'
            )
            s3_client.delete_object(Bucket=R2_BUCKET, Key='_health_check.txt')
            r2_status = 'connected'
        except Exception as e:
            r2_status = 'error'
            r2_error = str(e)
    else:
        r2_status = 'disabled'
    
    return jsonify({
        'status': 'ok',
        'r2_enabled': USE_R2,
        'r2_status': r2_status,
        'r2_error': r2_error,
        'r2_endpoint': R2_ENDPOINT[:30] + '...' if R2_ENDPOINT else 'not set',
        'r2_bucket': R2_BUCKET or 'not set'
    })


@app.route('/api/upload', methods=['POST'])
def upload_receipt():
    """Upload and process receipt image."""
    if 'receipt' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400
    
    file = request.files['receipt']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    if not allowed_file(file.filename):
        return jsonify({'error': 'Invalid file type. Use PNG, JPG, GIF, BMP, or WebP'}), 400
    
    # Save file
    filename = secure_filename(file.filename)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_')
    filename = timestamp + filename
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(filepath)
    
    # Upload to R2 if enabled
    if USE_R2 and s3_client:
        try:
            with open(filepath, 'rb') as f:
                file_data = f.read()
            s3_client.put_object(
                Bucket=R2_BUCKET,
                Key=f'receipts/{filename}',
                Body=file_data,
                ContentType=file.content_type or 'image/jpeg'
            )
            print(f"R2 upload success: receipts/{filename}")
        except Exception as e:
            import traceback
            print(f"R2 upload error: {e}")
            traceback.print_exc()
    
    # Extract text
    extracted_text = extract_text_from_image(filepath)
    
    # Parse receipt
    parsed = parse_receipt_text(extracted_text)
    parsed['receipt_image'] = filename
    parsed['extracted_text'] = extracted_text
    
    return jsonify({
        'success': True,
        'parsed': parsed
    })


@app.route('/api/expenses', methods=['POST'])
def add_expense():
    """Add a new expense."""
    data = request.json
    
    db = get_db()
    now = datetime.now().isoformat()
    
    cursor = db.execute('''
        INSERT INTO expenses (vendor, amount, date, category, description, 
                             receipt_image, extracted_text, items, payment_method,
                             created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        data.get('vendor', 'Unknown'),
        float(data.get('amount', 0)),
        data.get('date', datetime.now().strftime('%Y-%m-%d')),
        data.get('category', 'Other'),
        data.get('description', ''),
        data.get('receipt_image', ''),
        data.get('extracted_text', ''),
        json.dumps(data.get('items', [])),
        data.get('payment_method', 'Unknown'),
        now, now
    ))
    db.commit()
    
    expense_id = cursor.lastrowid
    
    return jsonify({
        'success': True,
        'id': expense_id,
        'message': 'Expense added successfully'
    })


@app.route('/api/expenses', methods=['GET'])
def get_expenses():
    """Get expenses with optional filters."""
    db = get_db()
    
    query = 'SELECT * FROM expenses WHERE 1=1'
    params = []
    
    # Date range filter
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    if start_date:
        query += ' AND date >= ?'
        params.append(start_date)
    if end_date:
        query += ' AND date <= ?'
        params.append(end_date)
    
    # Category filter
    category = request.args.get('category')
    if category:
        query += ' AND category = ?'
        params.append(category)
    
    # Vendor search
    vendor = request.args.get('vendor')
    if vendor:
        query += ' AND vendor LIKE ?'
        params.append(f'%{vendor}%')
    
    # Search
    search = request.args.get('search')
    if search:
        query += ' AND (vendor LIKE ? OR description LIKE ? OR extracted_text LIKE ?)'
        params.extend([f'%{search}%'] * 3)
    
    query += ' ORDER BY date DESC, created_at DESC'
    
    # Pagination
    limit = request.args.get('limit', 100)
    offset = request.args.get('offset', 0)
    query += ' LIMIT ? OFFSET ?'
    params.extend([int(limit), int(offset)])
    
    expenses = db.execute(query, params).fetchall()
    
    result = []
    for exp in expenses:
        result.append({
            'id': exp['id'],
            'vendor': exp['vendor'],
            'amount': exp['amount'],
            'date': exp['date'],
            'category': exp['category'],
            'description': exp['description'],
            'receipt_image': exp['receipt_image'],
            'items': json.loads(exp['items'] or '[]'),
            'payment_method': exp['payment_method'],
            'created_at': exp['created_at']
        })
    
    return jsonify({'expenses': result})


@app.route('/api/expenses/<int:expense_id>', methods=['PUT'])
def update_expense(expense_id):
    """Update an expense."""
    data = request.json
    db = get_db()
    
    db.execute('''
        UPDATE expenses 
        SET vendor=?, amount=?, date=?, category=?, description=?, 
            payment_method=?, items=?, updated_at=?
        WHERE id=?
    ''', (
        data.get('vendor'),
        float(data.get('amount', 0)),
        data.get('date'),
        data.get('category'),
        data.get('description', ''),
        data.get('payment_method', 'Unknown'),
        json.dumps(data.get('items', [])),
        datetime.now().isoformat(),
        expense_id
    ))
    db.commit()
    
    return jsonify({'success': True, 'message': 'Expense updated'})


@app.route('/api/expenses/<int:expense_id>', methods=['DELETE'])
def delete_expense(expense_id):
    """Delete an expense."""
    db = get_db()
    db.execute('DELETE FROM expenses WHERE id=?', (expense_id,))
    db.commit()
    
    return jsonify({'success': True, 'message': 'Expense deleted'})


@app.route('/api/categories', methods=['GET'])
def get_categories():
    """Get all categories with their keywords."""
    db = get_db()
    cats = db.execute('SELECT * FROM categories ORDER BY name').fetchall()
    
    result = []
    for c in cats:
        keywords = json.loads(c['keywords'] or '[]') if 'keywords' in c.keys() else []
        result.append({
            'id': c['id'], 
            'name': c['name'], 
            'color': c['color'], 
            'icon': c['icon'],
            'keywords': keywords
        })
    return jsonify({'categories': result})


@app.route('/api/categories', methods=['POST'])
def add_category():
    """Add a new category."""
    data = request.json
    db = get_db()
    
    try:
        cursor = db.execute(
            'INSERT INTO categories (name, keywords) VALUES (?, ?)',
            (data['name'], json.dumps(data.get('keywords', [])))
        )
        db.commit()
        return jsonify({'success': True, 'id': cursor.lastrowid})
    except sqlite3.IntegrityError:
        return jsonify({'error': 'Category already exists'}), 400


@app.route('/api/categories/<int:cat_id>', methods=['PUT'])
def update_category(cat_id):
    """Update a category."""
    data = request.json
    db = get_db()
    
    db.execute(
        'UPDATE categories SET name=?, keywords=? WHERE id=?',
        (data['name'], json.dumps(data.get('keywords', [])), cat_id)
    )
    db.commit()
    
    # Also update existing expenses with old category name if renamed
    if 'old_name' in data:
        db.execute(
            'UPDATE expenses SET category=? WHERE category=?',
            (data['name'], data['old_name'])
        )
        db.commit()
    
    return jsonify({'success': True})


@app.route('/api/categories/<int:cat_id>', methods=['DELETE'])
def delete_category(cat_id):
    """Delete a category (expenses move to 'Other')."""
    db = get_db()
    
    # Get category name first
    cat = db.execute('SELECT name FROM categories WHERE id=?', (cat_id,)).fetchone()
    if cat:
        # Move expenses to 'Other'
        db.execute('UPDATE expenses SET category=? WHERE category=?', ('Other', cat['name']))
        db.execute('DELETE FROM categories WHERE id=?', (cat_id,))
        db.commit()
    
    return jsonify({'success': True})


@app.route('/api/dashboard', methods=['GET'])
def get_dashboard():
    """Get dashboard summary data."""
    db = get_db()
    
    # Date ranges
    today = datetime.now().strftime('%Y-%m-%d')
    month_start = datetime.now().replace(day=1).strftime('%Y-%m-%d')
    last_month_start = (datetime.now().replace(day=1) - timedelta(days=1)).replace(day=1).strftime('%Y-%m-%d')
    last_month_end = (datetime.now().replace(day=1) - timedelta(days=1)).strftime('%Y-%m-%d')
    year_start = datetime.now().replace(month=1, day=1).strftime('%Y-%m-%d')
    
    # Today's total
    today_total = db.execute(
        'SELECT COALESCE(SUM(amount), 0) as total FROM expenses WHERE date = ?', (today,)
    ).fetchone()['total']
    
    # This month's total
    month_total = db.execute(
        'SELECT COALESCE(SUM(amount), 0) as total FROM expenses WHERE date >= ?', (month_start,)
    ).fetchone()['total']
    
    # Last month's total
    last_month_total = db.execute(
        'SELECT COALESCE(SUM(amount), 0) as total FROM expenses WHERE date >= ? AND date <= ?',
        (last_month_start, last_month_end)
    ).fetchone()['total']
    
    # Year total
    year_total = db.execute(
        'SELECT COALESCE(SUM(amount), 0) as total FROM expenses WHERE date >= ?', (year_start,)
    ).fetchone()['total']
    
    # Category breakdown (this month)
    category_breakdown = db.execute('''
        SELECT category, SUM(amount) as total, COUNT(*) as count
        FROM expenses
        WHERE date >= ?
        GROUP BY category
        ORDER BY total DESC
    ''', (month_start,)).fetchall()
    
    # Monthly trend (last 12 months)
    monthly_trend = db.execute('''
        SELECT strftime('%Y-%m', date) as month, SUM(amount) as total, COUNT(*) as count
        FROM expenses
        WHERE date >= date('now', '-12 months')
        GROUP BY strftime('%Y-%m', date)
        ORDER BY month
    ''').fetchall()
    
    # Top vendors (this month)
    top_vendors = db.execute('''
        SELECT vendor, SUM(amount) as total, COUNT(*) as count
        FROM expenses
        WHERE date >= ?
        GROUP BY vendor
        ORDER BY total DESC
        LIMIT 10
    ''', (month_start,)).fetchall()
    
    # Recent expenses
    recent = db.execute('''
        SELECT * FROM expenses
        ORDER BY created_at DESC
        LIMIT 10
    ''').fetchall()
    
    recent_list = []
    for exp in recent:
        recent_list.append({
            'id': exp['id'],
            'vendor': exp['vendor'],
            'amount': exp['amount'],
            'date': exp['date'],
            'category': exp['category']
        })
    
    # Expense count this month
    month_count = db.execute(
        'SELECT COUNT(*) as count FROM expenses WHERE date >= ?', (month_start,)
    ).fetchone()['count']
    
    return jsonify({
        'summary': {
            'today': today_total,
            'this_month': month_total,
            'last_month': last_month_total,
            'year_total': year_total,
            'month_count': month_count,
            'month_change_pct': ((month_total - last_month_total) / last_month_total * 100) if last_month_total > 0 else 0
        },
        'category_breakdown': [
            {'category': r['category'], 'total': r['total'], 'count': r['count']}
            for r in category_breakdown
        ],
        'monthly_trend': [
            {'month': r['month'], 'total': r['total'], 'count': r['count']}
            for r in monthly_trend
        ],
        'top_vendors': [
            {'vendor': r['vendor'], 'total': r['total'], 'count': r['count']}
            for r in top_vendors
        ],
        'recent_expenses': recent_list
    })


@app.route('/api/reports', methods=['GET'])
def get_report():
    """Generate expense reports."""
    db = get_db()
    
    report_type = request.args.get('type', 'summary')
    start_date = request.args.get('start_date', (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d'))
    end_date = request.args.get('end_date', datetime.now().strftime('%Y-%m-%d'))
    
    if report_type == 'summary':
        data = db.execute('''
            SELECT category, 
                   SUM(amount) as total, 
                   COUNT(*) as count,
                   AVG(amount) as average
            FROM expenses
            WHERE date >= ? AND date <= ?
            GROUP BY category
            ORDER BY total DESC
        ''', (start_date, end_date)).fetchall()
        
        return jsonify({
            'type': 'summary',
            'period': f'{start_date} to {end_date}',
            'data': [
                {
                    'category': r['category'],
                    'total': r['total'],
                    'count': r['count'],
                    'average': round(r['average'], 2)
                } for r in data
            ]
        })
    
    elif report_type == 'daily':
        data = db.execute('''
            SELECT date, SUM(amount) as total, COUNT(*) as count
            FROM expenses
            WHERE date >= ? AND date <= ?
            GROUP BY date
            ORDER BY date
        ''', (start_date, end_date)).fetchall()
        
        return jsonify({
            'type': 'daily',
            'period': f'{start_date} to {end_date}',
            'data': [
                {'date': r['date'], 'total': r['total'], 'count': r['count']}
                for r in data
            ]
        })
    
    elif report_type == 'vendor':
        data = db.execute('''
            SELECT vendor, 
                   SUM(amount) as total, 
                   COUNT(*) as count,
                   GROUP_CONCAT(DISTINCT category) as categories
            FROM expenses
            WHERE date >= ? AND date <= ?
            GROUP BY vendor
            ORDER BY total DESC
        ''', (start_date, end_date)).fetchall()
        
        return jsonify({
            'type': 'vendor',
            'period': f'{start_date} to {end_date}',
            'data': [
                {
                    'vendor': r['vendor'],
                    'total': r['total'],
                    'count': r['count'],
                    'categories': r['categories']
                } for r in data
            ]
        })
    
    return jsonify({'error': 'Invalid report type'}), 400


@app.route('/api/export', methods=['GET'])
def export_csv():
    """Export expenses as CSV."""
    import csv
    import io
    
    db = get_db()
    
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    category = request.args.get('category')
    
    query = 'SELECT * FROM expenses WHERE 1=1'
    params = []
    
    if start_date:
        query += ' AND date >= ?'
        params.append(start_date)
    if end_date:
        query += ' AND date <= ?'
        params.append(end_date)
    if category:
        query += ' AND category = ?'
        params.append(category)
    
    query += ' ORDER BY date DESC'
    
    expenses = db.execute(query, params).fetchall()
    
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Date', 'Vendor', 'Category', 'Amount', 'Description', 'Payment Method', 'Items'])
    
    for exp in expenses:
        items = json.loads(exp['items'] or '[]')
        items_str = '; '.join([f"{i['name']} (${i['price']})" for i in items])
        writer.writerow([
            exp['date'], exp['vendor'], exp['category'],
            f"${exp['amount']:.2f}", exp['description'],
            exp['payment_method'], items_str
        ])
    
    output.seek(0)
    
    from flask import Response
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename=expenses_{datetime.now().strftime("%Y%m%d")}.csv'}
    )


# Initialize database on startup
with app.app_context():
    init_db()


if __name__ == '__main__':
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    app.run(host='0.0.0.0', port=5000, debug=True)
