import json
import os
import re
import sys
import math
import time
from datetime import datetime
import argparse

try:
    from steamworks import STEAMWORKS
except ImportError:
    print("请先安装库: pip install git+https://github.com/philippj/SteamworksPy.git")
    input("回车结束...")
    sys.exit(1)

# ================= 配置区域 =================
GAME_APP_ID = 294100 
JSON_FILE_PATH = './translation_map.json'
# LANGUAGE_PREFERENCE 将通过命令行参数或交互式输入设置
LANGUAGE_PREFERENCE = None

GAME_VERSION_TIERS = {
    "1.6": "2025-07-12",
    "1.5": "2024-04-12",
    "1.4": "2022-10-21",
    "1.3": "2021-07-21",
}
WEIGHT_LOG_SUBS = 90.0

# --- 批量验证配置 ---
MAX_VERIFY_CYCLES = 15
VERIFY_INTERVAL = 3.0

# True = 仅模拟，False = 实际订阅
DRY_RUN = False
# ===========================================

def get_language_preference():
    """获取语言偏好设置"""
    parser = argparse.ArgumentParser(description='RimWorld 汉化自动订阅工具')
    parser.add_argument('--lang', choices=['1', '2'], help='语言选择: 1=简体中文, 2=繁体中文')
    
    args = parser.parse_args()
    
    if args.lang:
        # 通过命令行参数设置
        return 'simplified' if args.lang == '1' else 'traditional'
    else:
        # 交互式输入
        print("请选择语言偏好:")
        print("1. 简体中文")
        print("2. 繁体中文")
        while True:
            choice = input("请输入选择 (1 或 2): ").strip()
            if choice == '1':
                return 'simplified'
            elif choice == '2':
                return 'traditional'
            else:
                print("无效输入，请输入 1 或 2")

def load_translations(filepath):
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"错误: 找不到文件 {filepath}")
        input("回车结束...")
        sys.exit(1)

RE_TRADITIONAL = re.compile(r'(繁|\bTW\b|\bHK\b|\bCHT\b|\bTC\b|traditional)', re.IGNORECASE)
RE_SIMPLIFIED = re.compile(r'(简|簡|\bCN\b|\bCHS\b|\bSC\b|simplified)', re.IGNORECASE)

def detect_language_type(title):
    is_traditional = bool(RE_TRADITIONAL.search(title))
    is_simplified = bool(RE_SIMPLIFIED.search(title))
    if is_traditional and is_simplified: return 'both'
    elif is_traditional: return 'traditional'
    return 'both'

def preprocess_translations(translation_map):
    print("正在预处理所有汉化候选项的简繁类型...")
    count = 0
    for mod_id, data in translation_map.items():
        candidates = data.get("translations", [])
        for cand in candidates:
            cand['lang_type'] = detect_language_type(cand.get('title', ''))
            count += 1
    print(f"预处理完成，已标记 {count} 个候选项。")
    return translation_map

def parse_version_tiers():
    parsed = []
    sorted_items = sorted(GAME_VERSION_TIERS.items(), key=lambda x: x[1])
    for idx, (ver_name, date_str) in enumerate(sorted_items):
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            ts = dt.timestamp()
            parsed.append((ts, ver_name, idx + 1))
        except ValueError:
            pass
    return sorted(parsed, key=lambda x: x[0], reverse=True)

SORTED_VERSION_TIERS = parse_version_tiers()

def get_mod_tier_info(updated_timestamp):
    for ts, ver_name, tier_level in SORTED_VERSION_TIERS:
        if updated_timestamp >= ts: return tier_level, ver_name
    return 0, "Old"

def calculate_sort_score(candidate):
    subs = candidate.get('subs', 0)
    updated = candidate.get('updated', 0)
    tier_level, _ = get_mod_tier_info(updated)
    return (tier_level, (updated / 86400.0) + (math.log10(max(1, subs)) * WEIGHT_LOG_SUBS))

def select_best_translation(candidates):
    if not candidates: return None
    return sorted(candidates, key=calculate_sort_score, reverse=True)[0]

def get_current_subscribed_ids(steam):
    """获取当前所有已订阅的Item ID集合"""
    count = steam.Workshop.GetNumSubscribedItems()
    items = steam.Workshop.GetSubscribedItems(count)
    return set(str(item) for item in items)

def main():
    # 获取语言偏好设置
    global LANGUAGE_PREFERENCE
    LANGUAGE_PREFERENCE = get_language_preference()
    
    print(f"语言偏好已设置为: {'简体中文' if LANGUAGE_PREFERENCE == 'simplified' else '繁体中文'}")
    
    try:
        steam = STEAMWORKS()
        steam.initialize()
    except Exception as e:
        print(f"Steam 初始化失败: {e}")
        return

    if not steam.Apps.IsSubscribedApp(GAME_APP_ID):
        print(f"检测到你并未拥有 AppID: {GAME_APP_ID}")
        return

    print(f"Steam API 连接成功，正在为 AppID {GAME_APP_ID} 处理汉化...")
    
    if DRY_RUN:
        print("=" * 50 + "\n[测试模式] 仅模拟，不执行订阅\n" + "=" * 50)

    raw_map = load_translations(JSON_FILE_PATH)
    translation_map = preprocess_translations(raw_map)
    
    target_types = {'both'} 
    if LANGUAGE_PREFERENCE == 'simplified': target_types.add('simplified')
    elif LANGUAGE_PREFERENCE == 'traditional': target_types.add('traditional')
    
    # 1. 获取初始订阅列表
    print("正在获取初始订阅列表...")
    initial_subscribed_set = get_current_subscribed_ids(steam)
    print(f"当前已订阅 {len(initial_subscribed_set)} 个 Mod。")

    # 2. 筛选出所有需要订阅的目标
    pending_subscriptions = [] # 存储详细信息用于展示
    
    # [新增] 用于去重的集合，防止同一个汉化合集因为对应多个原Mod而被重复添加
    planned_subs_set = set()   

    print("正在筛选最佳汉化...")
    
    for mod_id in list(initial_subscribed_set):
        if mod_id in translation_map:
            mod_data = translation_map[mod_id]
            
            # --- 检查原Mod是否本身就是翻译Mod ---
            original_tags = [t.lower() for t in mod_data.get("tags", [])]
            if "translation" in original_tags:
                continue
            # ----------------------------------

            candidates = mod_data.get("translations", [])
            
            if not candidates: continue

            filtered_candidates = [c for c in candidates if c['lang_type'] in target_types]
            if LANGUAGE_PREFERENCE == 'traditional' and not filtered_candidates:
                filtered_candidates = [c for c in candidates if c['lang_type'] == 'simplified']
            
            best = select_best_translation(filtered_candidates)
            if not best: continue
            
            trans_id = str(best['id'])
            trans_title = best.get('title', 'Unknown')
            
            # 逻辑: 
            # 1. 如果这个汉化ID已经在 Steam 订阅了 -> 跳过
            # 2. 如果这个汉化ID已经在本次计划列表里了 -> 跳过 (去重关键)
            if trans_id in initial_subscribed_set:
                continue
            
            if trans_id in planned_subs_set:
                # 这是一个共用汉化，已经被之前的某个Mod触发了，无需重复添加
                continue

            # 加入待办
            pending_subscriptions.append({
                'id': trans_id,
                'title': trans_title,
                'origin': mod_id
            })
            planned_subs_set.add(trans_id)

    if not pending_subscriptions:
        print("没有发现需要新订阅的汉化。")
        input("回车结束...")
        return

    print(f"\n共发现 {len(pending_subscriptions)} 个缺失的汉化 Mod，准备处理...")

    # ================= DRY RUN =================
    if DRY_RUN:
        for item in pending_subscriptions:
            print(f"[拟订阅] 原Mod {item['origin']} -> {item['title']} (ID: {item['id']})")
        print(f"\n测试结束。请将 DRY_RUN = False 以执行批量订阅。")
        input("回车结束...")
        return

    # ================= 实际执行阶段 =================
    
    # 步骤 A: 第一次全量发送订阅请求
    print("\n>>> 开始批量发送订阅请求...")
    # target_ids 现在直接等于 planned_subs_set，因为我们已经去重过了
    target_ids = planned_subs_set 
    
    for item in pending_subscriptions:
        tid = item['id']
        print(f"发送订阅请求: {tid} ({item['title']})")
        try:
            steam.Workshop.SetItemSubscribedCallback(lambda result: print(f"订阅结果: {result}"))
            steam.Workshop.SubscribeItem(int(tid))
        except Exception as e:
            print(f"  请求发送失败: {e}")
    
    print("\n>>> 请求发送完毕，开始循环验证...")

    # 步骤 B: 循环检测与补漏
    cycle = 0
    all_success = False

    while cycle < MAX_VERIFY_CYCLES:
        print(f"等待 {VERIFY_INTERVAL} 秒以让 Steam 处理...", end="", flush=True)
        time.sleep(VERIFY_INTERVAL)
        print(" 正在刷新订阅列表...")

        current_subs = get_current_subscribed_ids(steam)
        missing_ids = target_ids - current_subs
        
        if not missing_ids:
            print("\n[成功] 所有目标汉化均已检测到订阅生效！")
            all_success = True
            break
        
        cycle += 1
        print(f"[{cycle}/{MAX_VERIFY_CYCLES}] 仍有 {len(missing_ids)} 个项目未生效。正在重试这些项目...")
        
        for tid in missing_ids:
            # 查找标题用于显示
            title = next((x['title'] for x in pending_subscriptions if x['id'] == tid), "Unknown")
            print(f"  -> 重试订阅: {tid} ({title})")
            steam.Workshop.SetItemSubscribedCallback(lambda result: print(f"订阅结果: {result}"))
            steam.Workshop.SubscribeItem(int(tid))
    
    print("-" * 30)
    if all_success:
        print(f"处理完成。成功添加了 {len(target_ids)} 个订阅。")
    else:
        remaining = target_ids - get_current_subscribed_ids(steam)
        print(f"处理结束，但有 {len(remaining)} 个项目似乎未能订阅成功。")
        print(f"失败ID: {remaining}")

    print("请在 Steam 下载页面检查下载队列。")

if __name__ == "__main__":
    main()