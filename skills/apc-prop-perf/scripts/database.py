import sqlite3
import pandas as pd
import os
import json
from pathlib import Path

class APCDatabase:
    def __init__(self, db_path='data/apc_prop.db'):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Initialize the SQLite database schema."""
        os.makedirs(os.path.dirname(self.db_path) or '.', exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS propellers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    diameter REAL NOT NULL,
                    pitch REAL NOT NULL,
                    filename TEXT,
                    version TEXT,
                    sim_date TEXT,
                    UNIQUE(diameter, pitch)
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS performance_data (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    prop_id INTEGER NOT NULL,
                    rpm INTEGER NOT NULL,
                    v REAL NOT NULL,
                    j REAL,
                    pe REAL,
                    ct REAL,
                    cp REAL,
                    pwr_hp REAL,
                    torque_lbft REAL,
                    thrust_lbf REAL,
                    pwr_w REAL,
                    torque_nm REAL,
                    thrust_n REAL,
                    thr_pwr REAL,
                    mach REAL,
                    reyn REAL,
                    fom REAL,
                    FOREIGN KEY(prop_id) REFERENCES propellers(id) ON DELETE CASCADE
                )
            ''')
            conn.commit()

    def save_propeller(self, meta, df):
        """Saves a propeller and its performance data to the database (upsert)."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT OR IGNORE INTO propellers (diameter, pitch, filename, version, sim_date)
                VALUES (?, ?, ?, ?, ?)
            ''', (meta['diameter'], meta['pitch'], meta['filename'],
                  meta.get('version'), meta.get('sim_date')))
            
            cursor.execute('SELECT id FROM propellers WHERE diameter=? AND pitch=?', 
                           (meta['diameter'], meta['pitch']))
            prop_id = cursor.fetchone()[0]

            cursor.execute('DELETE FROM performance_data WHERE prop_id=?', (prop_id,))

            data_rows = df.values.tolist()
            cursor.executemany('''
                INSERT INTO performance_data (
                    prop_id, rpm, v, j, pe, ct, cp, pwr_hp, torque_lbft, thrust_lbf, 
                    pwr_w, torque_nm, thrust_n, thr_pwr, mach, reyn, fom
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', [(prop_id, *row) for row in data_rows])
            
            conn.commit()
            return prop_id

    def get_propeller_data(self, diameter, pitch):
        """Retrieves performance data for a specific propeller."""
        with sqlite3.connect(self.db_path) as conn:
            query = '''
                SELECT rpm, v, j, pe, ct, cp, pwr_hp, torque_lbft, thrust_lbf, 
                       pwr_w, torque_nm, thrust_n, thr_pwr, mach, reyn, fom
                FROM performance_data
                WHERE prop_id = (SELECT id FROM propellers WHERE diameter=? AND pitch=?)
                ORDER BY rpm, v
            '''
            df = pd.read_sql_query(query, conn, params=(diameter, pitch))
            return df

    def get_propeller_info(self, diameter, pitch):
        """Retrieves propeller metadata."""
        with sqlite3.connect(self.db_path) as conn:
            query = '''
                SELECT id, diameter, pitch, filename, version, sim_date
                FROM propellers WHERE diameter=? AND pitch=?
            '''
            row = pd.read_sql_query(query, conn, params=(diameter, pitch)).iloc[0]
            return row.to_dict()

    def get_all_props(self):
        """Lists all propellers currently in the database."""
        with sqlite3.connect(self.db_path) as conn:
            return pd.read_sql_query('SELECT id, diameter, pitch, filename, version, sim_date FROM propellers', conn)

    def get_stats(self):
        """Returns database statistics."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT COUNT(*) FROM propellers')
            prop_count = cursor.fetchone()[0]
            cursor.execute('SELECT COUNT(*) FROM performance_data')
            data_count = cursor.fetchone()[0]
            cursor.execute('SELECT MIN(diameter), MAX(diameter), MIN(pitch), MAX(pitch) FROM propellers')
            min_d, max_d, min_p, max_p = cursor.fetchone()
            cursor.execute('SELECT MIN(rpm), MAX(rpm), MIN(v), MAX(v) FROM performance_data')
            min_rpm, max_rpm, min_v, max_v = cursor.fetchone()
            
            return {
                'propellers': prop_count,
                'data_points': data_count,
                'diameter_range': (min_d, max_d),
                'pitch_range': (min_p, max_p),
                'rpm_range': (min_rpm, max_rpm),
                'velocity_range': (min_v, max_v),
            }

    def to_json(self):
        """Export entire database to JSON."""
        stats = self.get_stats()
        props = self.get_all_props()
        result = {'stats': stats, 'props': []}
        
        for _, row in props.iterrows():
            df = self.get_propeller_data(row['diameter'], row['pitch'])
            prop_info = row.to_dict()
            prop_info['data'] = json.loads(df.to_json(orient='records'))
            result['props'].append(prop_info)
        
        return json.dumps(result, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    db = APCDatabase('data/test_apc.db')
    from parser import parse_apc_file
    meta, df = parse_apc_file('assets/sample.dat')
    pid = db.save_propeller(meta, df)
    print(f"Saved prop ID: {pid}")
    print(f"Stats: {db.get_stats()}")
    print(f"Info: {db.get_propeller_info(10.5, 4.5)}")
