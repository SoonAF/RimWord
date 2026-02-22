import json
import re
import os
import glob

# ================= 配置区域 =================
INPUT_FOLDER = './output' 
OUTPUT_FILE = 'translation_map.json'

# 关键词正则：匹配标题中包含汉化意图的词
CN_PATTERN = re.compile(r'(汉|漢|中|Chinese|\bCN\b|\bZH\b|\bTW\b|\bHK\b|\bCH\b|\bTC\b|简|繁|simplified|traditional)', re.IGNORECASE)

# ================= 核心逻辑 =================

def is_translation_mod(title, tags):
    """
    判断是否为汉化包
    条件：Tag包含 'Translation' 且 标题包含中文关键词
    """
    if not tags or not isinstance(tags, list):
        return False
    
    # 1. 检查 Tags
    tag_set = {t.lower() for t in tags}
    if 'translation' not in tag_set:
        return False

    # 2. 检查标题
    if not title or not CN_PATTERN.search(title):
        return False
    
    return True

def process_chunk_items(items, ref_map, relation_map):
    """
    处理分块数据
    ref_map:      存储所有Mod的基础信息 (ID -> {title, updated, tags})
    relation_map: 存储依赖关系 (原版ID -> [汉化包信息列表])
    """
    for item in items:
        # 基础数据提取
        item_id = str(item.get('publishedfileid'))
        title = item.get('title', '')
        updated = item.get('time_updated', 0)
        tags = item.get('tags', [])
        
        # 1. 【核心修改】记录该 Mod 的信息到查找表 (包含 Tags)
        # 无论它是原版还是汉化，先存下来，以便后续反查原版信息
        ref_map[item_id] = {
            'title': title,
            'updated': updated,
            'tags': tags  # 新增：保存原mod的tags
        }
        
        # 2. 汉化包筛选逻辑
        if not is_translation_mod(title, tags):
            continue

        # 3. 依赖检查：必须有依赖对象 (children)
        children = item.get('children', [])
        if not children:
            continue
        
        # 构建汉化包信息对象
        trans_info = {
            'id': item_id,
            'title': title,
            'updated': updated,
            'subs': item.get('subscriptions', 0),
            'score': item.get('vote_data', {}).get('score', 0),
            'tags': tags
        }

        # 4. 注册关系
        for child in children:
            parent_id = str(child.get('publishedfileid'))
            # 使用 setdefault 简化逻辑：如果键不存在则创建空列表，然后 append
            relation_map.setdefault(parent_id, []).append(trans_info)

def main():
    global_ref_map = {}      # ID -> Info
    global_relation_map = {} # ParentID -> [Translation Mods]
    
    json_files = glob.glob(os.path.join(INPUT_FOLDER, '*.json'))
    
    if not json_files:
        print(f"错误：在 '{INPUT_FOLDER}' 中未找到 JSON 文件。")
        return

    print(f"找到 {len(json_files)} 个文件，开始处理...")

    for idx, file_path in enumerate(json_files, 1):
        print(f"[{idx}/{len(json_files)}] 读取: {os.path.basename(file_path)}")
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, list):
                    process_chunk_items(data, global_ref_map, global_relation_map)
        except Exception as e:
            print(f"读取 {file_path} 失败: {e}")

    # ================= 数据合并阶段 =================
    print("\n正在合并原版Mod信息 (Title, Updated, Tags)...")
    
    final_output = {}
    
    # 遍历关系表，反查 ref_map 补全原版信息
    for parent_id, trans_list in global_relation_map.items():
        parent_info = global_ref_map.get(parent_id)
        
        if parent_info:
            final_output[parent_id] = {
                "title": parent_info['title'],
                "updated": parent_info['updated'],
                "tags": parent_info['tags'],  # 新增：输出原版tags
                "translations": trans_list
            }
        else:
            # 原版 Mod ID 存在于依赖关系中，但未在数据集中找到 (可能已删除或未爬取)
            final_output[parent_id] = {
                "title": "Unknown Original Mod",
                "updated": 0,
                "tags": [],
                "translations": trans_list
            }

    # 统计信息
    mod_count = len(final_output)
    translation_count = sum(len(v['translations']) for v in final_output.values())
    
    print(f"处理完成！")
    print(f"原Mod数量: {mod_count}")
    print(f"汉化包数量: {translation_count}")

    # 写入文件
    print(f"正在写入 {OUTPUT_FILE} ...")
    try:
        with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
            json.dump(final_output, f, ensure_ascii=False, indent=2)
        print("完成。")
    except Exception as e:
        print(f"写入文件失败: {e}")

if __name__ == '__main__':
    if not os.path.exists(INPUT_FOLDER):
        print(f"提示：请确保文件夹 '{INPUT_FOLDER}' 存在。")
    else:
        main()
