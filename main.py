import asyncio
import os
import json
import datetime
import logging
import aiohttp
import urllib.parse
from astrbot.api.all import AstrMessageEvent, CommandResult, Context, Plain
import astrbot.api.event.filter as filter
from astrbot.api.star import register, Star

logger = logging.getLogger("astrbot")


@register("D-G-N-C-J", "Tinyxi", "早晚安记录+王者战力查询+城际路线查询+360搜图", "1.0.0", "")
class Main(Star):
    def __init__(self, context: Context) -> None:
        super().__init__(context)
        self.PLUGIN_NAME = "astrbot_plugin_essential"
        PLUGIN_NAME = self.PLUGIN_NAME

        if not os.path.exists(f"data/{PLUGIN_NAME}_data.json"):
            with open(f"data/{PLUGIN_NAME}_data.json", "w", encoding="utf-8") as f:
                f.write(json.dumps({}, ensure_ascii=False, indent=2))
        with open(f"data/{PLUGIN_NAME}_data.json", "r", encoding="utf-8") as f:
            self.data = json.loads(f.read())
        self.good_morning_data = self.data.get("good_morning", {})

        self.daily_sleep_cache = {}
        self.good_morning_cd = {} 

    def get_cached_sleep_count(self, umo_id: str, date_str: str) -> int:
        """获取缓存的睡觉人数"""
        if umo_id not in self.daily_sleep_cache:
            self.daily_sleep_cache[umo_id] = {}
        return self.daily_sleep_cache[umo_id].get(date_str, -1)

    def update_sleep_cache(self, umo_id: str, date_str: str, count: int):
        """更新睡觉人数缓存"""
        if umo_id not in self.daily_sleep_cache:
            self.daily_sleep_cache[umo_id] = {}
        self.daily_sleep_cache[umo_id][date_str] = count

    def invalidate_sleep_cache(self, umo_id: str, date_str: str):
        """使缓存失效"""
        if umo_id in self.daily_sleep_cache and date_str in self.daily_sleep_cache[umo_id]:
            del self.daily_sleep_cache[umo_id][date_str]

    def check_good_morning_cd(self, user_id: str, current_time: datetime.datetime) -> bool:
        """检查用户是否在CD中，返回True表示在CD中"""
        if user_id not in self.good_morning_cd:
            return False
        
        last_time = self.good_morning_cd[user_id]
        time_diff = (current_time - last_time).total_seconds()
        return time_diff < 1800

    def update_good_morning_cd(self, user_id: str, current_time: datetime.datetime):
        """更新用户的CD时间"""
        self.good_morning_cd[user_id] = current_time

    @filter.regex(r"^(早安|晚安)")
    async def good_morning(self, message: AstrMessageEvent):
        """和Bot说早晚安，记录睡眠时间，培养良好作息"""
        umo_id = message.unified_msg_origin
        user_id = message.message_obj.sender.user_id
        user_name = message.message_obj.sender.nickname
        curr_utc8 = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8)))
        curr_human = curr_utc8.strftime("%Y-%m-%d %H:%M:%S")

        if self.check_good_morning_cd(user_id, curr_utc8):
            return CommandResult().message("你刚刚已经说过早安/晚安了，请30分钟后再试喵~").use_t2i(False)

        is_night = "晚安" in message.message_str

        if umo_id in self.good_morning_data:
            umo = self.good_morning_data[umo_id]
        else:
            umo = {}
        if user_id in umo:
            user = umo[user_id]
        else:
            user = {
                "daily": {
                    "morning_time": "",
                    "night_time": "",
                }
            }

        if is_night:
            user["daily"]["night_time"] = curr_human
            user["daily"]["morning_time"] = ""
        else:
            user["daily"]["morning_time"] = curr_human

        umo[user_id] = user
        self.good_morning_data[umo_id] = umo

        with open(f"data/{self.PLUGIN_NAME}_data.json", "w", encoding="utf-8") as f:
            f.write(json.dumps(self.good_morning_data, ensure_ascii=False, indent=2))
            
        self.update_good_morning_cd(user_id, curr_utc8)

        curr_day: int = curr_utc8.day
        curr_date_str = curr_utc8.strftime("%Y-%m-%d")

        self.invalidate_sleep_cache(umo_id, curr_date_str)
        curr_day_sleeping = 0
        for v in umo.values():
            if v["daily"]["night_time"] and not v["daily"]["morning_time"]:
                user_day = datetime.datetime.strptime(
                    v["daily"]["night_time"], "%Y-%m-%d %H:%M:%S"
                ).day
                if user_day == curr_day:
                    curr_day_sleeping += 1
        
        self.update_sleep_cache(umo_id, curr_date_str, curr_day_sleeping)

        if not is_night:
            sleep_duration_human = ""
            if user["daily"]["night_time"]:
                night_time = datetime.datetime.strptime(
                    user["daily"]["night_time"], "%Y-%m-%d %H:%M:%S"
                )
                morning_time = datetime.datetime.strptime(
                    user["daily"]["morning_time"], "%Y-%m-%d %H:%M:%S"
                )
                sleep_duration = (morning_time - night_time).total_seconds()
                hrs = int(sleep_duration / 3600)
                mins = int((sleep_duration % 3600) / 60)
                sleep_duration_human = f"{hrs}小时{mins}分"

            return (
                CommandResult()
                .message(
                    f"早上好喵，{user_name}！\n现在是 {curr_human}，昨晚你睡了 {sleep_duration_human}。"
                )
                .use_t2i(False)
            )
        else:
            return (
                CommandResult()
                .message(
                    f"快睡觉喵，{user_name}！\n现在是 {curr_human}，你是本群今天第 {curr_day_sleeping} 个睡觉的。"
                )
                .use_t2i(False)
            )



    @filter.command("战力查询")
    async def hero_power(self, message: AstrMessageEvent):
        """王者英雄战力查询，支持双区双系统"""
        msg = message.message_str.replace("战力查询", "").strip()
        
        if not msg:
            return CommandResult().error("正确指令：战力查询 <英雄名>\n\n示例：战力查询 小乔")
        
        hero_name = msg.strip()
        api_url = "https://www.sapi.run/hero/select.php"
        
        try:
            # 默认使用aqq（安卓-QQ区）进行查询
            params = {
                "hero": hero_name,
                "type": "aqq"
            }
            
            timeout = aiohttp.ClientTimeout(total=30)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(api_url, params=params) as resp:
                    if resp.status != 200:
                        return CommandResult().error("请求战力查询失败，服务器返回错误状态码")
                    
                    result = await resp.json()
                    
                    if result.get("code") != 200:
                        return CommandResult().error(f"查询失败：{result.get('msg', '未知错误')}")
                    
                    data = result.get("data", {})
                    if not data:
                        return CommandResult().error("未查询到该英雄的战力信息")
                    
                    # 格式化输出结果
                    response = f"{data.get('name', hero_name)}\n"
                    response += f"国服最低：{data.get('guobiao', '0')}\n"
                    response += f"省标最低：{data.get('provincePower', '0')}\n"
                    response += f"市标最低：{data.get('cityPower', '0')}\n"
                    response += f"区标最低：{data.get('areaPower', '0')}"
                    
                    return CommandResult().message(response).use_t2i(False)
                        
        except aiohttp.ClientError as e:
            logger.error(f"网络连接错误：{e}")
            return CommandResult().error("无法连接到战力查询服务器，请稍后重试或检查网络连接")
        except asyncio.TimeoutError:
            logger.error("请求超时")
            return CommandResult().error("请求超时，请稍后重试")
        except json.JSONDecodeError:
            logger.error("JSON解析错误")
            return CommandResult().error("服务器返回数据格式错误")
        except Exception as e:
            logger.error(f"请求战力查询时发生错误：{e}")
            return CommandResult().error(f"请求战力查询时发生错误：{str(e)}")

    @filter.command("路线查询")
    async def city_route(self, message: AstrMessageEvent):
        """城际路线查询，支持异步请求"""
        msg = message.message_str.replace("路线查询", "").strip()
        
        if not msg:
            return CommandResult().error("正确指令：路线查询 <出发地> <目的地>\n\n示例：路线查询 广州 深圳")
        
        # 解析出发地和目的地
        parts = msg.split()
        if len(parts) < 2:
            return CommandResult().error("请输入完整的出发地和目的地\n\n正确指令：路线查询 <出发地> <目的地>\n\n示例：路线查询 广州 深圳")
        
        from_city = parts[0]
        to_city = parts[1]
        
        api_url = "https://api.pearktrue.cn/api/citytravelroutes/"
        
        try:
            # 构造请求参数
            payload = {
                "from": from_city,
                "to": to_city
            }
            
            timeout = aiohttp.ClientTimeout(total=30)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(api_url, json=payload) as resp:
                    if resp.status != 200:
                        return CommandResult().error("请求路线查询失败，服务器返回错误状态码")
                    
                    result = await resp.json()
                    
                    if result.get("code") != 200:
                        return CommandResult().error(f"查询失败：{result.get('msg', '未知错误')}")
                    
                    data = result.get("data", {})
                    if not data:
                        return CommandResult().error("未查询到该路线的信息")
                    
                    # 格式化输出结果
                    response = f"{result.get('from', from_city)} -> {result.get('to', to_city)}\n"
                    response += f"路线：{data.get('corese', '')}\n"
                    response += f"总距离：{data.get('distance', '0')}\n"
                    response += f"总耗时：{data.get('time', '0')}\n"
                    response += f"油费：{data.get('fuelcosts', '0')}\n"
                    response += f"过桥费：{data.get('bridgetoll', '0')}\n"
                    response += f"总费用：{data.get('totalcost', '0')}\n"
                    response += f"路况：{data.get('roadconditions', '暂无数据')}"
                    
                    return CommandResult().message(response).use_t2i(False)
                        
        except aiohttp.ClientError as e:
            logger.error(f"网络连接错误：{e}")
            return CommandResult().error("无法连接到路线查询服务器，请稍后重试或检查网络连接")
        except asyncio.TimeoutError:
            logger.error("请求超时")
            return CommandResult().error("请求超时，请稍后重试")
        except json.JSONDecodeError:
            logger.error("JSON解析错误")
            return CommandResult().error("服务器返回数据格式错误")
        except Exception as e:
            logger.error(f"请求路线查询时发生错误：{e}")
            return CommandResult().error(f"请求路线查询时发生错误：{str(e)}")

    @filter.command("搜图")
    async def search_images(self, message: AstrMessageEvent):
        """360搜图，支持异步请求"""
        msg = message.message_str.replace("搜图", "").strip()
        
        if not msg:
            return CommandResult().error("正确指令：搜图 <关键词>\n\n示例：搜图 奥特曼")
        
        keyword = msg.strip()
        api_url = "https://api.cenguigui.cn/api/360/so_images.php"
        
        try:
            params = {
                "msg": keyword,
                "type": "json"
            }
            
            timeout = aiohttp.ClientTimeout(total=30)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(api_url, params=params) as resp:
                    if resp.status != 200:
                        return CommandResult().error("请求图片搜索失败，服务器返回错误状态码")
                    
                    result = await resp.json()
                    
                    if result.get("code") != "200":
                        return CommandResult().error(f"搜索失败：{result.get('msg', '未知错误')}")
                    
                    data = result.get("data", [])
                    if not data:
                        return CommandResult().error("未搜索到相关图片")
                    
                    # 获取第一张图片的URL
                    img_url = data[0].get("imgurl", "")
                    if not img_url:
                        return CommandResult().error("未获取到图片URL")
                    
                    # 直接返回图片
                    from astrbot.api.all import Image as ImageComponent
                    return CommandResult().message([ImageComponent(img_url)]).use_t2i(False)
                        
        except aiohttp.ClientError as e:
            logger.error(f"网络连接错误：{e}")
            return CommandResult().error("无法连接到图片搜索服务器，请稍后重试或检查网络连接")
        except asyncio.TimeoutError:
            logger.error("请求超时")
            return CommandResult().error("请求超时，请稍后重试")
        except json.JSONDecodeError:
            logger.error("JSON解析错误")
            return CommandResult().error("服务器返回数据格式错误")
        except Exception as e:
            logger.error(f"请求图片搜索时发生错误：{e}")
            return CommandResult().error(f"请求图片搜索时发生错误：{str(e)}")

    async def terminate(self):
        """插件卸载/重载时调用"""
        pass
