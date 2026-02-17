import json
import os
import glob


def main() -> None:
    root = os.path.dirname(os.path.abspath(__file__))
    backend_file = os.path.join(root, "backend", "data", "crawled_knowledge_base.json")
    data_dir = os.path.join(root, "data")

    # 读取已有 KB（如果为空或不是合法 JSON，就当作空列表）
    kb = []
    if os.path.exists(backend_file) and os.path.getsize(backend_file) > 0:
        with open(backend_file, "r", encoding="utf-8") as f:
            try:
                kb = json.load(f)
            except Exception:
                kb = []

    if not isinstance(kb, list):
        kb = []

    existing_keys = set()
    for d in kb:
        if isinstance(d, dict):
            key = (d.get("source_url"), d.get("title"))
            existing_keys.add(key)

    # 合并 data 目录下所有 JSON 列表文件
    pattern = os.path.join(data_dir, "*.json")
    for path in glob.glob(pattern):
        fname = os.path.basename(path)
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            print(f"[skip] {fname}: {e}")
            continue

        if not isinstance(data, list):
            print(f"[skip] {fname}: root is not list")
            continue

        added = 0
        for item in data:
            if not isinstance(item, dict):
                continue
            key = (item.get("source_url"), item.get("title"))
            if key in existing_keys:
                continue
            kb.append(item)
            existing_keys.add(key)
            added += 1
        print(f"[merge] {fname}: +{added}")

    os.makedirs(os.path.dirname(backend_file), exist_ok=True)
    with open(backend_file, "w", encoding="utf-8") as f:
        json.dump(kb, f, ensure_ascii=False, indent=2)

    print(f"[done] total documents: {len(kb)} -> {backend_file}")


if __name__ == "__main__":
    main()

