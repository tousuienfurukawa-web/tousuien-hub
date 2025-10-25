# --- ADD START: return list/index of reports when ?list=true is passed ---
if params.get('list', ['false'])[0].lower() == 'true':
    try:
        idx_path = os.path.join('data', 'reports', 'index.json')
        # 1) 既存の index.json を優先して返す
        if os.path.exists(idx_path):
            with open(idx_path, 'r', encoding='utf-8') as f:
                content = json.load(f)
        else:
            # 2) 存在しない場合は data/reports 以下を走査してインデックスを作成
            base = os.path.join('data', 'reports')
            index = {}
            if os.path.exists(base):
                for root, dirs, files in os.walk(base):
                    for fname in files:
                        if not fname.lower().endswith('.json'):
                            continue
                        full = os.path.join(root, fname)
                        # 相対パスは base 配下におけるパス（例: ILJ/ilj-2025-h1-sales.json）
                        rel = os.path.relpath(full, base).replace("\\", "/")
                        try:
                            mtime = os.path.getmtime(full)
                            index[rel] = {
                                "path": rel,
                                "modified_at": datetime.utcfromtimestamp(mtime).isoformat() + "Z"
                            }
                        except Exception:
                            index[rel] = {"path": rel, "modified_at": None}
            content = {
                "generated_at": datetime.utcnow().isoformat() + "Z",
                "reports": index
            }
            # 3) できれば index.json として保存（次回以降の高速化）
            try:
                os.makedirs(os.path.dirname(idx_path), exist_ok=True)
                with open(idx_path, 'w', encoding='utf-8') as f:
                    json.dump(content, f, ensure_ascii=False, indent=2)
            except Exception:
                # 書き込み失敗してもレスポンスは返す（ログは残せるなら残してください）
                pass

        # 4) レスポンスを返却
        self.send_response(200)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(content, ensure_ascii=False, indent=2).encode('utf-8'))
        return
    except Exception as e:
        import traceback
        self.send_response(500)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.end_headers()
        error_response = {
            "error": "Failed to build or return reports index",
            "detail": str(e),
            "traceback": traceback.format_exc()
        }
        self.wfile.write(json.dumps(error_response, ensure_ascii=False).encode('utf-8'))
        return
# --- ADD END ---
