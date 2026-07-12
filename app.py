import os
import sqlite3
from datetime import datetime
from functools import wraps
from flask import Flask, g, redirect, render_template, request, session, url_for, flash, current_app
from werkzeug.security import check_password_hash, generate_password_hash

DATABASE = os.path.join(os.path.dirname(__file__), 'transitops.db')
try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:
    psycopg = None

POSTGRES_SCHEMES = ('postgres://', 'postgresql://')


def get_user_role():
    user = g.get('user') or {}
    return (user.get('role') or '').strip()


def role_required(*allowed_roles):
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if not g.user:
                return redirect(url_for('login'))
            role = get_user_role()
            if allowed_roles and role not in allowed_roles:
                flash('You do not have permission to access this page.')
                return redirect(url_for('dashboard'))
            return view(*args, **kwargs)
        return wrapped
    return decorator


def get_db_connection():
    if 'db' not in g:
        database_url = current_app.config['DATABASE']
        if isinstance(database_url, str) and database_url.startswith(POSTGRES_SCHEMES):
            if psycopg is None:
                raise RuntimeError('psycopg is required for PostgreSQL support. Install psycopg[binary].')
            g.db = psycopg.connect(database_url)
            g.db.row_factory = dict_row
        else:
            g.db = sqlite3.connect(database_url)
            g.db.row_factory = sqlite3.Row
    return g.db


def is_password_valid(stored_password, submitted_password):
    if not stored_password:
        return False
    if stored_password == submitted_password:
        return True
    return check_password_hash(stored_password, submitted_password)


def init_db():
    conn = get_db_connection()
    conn.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'Fleet Manager'
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS vehicles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            registration_number TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            vehicle_type TEXT NOT NULL,
            max_load_capacity REAL NOT NULL,
            odometer REAL NOT NULL DEFAULT 0,
            acquisition_cost REAL NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'Available',
            region TEXT NOT NULL DEFAULT 'North'
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS drivers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            license_number TEXT UNIQUE NOT NULL,
            license_category TEXT NOT NULL,
            license_expiry TEXT NOT NULL,
            contact_number TEXT NOT NULL,
            safety_score REAL NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'Available'
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS trips (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL,
            destination TEXT NOT NULL,
            vehicle_id INTEGER NOT NULL,
            driver_id INTEGER NOT NULL,
            cargo_weight REAL NOT NULL,
            planned_distance REAL NOT NULL,
            status TEXT NOT NULL DEFAULT 'Draft',
            final_odometer REAL,
            fuel_consumed REAL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS maintenance_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            vehicle_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            cost REAL NOT NULL DEFAULT 0,
            start_date TEXT NOT NULL,
            end_date TEXT,
            status TEXT NOT NULL DEFAULT 'Open'
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS fuel_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            vehicle_id INTEGER NOT NULL,
            liters REAL NOT NULL,
            cost REAL NOT NULL,
            date TEXT NOT NULL
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            vehicle_id INTEGER NOT NULL,
            description TEXT NOT NULL,
            amount REAL NOT NULL,
            date TEXT NOT NULL,
            kind TEXT NOT NULL DEFAULT 'Other'
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS vehicle_documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            vehicle_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            note TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    if conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
        conn.execute("INSERT INTO users (email, password, role) VALUES (?, ?, ?)", ('admin@transitops.com', generate_password_hash('admin123', method='pbkdf2:sha256'), 'Fleet Manager'))
        conn.execute("INSERT INTO users (email, password, role) VALUES (?, ?, ?)", ('driver@transitops.com', generate_password_hash('driver123', method='pbkdf2:sha256'), 'Driver'))
        conn.execute("INSERT INTO users (email, password, role) VALUES (?, ?, ?)", ('safety@transitops.com', generate_password_hash('safety123', method='pbkdf2:sha256'), 'Safety Officer'))
        conn.execute("INSERT INTO users (email, password, role) VALUES (?, ?, ?)", ('finance@transitops.com', generate_password_hash('finance123', method='pbkdf2:sha256'), 'Financial Analyst'))
    else:
        for user in conn.execute('SELECT id, password FROM users').fetchall():
            if user['password'] and not user['password'].startswith('pbkdf2:'):
                conn.execute('UPDATE users SET password = ? WHERE id = ?', (generate_password_hash(user['password'], method='pbkdf2:sha256'), user['id']))
    conn.commit()


def create_app(test_config=None):
    app = Flask(__name__, static_folder='static', template_folder='templates')
    default_database = test_config.get('DATABASE') if test_config else os.environ.get('DATABASE', DATABASE)
    app.config.from_mapping(SECRET_KEY='dev-secret-key', DATABASE=default_database)
    if test_config:
        app.config.update(test_config)

    @app.before_request
    def load_user():
        g.user = session.get('user')

    def login_required(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if not g.user:
                return redirect(url_for('login'))
            return view(*args, **kwargs)
        return wrapped

    @app.teardown_appcontext
    def close_connection(exception):
        db = g.pop('db', None)
        if db is not None:
            db.commit()
            db.close()

    @app.route('/login', methods=['GET', 'POST'])
    def login():
        if request.method == 'POST':
            email = request.form['email']
            password = request.form['password']
            user = get_db_connection().execute('SELECT * FROM users WHERE email = ?', (email,)).fetchone()
            if user and is_password_valid(user['password'], password):
                session['user'] = dict(user)
                flash('Logged in successfully')
                return redirect(url_for('dashboard'))
            flash('Invalid credentials')
        return render_template('login.html')

    @app.route('/signup', methods=['GET', 'POST'])
    def signup():
        if request.method == 'POST':
            email = request.form['email'].strip()
            password = request.form['password']
            role = request.form.get('role', 'Fleet Manager')
            conn = get_db_connection()
            existing = conn.execute('SELECT * FROM users WHERE email = ?', (email,)).fetchone()
            if existing:
                flash('An account with that email already exists')
                return redirect(url_for('signup'))
            conn.execute('INSERT INTO users (email, password, role) VALUES (?, ?, ?)', (email, generate_password_hash(password, method='pbkdf2:sha256'), role))
            flash('Account created successfully. Please login.')
            return redirect(url_for('login'))
        return render_template('signup.html')

    @app.route('/logout')
    def logout():
        session.clear()
        return redirect(url_for('login'))

    @app.route('/toggle-theme')
    @login_required
    def toggle_theme():
        session['dark_mode'] = not session.get('dark_mode', False)
        return redirect(request.referrer or url_for('dashboard'))

    @app.route('/')
    @login_required
    def dashboard():
        conn = get_db_connection()
        vehicle_type_filter = request.args.get('vehicle_type', '').strip()
        status_filter = request.args.get('status', '').strip()
        region_filter = request.args.get('region', '').strip()
        search = request.args.get('search', '').strip()

        stats = {
            'active_vehicles': conn.execute("SELECT COUNT(*) FROM vehicles WHERE status != 'Retired'").fetchone()[0],
            'available_vehicles': conn.execute("SELECT COUNT(*) FROM vehicles WHERE status = 'Available'").fetchone()[0],
            'maintenance_vehicles': conn.execute("SELECT COUNT(*) FROM vehicles WHERE status = 'In Shop'").fetchone()[0],
            'active_trips': conn.execute("SELECT COUNT(*) FROM trips WHERE status = 'Dispatched'").fetchone()[0],
            'pending_trips': conn.execute("SELECT COUNT(*) FROM trips WHERE status = 'Draft'").fetchone()[0],
            'drivers_on_duty': conn.execute("SELECT COUNT(*) FROM drivers WHERE status = 'On Trip'").fetchone()[0],
        }
        total_fleet = max(1, stats['active_vehicles'])
        completed_trips = conn.execute("SELECT COUNT(*) FROM trips WHERE status = 'Completed'").fetchone()[0]
        stats['fleet_utilization'] = round((completed_trips / total_fleet) * 100, 1)

        vehicle_query = 'SELECT * FROM vehicles WHERE 1=1'
        vehicle_params = []
        if vehicle_type_filter:
            vehicle_query += ' AND vehicle_type = ?'
            vehicle_params.append(vehicle_type_filter)
        if status_filter:
            vehicle_query += ' AND status = ?'
            vehicle_params.append(status_filter)
        if region_filter:
            vehicle_query += ' AND region = ?'
            vehicle_params.append(region_filter)
        if search:
            vehicle_query += ' AND (registration_number LIKE ? OR name LIKE ? OR vehicle_type LIKE ?)' 
            vehicle_params.extend([f'%{search}%'] * 3)
        vehicle_query += ' ORDER BY id DESC'

        vehicles = conn.execute(vehicle_query, vehicle_params).fetchall()
        trips = conn.execute('SELECT * FROM trips ORDER BY id DESC LIMIT 10').fetchall()

        status_counts = {
            'Available': conn.execute("SELECT COUNT(*) FROM vehicles WHERE status = 'Available'").fetchone()[0],
            'On Trip': conn.execute("SELECT COUNT(*) FROM vehicles WHERE status = 'On Trip'").fetchone()[0],
            'In Shop': conn.execute("SELECT COUNT(*) FROM vehicles WHERE status = 'In Shop'").fetchone()[0],
            'Retired': conn.execute("SELECT COUNT(*) FROM vehicles WHERE status = 'Retired'").fetchone()[0],
        }

        return render_template(
            'dashboard.html',
            **stats,
            vehicles=vehicles,
            trips=trips,
            status_counts=status_counts,
            vehicle_type_filter=vehicle_type_filter,
            status_filter=status_filter,
            region_filter=region_filter,
            search=search,
        )

    @app.route('/vehicles', methods=['GET', 'POST'])
    @login_required
    @role_required('Fleet Manager', 'Safety Officer')
    def vehicles():
        conn = get_db_connection()
        if request.method == 'POST':
            try:
                conn.execute('INSERT INTO vehicles (registration_number, name, vehicle_type, max_load_capacity, odometer, acquisition_cost, status, region) VALUES (?, ?, ?, ?, ?, ?, ?, ?)', (
                    request.form['registration_number'].strip(),
                    request.form['name'].strip(),
                    request.form['vehicle_type'].strip(),
                    request.form['max_load_capacity'],
                    request.form['odometer'],
                    request.form['acquisition_cost'],
                    request.form['status'].strip(),
                    request.form.get('region', 'North').strip()
                ))
                flash('Vehicle registered')
            except sqlite3.IntegrityError:
                flash('Registration number already exists. Please use a unique registration.')
            return redirect(url_for('vehicles'))

        vehicle_type_filter = request.args.get('vehicle_type', '').strip()
        status_filter = request.args.get('status', '').strip()
        region_filter = request.args.get('region', '').strip()
        search = request.args.get('search', '').strip()

        query = 'SELECT * FROM vehicles WHERE 1=1'
        params = []
        if vehicle_type_filter:
            query += ' AND vehicle_type = ?'
            params.append(vehicle_type_filter)
        if status_filter:
            query += ' AND status = ?'
            params.append(status_filter)
        if region_filter:
            query += ' AND region LIKE ?'
            params.append(f'%{region_filter}%')
        if search:
            query += ' AND (registration_number LIKE ? OR name LIKE ? OR vehicle_type LIKE ? OR region LIKE ?)'
            params.extend([f'%{search}%'] * 4)
        query += ' ORDER BY id DESC'
        items = conn.execute(query, params).fetchall()

        return render_template('vehicles.html', items=items)

    @app.route('/vehicles/<int:vehicle_id>/edit', methods=['GET', 'POST'])
    @login_required
    @role_required('Fleet Manager')
    def edit_vehicle(vehicle_id):
        conn = get_db_connection()
        vehicle = conn.execute('SELECT * FROM vehicles WHERE id = ?', (vehicle_id,)).fetchone()
        if not vehicle:
            flash('Vehicle not found')
            return redirect(url_for('vehicles'))
        if request.method == 'POST':
            conn.execute('UPDATE vehicles SET registration_number = ?, name = ?, vehicle_type = ?, max_load_capacity = ?, odometer = ?, acquisition_cost = ?, status = ?, region = ? WHERE id = ?', (
                request.form['registration_number'], request.form['name'], request.form['vehicle_type'], request.form['max_load_capacity'], request.form['odometer'], request.form['acquisition_cost'], request.form['status'], request.form.get('region', 'North'), vehicle_id
            ))
            flash('Vehicle updated')
            return redirect(url_for('vehicles'))
        return render_template('vehicle_edit.html', vehicle=vehicle)

    @app.route('/vehicles/<int:vehicle_id>/delete', methods=['POST'])
    @login_required
    @role_required('Fleet Manager')
    def delete_vehicle(vehicle_id):
        conn = get_db_connection()
        conn.execute('DELETE FROM vehicles WHERE id = ?', (vehicle_id,))
        flash('Vehicle deleted')
        return redirect(url_for('vehicles'))

    @app.route('/vehicles/<int:vehicle_id>/documents', methods=['GET', 'POST'])
    @login_required
    @role_required('Fleet Manager')
    def vehicle_documents(vehicle_id):
        conn = get_db_connection()
        vehicle = conn.execute('SELECT * FROM vehicles WHERE id = ?', (vehicle_id,)).fetchone()
        if not vehicle:
            flash('Vehicle not found')
            return redirect(url_for('vehicles'))
        if request.method == 'POST':
            conn.execute('INSERT INTO vehicle_documents (vehicle_id, title, note) VALUES (?, ?, ?)', (
                vehicle_id, request.form['title'], request.form['note']
            ))
            flash('Document note saved')
            return redirect(url_for('vehicle_documents', vehicle_id=vehicle_id))
        documents = conn.execute('SELECT * FROM vehicle_documents WHERE vehicle_id = ? ORDER BY id DESC', (vehicle_id,)).fetchall()
        return render_template('vehicle_documents.html', vehicle=vehicle, documents=documents)

    @app.route('/drivers', methods=['GET', 'POST'])
    @login_required
    @role_required('Fleet Manager', 'Safety Officer')
    def drivers():
        conn = get_db_connection()
        if request.method == 'POST':
            conn.execute('INSERT INTO drivers (name, license_number, license_category, license_expiry, contact_number, safety_score, status) VALUES (?, ?, ?, ?, ?, ?, ?)', (
                request.form['name'].strip(),
                request.form['license_number'].strip(),
                request.form['license_category'].strip(),
                request.form['license_expiry'],
                request.form['contact_number'].strip(),
                request.form['safety_score'],
                request.form['status'].strip()
            ))
            flash('Driver registered')
            return redirect(url_for('drivers'))

        search = request.args.get('search', '').strip()
        status_filter = request.args.get('status', '').strip()
        query = 'SELECT * FROM drivers WHERE 1=1'
        params = []
        if search:
            query += ' AND (name LIKE ? OR license_number LIKE ? OR license_category LIKE ? OR contact_number LIKE ?)'
            params.extend([f'%{search}%', f'%{search}%', f'%{search}%', f'%{search}%'])
        if status_filter:
            query += ' AND status = ?'
            params.append(status_filter)
        query += ' ORDER BY id DESC'
        items = conn.execute(query, params).fetchall()

        trip_summary = conn.execute(
            "SELECT driver_id, SUM(CASE WHEN status = 'Completed' THEN 1 ELSE 0 END) AS completed, COUNT(*) AS total FROM trips GROUP BY driver_id"
        ).fetchall()
        driver_completion = {
            row['driver_id']: f"{round((row['completed'] or 0) / (row['total'] or 1) * 100)}%"
            for row in trip_summary
        }

        return render_template('drivers.html', items=items, driver_completion=driver_completion)

    @app.route('/drivers/<int:driver_id>/edit', methods=['GET', 'POST'])
    @login_required
    @role_required('Fleet Manager', 'Safety Officer')
    def edit_driver(driver_id):
        conn = get_db_connection()
        driver = conn.execute('SELECT * FROM drivers WHERE id = ?', (driver_id,)).fetchone()
        if not driver:
            flash('Driver not found')
            return redirect(url_for('drivers'))
        if request.method == 'POST':
            conn.execute('UPDATE drivers SET name = ?, license_number = ?, license_category = ?, license_expiry = ?, contact_number = ?, safety_score = ?, status = ? WHERE id = ?', (
                request.form['name'], request.form['license_number'], request.form['license_category'], request.form['license_expiry'], request.form['contact_number'], request.form['safety_score'], request.form['status'], driver_id
            ))
            flash('Driver details updated')
            return redirect(url_for('drivers'))
        return render_template('driver_edit.html', driver=driver)

    @app.route('/drivers/<int:driver_id>/delete', methods=['POST'])
    @login_required
    @role_required('Fleet Manager', 'Safety Officer')
    def delete_driver(driver_id):
        conn = get_db_connection()
        conn.execute('DELETE FROM drivers WHERE id = ?', (driver_id,))
        flash('Driver deleted')
        return redirect(url_for('drivers'))

    @app.route('/trips', methods=['GET', 'POST'])
    @login_required
    @role_required('Fleet Manager', 'Safety Officer', 'Driver')
    def trips():
        conn = get_db_connection()
        if request.method == 'POST':
            vehicle_id = request.form.get('vehicle_id')
            driver_id = request.form.get('driver_id')
            cargo_weight_value = request.form.get('cargo_weight')
            planned_distance = request.form.get('planned_distance')
            source = request.form.get('source')
            destination = request.form.get('destination')
            if not vehicle_id or not driver_id or not cargo_weight_value or not planned_distance or not source or not destination:
                flash('Please complete all trip fields.')
                return redirect(url_for('trips'))
            try:
                cargo_weight = float(cargo_weight_value)
            except (TypeError, ValueError):
                flash('Cargo weight must be a valid number.')
                return redirect(url_for('trips'))
            vehicle = conn.execute('SELECT * FROM vehicles WHERE id = ?', (vehicle_id,)).fetchone()
            driver = conn.execute('SELECT * FROM drivers WHERE id = ?', (driver_id,)).fetchone()
            if not vehicle or not driver:
                flash('Please select a valid vehicle and driver.')
                return redirect(url_for('trips'))
            if cargo_weight > vehicle['max_load_capacity']:
                flash('Cargo weight exceeds vehicle capacity')
                return redirect(url_for('trips'))
            if vehicle['status'] != 'Available' or driver['status'] != 'Available':
                flash('Vehicle or driver is not available')
                return redirect(url_for('trips'))
            if driver['license_expiry'] < datetime.now().strftime('%Y-%m-%d') or driver['status'] == 'Suspended':
                flash('Driver license is expired or suspended')
                return redirect(url_for('trips'))
            conn.execute('INSERT INTO trips (source, destination, vehicle_id, driver_id, cargo_weight, planned_distance, status) VALUES (?, ?, ?, ?, ?, ?, ?)', (
                source, destination, vehicle_id, driver_id, cargo_weight, planned_distance, 'Dispatched'
            ))
            conn.execute('UPDATE vehicles SET status = ? WHERE id = ?', ('On Trip', vehicle_id))
            conn.execute('UPDATE drivers SET status = ? WHERE id = ?', ('On Trip', driver_id))
            flash('Trip dispatched')
            return redirect(url_for('trips'))
        vehicles = conn.execute("SELECT * FROM vehicles WHERE status = 'Available' ORDER BY id DESC").fetchall()
        drivers = conn.execute("SELECT * FROM drivers WHERE status = 'Available' AND license_expiry >= ? ORDER BY id DESC", (datetime.now().strftime('%Y-%m-%d'),)).fetchall()
        items = conn.execute(
            'SELECT trips.*, vehicles.registration_number AS registration, vehicles.name AS vehicle_name, drivers.name AS driver_name FROM trips JOIN vehicles ON trips.vehicle_id = vehicles.id JOIN drivers ON trips.driver_id = drivers.id ORDER BY trips.id DESC'
        ).fetchall()
        status_counts = {
            'Dispatched': conn.execute("SELECT COUNT(*) FROM trips WHERE status = 'Dispatched'").fetchone()[0],
            'Completed': conn.execute("SELECT COUNT(*) FROM trips WHERE status = 'Completed'").fetchone()[0],
            'Cancelled': conn.execute("SELECT COUNT(*) FROM trips WHERE status = 'Cancelled'").fetchone()[0],
        }
        return render_template('trips.html', vehicles=vehicles, drivers=drivers, items=items, status_counts=status_counts)

    @app.route('/trips/<int:trip_id>/complete', methods=['POST'])
    @login_required
    @role_required('Fleet Manager')
    def complete_trip(trip_id):
        conn = get_db_connection()
        trip = conn.execute('SELECT * FROM trips WHERE id = ?', (trip_id,)).fetchone()
        if trip:
            final_odometer = request.form.get('final_odometer', 0)
            fuel_consumed = request.form.get('fuel_consumed', 0)
            conn.execute('UPDATE trips SET status = ?, final_odometer = ?, fuel_consumed = ? WHERE id = ?', ('Completed', final_odometer, fuel_consumed, trip_id))
            conn.execute('UPDATE vehicles SET status = ? WHERE id = ?', ('Available', trip['vehicle_id']))
            conn.execute('UPDATE drivers SET status = ? WHERE id = ?', ('Available', trip['driver_id']))
            conn.execute('INSERT INTO fuel_logs (vehicle_id, liters, cost, date) VALUES (?, ?, ?, ?)', (trip['vehicle_id'], fuel_consumed, 0, datetime.now().strftime('%Y-%m-%d')))
            flash('Trip completed')
        return redirect(url_for('trips'))

    @app.route('/trips/<int:trip_id>/cancel', methods=['POST'])
    @login_required
    @role_required('Fleet Manager', 'Safety Officer')
    def cancel_trip(trip_id):
        conn = get_db_connection()
        trip = conn.execute('SELECT * FROM trips WHERE id = ?', (trip_id,)).fetchone()
        if trip:
            conn.execute('UPDATE trips SET status = ? WHERE id = ?', ('Cancelled', trip_id))
            conn.execute('UPDATE vehicles SET status = ? WHERE id = ?', ('Available', trip['vehicle_id']))
            conn.execute('UPDATE drivers SET status = ? WHERE id = ?', ('Available', trip['driver_id']))
            flash('Trip cancelled')
        return redirect(url_for('trips'))

    @app.route('/maintenance', methods=['GET', 'POST'])
    @login_required
    @role_required('Fleet Manager', 'Safety Officer')
    def maintenance():
        conn = get_db_connection()
        if request.method == 'POST':
            vehicle_id = request.form['vehicle_id']
            conn.execute('INSERT INTO maintenance_logs (vehicle_id, title, description, cost, start_date, end_date, status) VALUES (?, ?, ?, ?, ?, ?, ?)', (
                vehicle_id, request.form['title'], request.form['description'], request.form['cost'], request.form['start_date'], request.form['end_date'], 'Open'
            ))
            conn.execute('UPDATE vehicles SET status = ? WHERE id = ?', ('In Shop', vehicle_id))
            flash('Maintenance logged')
            return redirect(url_for('maintenance'))
        items = conn.execute('SELECT * FROM maintenance_logs ORDER BY id DESC').fetchall()
        vehicles = conn.execute("SELECT * FROM vehicles WHERE status != 'Retired' ORDER BY id DESC").fetchall()
        return render_template('maintenance.html', items=items, vehicles=vehicles)

    @app.route('/maintenance/<int:maintenance_id>/close', methods=['POST'])
    @login_required
    @role_required('Fleet Manager', 'Safety Officer')
    def close_maintenance(maintenance_id):
        conn = get_db_connection()
        record = conn.execute('SELECT * FROM maintenance_logs WHERE id = ?', (maintenance_id,)).fetchone()
        if record:
            conn.execute('UPDATE maintenance_logs SET status = ? WHERE id = ?', ('Closed', maintenance_id))
            vehicle = conn.execute('SELECT status FROM vehicles WHERE id = ?', (record['vehicle_id'],)).fetchone()
            if vehicle and vehicle['status'] != 'Retired':
                conn.execute('UPDATE vehicles SET status = ? WHERE id = ?', ('Available', record['vehicle_id']))
            flash('Maintenance closed')
        return redirect(url_for('maintenance'))

    @app.route('/operations', methods=['GET', 'POST'])
    @login_required
    @role_required('Fleet Manager', 'Financial Analyst')
    def operations():
        conn = get_db_connection()
        if request.method == 'POST':
            vehicle_id = request.form['vehicle_id']
            if 'fuel' in request.form:
                conn.execute('INSERT INTO fuel_logs (vehicle_id, liters, cost, date) VALUES (?, ?, ?, ?)', (
                    vehicle_id, request.form['liters'], request.form['cost'], request.form['date']
                ))
                flash('Fuel log recorded')
            else:
                conn.execute('INSERT INTO expenses (vehicle_id, description, amount, date, kind) VALUES (?, ?, ?, ?, ?)', (
                    vehicle_id, request.form['description'], request.form['amount'], request.form['date'], request.form['kind']
                ))
                flash('Expense recorded')
            return redirect(url_for('operations'))
        vehicles = conn.execute("SELECT * FROM vehicles WHERE status != 'Retired' ORDER BY id DESC").fetchall()
        fuel_logs = conn.execute('SELECT * FROM fuel_logs ORDER BY id DESC').fetchall()
        expenses = conn.execute('SELECT * FROM expenses ORDER BY id DESC').fetchall()
        return render_template('operations.html', vehicles=vehicles, fuel_logs=fuel_logs, expenses=expenses)

    @app.route('/export/vehicles')
    @login_required
    @role_required('Fleet Manager', 'Safety Officer')
    def export_vehicles():
        conn = get_db_connection()
        rows = conn.execute('SELECT registration_number, name, vehicle_type, max_load_capacity, odometer, acquisition_cost, status FROM vehicles ORDER BY id').fetchall()
        import csv
        import io
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['registration_number', 'name', 'vehicle_type', 'max_load_capacity', 'odometer', 'acquisition_cost', 'status'])
        for row in rows:
            writer.writerow([row['registration_number'], row['name'], row['vehicle_type'], row['max_load_capacity'], row['odometer'], row['acquisition_cost'], row['status']])
        response = app.response_class(output.getvalue(), mimetype='text/csv')
        response.headers['Content-Disposition'] = 'attachment; filename=vehicles.csv'
        return response

    @app.route('/reports')
    @login_required
    @role_required('Fleet Manager', 'Safety Officer', 'Financial Analyst')
    def reports():
        conn = get_db_connection()
        fuel = conn.execute('SELECT SUM(liters) as total_liters, SUM(cost) as total_cost FROM fuel_logs').fetchone()
        expenses = conn.execute('SELECT SUM(amount) as total_amount FROM expenses').fetchone()
        maintenance = conn.execute('SELECT SUM(cost) as total_cost FROM maintenance_logs').fetchone()
        vehicles = conn.execute('SELECT * FROM vehicles').fetchall()
        total_vehicles = max(1, conn.execute("SELECT COUNT(*) FROM vehicles WHERE status != 'Retired'").fetchone()[0])
        completed_trips = conn.execute("SELECT * FROM trips WHERE status = 'Completed'").fetchall()
        utilization = round((len(completed_trips) / total_vehicles) * 100, 1)
        operational_cost = (fuel['total_cost'] or 0) + (expenses['total_amount'] or 0) + (maintenance['total_cost'] or 0)
        estimated_revenue = len(completed_trips) * 5000
        estimated_profit = estimated_revenue - operational_cost

        total_distance = sum(float(trip['planned_distance'] or 0) for trip in completed_trips)
        total_fuel_used = sum(float(trip['fuel_consumed'] or 0) for trip in completed_trips)
        fuel_efficiency = round(total_distance / total_fuel_used, 2) if total_fuel_used else 0

        vehicle_roi = {}
        for vehicle in vehicles:
            vehicle_fuel_cost = conn.execute('SELECT COALESCE(SUM(cost), 0) FROM fuel_logs WHERE vehicle_id = ?', (vehicle['id'],)).fetchone()[0]
            vehicle_expense_cost = conn.execute('SELECT COALESCE(SUM(amount), 0) FROM expenses WHERE vehicle_id = ?', (vehicle['id'],)).fetchone()[0]
            vehicle_maintenance_cost = conn.execute('SELECT COALESCE(SUM(cost), 0) FROM maintenance_logs WHERE vehicle_id = ?', (vehicle['id'],)).fetchone()[0]
            vehicle_cost = float(vehicle_fuel_cost or 0) + float(vehicle_expense_cost or 0) + float(vehicle_maintenance_cost or 0)
            vehicle_revenue = sum(5000 for trip in completed_trips if trip['vehicle_id'] == vehicle['id'])
            vehicle_roi[vehicle['id']] = round(((vehicle_revenue - vehicle_cost) / (vehicle['acquisition_cost'] or 1)) if vehicle['acquisition_cost'] else 0, 2)
        return render_template(
            'reports.html',
            fuel_total_liters=fuel['total_liters'] or 0,
            operational_cost=operational_cost,
            utilization=utilization,
            fuel_efficiency=fuel_efficiency,
            vehicles=vehicles,
            vehicle_roi=vehicle_roi,
            estimated_revenue=estimated_revenue,
            estimated_profit=estimated_profit,
        )

    @app.route('/settings', methods=['GET', 'POST'])
    @login_required
    @role_required('Fleet Manager')
    def settings():
        conn = get_db_connection()
        if request.method == 'POST':
            user_id = request.form.get('user_id')
            role = request.form.get('role')
            if user_id and role:
                conn.execute('UPDATE users SET role = ? WHERE id = ?', (role, user_id))
                flash('User role updated')
                return redirect(url_for('settings'))
        users = conn.execute('SELECT * FROM users ORDER BY id DESC').fetchall()
        return render_template('settings.html', users=users)

    @app.route('/settings/<int:user_id>/delete', methods=['POST'])
    @login_required
    @role_required('Fleet Manager')
    def delete_user(user_id):
        conn = get_db_connection()
        conn.execute('DELETE FROM users WHERE id = ?', (user_id,))
        flash('User deleted')
        return redirect(url_for('settings'))

    @app.route('/reminders')
    @login_required
    @role_required('Fleet Manager', 'Safety Officer', 'Financial Analyst', 'Driver')
    def reminders():
        conn = get_db_connection()
        today = datetime.now().strftime('%Y-%m-%d')
        drivers = conn.execute('SELECT * FROM drivers WHERE license_expiry <= ?', (today,)).fetchall()
        return render_template('reminders.html', drivers=drivers)

    with app.app_context():
        init_db()
    return app


app = create_app()


if __name__ == '__main__':
    app.run(debug=True)
