from flask import Flask, render_template, request, redirect, url_for, session, flash, send_file, get_flashed_messages
import sqlite3
from datetime import datetime
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase.pdfmetrics import stringWidth
from io import BytesIO




app = Flask(__name__)
app.secret_key = 'your-secret-key'  # จำเป็นหากใช้ session
 
def get_db_connection():
    conn = sqlite3.connect('users.db')
    conn.row_factory = sqlite3.Row
    return conn

def get_air_db_connection():
    conn = sqlite3.connect('air_system.db')
    conn.row_factory = sqlite3.Row
    return conn


# --- ฟังก์ชันบันทึกข้อมูลดิบลง chiller_data ---
def insert_data_to_db(form_data):
    try:
        conn = sqlite3.connect("kmp_energy_2025_fixed.db")
        cursor = conn.cursor()

        # ชื่อฟิลด์ที่ต้องการ (ตรงกับชื่อในฟอร์ม HTML)
        expected_fields = [
            "date", "chiller_id", "status", "chws_setpoint", "cw_outlet",
            "compressors_run", "chiller_demand", "total_amp", "system_demand",
            "compressors_on", "cond_split", "cond_pressure", "cond_saturated_temp",
            "cond_approach", "chwr", "chws", "evap_pressure_avg", "evap_saturated_temp",
            "evap_approach", "evap_flow", "evap_pressure_drop", "ct_inlet_temp",
            "ct_outlet_temp", "input_electrical", "actual_tr"
        ]

        # ดึงค่าตามลำดับ
        values = [form_data.get(field, None) for field in expected_fields]

        # ตรวจสอบจำนวนค่าที่จะใส่
        if len(values) != 25:
            return False, f"จำนวนค่าที่จะใส่ไม่ถูกต้อง: {len(values)} (คาดว่า 25)"

        cursor.execute("""
            INSERT INTO chiller_data (
                date, chiller_id, status, chws_setpoint, cw_outlet,
                compressors_run, chiller_demand, total_amp, system_demand,
                compressors_on, cond_split, cond_pressure, cond_saturated_temp,
                cond_approach, chwr, chws, evap_pressure_avg, evap_saturated_temp,
                evap_approach, evap_flow, evap_pressure_drop, ct_inlet_temp,
                ct_outlet_temp, input_electrical, actual_tr
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, values)

        conn.commit()
        conn.close()
        return True, "✅ บันทึกข้อมูลเรียบร้อยแล้ว"

    except Exception as e:
        return False, f"❌ เกิดข้อผิดพลาดในการบันทึก: {e}"





# --- คำแนะนำเมื่อค่าผิดปกติ ---
suggestion_map = {
    "Evap Pressure": "↪ ตรวจสอบแรงดันน้ำใน evaporator หรือความผิดปกติของระบบน้ำเย็น",
    "Evap Saturated Temp": "↪ ตรวจสอบค่าความเย็นที่จุดอิ่มตัวของสารทำความเย็น",
    "Evap Approach": "↪ ตรวจสอบประสิทธิภาพการแลกเปลี่ยนความร้อนใน evaporator",
    "Evap Flow": "↪ ตรวจสอบอัตราการไหลของน้ำเย็น และการทำงานของปั๊ม",
    "Evap Pressure Drop": "↪ ตรวจสอบความต้านทานในท่อหรือการอุดตัน",
    "Cond Split": "↪ ตรวจสอบความต่างอุณหภูมิระหว่างสารทำความเย็นกับน้ำหล่อเย็น",
    "Cond Pressure": "↪ ตรวจสอบแรงดันฝั่งคอนเดนเซอร์ และอุณหภูมิแวดล้อม",
    "Cond Saturated Temp": "↪ ตรวจสอบประสิทธิภาพการระบายความร้อน",
    "Cond Approach": "↪ ตรวจสอบการแลกเปลี่ยนความร้อนที่คอนเดนเซอร์",
    "Compressors Run": "↪ ตรวจสอบจำนวนคอมเพรสเซอร์ที่ทำงานสัมพันธ์กับโหลด",
    "Total Amp": "↪ ตรวจสอบกระแสรวมว่าอยู่ในช่วงปกติหรือไม่",
    "CT Inlet Temp": "↪ ตรวจสอบอุณหภูมิน้ำร้อนที่เข้าหอหล่อเย็น",
    "CT Outlet Temp": "↪ ตรวจสอบประสิทธิภาพ Cooling Tower เช่น พัดลม, สภาพน้ำ, หัวฉีด"
    
}

# --- ฟังก์ชันวิเคราะห์ข้อมูลจากแถวล่าสุด ---
def analyze_data(row):
    result_lines = []

    if not row:
        return ["❌ ไม่มีข้อมูลล่าสุดในฐานข้อมูล"]

    result_lines.append(f"📅 วันที่: {row[1]}")
    result_lines.append(f"🆔 Chiller ID: {row[2]}")
    result_lines.append(f"⚙️ สถานะ: {row[3]}")
    result_lines.append("")  # เว้นบรรทัด

    def check_range(label, val, unit, min_val=None, max_val=None, max_only=None):
        result_lines.append(f"{label}: {val:.2f} {unit}")
        if max_only is not None:
            result_lines.append(f"   เกณฑ์: ไม่เกิน {max_only} {unit}")
            if val > max_only:
                result_lines.append("   ❌ ผิดปกติ")
                if label in suggestion_map:
                    result_lines.append(f"   ❗ คำแนะนำ: {suggestion_map[label]}")
            else:
                result_lines.append("   ✅ ปกติ")
        else:
            result_lines.append(f"   เกณฑ์: {min_val} – {max_val} {unit}")
            if (min_val is not None and val < min_val) or (max_val is not None and val > max_val):
                result_lines.append("   ❌ ผิดปกติ")
                if label in suggestion_map:
                    result_lines.append(f"   ❗ คำแนะนำ: {suggestion_map[label]}")
            else:
                result_lines.append("   ✅ ปกติ")
        result_lines.append("")

    # กลุ่มวิเคราะห์: Evaporator
    result_lines.append("💧 Evaporator:")
    check_range("Evap Pressure", float(row[17]), "kPa", 200, 500)
    check_range("Evap Saturated Temp", float(row[18]), "°C", 2, 6)
    check_range("Evap Approach", float(row[19]), "°C", 0.5, 2.5)
    check_range("Evap Flow", float(row[20]), "L/s", 60, 100)
    check_range("Evap Pressure Drop", float(row[21]), "kPa", 10, 35)

    # กลุ่มวิเคราะห์: Condenser
    result_lines.append("🌡️ Condenser:")
    check_range("Cond Split", float(row[11]), "°C", 1.5, 4.0)
    check_range("Cond Pressure", float(row[12]), "kPa", 600, 1500)
    check_range("Cond Saturated Temp", float(row[13]), "°C", None, None, 40.0)
    check_range("Cond Approach", float(row[14]), "°C", 1.0, 3.0)

    # กลุ่มวิเคราะห์: Compressor
    result_lines.append("⚙️ Compressor:")
    check_range("Compressors Run", float(row[6]), "ชุด", 1, 4)

    # กลุ่มวิเคราะห์: ไฟฟ้า
    result_lines.append("🔌 ไฟฟ้า:")
    check_range("Total Amp", float(row[8]), "A", None, None, 300)

    # กลุ่มวิเคราะห์: Cooling Tower
    result_lines.append("💧 Cooling Tower:")
    check_range("CT Inlet Temp", float(row[22]), "°C", None, None, 35.0)
    check_range("CT Outlet Temp", float(row[23]), "°C", 30.4, 31)

    # COP และ kW/ton
    try:
        compressors_run = int(row[6])
        input_kw = float(row[24])
        actual_tr = float(row[25])
        ct_inlet_temp = float(row[22])
        ct_outlet_temp = float(row[23])



        if actual_tr > 0 and input_kw > 0:
            load_kw = actual_tr * 3.517
            cop = load_kw / input_kw
            kw_per_ton = input_kw / actual_tr


            result_lines.append("📊 ประสิทธิภาพ:")
            result_lines.append(f"⚡️ COP (Coefficient of Performance): {cop:.2f}")
            result_lines.append("   เกณฑ์: มากกว่า 3.0")

            if cop >= 3.0:
                result_lines.append("   ✅ ประสิทธิภาพดี")
            else:
                result_lines.append("   ❌ ประสิทธิภาพต่ำ")
                result_lines.append("   ❗ คำแนะนำ: ตรวจสอบโหลดของระบบหรือประสิทธิภาพการทำงานของคอมเพรสเซอร์")
            result_lines.append("")

            result_lines.append(f"⚙️ kW/ton: {kw_per_ton:.2f}")
            result_lines.append("   เกณฑ์: น้อยกว่า 1.0")
            if kw_per_ton < 1.0:
                result_lines.append("   ✅ ประสิทธิภาพดี")
            else:
                result_lines.append("   ❌ ใช้พลังงานมากเกินไป")
                result_lines.append("   ❗ คำแนะนำ: ตรวจสอบระบบโหลดเย็นและการทำงานของ Cooling Tower")
            result_lines.append("")

         # 🔍 วิเคราะห์ Cooling Tower
            ct_delta_t = ct_inlet_temp - ct_outlet_temp
            result_lines.append("🌡️ วิเคราะห์ Cooling Tower:")
            result_lines.append(f"🔁 ΔT (Inlet - Outlet): {ct_delta_t:.2f} °C")
            if ct_delta_t >= 4.0:
                result_lines.append("   ✅ Cooling Tower ระบายความร้อนได้ดี (∆T > 4°C)")
            elif ct_delta_t >= 2.0:
                result_lines.append("   ⚠️ ระบายความร้อนได้ปานกลาง (∆T = 2-4°C)")
                result_lines.append("   ❗ อาจมีคราบตะกรัน หรือปริมาณลมน้อยลง ตรวจสอบพัดลมหรือหัวฉีดน้ำ")
            else:
                result_lines.append("   ❌ ระบายความร้อนไม่ดี (∆T < 2°C)")
                result_lines.append("   ❗ ตรวจสอบการทำงานของพัดลม, ปั๊มน้ำ, หรือความสะอาดของฟิน/หัวฉีด")
            result_lines.append("")


    except Exception as e:
        result_lines.append(f"❌ เกิดข้อผิดพลาดในการคำนวณ COP/kW/ton หรือ Cooling Tower: {e}")


    result_lines.append("📌 สรุปผล: วิเคราะห์เสร็จสิ้น")
    return result_lines

# --- ฟังก์ชันบันทึกผลวิเคราะห์ลง analysis_result ---
def save_analysis_to_db(analysis_text):
    """
    แปลงจาก save_analysis_result() เวอร์ชัน GUI
    ให้รับ input เป็นข้อความวิเคราะห์แบบ multi‐line (analysis_text)
    แล้วบันทึกเข้า SQLite ในตาราง analysis_result
    """
    try:
        # 1) ตรวจเงื่อนไขเบื้องต้น
        if not analysis_text.strip() or "📅 วันที่" not in analysis_text or "📌 สรุปผล" not in analysis_text:
            return False, "❌ ยังไม่มีผลวิเคราะห์ หรือรูปแบบไม่ครบถ้วน"

        lines = analysis_text.splitlines()

        # 2) ดึงข้อมูลทั่วไป: date, chiller_id, status
        date = ""
        chiller = ""
        status = ""
        for line in lines:
            if line.startswith("📅 วันที่"):
                parts = line.split(":", 1)
                if len(parts) > 1:
                    date = parts[1].strip()
            elif line.startswith("🆔 Chiller ID"):
                parts = line.split(":", 1)
                if len(parts) > 1:
                    chiller = parts[1].strip()
            elif line.startswith("⚙️ สถานะ"):
                parts = line.split(":", 1)
                if len(parts) > 1:
                    status = parts[1].strip()

        cop_value = None
        kw_per_ton = None
        cop_comment = ""
        suggestions = []

        for line in lines:
            # หา COP: ตัวอย่าง "⚡️ COP (Coefficient of Performance): 3.65"
            if line.startswith("⚡️ COP") and ":" in line:
                try:
                    cop_value = float(line.split(":")[1].strip())
                    cop_comment = line.strip()
                except:
                    cop_value = None
            # หา kW/ton: ตัวอย่าง "⚙️ kW/ton: 0.95"
            if line.startswith("⚙️ kW/ton") and ":" in line:
                try:
                    kw_per_ton = float(line.split(":")[1].strip())
                except:
                    kw_per_ton = None
            # เก็บคำแนะนำ (ขึ้นต้นด้วย "❗" หรือ "↪")
            if line.strip().startswith("❗") or line.strip().startswith("↪"):
                suggestions.append(line.strip())

        # 3) เปิดเชื่อมต่อ SQLite แล้วดึง row ล่าสุดจาก chiller_data
        conn = sqlite3.connect("kmp_energy_2025_fixed.db")
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM chiller_data ORDER BY id DESC LIMIT 1")
        row = cursor.fetchone()
        if not row:
            conn.close()
            return False, "❌ ไม่พบข้อมูลล่าสุดในฐานข้อมูล chiller_data"

        # 4) ดึงค่าพารามิเตอร์จาก row ตาม index เดิม
        evap_pressure          = row[17]
        evap_saturated_temp     = row[18]
        evap_approach           = row[19]
        evap_flow               = row[20]
        evap_pressure_drop      = row[21]
        cond_split              = row[11]
        cond_pressure           = row[12]
        cond_saturated_temp     = row[13]
        cond_approach           = row[14]
        compressors_run         = row[6]
        total_amp               = row[8]
        ct_inlet_temp           = row[22]
        ct_outlet_temp          = row[23]
        input_electrical        = row[24]

        summary = "วิเคราะห์เสร็จสิ้น"
        status_flag = "normal" if ("✅" in analysis_text and "❌" not in analysis_text) else "warning"
        suggestions_str = "\n".join(suggestions)

        # 5) INSERT ลงตาราง analysis_result
        cursor.execute("""
            INSERT INTO analysis_result (
                date, chiller_id, status,
                evap_pressure, evap_saturated_temp, evap_approach, evap_flow, evap_pressure_drop,
                cond_split, cond_pressure, cond_saturated_temp, cond_approach,
                compressors_run, total_amp,
                ct_inlet_temp, ct_outlet_temp,
                input_electrical, cop,
                summary, suggestions, status_flag,
                result_comment, kw_per_ton
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            date, chiller, status,
            evap_pressure, evap_saturated_temp, evap_approach, evap_flow, evap_pressure_drop,
            cond_split, cond_pressure, cond_saturated_temp, cond_approach,
            compressors_run, total_amp,
            ct_inlet_temp, ct_outlet_temp,
            input_electrical, cop_value,
            summary, suggestions_str, status_flag,
            cop_comment, kw_per_ton
        ))
        conn.commit()
        conn.close()
        return True, "✅ บันทึกผลการวิเคราะห์เรียบร้อยแล้ว"
    except Exception as e:
        return False, f"❌ เกิดข้อผิดพลาดในการบันทึกผล: {e}"

# --- ROUTES ---

@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        conn = get_db_connection()
        user = conn.execute(
            'SELECT * FROM users WHERE username = ? AND password = ?', 
            (username, password)
        ).fetchone()
        conn.close()
        if user:
            session['username'] = user['username']
            session['role'] = user['role']
            session['login_time'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            return redirect(url_for('dashboard'))
        else:
            flash('ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง', 'warning')
    return render_template('login.html')

@app.route('/dashboard')
def dashboard():
    if 'username' not in session:
        return redirect(url_for('login'))
    return render_template('dashboard.html', username=session['username'], role=session['role'])

@app.route('/data-entry', methods=['GET', 'POST'])
def data_entry():
    analysis = []

    if request.method == 'POST':
        action = request.form.get("action", "")

        if action == "save_data":
            form_data = request.form.to_dict()
            required_fields = [
                "date", "chiller_id", "status", "chws_setpoint", "cw_outlet",
                "compressors_run", "chiller_demand", "total_amp", "system_demand",
                "compressors_on", "cond_split", "cond_pressure", "cond_saturated_temp",
                "cond_approach", "chwr", "chws", "evap_pressure_avg", "evap_saturated_temp",
                "evap_approach", "evap_flow", "evap_pressure_drop", "ct_inlet_temp",
                "ct_outlet_temp", "input_electrical","actual_tr"
            ]
            missing = [field for field in required_fields if not form_data.get(field, "").strip()]
            if missing:
                flash("กรุณากรอกข้อมูลให้ครบ: " + ", ".join(missing), "warning")
            else:
                success, message = insert_data_to_db(form_data)
                flash(message, "success" if success else "danger")
                if success:
                    try:
                        conn = sqlite3.connect("kmp_energy_2025_fixed.db")
                        cursor = conn.cursor()
                        cursor.execute("SELECT * FROM chiller_data ORDER BY id DESC LIMIT 1")
                        row = cursor.fetchone()
                        conn.close()
                        if row:
                            analysis = analyze_data(row)
                            session['analysis_text'] = "\n".join(analysis)
                    except Exception as e:
                        analysis = [f"❌ ไม่สามารถวิเคราะห์ข้อมูลได้: {e}"]

        elif action == "analyze":
            try:
                conn = sqlite3.connect("kmp_energy_2025_fixed.db")
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM chiller_data ORDER BY id DESC LIMIT 1")
                row = cursor.fetchone()
                conn.close()
                if row:
                    analysis = analyze_data(row)
                    session['analysis_text'] = "\n".join(analysis)
                else:
                    analysis = ["❌ ไม่มีข้อมูลในฐานข้อมูลให้วิเคราะห์"]
                    session['analysis_text'] = "\n".join(analysis)
            except Exception as e:
                analysis = [f"❌ ไม่สามารถวิเคราะห์ข้อมูลได้: {e}"]
                session['analysis_text'] = "\n".join(analysis)

    else:
        try:
            conn = sqlite3.connect("kmp_energy_2025_fixed.db")
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM chiller_data ORDER BY id DESC LIMIT 1")
            row = cursor.fetchone()
            conn.close()
            if row:
                analysis = analyze_data(row)
                session['analysis_text'] = "\n".join(analysis)
        except Exception as e:
            analysis = [f"❌ ไม่สามารถวิเคราะห์ข้อมูลได้: {e}"]
            session['analysis_text'] = "\n".join(analysis)

    analysis_text = session.get('analysis_text', '')
    return render_template('data-entry.html', analysis=analysis_text)


@app.route('/save-analysis', methods=['POST'])
def save_analysis():
    # บันทึกผลวิเคราะห์ที่ส่งมาจาก textarea ชื่อ "analysis"
    analysis_text = request.form.get("analysis", "").strip()
    success, message = save_analysis_to_db(analysis_text)
    flash(message, "success" if success else "warning")
    
    # ✅ เคลียร์ค่าใน session เพื่อให้กล่องวิเคราะห์ว่าง
    session['analysis_text'] = ""
    
    return redirect(url_for('data_entry'))




@app.route('/export-pdf')
def export_pdf():
    buffer = BytesIO()
    p = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    # Register Thai font
    pdfmetrics.registerFont(TTFont('Sarabun', 'fonts/Sarabun-Regular.ttf'))

    analysis_text = session.get('analysis_text', 'ไม่มีข้อมูลผลการวิเคราะห์')

    p.setFont("Sarabun", 16)
    p.drawString(50, height - 50, "📊 ผลการวิเคราะห์ระบบทำความเย็น")

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    p.setFont("Sarabun", 10)
    p.drawRightString(width - 50, height - 50, f"พิมพ์เมื่อ: {now}")

    p.setFont("Sarabun", 12)
    y = height - 100
    for line in analysis_text.splitlines():
        if y < 50:
            p.showPage()
            p.setFont("Sarabun", 12)
            y = height - 50
        p.drawString(50, y, line)
        y -= 18

    p.save()
    buffer.seek(0)
    return send_file(buffer, as_attachment=True, download_name="ผลการวิเคราะห์.pdf", mimetype='application/pdf')





# เริ่มระบบ air compressor======================================================================================================

@app.route('/air-system', methods=['GET', 'POST'])
def air_system():
    analysis = []

    if request.method == 'POST':
        form = request.form.to_dict()
        action = form.get("action")

        if action == "save":
            success, msg = save_air_data_from_form(form)
            flash(msg, "success" if success else "danger")

        elif action == "analyze":
            analysis = analyze_air_system_by_unit()

        else:
            flash("⚠️ ไม่พบ action", "warning")

    return render_template("air_system.html", analysis=analysis)


def save_air_data(form):
    try:
        conn = get_air_db_connection()
        cur = conn.cursor()

        # บันทึก compressor_data
        cur.execute("""
            INSERT INTO compressor_data (date, compressor_name, outlet_pressure, outlet_temp)
            VALUES (?, ?, ?, ?)
        """, (
            form.get("date"),
            form.get("compressor_name"),
            float(form.get("outlet_pressure")),
            float(form.get("outlet_temp"))
        ))

        # บันทึก dryer_data
        cur.execute("""
            INSERT INTO dryer_data (date, dew_point, dryer_delta_t)
            VALUES (?, ?, ?)
        """, (
            form.get("date"),
            float(form.get("dew_point")),
            float(form.get("dryer_delta_t"))
        ))

        conn.commit()
        conn.close()
        return True, "✅ บันทึกข้อมูล Air System สำเร็จ"
    except Exception as e:
        return False, f"❌ เกิดข้อผิดพลาด: {e}"
def analyze_air_system(form):
    result = []
    try:
        pressure = float(form.get("outlet_pressure"))
        temp = float(form.get("outlet_temp"))
        dew_point = float(form.get("dew_point"))
        delta_t = float(form.get("dryer_delta_t"))

        result.append("📋 วิเคราะห์ระบบอัดอากาศ:")
        result.append(f"🔹 แรงดันขาออก: {pressure:.1f} bar")
        if pressure < 6 or pressure > 8:
            result.append("   ❌ ผิดปกติ: แรงดันควรอยู่ในช่วง 6–8 bar")
        else:
            result.append("   ✅ ปกติ")

        result.append(f"🌡️ อุณหภูมิลมขาออก: {temp:.1f} °C")
        if temp > 45:
            result.append("   ❌ สูงเกินไป: ตรวจสอบระบบระบายความร้อน")
        else:
            result.append("   ✅ ปกติ")

        result.append(f"💧 Dew Point: {dew_point:.1f} °C")
        if dew_point > 10:
            result.append("   ❌ ความชื้นสูงเกินไป: ตรวจสอบ Air Dryer")
        else:
            result.append("   ✅ ปกติ")

        result.append(f"ΔT เครื่อง Dryer: {delta_t:.1f} °C")
        if delta_t < 5:
            result.append("   ⚠️ อาจมีปัญหาการถ่ายเทความร้อน")
        else:
            result.append("   ✅ ปกติ")

        result.append("📌 สรุป: วิเคราะห์ระบบอากาศอัดเสร็จสิ้น")
        return result
    except Exception as e:
        return [f"❌ วิเคราะห์ล้มเหลว: {e}"]

def save_air_data_from_form(form):
    try:
        conn = get_air_db_connection()
        cur = conn.cursor()

        date = form.get("date")

        # 1. บันทึก compressor_data (C1–C3)
        for i in range(1, 4):
            unit = f"C{i}"
            values = [
                form.get(f"comp_{i}_status"),
                float(form.get(f"comp_{i}_energy") or 0),
                float(form.get(f"comp_{i}_run_hour") or 0),
                float(form.get(f"comp_{i}_load_hour") or 0),
                float(form.get(f"comp_{i}_pressure") or 0),
                float(form.get(f"comp_{i}_temperature") or 0)
            ]
            cur.execute("""
                INSERT INTO compressor_data (date, unit, status, energy_kwh, run_hour, load_hour, pressure, temperature)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (date, unit, *values))

        # 2. บันทึก air dryer data
        for i in range(1, 4):
            unit = f"AD{i}"
            values = [
                form.get(f"dryer_{i}_status"),
                float(form.get(f"dryer_{i}_dew_point") or 0),
                float(form.get(f"dryer_{i}_pressure") or 0),
                form.get(f"dryer_{i}_alarm")
            ]
            cur.execute("""
                INSERT INTO airdryer_data (date, unit, status, dew_point, pressure, alarm)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (date, unit, *values))

        # 3. summary_data
        cur.execute("""
            INSERT INTO summary_data (date, total_airflow, avg_pressure, total_energy, note)
            VALUES (?, ?, ?, ?, ?)
        """, (
            date,
            float(form.get("total_airflow") or 0),
            float(form.get("avg_pressure") or 0),
            float(form.get("total_energy") or 0),
            form.get("note")
        ))

        conn.commit()
        conn.close()
        return True, "✅ บันทึกข้อมูลเรียบร้อย"
    except Exception as e:
        return False, f"❌ เกิดข้อผิดพลาด: {e}"
def analyze_air_system_by_unit():
    try:
        conn = get_air_db_connection()
        cur = conn.cursor()

        cur.execute("SELECT date FROM summary_data ORDER BY date DESC LIMIT 1")
        row = cur.fetchone()
        if not row:
            return ["❌ ไม่พบข้อมูลใน summary_data"]
        date = row[0]

        report = [f"🔍 วิเคราะห์รายเครื่อง - วันที่ {date}", "-"*40]

        # วิเคราะห์ Compressor C1–C3
        cur.execute("SELECT unit, energy_kwh, run_hour, load_hour, pressure, temperature FROM compressor_data WHERE date = ? ORDER BY unit", (date,))
        compressors = cur.fetchall()
        for c in compressors:
            unit, energy, run_hr, load_hr, pressure, temp = c
            report.append(f"🧊 Compressor {unit}:")

            if energy < 100 or energy > 250:
                report.append(f"⚡ พลังงาน: {energy:.1f} kWh ❌ ผิดปกติ (ควร 100–250)")
                report.append("💡 แนะนำ: ตรวจสอบโหลด, ความถี่เปิด-ปิด, หรือโหลดสูงผิดปกติ")
            else:
                report.append(f"⚡ พลังงาน: {energy:.1f} kWh ✅")

            if pressure < 6.0 or pressure > 8.0:
                report.append(f"📈 ความดัน: {pressure:.1f} bar ❌ ผิดปกติ (ควร 6–8)")
                report.append("💡 แนะนำ: ตรวจสอบการรั่ว, โหลดมาก, หรือระบบมีปัญหา Pressure Switch")
            else:
                report.append(f"📈 ความดัน: {pressure:.1f} bar ✅")

            if temp > 45:
                report.append(f"🌡️ อุณหภูมิ: {temp:.1f} °C ❌ สูงเกินไป")
                report.append("💡 แนะนำ: ตรวจสอบระบบระบายความร้อน, พัดลม, น้ำหล่อเย็น, หรือคราบตะกรัน")
            else:
                report.append(f"🌡️ อุณหภูมิ: {temp:.1f} °C ✅")

            if run_hr > 0 and load_hr / run_hr < 0.5:
                report.append(f"⏱️ Load ชั่วโมง ({load_hr:.1f}) น้อยกว่า 50% ของ Run ({run_hr:.1f}) ❗")
                report.append("💡 แนะนำ: Compressor ทำงาน Idle นาน อาจต้องพิจารณา Load Matching หรือเปิดปิดไม่เหมาะสม")
            else:
                report.append(f"⏱️ Run: {run_hr:.1f} hr / Load: {load_hr:.1f} hr ✅")

            report.append("")

        # วิเคราะห์ Air Dryer AD1–AD3
        cur.execute("SELECT unit, dew_point, pressure, alarm FROM airdryer_data WHERE date = ? ORDER BY unit", (date,))
        dryers = cur.fetchall()
        for d in dryers:
            unit, dew_point, pressure, alarm = d
            report.append(f"💨 Air Dryer {unit}:")

            if dew_point > 10:
                report.append(f"🌡️ Dew Point: {dew_point:.1f} °C ❌ สูงเกินไป")
                report.append("💡 แนะนำ: ตรวจสอบระบบทำความเย็นของ Dryer, สารทำความเย็น, หรือ bypass ทำงานผิดพลาด")
            else:
                report.append(f"🌡️ Dew Point: {dew_point:.1f} °C ✅")

            if pressure < 6.0 or pressure > 8.0:
                report.append(f"📈 ความดัน: {pressure:.1f} bar ❌ ผิดปกติ")
                report.append("💡 แนะนำ: ตรวจสอบค่าควบคุม Dryer, bypass valve, หรือ blockage ภายใน dryer")
            else:
                report.append(f"📈 ความดัน: {pressure:.1f} bar ✅")

            if alarm and alarm.strip().lower() in ["on", "true", "1"]:
                report.append(f"🚨 Alarm: ON ❌ พบการแจ้งเตือน")
                report.append("💡 แนะนำ: ตรวจสอบรหัสแจ้งเตือนที่หน้าจอ Dryer หรือ reset เครื่อง")
            else:
                report.append(f"🚨 Alarm: OFF ✅")

            report.append("")

        conn.close()
        report.append("📌 สรุป: วิเคราะห์รายเครื่องเสร็จสิ้น")
        return report

    except Exception as e:
        return [f"❌ วิเคราะห์ล้มเหลว: {e}"]
    
@app.route('/save-air-analysis', methods=['POST'])
def save_air_analysis():
    analysis_text = request.form.get("analysis_text", "")
    if not analysis_text.strip():
        flash("⚠️ ไม่มีข้อความผลวิเคราะห์", "warning")
        return redirect(url_for('air_system'))

    try:
        conn = get_air_db_connection()
        conn.execute("""
            INSERT INTO analysis_result (date, category, item, status, suggestion, severity, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            datetime.now().strftime("%Y-%m-%d"),
            "air_system",
            "summary",  # หรือใช้ "ALL" หรือ "-" ถ้าเป็นทั้งระบบ
            "N/A",
            analysis_text,
            "info",
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ))
        conn.commit()
        conn.close()
        flash("✅ บันทึกผลวิเคราะห์เรียบร้อย", "success")
    except Exception as e:
        flash(f"❌ บันทึกล้มเหลว: {e}", "danger")

    return redirect(url_for('air_system'))

@app.route('/export_air_analysis_pdf', methods=['POST'])
def export_air_analysis_pdf():
    analysis_text = request.form.get("analysis_text", "")

    # โหลดฟอนต์ Sarabun ที่รองรับภาษาไทย + อีโมจิ (หากได้)
    pdfmetrics.registerFont(TTFont('Sarabun', 'fonts/Sarabun-Regular.ttf'))

    buffer = BytesIO()
    p = canvas.Canvas(buffer, pagesize=A4)
    p.setFont("Sarabun", 12)

    # เตรียมตำแหน่งเริ่มต้น
    x_margin = 50
    y = 800
    line_height = 20
    max_width = A4[0] - 2 * x_margin  # ความกว้างหน้ากระดาษ - margin

    # วาดข้อความบรรทัดต่อบรรทัด เหมือน <pre>
    for line in analysis_text.split('\n'):
        # ตัดข้อความถ้าเกินความกว้างหน้ากระดาษ
        while stringWidth(line, "Sarabun", 12) > max_width:
            # หาจุดตัดใกล้ max_width
            split_index = len(line)
            while stringWidth(line[:split_index], "Sarabun", 12) > max_width and split_index > 0:
                split_index -= 1
            p.drawString(x_margin, y, line[:split_index])
            line = line[split_index:]
            y -= line_height
            if y < 50:
                p.showPage()
                p.setFont("Sarabun", 12)
                y = 800
        p.drawString(x_margin, y, line)
        y -= line_height

        if y < 50:
            p.showPage()
            p.setFont("Sarabun", 12)
            y = 800

    p.save()
    buffer.seek(0)
    return send_file(buffer, as_attachment=True, download_name='air_analysis_report.pdf', mimetype='application/pdf')

#==============================================================================================================================



# 🔧 กำหนดจุดควบคุมไฟ Zone A1-A16
# ชั้น 1: โซน A1-A13
LIGHTS_FLOOR1 = {
    f"zone_a{i}": {
        "name": f"โซน A{i}",
        "on_url": f"http://192.168.4.30/SetDyNet.cgi?A={i}&C=1&L=100",
        "off_url": f"http://192.168.4.30/SetDyNet.cgi?A={i}&C=1&L=0"
    }
    for i in range(1, 14)
}

# ชั้น 2: โซน B1-B16 (Address เริ่มจาก 101 ขึ้นไปหรือใช้ตามจริงที่ต้องการ)
LIGHTS_FLOOR2 = {
    f"zone_b{i}": {
        "name": f"โซน B{i}",
        "on_url": f"http://192.168.4.30/SetDyNet.cgi?A={i+100}&C=1&L=100",  # เปลี่ยน A เป็นเบอร์ Controller ที่แตกต่าง
        "off_url": f"http://192.168.4.30/SetDyNet.cgi?A={i+100}&C=1&L=0"
    }
    for i in range(1, 17)
}

# รวมทั้งหมดไว้ใน 1 Dictionary
ALL_LIGHTS = {**LIGHTS_FLOOR1, **LIGHTS_FLOOR2}


@app.route('/light-control')
def light_control():
    light_statuses = session.get('light_status', {lid: 'off' for lid in ALL_LIGHTS})

    lights_floor1 = [
        {
            "id": lid,
            "name": data["name"],
            "status": light_statuses.get(lid, 'off')
        }
        for lid, data in LIGHTS_FLOOR1.items()
    ]

    lights_floor2 = [
        {
            "id": lid,
            "name": data["name"],
            "status": light_statuses.get(lid, 'off')
        }
        for lid, data in LIGHTS_FLOOR2.items()
    ]

    return render_template('light_control.html', lights_floor1=lights_floor1, lights_floor2=lights_floor2)


@app.route('/toggle-light', methods=['POST'])
def toggle_light():
    light_id = request.form.get("id")
    status = request.form.get("status")

    if light_id in ALL_LIGHTS and status in ["on", "off"]:
        url = ALL_LIGHTS[light_id][f"{status}_url"]
        try:
            requests.get(url, timeout=2)
        except:
            pass

        light_statuses = session.get('light_status', {})
        light_statuses[light_id] = status
        session['light_status'] = light_statuses

    return redirect(url_for('light_control'))






#========================================================================================================================

@app.route('/user-management', methods=['GET', 'POST'])
def user_management():
    if 'username' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))

    conn = get_db_connection()

    if request.method == 'POST':
        if 'add_user' in request.form:
            new_user = request.form['new_username']
            new_pass = request.form['new_password']
            new_role = request.form['new_role']
            try:
                conn.execute(
                    'INSERT INTO users (username, password, role) VALUES (?, ?, ?)',
                    (new_user, new_pass, new_role)
                )
                conn.commit()
                flash(f'เพิ่มผู้ใช้ {new_user} สำเร็จ')
            except sqlite3.IntegrityError:
                flash('ชื่อผู้ใช้นี้มีอยู่แล้ว')
        elif 'change_password' in request.form:
            target_user = request.form['target_username']
            new_password = request.form['new_password']
            conn.execute(
                'UPDATE users SET password=? WHERE username=?',
                (new_password, target_user)
            )
            conn.commit()
            flash(f'เปลี่ยนรหัสผ่าน {target_user} แล้ว')
        elif 'delete_user' in request.form:
            user_to_delete = request.form['target_username']
            if user_to_delete == session['username']:
                flash('ไม่สามารถลบผู้ใช้ที่กำลังเข้าสู่ระบบอยู่ได้')
            else:
                conn.execute(
                    'DELETE FROM users WHERE username=?',
                    (user_to_delete,)
                )
                conn.commit()
                flash(f'ลบผู้ใช้ {user_to_delete} แล้ว')

    users = conn.execute('SELECT username, role FROM users').fetchall()
    conn.close()
    return render_template('user_management.html', users=users)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True)




