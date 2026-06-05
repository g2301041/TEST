import os
import json
from flask import Flask, request, jsonify, send_from_directory

app = Flask(__name__)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 1. トップページ（http://127.0.0.1:5000/）で index.html を返す
@app.route('/')
def index():
    return send_from_directory(BASE_DIR, 'index.html')

# 2. CSS, JS, data.json などの静的ファイルをブラウザに返す
@app.route('/<path:path>')
def send_static(path):
    return send_from_directory(BASE_DIR, path)

# 3. 新規投稿を受け取って data.json を自動で上書き保存するAPI
@app.route('/api/save', methods=['POST'])
def save_data():
    try:
        new_data = request.get_json()
        if not isinstance(new_data, list):
            return jsonify({"success": False, "message": "無効なデータ形式です"}), 400

        file_path = os.path.join(BASE_DIR, 'data.json')
        
        # 日本語が文字化けしないように ensure_ascii=False で保存
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(new_data, f, indent=2, ensure_ascii=False)
            
        print(f"[SUCCESS] data.json を更新しました。総件数: {len(new_data)}件")
        return jsonify({"success": True, "message": "サーバーのデータを更新しました"})
        
    except Exception as e:
        print(f"[ERROR] 保存失敗: {str(e)}")
        return jsonify({"success": False, "message": str(e)}), 500

if __name__ == '__main__':
    print("\n" + "="*50)
    print(" 🐻 ベアウェザー Python サーバーが起動しました")
    print(" http://127.0.0.1:5000/ にブラウザでアクセスしてください")
    print("="*50 + "\n")
    app.run(port=5000, debug=True)