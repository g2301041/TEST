function logDebug(msg) {
  const consoleEl = document.getElementById('debug-console');
  if (consoleEl) {
    consoleEl.innerHTML += `[${new Date().toLocaleTimeString()}] ${msg}\n`;
    consoleEl.scrollTop = consoleEl.scrollHeight;
  }
}

function updateDebugJsonView() {
  const jsonViewEl = document.getElementById('debug-json-view');
  if (jsonViewEl) {
    const previewData = CSV_DATA.slice(0, 3);
    let txt = JSON.stringify(previewData, null, 2);
    if (CSV_DATA.length > 3) txt += `\n... ほか計 ${CSV_DATA.length - 3} 件`;
    jsonViewEl.textContent = txt;
  }
}

function initDebugEvents() {
  const panel = document.getElementById('debug-panel');
  const toggle = document.getElementById('debug-toggle');
  if (!panel || !toggle) return;

  toggle.onclick = () => {
    panel.classList.toggle('expanded');
    document.getElementById('debug-arrow').textContent = panel.classList.contains('expanded') ? '▼' : '▲';
  };

  document.getElementById('db-mock-bear').onclick = () => {
    if (!map) return;
    const center = map.getCenter();
    const mock = {
      "出没情報ID": String(nextId++), "情報種別": "目撃", "市町村": "秋田市",
      "地番情報": "秋田県秋田市(テストデータ)", "目撃日時": "2026-06-05 09:00",
      "獣種": "ツキノワグマ", "目撃時の状況": "【デバッグ自動生成】システムテスト用のデータです。",
      "x(緯度)": String(center.lat + (Math.random() - 0.5) * 0.01), "y(経度)": String(center.lng + (Math.random() - 0.5) * 0.01)
    };
    CSV_DATA.unshift(mock);
    logDebug(`擬似データ追加 ID: ${mock.出没情報ID}`);
    saveToServer(); // サーバーへ同期保存
    setupYearSelect(); render(); updateDebugJsonView();
  };

  document.getElementById('db-refresh').onclick = () => { render(); updateDebugJsonView(); logDebug("画面を再描画しました"); };

  document.getElementById('db-clear').onclick = () => {
    if (confirm("メモリ内のデータを全消去しサーバーを空にしますか？")) {
      CSV_DATA = []; nextId = 1;
      saveToServer(); // 空になった状態を保存
      setupYearSelect(); render(); updateDebugJsonView();
      logDebug("データをすべて消去しました。");
    }
  };
}