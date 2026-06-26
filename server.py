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

# 1. データベースの初期化（余計なリセット処理はすべて排除）
def init_db():
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute('''
        CREATE TABLE IF NOT EXISTS bear_data (
            id SERIAL PRIMARY KEY,
            json_records TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    ''')
    
    cur.execute('''
        CREATE TABLE IF NOT EXISTS bear_archive (
            id SERIAL PRIMARY KEY,
            archive_name TEXT NOT NULL,
            json_records TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    ''')
    
    conn.commit()
    cur.close()
    conn.close()
    print("[INIT] データベースのテーブル確認が完了しました。")

init_db()

@app.route('/')
def index():
    return send_from_directory(BASE_DIR, 'index.html')

@app.route('/<path:path>')
def send_static(path):
    if path == 'data.json':
        return load_data()
    return send_from_directory(BASE_DIR, path)


# 2. データの読み込みAPI（過去5年分の目撃日時を正確に判定して合体）
@app.route('/api/load', methods=['GET'])
def load_data():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        all_raw_records = []
        
        # ① 通常テーブルからデータを取得
        cur.execute('SELECT json_records FROM bear_data ORDER BY id DESC;')
        rows = cur.fetchall()
        for row in rows:
            all_raw_records.extend(json.loads(row[0]))
            
        # ② アーカイブテーブルからデータを取得
        cur.execute('SELECT json_records FROM bear_archive;')
        archives = cur.fetchall()
        for archive in archives:
            all_raw_records.extend(json.loads(archive[0]))
            
        cur.close()
        conn.close()

        # 📅 「目撃日時」を基準にした5年間のフィルタリング
        filtered_data = []
        five_years_ago = datetime.now() - timedelta(days=5*365)
        
        for item in all_raw_records:
            if not item or "目撃日時" not in item:
                continue
            try:
                date_str = item["目撃日時"].split(" ")[0]
                item_date = datetime.strptime(date_str, '%Y/%m/%d')
                if item_date >= five_years_ago:
                    filtered_data.append(item)
            except Exception:
                filtered_data.append(item) # 解析エラーのデータは安全のため残す
                
        return jsonify(filtered_data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# 3. 🌟 【修正版】データの保存API（エラーを起こさず確実に新規保存）
@app.route('/api/save', methods=['POST'])
def save_data():
    try:
        new_data = request.get_json()
        if not isinstance(new_data, list):
            return jsonify({"success": False, "message": "無効なデータ形式です"}), 400

        conn = get_db_connection()
        cur = conn.cursor()
        
        # 🚨 1万件に達していたら自動で新アーカイブを作成
        if len(new_data) >= 10000:
            now = datetime.now()
            timestamp_str = now.strftime('%Y%m%d_%H%M%S')
            archive_name = f"archive_{timestamp_str}"
            
            cur.execute(
                'INSERT INTO bear_archive (archive_name, json_records, created_at) VALUES (%s, %s, %s);',
                (archive_name, json.dumps(new_data, ensure_ascii=False), now)
            )
            new_data = [] # メインをリセット

        # 💥 競合を避けるため、通常テーブルをクリアして最新配列を1件だけきれいに保存
        cur.execute('TRUNCATE TABLE bear_data;')
        cur.execute('INSERT INTO bear_data (json_records, updated_at) VALUES (%s, %s);', 
                    (json.dumps(new_data, ensure_ascii=False), datetime.now()))
        
        conn.commit()
        cur.close()
        conn.close()
            
        return jsonify({"success": True, "message": "投稿データをデータベースに正常に保存しました！"})
    except Exception as e:
        return jsonify({"success": False, "message": f"保存エラー: {str(e)}"}), 500


# 4. 【最新版】分割インポート用コマンド
@app.route('/api/force-import', methods=['GET'])
def force_import():
    try:
        page = int(request.args.get('page', 1))
        chunk_size = 3000
        
        local_json_path = os.path.join(BASE_DIR, 'data.json')
        if not os.path.exists(local_json_path):
            return jsonify({"status": "error", "message": "data.jsonが見つかりません"}), 404
            
        with open(local_json_path, 'r', encoding='utf-8') as f:
            raw_data = json.load(f)
            
        total_count = len(raw_data)
        chunks = [raw_data[i:i + chunk_size] for i in range(0, len(raw_data), chunk_size)]
        total_pages = len(chunks)
        
        if page < 1 or page > total_pages:
            return jsonify({"status": "error", "message": "無効なページ番号です"}), 400
            
        current_chunk = chunks[page - 1]
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        # 最初だけ完全リセット
        if page == 1:
            cur.execute('TRUNCATE TABLE bear_data CASCADE;')
            cur.execute('TRUNCATE TABLE bear_archive CASCADE;')
            
        if page < total_pages:
            archive_name = f"archive_init_part{page}"
            cur.execute(
                'INSERT INTO bear_archive (archive_name, json_records) VALUES (%s, %s);',
                (archive_name, json.dumps(current_chunk, ensure_ascii=False))
            )
        else:
            cur.execute('INSERT INTO bear_data (json_records) VALUES (%s);', (json.dumps(current_chunk, ensure_ascii=False),))
            
        conn.commit()
        cur.close()
        conn.close()
        
        return jsonify({
            "status": "success", 
            "message": f"【ステップ {page} / {total_pages}】データ移行成功！",
            "next_url": f"/api/force-import?page={page + 1}" if page < total_pages else "全データのインポートが完了しました！"
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == '__main__':
    app.run(port=5000, debug=True)
