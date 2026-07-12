import os
import tempfile
import pytest
from werkzeug.security import check_password_hash

from app import create_app, init_db, get_db_connection


@pytest.fixture()
def client():
    db_fd, db_path = tempfile.mkstemp()
    os.close(db_fd)
    app = create_app({'TESTING': True, 'DATABASE': db_path})
    with app.test_client() as client:
        with app.app_context():
            init_db()
        yield client
    os.unlink(db_path)


def test_vehicle_and_driver_registration_flow(client):
    login = client.post('/login', data={'email': 'admin@transitops.com', 'password': 'admin123'}, follow_redirects=True)
    assert login.status_code == 200

    vehicle_resp = client.post('/vehicles', data={
        'registration_number': 'Van-05',
        'name': 'Ford Transit',
        'vehicle_type': 'Van',
        'max_load_capacity': '500',
        'odometer': '1000',
        'acquisition_cost': '25000',
        'status': 'Available',
    }, follow_redirects=True)
    assert vehicle_resp.status_code == 200

    driver_resp = client.post('/drivers', data={
        'name': 'Alex',
        'license_number': 'LIC-100',
        'license_category': 'B',
        'license_expiry': '2035-01-01',
        'contact_number': '1234567890',
        'safety_score': '95',
        'status': 'Available',
    }, follow_redirects=True)
    assert driver_resp.status_code == 200

    trip_resp = client.post('/trips', data={
        'source': 'Hub A',
        'destination': 'Hub B',
        'vehicle_id': '1',
        'driver_id': '1',
        'cargo_weight': '450',
        'planned_distance': '120',
    }, follow_redirects=True)
    assert trip_resp.status_code == 200

    with client.application.app_context():
        conn = get_db_connection()
        vehicle = conn.execute('SELECT status FROM vehicles WHERE id = 1').fetchone()
        driver = conn.execute('SELECT status FROM drivers WHERE id = 1').fetchone()
        trip = conn.execute('SELECT status FROM trips WHERE id = 1').fetchone()
        assert vehicle[0] == 'On Trip'
        assert driver[0] == 'On Trip'
        assert trip[0] == 'Dispatched'


def test_maintenance_marks_vehicle_in_shop(client):
    client.post('/login', data={'email': 'admin@transitops.com', 'password': 'admin123'}, follow_redirects=True)
    client.post('/vehicles', data={
        'registration_number': 'Van-05',
        'name': 'Ford Transit',
        'vehicle_type': 'Van',
        'max_load_capacity': '500',
        'odometer': '1000',
        'acquisition_cost': '25000',
        'status': 'Available',
    }, follow_redirects=True)

    resp = client.post('/maintenance', data={
        'vehicle_id': '1',
        'title': 'Oil Change',
        'description': 'Routine service',
        'cost': '120',
        'start_date': '2026-07-12',
        'end_date': '2026-07-12',
    }, follow_redirects=True)
    assert resp.status_code == 200

    with client.application.app_context():
        vehicle = get_db_connection().execute('SELECT status FROM vehicles WHERE id = 1').fetchone()
        assert vehicle[0] == 'In Shop'


def test_vehicle_csv_export(client):
    client.post('/login', data={'email': 'admin@transitops.com', 'password': 'admin123'}, follow_redirects=True)
    client.post('/vehicles', data={
        'registration_number': 'Van-05',
        'name': 'Ford Transit',
        'vehicle_type': 'Van',
        'max_load_capacity': '500',
        'odometer': '1000',
        'acquisition_cost': '25000',
        'status': 'Available',
    }, follow_redirects=True)

    resp = client.get('/export/vehicles')
    assert resp.status_code == 200
    assert resp.mimetype == 'text/csv'
    assert b'registration_number' in resp.data
    assert b'Van-05' in resp.data


def test_driver_edit_page_renders(client):
    client.post('/login', data={'email': 'admin@transitops.com', 'password': 'admin123'}, follow_redirects=True)
    client.post('/drivers', data={
        'name': 'Alex',
        'license_number': 'LIC-100',
        'license_category': 'B',
        'license_expiry': '2035-01-01',
        'contact_number': '1234567890',
        'safety_score': '95',
        'status': 'Available',
    }, follow_redirects=True)

    resp = client.get('/drivers/1/edit')
    assert resp.status_code == 200
    assert b'Edit Driver' in resp.data
    assert b'Available' in resp.data


def test_driver_cannot_access_fleet_manager_pages(client):
    resp = client.post('/login', data={'email': 'driver@transitops.com', 'password': 'driver123'}, follow_redirects=True)
    assert resp.status_code == 200

    settings_resp = client.get('/settings', follow_redirects=True)
    assert settings_resp.status_code == 200
    assert b'You do not have permission' in settings_resp.data


def test_reports_show_profit_estimate(client):
    client.post('/login', data={'email': 'admin@transitops.com', 'password': 'admin123'}, follow_redirects=True)
    client.post('/vehicles', data={
        'registration_number': 'Van-05',
        'name': 'Ford Transit',
        'vehicle_type': 'Van',
        'max_load_capacity': '500',
        'odometer': '1000',
        'acquisition_cost': '25000',
        'status': 'Available',
    }, follow_redirects=True)
    client.post('/operations', data={
        'vehicle_id': '1',
        'fuel': 'on',
        'liters': '40',
        'cost': '3200',
        'date': '2026-07-12',
    }, follow_redirects=True)
    client.post('/operations', data={
        'vehicle_id': '1',
        'description': 'Toll fee',
        'amount': '150',
        'date': '2026-07-12',
        'kind': 'Other',
    }, follow_redirects=True)
    client.post('/maintenance', data={
        'vehicle_id': '1',
        'title': 'Oil Change',
        'description': 'Routine service',
        'cost': '120',
        'start_date': '2026-07-12',
        'end_date': '2026-07-12',
    }, follow_redirects=True)

    resp = client.get('/reports')
    assert resp.status_code == 200
    assert b'Estimated Profit' in resp.data
    assert b'Operational Cost' in resp.data


def test_signup_stores_hashed_password(client):
    resp = client.post('/signup', data={'email': 'temp@transitops.com', 'password': 'temp123', 'role': 'Driver'}, follow_redirects=True)
    assert resp.status_code == 200

    with client.application.app_context():
        stored_password = get_db_connection().execute("SELECT password FROM users WHERE email = ?", ('temp@transitops.com',)).fetchone()[0]
        assert stored_password != 'temp123'
        assert check_password_hash(stored_password, 'temp123')


def test_reports_show_fuel_efficiency_and_roi(client):
    client.post('/login', data={'email': 'admin@transitops.com', 'password': 'admin123'}, follow_redirects=True)
    client.post('/vehicles', data={
        'registration_number': 'Van-05',
        'name': 'Ford Transit',
        'vehicle_type': 'Van',
        'max_load_capacity': '500',
        'odometer': '1000',
        'acquisition_cost': '25000',
        'status': 'Available',
    }, follow_redirects=True)
    client.post('/drivers', data={
        'name': 'Alex',
        'license_number': 'LIC-100',
        'license_category': 'B',
        'license_expiry': '2035-01-01',
        'contact_number': '1234567890',
        'safety_score': '95',
        'status': 'Available',
    }, follow_redirects=True)
    client.post('/trips', data={
        'source': 'Hub A',
        'destination': 'Hub B',
        'vehicle_id': '1',
        'driver_id': '1',
        'cargo_weight': '450',
        'planned_distance': '120',
    }, follow_redirects=True)
    client.post('/trips/1/complete', data={'final_odometer': '1500', 'fuel_consumed': '40'}, follow_redirects=True)

    resp = client.get('/reports')
    assert resp.status_code == 200
    assert b'Fuel Efficiency' in resp.data
    assert b'ROI' in resp.data


def test_admin_can_delete_user(client):
    client.post('/login', data={'email': 'admin@transitops.com', 'password': 'admin123'}, follow_redirects=True)
    client.post('/signup', data={'email': 'temp@transitops.com', 'password': 'temp123', 'role': 'Driver'}, follow_redirects=True)

    with client.application.app_context():
        user_id = get_db_connection().execute("SELECT id FROM users WHERE email = ?", ('temp@transitops.com',)).fetchone()[0]

    resp = client.post(f'/settings/{user_id}/delete', follow_redirects=True)
    assert resp.status_code == 200

    with client.application.app_context():
        count = get_db_connection().execute("SELECT COUNT(*) FROM users WHERE email = ?", ('temp@transitops.com',)).fetchone()[0]
        assert count == 0


def test_driver_delete(client):
    client.post('/login', data={'email': 'admin@transitops.com', 'password': 'admin123'}, follow_redirects=True)
    client.post('/drivers', data={
        'name': 'Alex',
        'license_number': 'LIC-100',
        'license_category': 'B',
        'license_expiry': '2035-01-01',
        'contact_number': '1234567890',
        'safety_score': '95',
        'status': 'Available',
    }, follow_redirects=True)

    delete_resp = client.post('/drivers/1/delete', follow_redirects=True)
    assert delete_resp.status_code == 200

    with client.application.app_context():
        count = get_db_connection().execute('SELECT COUNT(*) FROM drivers').fetchone()[0]
        assert count == 0


def test_vehicle_update_and_delete(client):
    client.post('/login', data={'email': 'admin@transitops.com', 'password': 'admin123'}, follow_redirects=True)
    client.post('/vehicles', data={
        'registration_number': 'Van-05',
        'name': 'Ford Transit',
        'vehicle_type': 'Van',
        'max_load_capacity': '500',
        'odometer': '1000',
        'acquisition_cost': '25000',
        'status': 'Available',
    }, follow_redirects=True)

    update_resp = client.post('/vehicles/1/edit', data={
        'registration_number': 'Van-05',
        'name': 'Ford Transit XL',
        'vehicle_type': 'Van',
        'max_load_capacity': '550',
        'odometer': '1200',
        'acquisition_cost': '26000',
        'status': 'In Shop',
    }, follow_redirects=True)
    assert update_resp.status_code == 200

    with client.application.app_context():
        vehicle = get_db_connection().execute('SELECT name, max_load_capacity, status FROM vehicles WHERE id = 1').fetchone()
        assert vehicle[0] == 'Ford Transit XL'
        assert vehicle[1] == 550.0
        assert vehicle[2] == 'In Shop'

    delete_resp = client.post('/vehicles/1/delete', follow_redirects=True)
    assert delete_resp.status_code == 200

    with client.application.app_context():
        count = get_db_connection().execute('SELECT COUNT(*) FROM vehicles').fetchone()[0]
        assert count == 0
