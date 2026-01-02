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
from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.core.utils.session_waiter import session_waiter, SessionController
from astrbot.core.message.components import Record
from astrbot.core.message.message_event_result import MessageChain

logger = logging.getLogger("astrbot")


@register("D-G-N-C-J", "Tinyxi", "早晚安记录+王者战力查询+城际路线查询+AI绘画+点歌功能", "1.0.0", "")
class Main(Star):
    def __init__(self, context: Context, config: "AstrBotConfig") -> None:
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
        
        # 点歌功能配置，从配置文件读取
        self.music_platform = config.get("music_platform", "网易")  # 网易，QQ，酷我
        self.search_display_mode = config.get("search_display_mode", "文字")  # 文字，图片
        self.send_song_mode = config.get("send_song_mode", "卡片")  # 卡片，语音
        self.enable_lyrics = config.get("enable_lyrics", False)  # 是否启用歌词
        self.timeout = config.get("timeout", 30)  # 点歌操作的超时时长（秒）
        self.playlist_page = config.get("playlist_page", 1)  # 歌单页数（默认第一页）
        self.show_song_count = config.get("show_song_count", 10)  # 展示歌曲数量
        
        # 音乐搜索API配置
        self.music_search_api = config.get("music_search_api", "https://www.example.com/api/music/search")  # 音乐聚合搜索API
        self.music_id_api = config.get("music_id_api", "https://www.example.com/api/music/id")  # 获取音乐ID API
        
        # 会话缓存，用于存储搜索结果
        self.music_search_cache = {}

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
            from astrbot.api.all import CommandResult
            yield CommandResult().message("你刚刚已经说过早安/晚安了，请30分钟后再试喵~").use_t2i(False)
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

            from astrbot.api.all import CommandResult
            yield CommandResult().message(
                f"早上好喵，{user_name}！\n现在是 {curr_human}，昨晚你睡了 {sleep_duration_human}。"
            ).use_t2i(False)
        else:
            from astrbot.api.all import CommandResult
            yield CommandResult().message(
                f"快睡觉喵，{user_name}！\n现在是 {curr_human}，你是本群今天第 {curr_day_sleeping} 个睡觉的。"
            ).use_t2i(False)



    @filter.command("战力查询")
    async def hero_power(self, message: AstrMessageEvent):
        """王者英雄战力查询，支持双区双系统"""
        msg = message.message_str.replace("战力查询", "").strip()
        
        if not msg:
            from astrbot.api.all import CommandResult
            yield CommandResult().error("正确示例：\n\n战力查询 小乔").use_t2i(False)
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
                        from astrbot.api.all import CommandResult
                        yield CommandResult().error("请求战力查询失败，服务器返回错误状态码").use_t2i(False)
                        return
                    
                    result = await resp.json()
                    
                    if result.get("code") != 200:
                        from astrbot.api.all import CommandResult
                        yield CommandResult().error(f"查询失败：{result.get('msg', '未知错误')}").use_t2i(False)
                        return
                    
                    data = result.get("data", {})
                    if not data:
                        from astrbot.api.all import CommandResult
                        yield CommandResult().error("未查询到该英雄的战力信息").use_t2i(False)
                        return
                    
                    # 格式化输出结果
                    response = f"{data.get('name', hero_name)}\n"
                    response += f"国服最低：{data.get('guobiao', '0')}\n"
                    response += f"【{data.get('province', '未知省')}】省标最低：{data.get('provincePower', '0')}\n"
                    response += f"【{data.get('city', '未知市')}】市标最低：{data.get('cityPower', '0')}\n"
                    response += f"【{data.get('area', '未知区')}】区标最低：{data.get('areaPower', '0')}"
                    
                    from astrbot.api.all import CommandResult
                    yield CommandResult().message(response).use_t2i(False)
                    return
                        
        except aiohttp.ClientError as e:
            logger.error(f"网络连接错误：{e}")
            from astrbot.api.all import CommandResult
            yield CommandResult().error("无法连接到战力查询服务器，请稍后重试或检查网络连接").use_t2i(False)
            return
        except asyncio.TimeoutError:
            logger.error("请求超时")
            from astrbot.api.all import CommandResult
            yield CommandResult().error("请求超时，请稍后重试").use_t2i(False)
            return
        except json.JSONDecodeError:
            logger.error("JSON解析错误")
            from astrbot.api.all import CommandResult
            yield CommandResult().error("服务器返回数据格式错误").use_t2i(False)
            return
        except Exception as e:
            logger.error(f"请求战力查询时发生错误：{e}")
            from astrbot.api.all import CommandResult
            yield CommandResult().error(f"请求战力查询时发生错误：{str(e)}").use_t2i(False)
            return

    @filter.command("路线查询")
    async def city_route(self, message: AstrMessageEvent):
        """城际路线查询，支持异步请求"""
        msg = message.message_str.replace("路线查询", "").strip()
        
        if not msg:
            from astrbot.api.all import CommandResult
            yield CommandResult().error("正确指令：路线查询 <出发地> <目的地>\n\n示例：路线查询 广州 深圳").use_t2i(False)
            return
        
        # 解析出发地和目的地
        parts = msg.split()
        if len(parts) < 2:
            from astrbot.api.all import CommandResult
            yield CommandResult().error("请输入完整的出发地和目的地\n\n正确指令：路线查询 <出发地> <目的地>\n\n示例：路线查询 广州 深圳").use_t2i(False)
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
                        from astrbot.api.all import CommandResult
                        yield CommandResult().error("请求路线查询失败，服务器返回错误状态码").use_t2i(False)
                        return
                    
                    result = await resp.json()
                    
                    if result.get("code") != 200:
                        from astrbot.api.all import CommandResult
                        yield CommandResult().error(f"查询失败：{result.get('msg', '未知错误')}").use_t2i(False)
                        return
                    
                    data = result.get("data", {})
                    if not data:
                        from astrbot.api.all import CommandResult
                        yield CommandResult().error("未查询到该路线的信息").use_t2i(False)
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
                    
                    from astrbot.api.all import CommandResult
                    yield CommandResult().message(response).use_t2i(False)
                    return
                        
        except aiohttp.ClientError as e:
            logger.error(f"网络连接错误：{e}")
            from astrbot.api.all import CommandResult
            yield CommandResult().error("无法连接到路线查询服务器，请稍后重试或检查网络连接").use_t2i(False)
            return
        except asyncio.TimeoutError:
            logger.error("请求超时")
            from astrbot.api.all import CommandResult
            yield CommandResult().error("请求超时，请稍后重试").use_t2i(False)
            return
        except json.JSONDecodeError:
            logger.error("JSON解析错误")
            from astrbot.api.all import CommandResult
            yield CommandResult().error("服务器返回数据格式错误").use_t2i(False)
            return
        except Exception as e:
            logger.error(f"请求路线查询时发生错误：{e}")
            from astrbot.api.all import CommandResult
            yield CommandResult().error(f"请求路线查询时发生错误：{str(e)}").use_t2i(False)
            return

    @filter.regex(r"^[Aa][Ii]绘画")
    async def ai_painting(self, message: AstrMessageEvent):
        """AI绘画功能，根据提示词生成图片"""
        # 提取提示词，支持大小写AI
        import re
        msg = re.sub(r"^[Aa][Ii]绘画", "", message.message_str).strip()
        
        if not msg:
            from astrbot.api.all import CommandResult
            yield CommandResult().error("正确指令：ai绘画 <提示词>\n\n示例：ai绘画 一条狗").use_t2i(False)
            return
        
        prompt = msg.strip()
        api_url = "https://api.jkyai.top/API/ks/api.php"
        
        try:
            # 先回复用户正在生成图片
            from astrbot.api.all import CommandResult
            yield CommandResult().message("正在制作精美图片..........").use_t2i(False)
            
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
                        from astrbot.api.all import CommandResult
                        yield CommandResult().error("请求AI绘画失败，服务器返回错误状态码").use_t2i(False)
                        return
                    
                    image_url = await resp.text()
                    
                    # 检查返回的是否为有效的URL
                    if not image_url.startswith("http"):
                        from astrbot.api.all import CommandResult
                        yield CommandResult().error(f"AI绘画生成失败：{image_url}").use_t2i(False)
                        return
                    
                    # 直接返回图片URL，让系统自动处理
                    from astrbot.api.all import CommandResult
                    yield CommandResult().image_result(image_url).use_t2i(False)
                    return
                        
        except aiohttp.ClientError as e:
            logger.error(f"网络连接错误：{e}")
            from astrbot.api.all import CommandResult
            yield CommandResult().error("无法连接到AI绘画服务器，请稍后重试或检查网络连接").use_t2i(False)
            return
        except asyncio.TimeoutError:
            logger.error("请求超时")
            from astrbot.api.all import CommandResult
            yield CommandResult().error("请求超时，请稍后重试").use_t2i(False)
            return
        except Exception as e:
            logger.error(f"请求AI绘画时发生错误：{e}")
            from astrbot.api.all import CommandResult
            yield CommandResult().error(f"请求AI绘画时发生错误：{str(e)}").use_t2i(False)
            return

    @filter.command("点歌")
    async def music_search(self, message: AstrMessageEvent):
        """点歌功能，支持搜索歌曲并播放"""
        # 解析用户输入，提取歌名
        msg = message.message_str.replace("点歌", "").strip()
        
        if not msg:
            # 用户未输入歌名
            from astrbot.api.all import CommandResult
            yield CommandResult().error("未输入歌名哦，示例：\n\n点歌 泡沫").use_t2i(False)
            return
        
        # 搜索歌曲
        song_name = msg.strip()
        songs = await self._search_music(song_name)
        
        if not songs:
            from astrbot.api.all import CommandResult
            yield CommandResult().error("未找到相关歌曲哦，请尝试其他关键词").use_t2i(False)
            return
        
        # 展示搜索结果
        await self._show_search_result(message, songs)
        
        # 缓存搜索结果
        session_id = message.unified_msg_origin
        self.music_search_cache[session_id] = songs
        
        # 等待用户输入序号
        @session_waiter(timeout=self.timeout, record_history_chains=False)
        async def music_select_waiter(controller: SessionController, event: AstrMessageEvent):
            """等待用户选择歌曲"""
            try:
                index = int(event.message_str.strip())
                if 1 <= index <= len(songs):
                    selected_song = songs[index - 1]
                    await self._play_song(message, selected_song)
                    controller.stop()
                    return
            except ValueError:
                pass
        
        try:
            await music_select_waiter(message)
        except TimeoutError:
            from astrbot.api.all import CommandResult
            yield CommandResult().error("已超时，请重新点歌").use_t2i(False)
        except Exception as e:
            logger.error(f"点歌时发生错误：{e}")
            from astrbot.api.all import CommandResult
            yield CommandResult().error(f"点歌时发生错误：{str(e)}").use_t2i(False)
        finally:
            # 清除缓存
            if session_id in self.music_search_cache:
                del self.music_search_cache[session_id]
    
    async def _search_music(self, keyword: str) -> list:
        """搜索音乐"""
        try:
            # 调用音乐聚合搜索API
            async with aiohttp.ClientSession() as session:
                params = {
                    "keyword": keyword,
                    "platform": self.music_platform,
                    "page": self.playlist_page,
                    "limit": self.show_song_count
                }
                async with session.get(self.music_search_api, params=params) as resp:
                    if resp.status != 200:
                        logger.error(f"音乐搜索失败，状态码：{resp.status}")
                        return []
                    result = await resp.json()
                    return result.get("songs", [])[:self.show_song_count]
        except Exception as e:
            logger.error(f"音乐搜索失败：{e}")
            return []
    
    async def _show_search_result(self, message: AstrMessageEvent, songs: list):
        """展示搜索结果"""
        if self.search_display_mode == "文字":
            # 文字模式展示
            response = "搜索结果：\n"
            for i, song in enumerate(songs):
                response += f"{i+1}. {song.get('name', '未知歌曲')} - {song.get('artist', '未知歌手')}\n"
            
            from astrbot.api.all import CommandResult
            await message.send(CommandResult().message(response).use_t2i(False))
        else:
            # 图片模式展示（这里简化处理，实际应该生成图片）
            response = "搜索结果：\n"
            for i, song in enumerate(songs):
                response += f"{i+1}. {song.get('name', '未知歌曲')} - {song.get('artist', '未知歌手')}\n"
            
            from astrbot.api.all import CommandResult
            await message.send(CommandResult().message(response).use_t2i(False))
    
    async def _play_song(self, message: AstrMessageEvent, song: dict):
        """播放歌曲"""
        song_id = song.get("id")
        
        if not song_id:
            from astrbot.api.all import CommandResult
            await message.send(CommandResult().error("歌曲ID获取失败").use_t2i(False))
            return
        
        try:
            if self.send_song_mode == "卡片":
                # 卡片模式播放（仅支持QQ平台）
                platform_name = message.get_platform_name()
                if platform_name == "aiocqhttp":
                    # 调用QQ机器人API发送音乐卡片
                    from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import AiocqhttpMessageEvent
                    assert isinstance(message, AiocqhttpMessageEvent)
                    client = message.bot
                    is_private = message.is_private_chat()
                    
                    # 获取歌曲ID
                    music_id = await self._get_music_id(song_id)
                    
                    payloads = {
                        "message": [
                            {
                                "type": "music",
                                "data": {
                                    "type": "163" if self.music_platform == "网易" else "qq" if self.music_platform == "QQ" else "163",
                                    "id": str(music_id),
                                },
                            }
                        ],
                    }
                    
                    if is_private:
                        payloads["user_id"] = message.get_sender_id()
                        await client.api.call_action("send_private_msg", **payloads)
                    else:
                        payloads["group_id"] = message.get_group_id()
                        await client.api.call_action("send_group_msg", **payloads)
                else:
                    # 其他平台不支持卡片模式，降级为文字模式
                    await self._send_text_song(message, song)
            elif self.send_song_mode == "语音":
                # 语音模式播放
                audio_url = song.get("audio_url")
                if audio_url:
                    await message.send(message.chain_result([Record.fromURL(audio_url)]))
                else:
                    # 降级为文字模式
                    await self._send_text_song(message, song)
            else:
                # 默认文字模式
                await self._send_text_song(message, song)
            
            # 如果启用了歌词，发送歌词图片
            if self.enable_lyrics:
                await self._send_lyrics(message, song_id)
                
        except Exception as e:
            logger.error(f"播放歌曲失败：{e}")
            from astrbot.api.all import CommandResult
            await message.send(CommandResult().error(f"播放歌曲失败：{str(e)}").use_t2i(False))
    
    async def _get_music_id(self, song_id: str) -> str:
        """获取音乐平台的歌曲ID"""
        try:
            async with aiohttp.ClientSession() as session:
                params = {
                    "song_id": song_id,
                    "platform": self.music_platform
                }
                async with session.get(self.music_id_api, params=params) as resp:
                    if resp.status != 200:
                        logger.error(f"获取音乐ID失败，状态码：{resp.status}")
                        return song_id
                    result = await resp.json()
                    return result.get("music_id", song_id)
        except Exception as e:
            logger.error(f"获取音乐ID失败：{e}")
            return song_id
    
    async def _send_text_song(self, message: AstrMessageEvent, song: dict):
        """发送文字形式的歌曲信息"""
        song_name = song.get("name", "未知歌曲")
        artist = song.get("artist", "未知歌手")
        song_url = song.get("url", "")
        
        response = f"{song_name} - {artist}\n"
        if song_url:
            response += f"链接：{song_url}\n"
        
        from astrbot.api.all import CommandResult
        await message.send(CommandResult().message(response).use_t2i(False))
    
    async def _send_lyrics(self, message: AstrMessageEvent, song_id: str):
        """发送歌词图片"""
        # 这里简化处理，实际应该调用API获取歌词并生成图片
        from astrbot.api.all import CommandResult
        await message.send(CommandResult().message("歌词功能暂未实现").use_t2i(False))
    
    async def terminate(self):
        """插件卸载/重载时调用"""
        pass
