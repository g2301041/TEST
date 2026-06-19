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

# 🌟 データベースの初期化（通常用とアーカイブ用の2つのテーブルを作成）
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
            archive_name TEXT NOT NULL,  # 例: "archive_20260619_10000"
            json_records TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    ''')
    
    # 初回起動時のみ、データがなければ空の配列を入れておく
    cur.execute('SELECT COUNT(*) FROM bear_data;')
    if cur.fetchone()[0] == 0:
        # もしGitHubにdata.jsonがあればそれを初期値にする
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
    # フロントエンドが旧仕様のまま「data.json」をGETしにきても、自動で/api/loadと同じ5年分データを返す
    if path == 'data.json':
        return load_data()
    return send_from_directory(BASE_DIR, path)


# 🌟 1. データの読み込みAPI（過去5年分のみを自動抽出して結合）
@app.route('/api/load', methods=['GET'])
def load_data():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # 5年前の境界線を計算
        five_years_ago = datetime.now() - timedelta(days=5*365)
        
        all_combined_data = []
        
        # ① 現在のアクティブデータを取得
        cur.execute('SELECT json_records FROM bear_data ORDER BY id DESC LIMIT 1;')
        row = cur.fetchone()
        if row:
            all_combined_data.extend(json.loads(row[0]))
            
        # ② アーカイブテーブルから過去5年以内に作成されたデータを全て取得
        cur.execute('SELECT json_records FROM bear_archive WHERE created_at >= %s;', (five_years_ago,))
        archives = cur.fetchall()
        for archive in archives:
            all_combined_data.extend(json.loads(archive[0]))
            
        # 💡 フロントエンドにデータを渡す前に、念のため各データ内の日付（もしあれば）で5年分に絞り込むことも可能です。
        # 今回は簡易的に、5年以内に作成された「アーカイブファイル丸ごと」を結合して返します。
        
        cur.close()
        conn.close()
        return jsonify(all_combined_data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# 🌟 2. データの保存API（1万件に達したら自動で作成日付きで別データ化）
@app.route('/api/save', methods=['POST'])
def save_data():
    try:
        new_data = request.get_json()
        if not isinstance(new_data, list):
            return jsonify({"success": False, "message": "無効なデータ形式です"}), 400

        conn = get_db_connection()
        cur = conn.cursor()
        
        # 🚨 【重要】もしデータが1万件に達していたらアーカイブ化する
        if len(new_data) >= 10000:
            # 現在の日時でアーカイブ名を作成 (例: archive_20260619_123000)
            timestamp_str = datetime.now().strftime('%Y%m%d_%H%m%S')
            archive_name = f"archive_{timestamp_str}"
            
            # 1万件のデータをアーカイブテーブルへ退避
            cur.execute(
                'INSERT INTO bear_archive (archive_name, json_records, created_at) VALUES (%s, %s, %s);',
                (archive_name, json.dumps(new_data, ensure_ascii=False), datetime.now())
            )
            
            # 現行テーブル側は、空の配列 `[]` にリセットして新しくスタートさせる
            new_data = []
            print(f"[ARCHIVE] 1万件に達したため '{archive_name}' として退避し、メインをリセットしました。")

        # データを更新（常に最新状態を1件保持）
        cur.execute('DELETE FROM bear_data;')
        cur.execute('INSERT INTO bear_data (json_records, updated_at) VALUES (%s, %s);', 
                    (json.dumps(new_data, ensure_ascii=False), datetime.now()))
        
        conn.commit()
        cur.close()
        conn.close()
            
        return jsonify({"success": True, "message": "データを更新しました（1万件チェック実施済）"})
        
    except Exception as e:
        return jsonify({"success": False, "message": f"エラー: {str(e)}"}), 500

if __name__ == '__main__':
    app.run(port=5000, debug=True)
