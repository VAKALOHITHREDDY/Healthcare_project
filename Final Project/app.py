import sqlite3
from flask import Flask, render_template, request, redirect, url_for, session, send_file
import pandas as pd

app = Flask(__name__)
app.secret_key = 'supersecretkey'
DATABASE = 'database.db'

# Helper Function: Get Database Connection
def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row  # Enable row access by column name
    return conn



@app.route('/')
def index():
    return render_template('index.html')

@app.route('/phc_login', methods=['GET', 'POST'])
def phc_login():
    session.clear()  # Clear session on each login attempt
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        # Query user from the database
        conn = get_db_connection()
        user = conn.execute("SELECT * FROM Users WHERE username = ? AND role = 'phc'", (username,)).fetchone()
        conn.close()

        # Validate the user
        if user:
            if user['password'] == password:  # Plain-text password validation
                session['user_id'] = user['id']
                session['username'] = user['username']
                session['role'] = user['role']
                session['assigned_phc_id'] = user['assigned_phc_id']
                return redirect(url_for('phc_dashboard', phc_id=user['assigned_phc_id']))
            else:
                return render_template('phc_login.html', error="Invalid password")
        else:
            return render_template('phc_login.html', error="Invalid username")

    return render_template('phc_login.html')





@app.route('/phc_dashboard/<int:phc_id>')
def phc_dashboard(phc_id):
    if 'role' not in session or session['role'] != 'phc':
        return redirect(url_for('phc_login'))

    conn = get_db_connection()

    # Fetch PHC details
    phc = conn.execute("SELECT * FROM PHC WHERE id = ?", (phc_id,)).fetchone()

    # Fetch doctors
    doctors = conn.execute("SELECT * FROM Doctors WHERE phc_id = ?", (phc_id,)).fetchall()

    # Fetch patients
    patients = conn.execute("SELECT * FROM Patients WHERE phc_id = ?", (phc_id,)).fetchall()

    appointments = conn.execute("""
        SELECT a.id, p.name AS patient_name, d.name AS doctor_name, a.date, a.time, a.status
        FROM Appointments a
        JOIN Patients p ON a.patient_id = p.id
        JOIN Doctors d ON a.doctor_id = d.id
        WHERE p.phc_id = ?
        ORDER BY a.date, a.time
    """, (session['user_id'],)).fetchall()

    

    # Fetch medicines
    medicines = conn.execute("SELECT * FROM Medicines WHERE phc_id = ?", (phc_id,)).fetchall()

    # Fetch vaccines
    vaccines = conn.execute("SELECT * FROM Vaccines WHERE phc_id = ?", (phc_id,)).fetchall()

    # Low stock notifications
    low_stock_medicines = conn.execute("""
        SELECT name, quantity 
        FROM Medicines 
        WHERE phc_id = ? AND quantity < 10
    """, (phc_id,)).fetchall()

    low_stock_vaccines = conn.execute("""
        SELECT name, quantity 
        FROM Vaccines 
        WHERE phc_id = ? AND quantity < 10
    """, (phc_id,)).fetchall()

    # Attendance summary
    attendance_summary = conn.execute("""
        SELECT 
            Doctors.name AS doctor_name,
            SUM(CASE WHEN Attendance.status = 'Present' THEN 1 ELSE 0 END) AS present_days,
            COUNT(Attendance.status) AS total_days
        FROM Attendance
        JOIN Doctors ON Attendance.doctor_id = Doctors.id
        WHERE Doctors.phc_id = ?
        GROUP BY Doctors.id
    """, (phc_id,)).fetchall()

    # Treatment history
    treatments = conn.execute("""
        SELECT 
            Treatments.date, 
            Patients.name AS patient_name, 
            Doctors.name AS doctor_name, 
            Treatments.medicine_name, 
            Treatments.vaccine_name, 
            Treatments.quantity
        FROM Treatments
        JOIN Patients ON Treatments.patient_id = Patients.id
        JOIN Doctors ON Treatments.doctor_id = Doctors.id
        WHERE Patients.phc_id = ?
        ORDER BY Treatments.date DESC
    """, (phc_id,)).fetchall()

    conn.close()

    return render_template(
        'phc_dashboard.html',
        phc=phc,
        doctors=doctors,
        patients=patients,
        medicines=medicines,
        vaccines=vaccines,
        appointments=appointments,
        low_stock_medicines=low_stock_medicines,
        low_stock_vaccines=low_stock_vaccines,
        attendance_summary=attendance_summary,
        treatments=treatments
    )



def check_low_stock(phc_id):
    conn = get_db_connection()
    low_stock_medicines = conn.execute("""
        SELECT name, quantity FROM Medicines 
        WHERE phc_id = ? AND quantity < 10
    """, (phc_id,)).fetchall()

    low_stock_vaccines = conn.execute("""
        SELECT name, quantity FROM Vaccines 
        WHERE phc_id = ? AND quantity < 10
    """, (phc_id,)).fetchall()

    conn.close()
    return low_stock_medicines, low_stock_vaccines


def get_dashboard_analytics(phc_id):
    conn = get_db_connection()

    # Example: Fetch daily patient visits
    daily_visits = conn.execute("""
        SELECT DATE(visited_at) AS date, COUNT(*) AS count
        FROM Patients
        WHERE phc_id = ?
        GROUP BY DATE(visited_at)
        ORDER BY date DESC
        LIMIT 7
    """, (phc_id,)).fetchall()

    conn.close()
    return daily_visits



@app.route('/add_health_metrics', methods=['POST'])
def add_health_metrics():
    patient_id = request.form['patient_id']
    blood_pressure = request.form['blood_pressure']
    sugar_level = request.form['sugar_level']

    conn = get_db_connection()
    conn.execute("""
        INSERT INTO PatientHealth (patient_id, blood_pressure, sugar_level) 
        VALUES (?, ?, ?)
    """, (patient_id, blood_pressure, sugar_level))
    conn.commit()
    conn.close()

    return redirect(url_for('phc_dashboard', phc_id=session['assigned_phc_id']))



@app.route('/place_order', methods=['POST'])
def place_order():
    if 'role' not in session or session['role'] != 'phc':
        return redirect(url_for('phc_login'))

    phc_id = session['assigned_phc_id']
    item_name = request.form['item_name']
    quantity = int(request.form['quantity'])

    conn = get_db_connection()
    conn.execute("INSERT INTO Orders (phc_id, item_name, quantity) VALUES (?, ?, ?)", (phc_id, item_name, quantity))
    conn.commit()
    conn.close()

    return redirect(url_for('phc_dashboard', phc_id=phc_id))




@app.route('/download_report')
def download_report():
    conn = get_db_connection()
    data = conn.execute("SELECT * FROM Treatments WHERE phc_id = ?", (session['assigned_phc_id'],)).fetchall()
    df = pd.DataFrame(data)
    df.to_csv('treatment_report.csv', index=False)
    return send_file('treatment_report.csv', as_attachment=True)



@app.route('/mark_attendance', methods=['POST'])
def mark_attendance():
    if 'role' not in session or session['role'] != 'phc':
        return redirect(url_for('phc_login'))

    doctor_id = request.form['doctor_id']
    date = request.form['date']
    status = request.form['status']

    conn = get_db_connection()
    conn.execute(
        "INSERT INTO Attendance (doctor_id, date, status, marked_by) VALUES (?, ?, ?, ?)",
        (doctor_id, date, status, session['user_id'])
    )
    conn.commit()
    conn.close()

    return redirect(url_for('phc_dashboard', phc_id=session['assigned_phc_id']))

@app.route('/add_patient', methods=['POST'])
def add_patient():
    if 'role' not in session or session['role'] != 'phc':
        return redirect(url_for('phc_login'))

    name = request.form['name']
    age = request.form['age']
    gender = request.form['gender']
    phc_id = session['assigned_phc_id']

    conn = get_db_connection()
    conn.execute(
        "INSERT INTO Patients (name, age, gender, phc_id) VALUES (?, ?, ?, ?)",
        (name, age, gender, phc_id)
    )
    conn.commit()
    conn.close()

    return redirect(url_for('phc_dashboard', phc_id=phc_id))



@app.route('/log_treatment', methods=['POST'])
def log_treatment():
    if 'role' not in session or session['role'] != 'phc':
        return redirect(url_for('phc_login'))

    patient_id = request.form['patient_id']
    doctor_id = request.form['doctor_id']
    date = request.form['date']
    medicine_name = request.form['medicine_name']
    vaccine_name = request.form['vaccine_name']
    quantity = int(request.form['quantity'])

    conn = get_db_connection()

    # Log treatment
    conn.execute(
        "INSERT INTO Treatments (patient_id, doctor_id, date, medicine_name, vaccine_name, quantity) VALUES (?, ?, ?, ?, ?, ?)",
        (patient_id, doctor_id, date, medicine_name, vaccine_name, quantity)
    )

    # Update medicine or vaccine inventory
    if medicine_name:
        conn.execute(
            "UPDATE Medicines SET quantity = quantity - ? WHERE name = ? AND phc_id = ?",
            (quantity, medicine_name, session['assigned_phc_id'])
        )
    if vaccine_name:
        conn.execute(
            "UPDATE Vaccines SET quantity = quantity - ? WHERE name = ? AND phc_id = ?",
            (quantity, vaccine_name, session['assigned_phc_id'])
        )

    conn.commit()
    conn.close()

    return redirect(url_for('phc_dashboard', phc_id=session['assigned_phc_id']))



# Route: Logout
@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))




# Sub-Center Login Route
@app.route('/sub_center_login', methods=['GET', 'POST'])
def sub_center_login():
    session.clear()  # Clear session on each login attempt
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        # Query user from the database
        conn = get_db_connection()
        user = conn.execute("SELECT * FROM Users WHERE username = ? AND role = 'sub_center'", (username,)).fetchone()
        conn.close()

        # Validate the user
        if user:
            if user['password'] == password:  # Plain-text password validation
                session['user_id'] = user['id']
                session['username'] = user['username']
                session['role'] = user['role']
                session['assigned_sub_center_id'] = user['assigned_sub_center_id']
                return redirect(url_for('sub_center_dashboard', sub_center_id=user['assigned_sub_center_id']))
            else:
                return render_template('sub_center_login.html', error="Invalid password")
        else:
            return render_template('sub_center_login.html', error="Invalid username")

    return render_template('sub_center_login.html')

@app.route('/add_patient_sub_center', methods=['POST'])
def add_patient_sub_center():
    if 'role' not in session or session['role'] != 'sub_center':
        return redirect(url_for('sub_center_login'))

    sub_center_id = session['assigned_sub_center_id']
    name = request.form['name']
    age = int(request.form['age'])
    gender = request.form['gender']

    conn = get_db_connection()
    conn.execute("""
        INSERT INTO Patients (name, age, gender, sub_center_id)
        VALUES (?, ?, ?, ?)
    """, (name, age, gender, sub_center_id))
    conn.commit()
    conn.close()

    return redirect(url_for('sub_center_dashboard', sub_center_id=sub_center_id))



@app.route('/log_treatment_sub_center', methods=['POST'])
def log_treatment_sub_center():
    if 'role' not in session or session['role'] != 'sub_center':
        return redirect(url_for('sub_center_login'))

    sub_center_id = session['assigned_sub_center_id']
    patient_id = int(request.form['patient_id'])
    doctor_id = int(request.form['doctor_id'])
    date = request.form['date']
    medicine_name = request.form['medicine_name']
    vaccine_name = request.form['vaccine_name']
    quantity = int(request.form['quantity']) if request.form['quantity'] else None

    conn = get_db_connection()
    # Insert treatment record
    conn.execute("""
        INSERT INTO Treatments (patient_id, doctor_id, date, medicine_name, vaccine_name, quantity)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (patient_id, doctor_id, date, medicine_name, vaccine_name, quantity))

    # Reduce medicine/vaccine stock if provided
    if medicine_name:
        conn.execute("""
            UPDATE Medicines SET quantity = quantity - ?
            WHERE name = ? AND sub_center_id = ? AND quantity >= ?
        """, (quantity, medicine_name, sub_center_id, quantity))

    if vaccine_name:
        conn.execute("""
            UPDATE Vaccines SET quantity = quantity - ?
            WHERE name = ? AND sub_center_id = ? AND quantity >= ?
        """, (quantity, vaccine_name, sub_center_id, quantity))

    conn.commit()
    conn.close()

    return redirect(url_for('sub_center_dashboard', sub_center_id=sub_center_id))








# Sub-Center Dashboard Route
@app.route('/sub_center_dashboard/<int:sub_center_id>')
def sub_center_dashboard(sub_center_id):
    if 'role' not in session or session['role'] != 'sub_center':
        return redirect(url_for('sub_center_login'))

    conn = get_db_connection()

    # Fetch Sub-Center details
    sub_center = conn.execute("SELECT * FROM SubCenter WHERE id = ?", (sub_center_id,)).fetchone()

    # Fetch doctors assigned to this sub-center
    doctors = conn.execute("SELECT * FROM Doctors WHERE sub_center_id = ?", (sub_center_id,)).fetchall()

    # Fetch patients registered in this sub-center
    patients = conn.execute("SELECT * FROM Patients WHERE sub_center_id = ?", (sub_center_id,)).fetchall()

    # Fetch medicines available in this sub-center
    medicines = conn.execute("SELECT * FROM Medicines WHERE sub_center_id = ?", (sub_center_id,)).fetchall()

    # Fetch vaccines available in this sub-center
    vaccines = conn.execute("SELECT * FROM Vaccines WHERE sub_center_id = ?", (sub_center_id,)).fetchall()

    # Low stock notifications
    low_stock_medicines = conn.execute("""
        SELECT name, quantity 
        FROM Medicines 
        WHERE sub_center_id = ? AND quantity < 10
    """, (sub_center_id,)).fetchall()

    low_stock_vaccines = conn.execute("""
        SELECT name, quantity 
        FROM Vaccines 
        WHERE sub_center_id = ? AND quantity < 10
    """, (sub_center_id,)).fetchall()

    # Attendance summary for doctors
    attendance_summary = conn.execute("""
        SELECT 
            Doctors.name AS doctor_name,
            SUM(CASE WHEN Attendance.status = 'Present' THEN 1 ELSE 0 END) AS present_days,
            COUNT(Attendance.status) AS total_days
        FROM Attendance
        JOIN Doctors ON Attendance.doctor_id = Doctors.id
        WHERE Doctors.sub_center_id = ?
        GROUP BY Doctors.id
    """, (sub_center_id,)).fetchall()

    # Treatment history for patients
    treatments = conn.execute("""
        SELECT 
            Treatments.date, 
            Patients.name AS patient_name, 
            Doctors.name AS doctor_name, 
            Treatments.medicine_name, 
            Treatments.vaccine_name, 
            Treatments.quantity
        FROM Treatments
        JOIN Patients ON Treatments.patient_id = Patients.id
        JOIN Doctors ON Treatments.doctor_id = Doctors.id
        WHERE Patients.sub_center_id = ?
        ORDER BY Treatments.date DESC
    """, (sub_center_id,)).fetchall()

    conn.close()

    return render_template(
        'sub_center_dashboard.html',
        sub_center=sub_center,
        doctors=doctors,
        patients=patients,
        medicines=medicines,
        vaccines=vaccines,
        low_stock_medicines=low_stock_medicines,
        low_stock_vaccines=low_stock_vaccines,
        attendance_summary=attendance_summary,
        treatments=treatments
    )



# DDHS Login Route
@app.route('/ddhs_login', methods=['GET', 'POST'])
def ddhs_login():
    session.clear()  # Clear session on each login attempt
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        # Query user from the database
        conn = get_db_connection()
        user = conn.execute("SELECT * FROM Users WHERE username = ? AND role = 'ddhs'", (username,)).fetchone()
        conn.close()

        # Validate the user
        if user:
            if user['password'] == password:  # Plain-text password validation
                session['user_id'] = user['id']
                session['username'] = user['username']
                session['role'] = user['role']
                return redirect(url_for('ddhs_dashboard'))

            else:
                return render_template('ddhs_login.html', error="Invalid password")
        else:
            return render_template('ddhs_login.html', error="Invalid username")

    return render_template('ddhs_login.html')






@app.route('/ddhs_dashboard')
def ddhs_dashboard():
    if 'role' not in session or session['role'] != 'ddhs':
        return redirect(url_for('ddhs_login'))

    conn = get_db_connection()

    # 📌 Fetch Overview Metrics
    total_phcs = conn.execute("SELECT COUNT(*) FROM PHC").fetchone()[0]
    total_sub_centers = conn.execute("SELECT COUNT(*) FROM SubCenter").fetchone()[0]
    total_doctors = conn.execute("SELECT COUNT(*) FROM Doctors").fetchone()[0]
    total_patients = conn.execute("SELECT COUNT(*) FROM Patients").fetchone()[0]
    todays_appointments = conn.execute("""
        SELECT COUNT(*) FROM Appointments 
        WHERE date = DATE('now') AND status = 'Pending'
    """).fetchone()[0]
    pending_orders = conn.execute("SELECT COUNT(*) FROM Orders WHERE status = 'Pending'").fetchone()[0]

    # 📌 Fetch Doctor Attendance Logs
    attendance_logs = conn.execute("""
        SELECT d.name AS doctor_name, p.name AS phc_name, s.name AS sub_center_name,
               SUM(CASE WHEN a.status = 'Present' THEN 1 ELSE 0 END) AS present_days,
               COUNT(a.status) AS total_days
        FROM Attendance a
        JOIN Doctors d ON a.doctor_id = d.id
        LEFT JOIN PHC p ON d.phc_id = p.id
        LEFT JOIN SubCenter s ON d.sub_center_id = s.id
        GROUP BY d.id
    """).fetchall()

    # 📌 Fetch Appointments (PHC & SubCenter)
    appointments = conn.execute("""
        SELECT a.id, p.name AS patient_name, d.name AS doctor_name, ph.name AS phc_name, 
               s.name AS sub_center_name, a.date, a.time, a.status, a.reason
        FROM Appointments a
        JOIN Patients p ON a.patient_id = p.id
        JOIN Doctors d ON a.doctor_id = d.id
        LEFT JOIN PHC ph ON p.phc_id = ph.id
        LEFT JOIN SubCenter s ON p.sub_center_id = s.id
        ORDER BY a.date, a.time
    """).fetchall()

    # 📌 Fetch Treatments
    treatments = conn.execute("""
        SELECT t.date, pat.name AS patient_name, doc.name AS doctor_name, 
               t.medicine_name, t.vaccine_name, t.quantity, 
               p.name AS phc_name, s.name AS sub_center_name
        FROM Treatments t
        JOIN Patients pat ON t.patient_id = pat.id
        JOIN Doctors doc ON t.doctor_id = doc.id
        LEFT JOIN PHC p ON pat.phc_id = p.id
        LEFT JOIN SubCenter s ON pat.sub_center_id = s.id
        ORDER BY t.date DESC
    """).fetchall()

    # 📌 Fetch Stock Availability (Medicines & Vaccines for PHCs & SubCenters)
    medicines = conn.execute("""
        SELECT m.name, m.quantity, p.name AS phc_name, s.name AS sub_center_name
        FROM Medicines m
        LEFT JOIN PHC p ON m.phc_id = p.id
        LEFT JOIN SubCenter s ON m.sub_center_id = s.id
    """).fetchall()

    vaccines = conn.execute("""
        SELECT v.name, v.quantity, p.name AS phc_name, s.name AS sub_center_name
        FROM Vaccines v
        LEFT JOIN PHC p ON v.phc_id = p.id
        LEFT JOIN SubCenter s ON v.sub_center_id = s.id
    """).fetchall()

    # 📌 Fetch Stock Orders
    stock_orders = conn.execute("""
        SELECT o.id, ph.name AS phc_name, o.item_name, o.quantity, o.status
        FROM Orders o
        LEFT JOIN PHC ph ON o.phc_id = ph.id
        ORDER BY o.id DESC
    """).fetchall()

    conn.close()

    return render_template(
        'ddhs_dashboard.html',
        total_phcs=total_phcs,
        total_sub_centers=total_sub_centers,
        total_doctors=total_doctors,
        total_patients=total_patients,
        todays_appointments=todays_appointments,
        pending_orders=pending_orders,
        attendance_logs=attendance_logs,
        appointments=appointments,
        treatments=treatments,
        medicines=medicines,
        vaccines=vaccines,
        stock_orders=stock_orders
    )



# Doctor Login Route
@app.route('/doctor_login', methods=['GET', 'POST'])
def doctor_login():
    session.clear()  # Clear session on each login attempt
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        # Query doctor from the Doctors table
        conn = get_db_connection()
        doctor = conn.execute("SELECT * FROM Doctors WHERE username = ?", (username,)).fetchone()
        conn.close()

        # Validate doctor credentials (No Hashing)
        if doctor:
            if doctor['password'] == password:  # Plaintext password check
                session['user_id'] = doctor['id']
                session['username'] = doctor['username']
                session['role'] = 'doctor'
                session['phc_id'] = doctor['phc_id']  # Store PHC ID in session

                return redirect(url_for('doctor_dashboard', doctor_id=doctor['id']))
            else:
                return render_template('doctor_login.html', error="Invalid password")
        else:
            return render_template('doctor_login.html', error="Invalid username")

    return render_template('doctor_login.html')





@app.route('/doctor_dashboard/<int:doctor_id>')
def doctor_dashboard(doctor_id):
    if 'role' not in session or session['role'] != 'doctor':
        return redirect(url_for('doctor_login'))

    conn = get_db_connection()

    # Fetch doctor details
    doctor = conn.execute("SELECT * FROM Doctors WHERE id = ?", (doctor_id,)).fetchone()
    if not doctor:
        conn.close()
        return "Doctor not found", 404  # Handle invalid doctor ID

    # Fetch PHC or Sub-Center details
    phc = conn.execute("SELECT * FROM PHC WHERE id = ?", (doctor['phc_id'],)).fetchone()
    sub_center = conn.execute("SELECT * FROM SubCenter WHERE id = ?", (doctor['sub_center_id'],)).fetchone()

    # Fetch patients assigned to this doctor’s PHC or Sub-Center
    patients = conn.execute("""
        SELECT * FROM Patients
        WHERE phc_id = ? OR sub_center_id = ?
    """, (doctor['phc_id'], doctor['sub_center_id'])).fetchall()

    appointments = conn.execute("""
        SELECT a.id, p.name AS patient_name, a.date, a.time, a.status
        FROM Appointments a
        JOIN Patients p ON a.patient_id = p.id
        WHERE a.doctor_id = ?
        ORDER BY a.date, a.time
    """, (doctor_id,)).fetchall()
    conn.close()

    return render_template(
        'doctor_dashboard.html',
        doctor=doctor,
        phc=phc,
        sub_center=sub_center,
        patients=patients,
        appointments=appointments
    )






@app.route('/patient_login', methods=['GET', 'POST'])
def patient_login():
    session.clear()  # Clear session on each login attempt
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        # Query patient from the Patients table
        conn = get_db_connection()
        patient = conn.execute("SELECT * FROM Patients WHERE username = ?", (username,)).fetchone()
        conn.close()

        # Validate patient credentials (No Hashing)
        if patient:
            if patient['password'] == password:  # Plaintext password check
                session['user_id'] = patient['id']
                session['username'] = patient['username']
                session['role'] = 'patient'

                return redirect(url_for('patient_dashboard', patient_id=patient['id']))
            else:
                return render_template('patient_login.html', error="Invalid password")
        else:
            return render_template('patient_login.html', error="Invalid username")

    return render_template('patient_login.html')


@app.route('/schedule_appointment', methods=['POST'])
def schedule_appointment():
    """ Patients request an appointment with a specific doctor. """
    if 'role' not in session or session['role'] != 'patient':
        return redirect(url_for('patient_login'))

    patient_id = session['user_id']
    doctor_id = request.form['doctor_id']
    date = request.form['date']
    time = request.form['time']
    reason = request.form['reason']

    conn = get_db_connection()
    conn.execute("""
        INSERT INTO Appointments (patient_id, doctor_id, date, time, reason, status)
        VALUES (?, ?, ?, ?, ?, 'Pending')
    """, (patient_id, doctor_id, date, time, reason))
    conn.commit()
    conn.close()

    return redirect(url_for('patient_dashboard', patient_id=patient_id))








@app.route('/patient_dashboard/<int:patient_id>')
def patient_dashboard(patient_id):
    if 'role' not in session or session['role'] != 'patient':
        return redirect(url_for('patient_login'))

    conn = get_db_connection()
    patient = conn.execute("SELECT * FROM Patients WHERE id = ?", (patient_id,)).fetchone()

    # Fetch assigned PHC or Sub-Center
    phc = conn.execute("SELECT * FROM PHC WHERE id = ?", (patient['phc_id'],)).fetchone()
    sub_center = conn.execute("SELECT * FROM SubCenter WHERE id = ?", (patient['sub_center_id'],)).fetchone()

    # Fetch doctors available in the patient's PHC or Sub-Center
    doctors = conn.execute("""
        SELECT * FROM Doctors WHERE phc_id = ? OR sub_center_id = ?
    """, (patient['phc_id'], patient['sub_center_id'])).fetchall()

    # Fetch upcoming appointments for the patient
    appointments = conn.execute("""
        SELECT a.id, d.name AS doctor_name, a.date, a.time, a.status
        FROM Appointments a
        JOIN Doctors d ON a.doctor_id = d.id
        WHERE a.patient_id = ?
        ORDER BY a.date DESC
    """, (patient_id,)).fetchall()

    conn.close()

    return render_template(
        'patient_dashboard.html',
        patient=patient,
        phc=phc,
        sub_center=sub_center,
        doctors=doctors,
        appointments=appointments
    )


    
if __name__ == '__main__':
    app.run(debug=True)