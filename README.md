# -TransitOps-Smart-Transport-Operations-Platform# 🚛 TransitOps Frontend

A modern, responsive frontend for the **TransitOps - Smart Transport Operations Platform**. This application provides an intuitive interface for managing vehicles, drivers, trips, maintenance, fuel expenses, and operational analytics.

---

## 📌 Project Overview

TransitOps is a fleet and transport management system designed to help logistics companies manage their daily transport operations digitally.

This frontend communicates with the backend APIs and provides role-based dashboards for different users.

---

# ✨ Features

## 🔐 Authentication
- Login
- Logout
- JWT Authentication
- Role-Based Access Control (RBAC)

---

## 📊 Dashboard

Displays:

- Active Vehicles
- Available Vehicles
- Vehicles in Maintenance
- Active Trips
- Pending Trips
- Drivers On Duty
- Fleet Utilization
- Recent Activities

---

## 🚚 Vehicle Management

- View Vehicles
- Add Vehicle
- Edit Vehicle
- Delete Vehicle
- Vehicle Status
- Search Vehicles
- Filter by Type
- Filter by Status

---

## 👨‍✈️ Driver Management

- View Drivers
- Add Driver
- Update Driver
- Delete Driver
- License Expiry Status
- Safety Score
- Driver Availability

---

## 🛣 Trip Management

- Create Trip
- Assign Vehicle
- Assign Driver
- Trip Details
- Dispatch Trip
- Complete Trip
- Cancel Trip

---

## 🔧 Maintenance Management

- Create Maintenance Record
- Update Maintenance Status
- Maintenance History
- Vehicle Availability

---

## ⛽ Fuel & Expense Management

- Fuel Logs
- Fuel Cost
- Maintenance Cost
- Toll Expenses
- Other Expenses

---

## 📈 Reports & Analytics

- Fleet Utilization
- Fuel Efficiency
- Operational Cost
- Vehicle ROI
- Charts
- Export CSV
- Export PDF

---

## 🌙 Additional Features

- Responsive Design
- Dark Mode
- Search
- Filters
- Pagination
- Notifications
- Loading Skeleton
- Error Handling

---
# 🎨 Pages

- Login
- Dashboard
- Vehicles
- Add Vehicle
- Edit Vehicle
- Drivers
- Add Driver
- Trips
- Create Trip
- Maintenance
- Fuel Logs
- Expenses
- Reports
- Analytics
- Profile
- Settings
- Not Found (404)

TransitOps
│
├── app.py
├── transitops.db
├── requirements.txt
│
├── static
│      style.css
│      dashboard.js
│
├── templates
│      login.html
│      dashboard.html
│      vehicles.html
│      add_vehicle.html
│      drivers.html
│      add_driver.html
│      trips.html
│      maintenance.html
│      fuel.html
│      reports.html
│
└── tests
