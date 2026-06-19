import os
import json
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, send_from_directory
import psycopg2
from psycopg2.extras import RealDictCursor

app = Flask(__name__)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DATABASE_URL = os.environ.get('DATABASE_URL')

def get_db_connection():
    return psycopg2.connect(DATABASE_URL)

# データベースの初期化
def init_db():
    conn = get_db_connection()
    cur = conn.cursor()
    
    # 1. 現行アクティブデータ用のテーブル
    cur.execute('''
        CREATE TABLE IF NOT EXISTS bear_data (
            id SERIAL PRIMARY KEY,
            json_records TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    ''')
    
    # 2. 1万件を超えたときの退避用（アーカイブ）テーブル
    cur.execute('''
        CREATE TABLE IF NOT EXISTS bear_archive (
            id SERIAL PRIMARY KEY,
            archive_name TEXT NOT NULL,
            json_records TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    ''')
    
    # 初回起動時のみ、データがなければ空の配列を入れておく
    cur.execute('SELECT COUNT(*) FROM bear_data;')
    if cur.fetchone()[0] == 0:
        local_json_path = os.path.join(BASE_DIR, 'data.json')
        initial_data = []
        if os.path.exists(local_json_path):
            try:
                with open(local_json_path, 'r', encoding='utf-8') as f:
                    initial_data = json.load(f)
            except Exception:
                pass
        cur.execute('INSERT INTO bear_data (json_records) VALUES (%s);', (json.dumps(initial_data, ensure_ascii=False),))
        
    conn.commit()
    cur.close()
    conn.close()

init_db()

@app.route('/')
def index():
    return send_from_directory(BASE_DIR, 'index.html')

@app.route('/<path:path>')
def send_static(path):
    if path == 'data.json':
        return load_data()
    return send_from_directory(BASE_DIR, path)


# 🌟 1. データの読み込みAPI（ご提示の「目撃日時」を基準に過去5年分のみを厳密にフィルタリング）
@app.route('/api/load', methods=['GET'])
def load_data():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # データベースからすべてのアクティブデータとアーカイブデータを一旦取得
        all_raw_records = []
        
        # ① 現在のアクティブデータを取得
        cur.execute('SELECT json_records FROM bear_data ORDER BY id DESC LIMIT 1;')
        row = cur.fetchone()
        if row:
            all_raw_records.extend(json.loads(row[0]))
            
        # ② 全てのアーカイブデータを取得
        cur.execute('SELECT json_records FROM bear_archive;')
        archives = cur.fetchall()
        for archive in archives:
            all_raw_records.extend(json.loads(archive[0]))
            
        cur.close()
        conn.close()

        # 📅 「目撃日時」を基準にした5年間のフィルタリング処理
        filtered_data = []
        five_years_ago = datetime.now() - timedelta(days=5*365)
        
        for item in all_raw_records:
            # データのゴミ（空の項目）はスキップ
            if not item or "目撃日時" not in item:
                continue
                
            try:
                # フォーマット「2026/3/31 14:00」または「2026/03/31 14:00」の日付文字列を解析
                # 時間部分が含まれない場合なども考慮し、柔軟にパースします
                date_str = item["目撃日時"].split(" ")[0] # "2026/3/31" を取得
                item_date = datetime.strptime(date_str, '%Y/%m/%d')
                
                # 5年以内であればリストに残す
                if item_date >= five_years_ago:
                    filtered_data.append(item)
            except Exception:
                # 万が一、日付の形式が崩れていてパースできないデータは、安全のため一応残す設定にします
                filtered_data.append(item)
                
        return jsonify(filtered_data)
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# 🌟 2. データの保存API（1万件に達したら自動で「作成日」を付けた新しいアーカイブを作成して書き込み）
@app.route('/api/save', methods=['POST'])
def save_data():
    try:
        new_data = request.get_json()
        if not isinstance(new_data, list):
            return jsonify({"success": False, "message": "無効なデータ形式です"}), 400

        conn = get_db_connection()
        cur = conn.cursor()
        
        # 🚨 【重要】データが1万件に達していたら自動で新しいアーカイブに切り替え
        if len(new_data) >= 10000:
            # 現在の日時（作成日）を取得してアーカイブ名にする (例: archive_20260619_095200)
            now = datetime.now()
            timestamp_str = now.strftime('%Y%m%d_%H%M%S')
            archive_name = f"archive_{timestamp_str}"
            
            # 1万件に達したこれまでのデータをアーカイブテーブルに新しく作成して書き込み
            cur.execute(
                'INSERT INTO bear_archive (archive_name, json_records, created_at) VALUES (%s, %s, %s);',
                (archive_name, json.dumps(new_data, ensure_ascii=False), now)
            )
            
            # アーカイブへ書き込んだので、メインの書き込み先（現行データ）は空 `[]` にリセット
            new_data = []
            print(f"[ARCHIVE CREATED] 1万件に達したため、新たに '{archive_name}' を作成しデータを退避しました。")

        # 現行の最新データを更新（常に1レコードに最新の配列を維持）
        cur.execute('DELETE FROM bear_data;')
        cur.execute('INSERT INTO bear_data (json_records, updated_at) VALUES (%s, %s);', 
                    (json.dumps(new_data, ensure_ascii=False), datetime.now()))
        
        conn.commit()
        cur.close()
        conn.close()
            
        return jsonify({"success": True, "message": "データを更新しました（1万件・フォーマット自動チェック済）"})
        
    except Exception as e:
        return jsonify({"success": False, "message": f"エラー: {str(e)}"}), 500

if __name__ == '__main__':
    app.run(port=5000, debug=True)
