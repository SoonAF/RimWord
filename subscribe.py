import json
import os
import sys
from operator import itemgetter

try:
    from steamworks import STEAMWORKS
except ImportError:
    print("请先安装库: pip install git+https://github.com/philippj/SteamworksPy.git")
    input("回车结束...")
    sys.exit(1)

# ================= 配置区域 =================
# 替换为你的游戏 App ID (例如 RimWorld 是 294100)
GAME_APP_ID = 294100 

# 本地 JSON 文件路径
JSON_FILE_PATH = './translation_map.json'
# ===========================================

def load_translations(filepath):
    """加载汉化对照表"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"错误: 找不到文件 {filepath}")
        input("回车结束...")
        sys.exit(1)

def select_best_translation(candidates):
    """
    从多个汉化候选中选择最好的一个。
    策略优先级: 
    1. 订阅数 (subs) - 越多越好，代表社区认可
    2. 评分 (score) - 越高越好
    3. 更新时间 (updated) - 越新越好
    """
    if not candidates:
        return None
        
    # Python 的 sort 是稳定的，我们可以通过多重排序来实现优先级
    # 按照元组排序: (订阅数倒序, 评分倒序, 更新时间倒序)
    sorted_candidates = sorted(
        candidates, 
        key=lambda x: (x.get('subs', 0), x.get('score', 0), x.get('updated', 0)), 
        reverse=True
    )
    
    return sorted_candidates[0]

def main():
    # 1. 初始化 Steamworks API
    try:
        steam = STEAMWORKS()
        steam.initialize()
    except Exception as e:
        print(f"Steam 初始化失败: {e}")
        print("请确保 Steam 正在运行，并且 steam_api64.dll 在脚本目录下或环境变量中。")
        return

    if not steam.Apps.IsSubscribedApp(GAME_APP_ID):
        print(f"检测到你并未拥有 AppID: {GAME_APP_ID}")
        return

    print(f"Steam API 连接成功，正在为 AppID {GAME_APP_ID} 处理汉化...")

    # 2. 加载本地汉化映射表
    translation_map = load_translations(JSON_FILE_PATH)
    print(f"已加载汉化映射表，包含 {len(translation_map)} 个原版 Mod 的汉化信息。")

    # 3. 获取当前已订阅的 Mod 列表
    # 注意: GetSubscribedItems 返回的是 list of integers
    subscribed_count = steam.Workshop.GetNumSubscribedItems()
    subscribed_items = steam.Workshop.GetSubscribedItems(subscribed_count)
    
    # 转换为集合方便快速查找 (StringSet)
    subscribed_set = set(str(item) for item in subscribed_items)
    
    print(f"当前已订阅 {len(subscribed_set)} 个 Mod。")

    new_subs_count = 0

    # 4. 遍历并匹配 (使用列表副本避免集合大小变化错误)
    for mod_id in list(subscribed_set):
        # 检查这个 Mod 是否有对应的汉化记录
        if mod_id in translation_map:
            candidates = translation_map[mod_id]
            
            # 选择最佳汉化
            best_translation = select_best_translation(candidates)
            
            if not best_translation:
                continue

            trans_id = str(best_translation['id'])
            trans_title = best_translation.get('title', 'Unknown Title')

            # 5. 检查是否已经订阅了该汉化
            if trans_id in subscribed_set:
                # print(f"[跳过] 原版 {mod_id} 的汉化已存在: {trans_title}")
                pass
            else:
                print(f"[订阅中] 原版 {mod_id} -> 发现汉化: {trans_title} (ID: {trans_id}, Subs: {best_translation.get('subs')})")
                
                # 执行订阅操作
                steam.Workshop.SetItemSubscribedCallback(lambda result: print(f"订阅结果: {result}"))
                try:
                    steam.Workshop.SubscribeItem(int(trans_id))
                    new_subs_count += 1
                    # 将新订阅的也加入集合，防止重复逻辑（尽管不太可能）
                    subscribed_set.add(trans_id) 
                except Exception as e:
                    print(f"  订阅失败: {e}")

    print("-" * 30)
    print(f"处理完成。共自动订阅了 {new_subs_count} 个汉化 Mod。")
    print("请在 Steam 下载页面检查下载队列。")

if __name__ == "__main__":
    main()
    input("回车结束...")