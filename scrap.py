import requests
import time
import json
import urllib3
import signal
import sys
from functools import wraps
import os

# 忽略 SSL 验证警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 全局变量用于存储临时数据
temp_data = []

# ================= 配置区域 =================
API_KEY = ""       # 替换这里
APP_ID = 294100                      # 替换这里 (例如 Wallpaper Engine)

# 筛选条件
TARGET_TAGS = ["1.4", "1.5", "1.6"]              # 包含这些标签 (留空 [] 则不筛选)
EXCLUDED_TAGS = ["Scenario"]      # 排除这些标签 (留空 [] 则不排除)

# Steam Workshop文件查询类型常量
'''
k_PublishedFileQueryType_RankedByVote	按投票排序	0
k_PublishedFileQueryType_RankedByPublicationDate	按发布日期排序	1
k_PublishedFileQueryType_AcceptedForGameRankedByAcceptanceDate	按游戏接受日期排序	2
k_PublishedFileQueryType_RankedByTrend	按热度排序	3
k_PublishedFileQueryType_FavoritedByFriendsRankedByPublicationDate	按好友收藏发布日期排序	4
k_PublishedFileQueryType_CreatedByFriendsRankedByPublicationDate	按好友创建发布日期排序	5
k_PublishedFileQueryType_RankedByNumTimesReported	按举报次数排序	6
k_PublishedFileQueryType_CreatedByFollowedUsersRankedByPublicationDate	按关注用户创建发布日期排序	7
k_PublishedFileQueryType_NotYetRated	未评分	8
k_PublishedFileQueryType_RankedByTotalUniqueSubscriptions	按总订阅数排序	9
k_PublishedFileQueryType_RankedByTotalVotesAsc	按总投票数升序排序	10
k_PublishedFileQueryType_RankedByVotesUp	按赞成票数排序	11
k_PublishedFileQueryType_RankedByTextSearch	按文本搜索排序	12
k_PublishedFileQueryType_RankedByPlaytimeTrend	按游玩时间趋势排序	13
k_PublishedFileQueryType_RankedByTotalPlaytime	按总游玩时间排序	14
k_PublishedFileQueryType_RankedByAveragePlaytimeTrend	按平均游玩时间趋势排序	15
k_PublishedFileQueryType_RankedByLifetimeAveragePlaytime	按生命周期平均游玩时间排序	16
k_PublishedFileQueryType_RankedByPlaytimeSessionsTrend	按游玩时间会话趋势排序	17
k_PublishedFileQueryType_RankedByLifetimePlaytimeSessions	按生命周期游玩时间会话排序	18
k_PublishedFileQueryType_RankedByInappropriateContentRating	按不当内容评分排序	19
k_PublishedFileQueryType_RankedByBanContentCheck	按禁止内容检查排序	20
k_PublishedFileQueryType_RankedByLastUpdatedDate	按最后更新日期排序	21
'''

QUERY_TYPE = 1

MAX_PAGES = 999                       # 爬取页数 (每页100条)
OUTPUT_FOLDER = "output"               # 输出文件夹名称
OUTPUT_FILE = "workshop_data.json"
CHUNK_SIZE = 1000                     # 每1000条保存一个文件
MAX_RETRIES = 12                       # 最大重试次数
RETRY_DELAY = 5                       # 重试延迟秒数
FULL_DATA = True
# ===========================================

def retry_on_failure(max_retries=3, delay=5):
    """重试装饰器"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt < max_retries - 1:
                        print(f"第 {attempt + 1} 次尝试失败: {str(e)}")
                        print(f"{delay} 秒后进行第 {attempt + 2} 次重试...")
                        time.sleep(delay)
                    else:
                        print(f"所有 {max_retries} 次重试都失败了")
            raise last_exception
        return wrapper
    return decorator

def signal_handler(sig, frame):
    """Ctrl+C 信号处理器"""
    print('\n\n检测到中断信号 (Ctrl+C)')
    print('正在保存已获取的数据...')
    
    # 确保输出文件夹存在
    if not os.path.exists(OUTPUT_FOLDER):
        os.makedirs(OUTPUT_FOLDER)
    
    if temp_data:
        # 保存临时数据
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        interrupt_file = os.path.join(OUTPUT_FOLDER, f"interrupted_data_{timestamp}.json")
        
        # 分块保存中断数据
        chunk_index = 0
        total_saved = 0
        for i in range(0, len(temp_data), CHUNK_SIZE):
            chunk = temp_data[i:i + CHUNK_SIZE]
            if chunk_index == 0:
                chunk_filename = interrupt_file
            else:
                chunk_filename = os.path.join(OUTPUT_FOLDER, f"interrupted_data_{timestamp}_{chunk_index + 1}.json")
            
            with open(chunk_filename, 'w', encoding='utf-8') as f:
                json.dump(chunk, f, ensure_ascii=False, indent=4)
            print(f"已保存 {len(chunk)} 条数据到 {chunk_filename}")
            total_saved += len(chunk)
            chunk_index += 1
        
        print(f"\n中断时成功保存 {total_saved} 条数据到 {interrupt_file}")
    else:
        print("没有可保存的数据")
    
    print("程序已安全退出")
    sys.exit(0)

@retry_on_failure(max_retries=MAX_RETRIES, delay=RETRY_DELAY)
def make_request(url, params, timeout=15):
    """带重试的网络请求函数"""
    response = requests.get(url, params=params, timeout=timeout, verify=False)
    response.raise_for_status()  # 如果状态码不是200会抛出异常
    return response.json()

def save_progress_data(data, page_num):
    """保存进度数据"""
    if data:
        # 确保输出文件夹存在
        if not os.path.exists(OUTPUT_FOLDER):
            os.makedirs(OUTPUT_FOLDER)
        
        progress_file = os.path.join(OUTPUT_FOLDER, f"progress_data_page_{page_num}.json")
        with open(progress_file, 'w', encoding='utf-8') as f:
            json.dump(data[-100:], f, ensure_ascii=False, indent=4)  # 只保存最近100条
        print(f"进度数据已保存到 {progress_file}")

def fetch_clean_workshop_data(api_key, app_id, required_tags=None, excluded_tags=None, query_type=1, max_pages=1, full_data=FULL_DATA):
    global temp_data
    base_url = "https://api.steampowered.com/IPublishedFileService/QueryFiles/v1/"
    cursor = "*" # 初始游标
    cleaned_items = []
    successful_pages = 0

    for page in range(max_pages):
        print(f"--- 正在爬取第 {page + 1} 页 (模式: {query_type}, 数据模式: {'全部' if full_data else '裁剪'}) ---")
        
        # 1. 构造基本参数
        params = {
            'key': api_key,
            'appid': app_id,
            'cursor': cursor,
            'numperpage': 100,
            'query_type': query_type,
            'return_children' : 1,
            
            # 开启详细数据返回，以便获取统计数据和标签
            'return_vote_data': 1, 
            'return_tags': 1, 
            'return_details': 1,
            'return_kv_tags': 1 
        }

        # 2. 处理包含标签 (Required Tags)
        if required_tags:
            for i, tag in enumerate(required_tags):
                params[f'requiredtags[{i}]'] = tag

        # 3. 处理排除标签 (Excluded Tags)
        if excluded_tags:
            for i, tag in enumerate(excluded_tags):
                params[f'excludedtags[{i}]'] = tag

        try:
            # 发送请求
            print(f"[请求] 第 {page + 1} 页 - cursor: {cursor}")
            data = make_request(base_url, params, timeout=15)
            
            # 检查是否有数据
            if 'response' not in data or 'publishedfiledetails' not in data['response']:
                print("未获取到数据，可能已到达末尾。")
                break
            
            items = data['response']['publishedfiledetails']
            if not items:
                print("本页无数据，停止。")
                break

            # 4. 数据清洗与提取
            page_items = []
            for item in items:
                if full_data:
                    # 获取全部数据
                    clean_item = item.copy()
                    # 处理标签格式
                    if 'tags' in clean_item:
                        raw_tags = clean_item['tags']
                        tag_list = [t.get('tag') for t in raw_tags if 'tag' in t]
                        clean_item['tags'] = tag_list
                else:
                    # 只保留指定字段
                    # 提取标签列表 (API返回的是 [{'tag': 'A'}, {'tag': 'B'}] 格式，转为 ['A', 'B'])
                    raw_tags = item.get('tags', [])
                    tag_list = [t.get('tag') for t in raw_tags if 'tag' in t]

                    clean_item = {
                        'publishedfileid': item.get('publishedfileid'),
                        'title': item.get('title'),
                        'time_created': item.get('time_created'),
                        'time_updated': item.get('time_updated'),
                        # 统计数据如果为0，API有时会省略该字段，所以用 .get(key, 0)
                        'views': item.get('views', 0),
                        'subscriptions': item.get('subscriptions', 0),
                        'favorited': item.get('favorited', 0),
                        'tags': tag_list,
                        'children': item.get('children', [])
                    }
                page_items.append(clean_item)
                cleaned_items.append(clean_item)
            
            # 更新全局临时数据
            temp_data = cleaned_items.copy()
            
            print(f"本页获取 {len(page_items)} 条，总计已获取 {len(cleaned_items)} 条。")

            # 保存进度数据（每5页保存一次）
            if (page + 1) % 5 == 0:
                save_progress_data(page_items, page + 1)

            # 5. 处理翻页游标
            next_cursor = data['response'].get('next_cursor')
            if not next_cursor or next_cursor == cursor:
                print("所有页面已爬取完毕。")
                break
            cursor = next_cursor
            
            successful_pages += 1
            
            # 延时
            time.sleep(1)

        except requests.exceptions.RequestException as e:
            print(f"网络请求错误: {e}")
            print("跳过当前页，继续下一页...")
            continue
        except Exception as e:
            print(f"处理数据时发生错误: {e}")
            print("跳过当前页，继续下一页...")
            continue

    print(f"\n爬取完成！成功处理 {successful_pages} 页，共获取 {len(cleaned_items)} 条数据。")
    return cleaned_items

# 执行主程序
if __name__ == "__main__":
    # 注册信号处理器
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    print("=" * 50)
    print("Steam Workshop 数据爬虫")
    print("=" * 50)
    print(f"目标 AppID: {APP_ID}")
    print(f"包含标签: {TARGET_TAGS}")
    print(f"排除标签: {EXCLUDED_TAGS}")
    print(f"最大重试次数: {MAX_RETRIES}")
    print(f"重试延迟: {RETRY_DELAY} 秒")
    print("提示: 按 Ctrl+C 可随时中断并保存已获取的数据")
    print("=" * 50)
    
    try:
        data = fetch_clean_workshop_data(
            API_KEY, 
            APP_ID, 
            required_tags=TARGET_TAGS, 
            excluded_tags=EXCLUDED_TAGS, 
            query_type=QUERY_TYPE, 
            max_pages=MAX_PAGES,
            match_all_tags=False
        )
        
        # 确保输出文件夹存在
        if not os.path.exists(OUTPUT_FOLDER):
            os.makedirs(OUTPUT_FOLDER)
        
        # 分块保存最终结果
        chunk_index = 0
        for i in range(0, len(data), CHUNK_SIZE):
            chunk = data[i:i + CHUNK_SIZE]
            if chunk_index == 0:
                chunk_filename = os.path.join(OUTPUT_FOLDER, OUTPUT_FILE)
            else:
                chunk_filename = os.path.join(OUTPUT_FOLDER, f"workshop_data_{chunk_index + 1}.json")
            with open(chunk_filename, 'w', encoding='utf-8') as f:
                json.dump(chunk, f, ensure_ascii=False, indent=4)
            print(f"已保存 {len(chunk)} 条数据到 {chunk_filename}")
            chunk_index += 1
        
        print(f"\n爬取结束！共保存 {len(data)} 条数据，分为 {chunk_index} 个文件。")
        
        # 清理进度文件
        progress_files = [f for f in os.listdir(OUTPUT_FOLDER) if f.startswith('progress_data_page_')]
        for pf in progress_files:
            os.remove(os.path.join(OUTPUT_FOLDER, pf))
        if progress_files:
            print(f"已清理 {len(progress_files)} 个进度文件")
        
        # 打印第一条数据示例
        if data:
            print("\n第一条数据示例:")
            print(json.dumps(data[0], ensure_ascii=False, indent=2))
            
    except Exception as e:
        print(f"程序执行出错: {e}")
        if temp_data:
            print("正在保存已获取的临时数据...")
            signal_handler(None, None)  # 调用信号处理器保存数据