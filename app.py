from flask import Flask, render_template, request, jsonify
import sqlite3, json, os
from datetime import datetime

app = Flask(__name__)
DB = os.environ.get('DATABASE_URL', 'calculations.db')

def get_db():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    return con

def init_db():
    with get_db() as con:
        con.execute('''CREATE TABLE IF NOT EXISTS calculations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            created_at TEXT NOT NULL,
            data TEXT NOT NULL
        )''')

init_db()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/calculate', methods=['POST'])
def calculate():
    d = request.get_json(force=True) or {}

    def f(x):
        try:
            return float(x or 0)
        except (ValueError, TypeError):
            return 0.0

    # Материалы
    materials = d.get('materials', [])
    materials_cost = sum(f(m.get('cost')) * f(m.get('qty')) for m in materials)
    per_material = [
        {'name': m.get('name') or 'Без названия', 'cost': round(f(m.get('cost')) * f(m.get('qty')), 2), 'link': m.get('link', '')}
        for m in materials
    ]

    # Электроэнергия
    elec_kwh = f(d.get('elec_kwh'))
    elec_price = f(d.get('elec_price'))

    # Оборудование
    equipment = d.get('equipment', [])
    equipment_energy_kwh = 0.0
    equipment_energy_cost = 0.0
    depreciation = 0.0
    equipment_rows = []

    for e in equipment:
        h, pwr, price, life = f(e.get('hours')), f(e.get('power')), f(e.get('price')), f(e.get('lifetime'))
        kwh = h * pwr
        e_cost = kwh * elec_price
        amort = (h / life * price) if (life > 0 and price > 0 and h > 0) else 0.0
        equipment_energy_kwh += kwh
        equipment_energy_cost += e_cost
        depreciation += amort
        equipment_rows.append({'name': e.get('name') or 'Оборудование', 'hours': h, 'kwh': round(kwh, 3), 'energy_cost': round(e_cost, 2), 'amortization': round(amort, 2)})

    total_energy_kwh = elec_kwh + equipment_energy_kwh
    electricity = total_energy_kwh * elec_price

    # Работники
    workers = d.get('workers', [])
    labor = 0.0
    worker_rows = []
    for w in workers:
        h, r = f(w.get('hours')), f(w.get('rate'))
        cost = h * r
        labor += cost
        worker_rows.append({'name': w.get('name') or 'Работник', 'hours': h, 'rate': r, 'cost': round(cost, 2)})

    overhead = f(d.get('overhead'))

    # Партия и брак
    defect = f(d.get('defect')) / 100.0
    batch = int(f(d.get('batch')) or 1)
    defect = max(0, min(defect, 0.99))
    batch = max(1, batch)

    total_batch = (materials_cost + electricity + labor + overhead + depreciation)
    per_unit = total_batch / batch
    per_good_unit = per_unit / (1 - defect) if defect > 0 else per_unit
    total_with_defect = total_batch / (1 - defect) if defect > 0 else total_batch
    defect_cost = total_with_defect - total_batch

    return jsonify({
        'materials_cost': round(materials_cost, 2),
        'electricity': round(electricity, 2),
        'equipment_energy': round(equipment_energy_cost, 2),
        'depreciation': round(depreciation, 2),
        'labor': round(labor, 2),
        'overhead': round(overhead, 2),
        'total_batch': round(total_batch, 2),
        'per_unit': round(per_unit, 2),
        'per_good_unit': round(per_good_unit, 2),
        'total_with_defect': round(total_with_defect, 2),
        'defect_cost': round(defect_cost, 2),
        'batch': batch,
        'total_energy_kwh': round(total_energy_kwh, 3),
        'per_material': per_material,
        'equipment_rows': equipment_rows,
        'worker_rows': worker_rows,
    })

@app.route('/api/save', methods=['POST'])
def save():
    d = request.get_json(force=True) or {}
    name = (d.get('name') or '').strip() or f"Расчёт {datetime.now().strftime('%d.%m.%Y %H:%M')}"
    data = json.dumps(d.get('data', {}), ensure_ascii=False)
    with get_db() as con:
        cur = con.execute('INSERT INTO calculations (name, created_at, data) VALUES (?,?,?)', (name, datetime.now().strftime('%d.%m.%Y %H:%M:%S'), data))
        new_id = cur.lastrowid
    return jsonify({'id': new_id, 'name': name})

@app.route('/api/list')
def list_calcs():
    with get_db() as con:
        rows = con.execute('SELECT id, name, created_at FROM calculations ORDER BY id DESC').fetchall()
    return jsonify([dict(r) for r in rows])

@app.route('/api/load/<int:cid>')
def load(cid):
    with get_db() as con:
        row = con.execute('SELECT * FROM calculations WHERE id=?', (cid,)).fetchone()
    if not row:
        return jsonify({'error': 'not found'}), 404
    return jsonify({'id': row['id'], 'name': row['name'], 'created_at': row['created_at'], 'data': json.loads(row['data'])})

@app.route('/api/delete/<int:cid>', methods=['DELETE'])
def delete(cid):
    with get_db() as con:
        con.execute('DELETE FROM calculations WHERE id=?', (cid,))
    return jsonify({'ok': True})

if __name__ == '__main__':
    app.run(debug=True)
