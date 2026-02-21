import json
import re
import os
import glob

# ================= 配置区域 =================
# 输入文件夹路径 (存放分块json的文件夹)
INPUT_FOLDER = './output' 

# 输出文件路径
OUTPUT_FILE = 'translation_map.json'

# 关键词正则，匹配标题中包含汉化意图的词
CN_PATTERN = re.compile(r'(汉化|中文|Chinese|CN|ZH|简体|繁体)', re.IGNORECASE)

# ================= 核心逻辑 =================

def is_valid_translation(item):
    """
    判断一个项目是否为汉化包：
    1. tags 中必须包含 "Translation"
    2. title 中必须包含中文相关关键词
    """
    # 1. 检查 Tags (必须包含 "Translation")
    tags = item.get('tags', [])
    if not isinstance(tags, list):
        return False
    
    # 将所有 tag 转为小写进行比对
    has_translation_tag = any(tag.lower() == 'translation' for tag in tags)
    if not has_translation_tag:
        return False
    # 2. 检查标题 (必须包含中文关键词)
    title = item.get('title', '')
    if not CN_PATTERN.search(title):
        return False
    return True

def process_chunk_items(items, dependency_map):
    """
    处理单个分块文件的数据，并将结果更新到 dependency_map 中
    """
    for item in items:
        title = item.get('title', '')
        
        # 1. 标题筛选：必须包含中文关键词
        if not is_valid_translation(item):
            continue

        # 2. 依赖检查：必须有依赖对象 (children)
        children = item.get('children', [])
        if not children:
            continue
        
        # 提取汉化包的元数据
        trans_info = {
            'id': str(item.get('publishedfileid')), # 统一转为字符串
            'title': title,
            'tags': item.get('tags', []),
            'updated': item.get('time_updated', 0),
            'subs': item.get('subscriptions', 0),
            'score': item.get('vote_data', {}).get('score', 0)
        }

        # 3. 注册到原版 Mod ID 下
        for child in children:
            # 这里的 parent_id 是这个汉化包所依赖的原版 Mod ID
            parent_id = str(child.get('publishedfileid'))
            
            if parent_id not in dependency_map:
                dependency_map[parent_id] = []
            
            # 将汉化信息加入列表 (此处暂不去重，保留所有候选)
            dependency_map[parent_id].append(trans_info)

def main():
    # 结果字典: { '原版ModID': [汉化包Info1, 汉化包Info2, ...] }
    global_map = {}
    
    # 获取所有json文件
    json_files = glob.glob(os.path.join(INPUT_FOLDER, '*.json'))
    
    if not json_files:
        print(f"错误：在 '{INPUT_FOLDER}' 中未找到 JSON 文件。")
        return

    print(f"找到 {len(json_files)} 个文件，开始处理...")

    count = 0
    for file_path in json_files:
        count += 1
        print(f"[{count}/{len(json_files)}] 读取文件: {os.path.basename(file_path)}")
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
                # 确保读取的是列表
                if isinstance(data, list):
                    process_chunk_items(data, global_map)
                else:
                    print(f"警告: 文件 {file_path} 格式不正确(不是列表)，跳过。")
                    
        except Exception as e:
            print(f"读取 {file_path} 时出错: {e}")

    # 统计信息
    original_mod_count = len(global_map)
    translation_mod_count = sum(len(v) for v in global_map.values())
    
    print(f"\n处理完成！")
    print(f"共索引了 {original_mod_count} 个原版Mod的汉化关系。")
    print(f"累计找到 {translation_mod_count} 个候选汉化项。")

    # 写入文件
    print(f"正在写入结果到 {OUTPUT_FILE} ...")
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(global_map, f, ensure_ascii=False, indent=2)
    
    print("完成。")

if __name__ == '__main__':
    # 确保输入目录存在
    if not os.path.exists(INPUT_FOLDER):
        print(f"提示：请创建文件夹 '{INPUT_FOLDER}' 并放入分块json文件，或者修改脚本中的 INPUT_FOLDER 变量。")
    else:
        main()
