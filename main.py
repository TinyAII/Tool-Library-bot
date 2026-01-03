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


@register("D-G-N-C-J", "Tinyxi", "早晚安记录+王者战力查询+城际路线查询+AI绘画", "1.0.0", "")
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
            yield message.plain_result("你刚刚已经说过早安/晚安了，请30分钟后再试喵~").use_t2i(False)
            return

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

            yield message.plain_result(
                f"早上好喵，{user_name}！\n现在是 {curr_human}，昨晚你睡了 {sleep_duration_human}。"
            ).use_t2i(False)
        else:
            yield message.plain_result(
                f"快睡觉喵，{user_name}！\n现在是 {curr_human}，你是本群今天第 {curr_day_sleeping} 个睡觉的。"
            ).use_t2i(False)



    @filter.command("战力查询")
    async def hero_power(self, message: AstrMessageEvent):
        """王者英雄战力查询，支持双区双系统"""
        msg = message.message_str.replace("战力查询", "").strip()
        
        if not msg:
            yield message.plain_result("缺少参数，正确示例：\n\n战力查询 小乔").use_t2i(False)
            return
        
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
                        yield message.plain_result("请求战力查询失败，服务器返回错误状态码").use_t2i(False)
                        return
                    
                    # 先读取响应文本，再使用json.loads()解析，解决Content-Type问题
                    raw_content = await resp.text()
                    result = json.loads(raw_content)
                    
                    if result.get("code") != 200:
                        yield message.plain_result(f"查询失败：{result.get('msg', '未知错误')}").use_t2i(False)
                        return
                    
                    data = result.get("data", {})
                    if not data:
                        yield message.plain_result("未查询到该英雄的战力信息").use_t2i(False)
                        return
                    
                    # 格式化输出结果
                    response = f"{data.get('name', hero_name)}\n"
                    response += f"国服最低：{data.get('guobiao', '0')}\n"
                    response += f"【{data.get('province', '未知省')}】省标最低：{data.get('provincePower', '0')}\n"
                    response += f"【{data.get('city', '未知市')}】市标最低：{data.get('cityPower', '0')}\n"
                    response += f"【{data.get('area', '未知区')}】区标最低：{data.get('areaPower', '0')}"
                    
                    yield message.plain_result(response).use_t2i(False)
                    return
                        
        except aiohttp.ClientError as e:
            logger.error(f"网络连接错误：{e}")
            yield message.plain_result("无法连接到战力查询服务器，请稍后重试或检查网络连接").use_t2i(False)
            return
        except asyncio.TimeoutError:
            logger.error("请求超时")
            yield message.plain_result("请求超时，请稍后重试").use_t2i(False)
            return
        except json.JSONDecodeError:
            logger.error("JSON解析错误")
            yield message.plain_result("服务器返回数据格式错误").use_t2i(False)
            return
        except Exception as e:
            logger.error(f"请求战力查询时发生错误：{e}")
            yield message.plain_result(f"请求战力查询时发生错误：{str(e)}").use_t2i(False)
            return

    @filter.command("路线查询")
    async def city_route(self, message: AstrMessageEvent):
        """城际路线查询，支持异步请求"""
        msg = message.message_str.replace("路线查询", "").strip()
        
        if not msg:
            yield message.plain_result("正确指令：路线查询 <出发地> <目的地>\n\n示例：路线查询 广州 深圳").use_t2i(False)
            return
        
        # 解析出发地和目的地
        parts = msg.split()
        if len(parts) < 2:
            yield message.plain_result("请输入完整的出发地和目的地\n\n正确指令：路线查询 <出发地> <目的地>\n\n示例：路线查询 广州 深圳").use_t2i(False)
            return
        
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
                        yield message.plain_result("请求路线查询失败，服务器返回错误状态码").use_t2i(False)
                        return
                    
                    # 先读取响应文本，再使用json.loads()解析，解决Content-Type问题
                    raw_content = await resp.text()
                    result = json.loads(raw_content)
                    
                    if result.get("code") != 200:
                        yield message.plain_result(f"查询失败：{result.get('msg', '未知错误')}").use_t2i(False)
                        return
                    
                    data = result.get("data", {})
                    if not data:
                        yield message.plain_result("未查询到该路线的信息").use_t2i(False)
                        return
                    
                    # 格式化输出结果
                    response = f"{result.get('from', from_city)} -> {result.get('to', to_city)}\n"
                    response += f"路线：{data.get('corese', '')}\n"
                    response += f"总距离：{data.get('distance', '0')}\n"
                    response += f"总耗时：{data.get('time', '0')}\n"
                    response += f"油费：{data.get('fuelcosts', '0')}\n"
                    response += f"过桥费：{data.get('bridgetoll', '0')}\n"
                    response += f"总费用：{data.get('totalcost', '0')}\n"
                    response += f"路况：{data.get('roadconditions', '暂无数据')}"
                    
                    yield message.plain_result(response).use_t2i(False)
                    return
                        
        except aiohttp.ClientError as e:
            logger.error(f"网络连接错误：{e}")
            yield message.plain_result("无法连接到路线查询服务器，请稍后重试或检查网络连接").use_t2i(False)
            return
        except asyncio.TimeoutError:
            logger.error("请求超时")
            yield message.plain_result("请求超时，请稍后重试").use_t2i(False)
            return
        except json.JSONDecodeError:
            logger.error("JSON解析错误")
            yield message.plain_result("服务器返回数据格式错误").use_t2i(False)
            return
        except Exception as e:
            logger.error(f"请求路线查询时发生错误：{e}")
            yield message.plain_result(f"请求路线查询时发生错误：{str(e)}").use_t2i(False)
            return

    @filter.command("绘画")
    async def ai_painting(self, message: AstrMessageEvent):
        """AI绘画功能，根据提示词生成图片"""
        # 提取提示词，命令匹配会自动处理命令前缀
        msg = message.message_str.replace("绘画", "").strip()
        
        if not msg:
            yield message.plain_result("正确指令：绘画 <提示词>\n\n示例：绘画 一条狗").use_t2i(False)
            return
        
        prompt = msg.strip()
        api_url = "https://api.jkyai.top/API/ks/api.php"
        
        try:
            # 先回复用户正在生成图片
            yield message.plain_result("正在制作精美图片..........").use_t2i(False)
            
            # 构造请求参数，使用默认的1024x1024大小，guidance设为最高10，batch为1
            params = {
                "msg": prompt,
                "size": "1024x1024",
                "guidance": 10,
                "batch": 1
            }
            
            timeout = aiohttp.ClientTimeout(total=30)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(api_url, params=params) as resp:
                    if resp.status != 200:
                        yield message.plain_result("请求AI绘画失败，服务器返回错误状态码").use_t2i(False)
                        return
                    
                    image_url = await resp.text()
                    
                    # 检查返回的是否为有效的URL
                    if not image_url.startswith("http"):
                        yield message.plain_result(f"AI绘画生成失败：{image_url}").use_t2i(False)
                        return
                    
                    # 下载图片到本地并发送
                    import uuid
                    import os
                    from astrbot.api.message_components import Image
                    
                    # 创建存储目录
                    save_dir = f"data/{self.PLUGIN_NAME}_images"
                    if not os.path.exists(save_dir):
                        os.makedirs(save_dir)
                    
                    # 生成唯一文件名
                    file_name = f"{uuid.uuid4().hex}.jpg"
                    file_path = os.path.join(save_dir, file_name)
                    
                    # 下载图片
                    async with session.get(image_url, timeout=30) as img_resp:
                        if img_resp.status != 200:
                            yield message.plain_result("下载图片失败，服务器返回错误状态码").use_t2i(False)
                            return
                        
                        with open(file_path, "wb") as f:
                            f.write(await img_resp.read())
                    
                    # 使用本地文件路径发送图片
                    yield message.chain_result([Image.fromFileSystem(file_path)]).use_t2i(False)
                    return
                        
        except aiohttp.ClientError as e:
            logger.error(f"网络连接错误：{e}")
            yield message.plain_result("无法连接到AI绘画服务器，请稍后重试或检查网络连接").use_t2i(False)
            return
        except asyncio.TimeoutError:
            logger.error("请求超时")
            yield message.plain_result("请求超时，请稍后重试").use_t2i(False)
            return
        except Exception as e:
            logger.error(f"请求AI绘画时发生错误：{e}")
            yield message.plain_result(f"请求AI绘画时发生错误：{str(e)}").use_t2i(False)
            return

    @filter.command("mc服务器")
    async def mc_server_status(self, message: AstrMessageEvent):
        """查询Minecraft服务器状态"""
        # 提取服务器地址参数
        msg = message.message_str.replace("mc服务器", "").strip()
        
        if not msg:
            yield message.plain_result("缺少必要参数，正确示例：\n\nmc服务器 121.com").use_t2i(False)
            return
        
        server_addr = msg.strip()
        api_url = "https://uapis.cn/api/v1/game/minecraft/serverstatus"
        
        try:
            # 构造请求参数
            params = {
                "server": server_addr
            }
            
            timeout = aiohttp.ClientTimeout(total=30)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(api_url, params=params) as resp:
                    if resp.status != 200:
                        raw_content = await resp.text()
                        result = json.loads(raw_content)
                        yield message.plain_result(f"查询失败：{result.get('message', '未知错误')}").use_t2i(False)
                        return
                    
                    raw_content = await resp.text()
                    data = json.loads(raw_content)
                    
                    if data.get('code') != 200:
                        yield message.plain_result(f"查询失败：{data.get('message', '未知错误')}").use_t2i(False)
                        return
                    
                    # 格式化输出结果
                    online_status = "是" if data.get('online') else "否"
                    response = f"查询【{server_addr}】成功！\n"
                    response += f"是否在线：{online_status}\n"
                    response += f"ip:{data.get('ip', '未知')}\n"
                    response += f"端口：{data.get('port', 25565)}\n"
                    response += f"玩家数：{data.get('players', 0)}\n"
                    response += f"最大玩家数：{data.get('max_players', 0)}\n"
                    response += f"版本：{data.get('version', '未知')}"
                    
                    yield message.plain_result(response).use_t2i(False)
                    return
                        
        except aiohttp.ClientError as e:
            logger.error(f"网络连接错误：{e}")
            yield message.plain_result("无法连接到查询服务器，请稍后重试或检查网络连接").use_t2i(False)
            return
        except asyncio.TimeoutError:
            logger.error("请求超时")
            yield message.plain_result("请求超时，请稍后重试").use_t2i(False)
            return
        except json.JSONDecodeError:
            logger.error("JSON解析错误")
            yield message.plain_result("服务器返回数据格式错误").use_t2i(False)
            return
        except Exception as e:
            logger.error(f"请求Minecraft服务器查询时发生错误：{e}")
            yield message.plain_result(f"请求Minecraft服务器查询时发生错误：{str(e)}").use_t2i(False)
            return

    @filter.command("代理ip")
    async def proxy_ip(self, message: AstrMessageEvent):
        """获取socks5代理IP信息"""
        api_url = "https://api.pearktrue.cn/api/proxy/"
        
        try:
            # 构造请求参数，默认获取socks5代理
            params = {
                "agreement": "socks5"
            }
            
            timeout = aiohttp.ClientTimeout(total=30)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(api_url, params=params) as resp:
                    if resp.status != 200:
                        yield message.plain_result("请求代理IP失败，服务器返回错误状态码").use_t2i(False)
                        return
                    
                    # 先读取响应文本，再使用json.loads()解析，解决Content-Type问题
                    raw_content = await resp.text()
                    result = json.loads(raw_content)
                    
                    if result.get("code") != 200:
                        yield message.plain_result(f"获取失败：{result.get('msg', '未知错误')}").use_t2i(False)
                        return
                    
                    # 格式化输出结果
                    response = f"成功获取ip\n"
                    response += f"时间：{result.get('time', '未知')}\n"
                    response += f"类型：{result.get('type', '未知')}\n"
                    response += f"ip:{result.get('proxy', '未知')}"
                    
                    yield message.plain_result(response).use_t2i(False)
                    return
                        
        except aiohttp.ClientError as e:
            logger.error(f"网络连接错误：{e}")
            yield message.plain_result("无法连接到代理IP服务器，请稍后重试或检查网络连接").use_t2i(False)
            return
        except asyncio.TimeoutError:
            logger.error("请求超时")
            yield message.plain_result("请求超时，请稍后重试").use_t2i(False)
            return
        except json.JSONDecodeError:
            logger.error("JSON解析错误")
            yield message.plain_result("服务器返回数据格式错误").use_t2i(False)
            return
        except Exception as e:
            logger.error(f"请求代理IP时发生错误：{e}")
            yield message.plain_result(f"请求代理IP时发生错误：{str(e)}").use_t2i(False)
            return

    @filter.command("油价查询")
    async def oil_price(self, message: AstrMessageEvent):
        """查询指定城市的油价信息"""
        # 提取城市名称参数
        msg = message.message_str.replace("油价查询", "").strip()
        
        if not msg:
            yield message.plain_result("正确指令：油价查询 <城市名>\n\n示例：油价查询 上海").use_t2i(False)
            return
        
        city_name = msg.strip()
        api_url = "https://free.wqwlkj.cn/wqwlapi/oilprice.php"
        
        try:
            # 构造请求参数
            params = {
                "city": city_name,
                "type": "json"
            }
            
            # 添加详细日志
            logger.info(f"开始查询{city_name}的油价，API地址：{api_url}，参数：{params}")
            
            timeout = aiohttp.ClientTimeout(total=60)  # 延长超时时间到60秒
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(api_url, params=params) as resp:
                    logger.info(f"油价查询响应状态码：{resp.status}")
                    logger.info(f"油价查询响应头：{resp.headers}")
                    
                    if resp.status != 200:
                        yield message.plain_result(f"请求油价查询失败，服务器返回错误状态码：{resp.status}").use_t2i(False)
                        return
                    
                    # 先读取原始响应内容，方便调试
                    raw_content = await resp.text()
                    logger.info(f"油价查询原始响应：{raw_content}")
                    
                    # 尝试解析JSON，使用json.loads()直接解析文本
                    result = json.loads(raw_content)
                    
                    logger.info(f"油价查询解析结果：{result}")
                    
                    if result.get("code") != 1:
                        yield message.plain_result(f"查询失败：{result.get('msg', '未知错误')}").use_t2i(False)
                        return
                    
                    # 格式化输出结果
                    data = result.get("data", [])
                    qushi = result.get("qushi", "")
                    
                    # 提取不同类型的油价
                    oil_prices = {}
                    for item in data:
                        oil_type = item.get("type", "")
                        price = item.get("price", 0)
                        # 提取油价类型，如"92#汽油"、"95#汽油"等
                        if "92#" in oil_type:
                            oil_prices["92"] = price
                        elif "95#" in oil_type:
                            oil_prices["95"] = price
                        elif "98#" in oil_type:
                            oil_prices["98"] = price
                        elif "0#" in oil_type:
                            oil_prices["0"] = price
                    
                    # 构造响应消息
                    response = f"查询成功！地区[{city_name}]\n"
                    response += f"趋势：前{qushi}\n"
                    response += f"92号汽油：{oil_prices.get('92', '未知')}元/升\n"
                    response += f"95号汽油：{oil_prices.get('95', '未知')}元/升\n"
                    response += f"98号汽油：{oil_prices.get('98', '未知')}元/升\n"
                    response += f"0号柴油：{oil_prices.get('0', '未知')}元/升"
                    
                    yield message.plain_result(response).use_t2i(False)
                    return
                        
        except aiohttp.ClientError as e:
            logger.error(f"网络连接错误：{e}")
            yield message.plain_result(f"无法连接到油价查询服务器：{str(e)}").use_t2i(False)
            return
        except asyncio.TimeoutError:
            logger.error("请求超时")
            yield message.plain_result("请求超时，请稍后重试，服务器响应较慢").use_t2i(False)
            return
        except json.JSONDecodeError as e:
            logger.error(f"JSON解析错误：{e}")
            yield message.plain_result(f"服务器返回数据格式错误：{str(e)}").use_t2i(False)
            return
        except Exception as e:
            logger.error(f"请求油价查询时发生错误：{e}")
            yield message.plain_result(f"请求油价查询时发生错误：{str(e)}").use_t2i(False)
            return

    @filter.command("qq估价")
    async def qq_valuation(self, message: AstrMessageEvent):
        """查询指定QQ号的估价信息"""
        # 提取QQ号参数
        msg = message.message_str.replace("qq估价", "").strip()
        
        if not msg:
            yield message.plain_result("正确指令：qq估价 <QQ号>\n\n示例：qq估价 123456").use_t2i(False)
            return
        
        qq_number = msg.strip()
        api_url = "https://free.wqwlkj.cn/wqwlapi/qq_gj.php"
        
        try:
            # 构造请求参数
            params = {
                "qq": qq_number,
                "type": "json"
            }
            
            timeout = aiohttp.ClientTimeout(total=30)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(api_url, params=params) as resp:
                    if resp.status != 200:
                        yield message.plain_result("请求QQ估价失败，服务器返回错误状态码").use_t2i(False)
                        return
                    
                    # 先读取响应文本，再使用json.loads()解析，解决Content-Type问题
                    raw_content = await resp.text()
                    result = json.loads(raw_content)
                    
                    if result.get("code") != 1:
                        yield message.plain_result(f"查询失败：{result.get('msg', '未知错误')}").use_t2i(False)
                        return
                    
                    # 格式化输出结果
                    response = f"成功估价【{result.get('qq', qq_number)}】\n"
                    response += f"评估：{result.get('valuation', 0)}元\n"
                    response += f"特点：{result.get('law', '')}\n"
                    response += f"数字：{result.get('digit', '')}"
                    
                    yield message.plain_result(response).use_t2i(False)
                    return
                        
        except aiohttp.ClientError as e:
            logger.error(f"网络连接错误：{e}")
            yield message.plain_result("无法连接到QQ估价服务器，请稍后重试或检查网络连接").use_t2i(False)
            return
        except asyncio.TimeoutError:
            logger.error("请求超时")
            yield message.plain_result("请求超时，请稍后重试").use_t2i(False)
            return
        except json.JSONDecodeError:
            logger.error("JSON解析错误")
            yield message.plain_result("服务器返回数据格式错误").use_t2i(False)
            return
        except Exception as e:
            logger.error(f"请求QQ估价时发生错误：{e}")
            yield message.plain_result(f"请求QQ估价时发生错误：{str(e)}").use_t2i(False)
            return

    async def terminate(self):
        """插件卸载/重载时调用"""
        pass
