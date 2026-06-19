import os
import json
from flask import Flask, request, jsonify, send_from_directory
import psycopg2
from psycopg2.extras import RealDictCursor

app = Flask(__name__)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 🌟 RenderのデータベースURLを取得 (ローカルテスト用のデフォルト値も設定)
DATABASE_URL = os.environ.get('DATABASE_URL', 'postgres://localhost/beardb')

def get_db_connection():
    # データベースに接続する関数
    return psycopg2.connect(DATABASE_URL)

# 🌟 サーバー起動時に、テーブル（データの保管箱）がなければ自動で作成する
def init_db():
    conn = get_db_connection()
    cur = conn.cursor()
    # bear_data というテーブルを作り、JSONデータを丸ごと保存できる「json_records」列を用意します
    cur.execute('''
        CREATE TABLE IF NOT EXISTS bear_data (
            id SERIAL PRIMARY KEY,
            json_records TEXT NOT NULL
        );
    ''')
    # もしテーブルが空なら、初期データとして空の配列（[]）を入れておく
    cur.execute('SELECT COUNT(*) FROM bear_data;')
    if cur.fetchone()[0] == 0:
        cur.execute('INSERT INTO bear_data (json_records) VALUES (%s);', (json.dumps([]),))
    conn.commit()
    cur.close()
    conn.close()

# データベース初期化を実行
init_db()

@app.route('/')
def index():
    return send_from_directory(BASE_DIR, 'index.html')

@app.route('/<path:path>')
def send_static(path):
    # もしフロントエンドが直接「data.json」を通信(GET)で取りに来た場合は、DBの中身をjsonとして返す
    if path == 'data.json':
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute('SELECT json_records FROM bear_data ORDER BY id DESC LIMIT 1;')
            row = cur.fetchone()
            cur.close()
            conn.close()
            if row:
                return jsonify(json.loads(row[0]))
            return jsonify([])
        except Exception as e:
            return jsonify({"error": str(e)}), 500
            
    return send_from_directory(BASE_DIR, path)

# 🌟 フロントエンドからの「保存リクエスト」をDBに書き込む
@app.route('/api/save', methods=['POST'])
def save_data():
    try:
        new_data = request.get_json()
        if not isinstance(new_data, list):
            return jsonify({"success": False, "message": "無効なデータ形式です"}), 400

        # 最新のJSON配列を文字列に変換して、データベースに上書き（追加保存）する
        conn = get_db_connection()
        cur = conn.cursor()
        # 常に最新の1件だけ参照するため、古いデータを消して新しく挿入します
        cur.execute('DELETE FROM bear_data;')
        cur.execute('INSERT INTO bear_data (json_records) VALUES (%s);', (json.dumps(new_data, ensure_ascii=False),))
        conn.commit()
        cur.close()
        conn.close()
            
        print(f"[SUCCESS] データベースを更新しました。総件数: {len(new_data)}件")
        return jsonify({"success": True, "message": "データベースのデータを更新しました"})
        
    except Exception as e:
        print(f"[ERROR] DB保存失敗: {str(e)}")
        return jsonify({"success": False, "message": f"DBエラー: {str(e)}"}), 500

if __name__ == '__main__':
    app.run(port=5000, debug=True)
