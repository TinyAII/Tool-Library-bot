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
        
    # 菜单样式的HTML模板
    MENU_TEMPLATE = '''
    <!DOCTYPE html>
    <html lang="zh-CN">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>工具箱菜单</title>
        <style>
            body {
                font-family: 'Microsoft YaHei', Arial, sans-serif;
                background-color: #f5f5f5;
                margin: 0;
                padding: 20px;
                line-height: 2.0;
            }
            .container {
                max-width: 950px;
                margin: 0 auto;
                background-color: white;
                padding: 40px;
                border-radius: 12px;
                box-shadow: 0 4px 15px rgba(0,0,0,0.15);
            }
            .menu-title {
                font-size: 32px;
                font-weight: bold;
                color: #28a745;
                text-align: center;
                margin-bottom: 40px;
                padding: 15px;
                background-color: #e8f5e8;
                border-radius: 8px;
                text-shadow: 2px 2px 4px rgba(0,0,0,0.1);
            }
            .category-title {
                font-size: 24px;
                font-weight: bold;
                color: #17a2b8;
                margin: 30px 0 20px 0;
                padding: 10px 0;
                border-bottom: 3px solid #17a2b8;
                text-transform: uppercase;
                letter-spacing: 1px;
            }
            .menu-item {
                font-size: 18px;
                line-height: 2.2;
                margin: 15px 0;
                padding: 10px;
                background-color: #f8f9fa;
                border-radius: 8px;
                border-left: 4px solid #ffc107;
            }
            .command-name {
                font-weight: bold;
                color: #dc3545;
                font-size: 24px;
            }
            .command-format {
                color: #dc3545;
                font-weight: bold;
                font-size: 20px;
            }
            .command-desc {
                color: #495057;
                font-weight: bold;
            }
            .example-section {
                margin-top: 40px;
                padding-top: 20px;
                border-top: 2px solid #e9ecef;
            }
            .example-title {
                font-size: 22px;
                font-weight: bold;
                color: #6f42c1;
                margin-bottom: 20px;
            }
            .example-item {
                font-size: 16px;
                line-height: 1.8;
                margin: 10px 0;
                padding: 10px;
                background-color: #e7f5ff;
                border-radius: 6px;
                border-left: 4px solid #007bff;
            }
            .note-section {
                margin-top: 30px;
                padding: 15px;
                background-color: #fff3cd;
                border: 1px solid #ffeeba;
                border-radius: 6px;
                color: #856404;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1 class="menu-title">🔧 工具箱插件菜单 🔧</h1>
            {{content}}
        </div>
    </body>
    </html>
    '''
    
    # 战力查询结果的HTML模板（支持四个战区）
    HERO_POWER_TEMPLATE = '''
    <!DOCTYPE html>
    <html lang="zh-CN">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>王者荣耀战力查询</title>
        <style>
            body {
                font-family: 'Microsoft YaHei', Arial, sans-serif;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                margin: 0;
                padding: 30px;
                line-height: 1.6;
                color: #333;
            }
            .container {
                max-width: 800px;
                margin: 0 auto;
                background-color: white;
                border-radius: 15px;
                padding: 40px;
                box-shadow: 0 8px 32px rgba(0,0,0,0.15);
            }
            .title {
                font-size: 32px;
                font-weight: bold;
                text-align: center;
                color: #e74c3c;
                margin-bottom: 30px;
                text-shadow: 2px 2px 4px rgba(0,0,0,0.1);
            }
            .hero-header {
                text-align: center;
                margin-bottom: 30px;
                padding: 20px;
                background-color: #ecf0f1;
                border-radius: 10px;
            }
            .hero-name {
                font-size: 36px;
                font-weight: bold;
                color: #3498db;
                margin-bottom: 10px;
            }
            .update-time {
                font-size: 14px;
                color: #7f8c8d;
            }
            .platforms-grid {
                display: grid;
                grid-template-columns: 1fr;
                gap: 30px;
                margin: 30px 0;
            }
            .platform-card {
                background-color: #f8f9fa;
                border-radius: 12px;
                padding: 30px;
                box-shadow: 0 4px 12px rgba(0,0,0,0.1);
                border-top: 5px solid #3498db;
            }
            .platform-name {
                font-size: 24px;
                font-weight: bold;
                color: #2c3e50;
                text-align: center;
                margin-bottom: 25px;
                padding-bottom: 15px;
                border-bottom: 2px solid #ecf0f1;
            }
            .power-list {
                display: flex;
                flex-direction: column;
                gap: 15px;
            }
            .power-item {
                background-color: white;
                border-radius: 10px;
                padding: 18px 25px;
                box-shadow: 0 2px 8px rgba(0,0,0,0.1);
                border-left: 5px solid #e67e22;
                display: flex;
                justify-content: space-between;
                align-items: center;
                font-size: 18px;
                font-weight: bold;
            }
            .power-section {
                color: #e74c3c;
                font-size: 20px;
                font-weight: bold;
            }
            .power-region {
                color: #3498db;
                font-size: 18px;
                font-weight: bold;
            }
            .power-num {
                color: #27ae60;
                font-size: 22px;
                font-weight: bold;
            }
            .footer {
                margin-top: 30px;
                text-align: center;
                color: #95a5a6;
                font-size: 14px;
                padding-top: 20px;
                border-top: 1px solid #ecf0f1;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1 class="title">🏆 王者荣耀战力查询 🏆</h1>
            <div class="hero-header">
                <div class="hero-name">{{hero_name}}</div>
                <div class="update-time">数据更新时间：{{updatetime}}</div>
            </div>
            <div class="platforms-grid">
                <!-- Android QQ区 -->
                <div class="platform-card">
                    <div class="platform-name">📱 Android QQ</div>
                    <div class="power-list">
                        <div class="power-item">
                            <span><span class="power-section">【国服】</span><span class="power-region">[全服]</span></span>
                            <span class="power-num">{{aqq_guobiao}}</span>
                        </div>
                        <div class="power-item">
                            <span><span class="power-section">【省】</span><span class="power-region">[{{aqq_province}}]</span></span>
                            <span class="power-num">{{aqq_provincePower}}</span>
                        </div>
                        <div class="power-item">
                            <span><span class="power-section">【市】</span><span class="power-region">[{{aqq_city}}]</span></span>
                            <span class="power-num">{{aqq_cityPower}}</span>
                        </div>
                        <div class="power-item">
                            <span><span class="power-section">【区】</span><span class="power-region">[{{aqq_area}}]</span></span>
                            <span class="power-num">{{aqq_areaPower}}</span>
                        </div>
                    </div>
                </div>
                <!-- Android 微信区 -->
                <div class="platform-card">
                    <div class="platform-name">📱 Android 微信</div>
                    <div class="power-list">
                        <div class="power-item">
                            <span><span class="power-section">【国服】</span><span class="power-region">[全服]</span></span>
                            <span class="power-num">{{awx_guobiao}}</span>
                        </div>
                        <div class="power-item">
                            <span><span class="power-section">【省】</span><span class="power-region">[{{awx_province}}]</span></span>
                            <span class="power-num">{{awx_provincePower}}</span>
                        </div>
                        <div class="power-item">
                            <span><span class="power-section">【市】</span><span class="power-region">[{{awx_city}}]</span></span>
                            <span class="power-num">{{awx_cityPower}}</span>
                        </div>
                        <div class="power-item">
                            <span><span class="power-section">【区】</span><span class="power-region">[{{awx_area}}]</span></span>
                            <span class="power-num">{{awx_areaPower}}</span>
                        </div>
                    </div>
                </div>
                <!-- iOS QQ区 -->
                <div class="platform-card">
                    <div class="platform-name">🍎 iOS QQ</div>
                    <div class="power-list">
                        <div class="power-item">
                            <span><span class="power-section">【国服】</span><span class="power-region">[全服]</span></span>
                            <span class="power-num">{{iqq_guobiao}}</span>
                        </div>
                        <div class="power-item">
                            <span><span class="power-section">【省】</span><span class="power-region">[{{iqq_province}}]</span></span>
                            <span class="power-num">{{iqq_provincePower}}</span>
                        </div>
                        <div class="power-item">
                            <span><span class="power-section">【市】</span><span class="power-region">[{{iqq_city}}]</span></span>
                            <span class="power-num">{{iqq_cityPower}}</span>
                        </div>
                        <div class="power-item">
                            <span><span class="power-section">【区】</span><span class="power-region">[{{iqq_area}}]</span></span>
                            <span class="power-num">{{iqq_areaPower}}</span>
                        </div>
                    </div>
                </div>
                <!-- iOS 微信区 -->
                <div class="platform-card">
                    <div class="platform-name">🍎 iOS 微信</div>
                    <div class="power-list">
                        <div class="power-item">
                            <span><span class="power-section">【国服】</span><span class="power-region">[全服]</span></span>
                            <span class="power-num">{{iwx_guobiao}}</span>
                        </div>
                        <div class="power-item">
                            <span><span class="power-section">【省】</span><span class="power-region">[{{iwx_province}}]</span></span>
                            <span class="power-num">{{iwx_provincePower}}</span>
                        </div>
                        <div class="power-item">
                            <span><span class="power-section">【市】</span><span class="power-region">[{{iwx_city}}]</span></span>
                            <span class="power-num">{{iwx_cityPower}}</span>
                        </div>
                        <div class="power-item">
                            <span><span class="power-section">【区】</span><span class="power-region">[{{iwx_area}}]</span></span>
                            <span class="power-num">{{iwx_areaPower}}</span>
                        </div>
                    </div>
                </div>
            </div>
            <div class="footer">
                查询时间：{{current_time}} | 数据来源：王者荣耀官方
            </div>
        </div>
    </body>
    </html>
    '''
    
    # 路线查询结果的HTML模板
    ROUTE_QUERY_TEMPLATE = '''
    <!DOCTYPE html>
    <html lang="zh-CN">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>城际路线查询</title>
        <style>
            body {
                font-family: 'Microsoft YaHei', Arial, sans-serif;
                background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
                margin: 0;
                padding: 30px;
                line-height: 1.6;
                color: #333;
            }
            .container {
                max-width: 600px;
                margin: 0 auto;
                background-color: white;
                border-radius: 15px;
                padding: 40px;
                box-shadow: 0 8px 32px rgba(0,0,0,0.15);
            }
            .title {
                font-size: 28px;
                font-weight: bold;
                text-align: center;
                color: #3498db;
                margin-bottom: 30px;
                text-shadow: 2px 2px 4px rgba(0,0,0,0.1);
            }
            .route-header {
                text-align: center;
                margin-bottom: 30px;
                padding: 20px;
                background-color: #e3f2fd;
                border-radius: 10px;
            }
            .route-title {
                font-size: 32px;
                font-weight: bold;
                color: #1976d2;
                margin-bottom: 10px;
            }
            .route-desc {
                font-size: 16px;
                color: #666;
            }
            .info-grid {
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 15px;
                margin: 30px 0;
            }
            .info-item {
                background-color: #f8f9fa;
                padding: 20px;
                border-radius: 8px;
                box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            }
            .info-label {
                font-size: 14px;
                color: #7f8c8d;
                margin-bottom: 5px;
                text-transform: uppercase;
                letter-spacing: 1px;
            }
            .info-value {
                font-size: 22px;
                font-weight: bold;
                color: #2c3e50;
            }
            .route-info {
                margin-top: 20px;
                padding: 20px;
                background-color: #e8f5e8;
                border-radius: 8px;
                border-left: 5px solid #4caf50;
            }
            .route-info-label {
                font-size: 16px;
                font-weight: bold;
                color: #2e7d32;
                margin-bottom: 10px;
            }
            .route-info-content {
                font-size: 18px;
                color: #388e3c;
            }
            .road-conditions {
                margin-top: 20px;
                padding: 15px;
                background-color: #fff3cd;
                border: 1px solid #ffeeba;
                border-radius: 6px;
                color: #856404;
            }
            .footer {
                margin-top: 30px;
                text-align: center;
                color: #95a5a6;
                font-size: 14px;
                padding-top: 20px;
                border-top: 1px solid #ecf0f1;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1 class="title">🗺️ 城际路线查询 🗺️</h1>
            <div class="route-header">
                <div class="route-title">{{from_city}} → {{to_city}}</div>
                <div class="route-desc">为您提供详细的城际出行信息</div>
            </div>
            <div class="info-grid">
                <div class="info-item">
                    <div class="info-label">总距离</div>
                    <div class="info-value">{{distance}}</div>
                </div>
                <div class="info-item">
                    <div class="info-label">总耗时</div>
                    <div class="info-value">{{time}}</div>
                </div>
                <div class="info-item">
                    <div class="info-label">油费</div>
                    <div class="info-value">{{fuelcosts}}</div>
                </div>
                <div class="info-item">
                    <div class="info-label">过桥费</div>
                    <div class="info-value">{{bridgetoll}}</div>
                </div>
                <div class="info-item" style="grid-column: 1 / -1;">
                    <div class="info-label">总费用</div>
                    <div class="info-value">{{totalcost}}</div>
                </div>
            </div>
            <div class="route-info">
                <div class="route-info-label">推荐路线</div>
                <div class="route-info-content">{{corese}}</div>
            </div>
            <div class="road-conditions">
                <strong>路况信息：</strong>{{roadconditions}}
            </div>
            <div class="footer">
                查询时间：{{current_time}} | 数据来源：专业地图服务
            </div>
        </div>
    </body>
    </html>
    '''
    
    # Minecraft服务器查询结果的HTML模板
    MC_SERVER_TEMPLATE = '''
    <!DOCTYPE html>
    <html lang="zh-CN">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Minecraft服务器状态</title>
        <style>
            body {
                font-family: 'Microsoft YaHei', Arial, sans-serif;
                background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%);
                margin: 0;
                padding: 30px;
                line-height: 1.6;
                color: #333;
            }
            .container {
                max-width: 600px;
                margin: 0 auto;
                background-color: white;
                border-radius: 15px;
                padding: 40px;
                box-shadow: 0 8px 32px rgba(0,0,0,0.15);
            }
            .title {
                font-size: 28px;
                font-weight: bold;
                text-align: center;
                color: #2196f3;
                margin-bottom: 30px;
                text-shadow: 2px 2px 4px rgba(0,0,0,0.1);
            }
            .server-header {
                text-align: center;
                margin-bottom: 30px;
                padding: 20px;
                background-color: #e3f2fd;
                border-radius: 10px;
            }
            .server-title {
                font-size: 32px;
                font-weight: bold;
                color: #1976d2;
                margin-bottom: 10px;
            }
            .server-desc {
                font-size: 16px;
                color: #666;
            }
            .status-indicator {
                text-align: center;
                margin-bottom: 30px;
            }
            .status-badge {
                display: inline-block;
                padding: 10px 20px;
                border-radius: 25px;
                font-size: 20px;
                font-weight: bold;
            }
            .status-online {
                background-color: #4caf50;
                color: white;
            }
            .status-offline {
                background-color: #f44336;
                color: white;
            }
            .info-grid {
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 15px;
                margin: 30px 0;
            }
            .info-item {
                background-color: #f8f9fa;
                padding: 20px;
                border-radius: 8px;
                box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            }
            .info-label {
                font-size: 14px;
                color: #7f8c8d;
                margin-bottom: 5px;
                text-transform: uppercase;
                letter-spacing: 1px;
            }
            .info-value {
                font-size: 22px;
                font-weight: bold;
                color: #2c3e50;
            }
            .footer {
                margin-top: 30px;
                text-align: center;
                color: #95a5a6;
                font-size: 14px;
                padding-top: 20px;
                border-top: 1px solid #ecf0f1;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1 class="title">🎮 Minecraft服务器状态 🎮</h1>
            <div class="server-header">
                <div class="server-title">{{server_addr}}</div>
                <div class="server-desc">Minecraft服务器详细状态信息</div>
            </div>
            <div class="status-indicator">
                <div class="status-badge status-{{online_status}}">{{online_text}}</div>
            </div>
            <div class="info-grid">
                <div class="info-item">
                    <div class="info-label">IP地址</div>
                    <div class="info-value">{{ip}}</div>
                </div>
                <div class="info-item">
                    <div class="info-label">端口</div>
                    <div class="info-value">{{port}}</div>
                </div>
                <div class="info-item">
                    <div class="info-label">当前玩家</div>
                    <div class="info-value">{{players}}</div>
                </div>
                <div class="info-item">
                    <div class="info-label">最大玩家</div>
                    <div class="info-value">{{max_players}}</div>
                </div>
                <div class="info-item" style="grid-column: 1 / -1;">
                    <div class="info-label">服务器版本</div>
                    <div class="info-value">{{version}}</div>
                </div>
            </div>
            <div class="footer">
                查询时间：{{current_time}} | 数据来源：专业游戏服务器监控服务
            </div>
        </div>
    </body>
    </html>
    '''
    
    # 油价查询结果的HTML模板
    OIL_PRICE_TEMPLATE = '''
    <!DOCTYPE html>
    <html lang="zh-CN">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>油价查询结果</title>
        <style>
            body {
                font-family: 'Microsoft YaHei', Arial, sans-serif;
                background: linear-gradient(135deg, #ff6b6b 0%, #ee5a24 100%);
                margin: 0;
                padding: 30px;
                line-height: 1.6;
                color: #333;
            }
            .container {
                max-width: 600px;
                margin: 0 auto;
                background-color: white;
                border-radius: 15px;
                padding: 40px;
                box-shadow: 0 8px 32px rgba(0,0,0,0.15);
            }
            .title {
                font-size: 28px;
                font-weight: bold;
                text-align: center;
                color: #c0392b;
                margin-bottom: 30px;
                text-shadow: 2px 2px 4px rgba(0,0,0,0.1);
            }
            .city-header {
                text-align: center;
                margin-bottom: 30px;
                padding: 20px;
                background-color: #ffeaa7;
                border-radius: 10px;
            }
            .city-name {
                font-size: 32px;
                font-weight: bold;
                color: #d35400;
                margin-bottom: 10px;
            }
            .city-desc {
                font-size: 16px;
                color: #666;
            }
            .trend-info {
                text-align: center;
                margin-bottom: 30px;
                padding: 15px;
                background-color: #e8f5e8;
                border-radius: 8px;
                border-left: 5px solid #4caf50;
            }
            .trend-label {
                font-size: 18px;
                font-weight: bold;
                color: #2e7d32;
            }
            .info-grid {
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 15px;
                margin: 30px 0;
            }
            .info-item {
                background-color: #f8f9fa;
                padding: 20px;
                border-radius: 8px;
                box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            }
            .info-label {
                font-size: 14px;
                color: #7f8c8d;
                margin-bottom: 5px;
                text-transform: uppercase;
                letter-spacing: 1px;
            }
            .info-value {
                font-size: 22px;
                font-weight: bold;
                color: #e67e22;
            }
            .footer {
                margin-top: 30px;
                text-align: center;
                color: #95a5a6;
                font-size: 14px;
                padding-top: 20px;
                border-top: 1px solid #ecf0f1;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1 class="title">⛽ 油价查询结果 ⛽</h1>
            <div class="city-header">
                <div class="city-name">{{city_name}}</div>
                <div class="city-desc">最新油价信息</div>
            </div>
            <div class="trend-info">
                <div class="trend-label">趋势：前{{trend}}</div>
            </div>
            <div class="info-grid">
                <div class="info-item">
                    <div class="info-label">92号汽油</div>
                    <div class="info-value">{{oil_92}}元/升</div>
                </div>
                <div class="info-item">
                    <div class="info-label">95号汽油</div>
                    <div class="info-value">{{oil_95}}元/升</div>
                </div>
                <div class="info-item">
                    <div class="info-label">98号汽油</div>
                    <div class="info-value">{{oil_98}}元/升</div>
                </div>
                <div class="info-item">
                    <div class="info-label">0号柴油</div>
                    <div class="info-value">{{oil_0}}元/升</div>
                </div>
            </div>
            <div class="footer">
                查询时间：{{current_time}} | 数据来源：专业油价查询服务
            </div>
        </div>
    </body>
    </html>
    '''
    
    # QQ估价结果的HTML模板
    QQ_VALUATION_TEMPLATE = '''
    <!DOCTYPE html>
    <html lang="zh-CN">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>QQ估价结果</title>
        <style>
            body {
                font-family: 'Microsoft YaHei', Arial, sans-serif;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                margin: 0;
                padding: 30px;
                line-height: 1.6;
                color: #333;
            }
            .container {
                max-width: 600px;
                margin: 0 auto;
                background-color: white;
                border-radius: 15px;
                padding: 40px;
                box-shadow: 0 8px 32px rgba(0,0,0,0.15);
            }
            .title {
                font-size: 28px;
                font-weight: bold;
                text-align: center;
                color: #667eea;
                margin-bottom: 30px;
                text-shadow: 2px 2px 4px rgba(0,0,0,0.1);
            }
            .qq-header {
                text-align: center;
                margin-bottom: 30px;
                padding: 20px;
                background-color: #e8f5e8;
                border-radius: 10px;
            }
            .qq-number {
                font-size: 32px;
                font-weight: bold;
                color: #2e7d32;
                margin-bottom: 10px;
            }
            .qq-desc {
                font-size: 16px;
                color: #666;
            }
            .valuation-info {
                text-align: center;
                margin-bottom: 30px;
                padding: 20px;
                background-color: #fff3cd;
                border-radius: 10px;
                border: 2px solid #ffc107;
            }
            .valuation-label {
                font-size: 18px;
                color: #856404;
                margin-bottom: 10px;
            }
            .valuation-value {
                font-size: 48px;
                font-weight: bold;
                color: #d35400;
            }
            .info-grid {
                display: grid;
                grid-template-columns: 1fr;
                gap: 15px;
                margin: 30px 0;
            }
            .info-item {
                background-color: #f8f9fa;
                padding: 20px;
                border-radius: 8px;
                box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            }
            .info-label {
                font-size: 14px;
                color: #7f8c8d;
                margin-bottom: 10px;
                text-transform: uppercase;
                letter-spacing: 1px;
            }
            .info-value {
                font-size: 18px;
                font-weight: bold;
                color: #2c3e50;
            }
            .footer {
                margin-top: 30px;
                text-align: center;
                color: #95a5a6;
                font-size: 14px;
                padding-top: 20px;
                border-top: 1px solid #ecf0f1;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1 class="title">💰 QQ估价结果 💰</h1>
            <div class="qq-header">
                <div class="qq-number">{{qq_number}}</div>
                <div class="qq-desc">QQ号码详细估价信息</div>
            </div>
            <div class="valuation-info">
                <div class="valuation-label">评估价值</div>
                <div class="valuation-value">{{valuation}}元</div>
            </div>
            <div class="info-grid">
                <div class="info-item">
                    <div class="info-label">特点</div>
                    <div class="info-value">{{law}}</div>
                </div>
                <div class="info-item">
                    <div class="info-label">数字特征</div>
                    <div class="info-value">{{digit}}</div>
                </div>
            </div>
            <div class="footer">
                查询时间：{{current_time}} | 数据来源：专业QQ估价服务
            </div>
        </div>
    </body>
    </html>
    '''
    
    # 天气查询结果的HTML模板
    WEATHER_TEMPLATE = '''
    <!DOCTYPE html>
    <html lang="zh-CN">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>天气查询结果</title>
        <style>
            body {
                font-family: 'Microsoft YaHei', Arial, sans-serif;
                background: linear-gradient(135deg, #87CEEB 0%, #4682B4 100%);
                margin: 0;
                padding: 30px;
                line-height: 1.6;
                color: #333;
            }
            .container {
                max-width: 800px;
                margin: 0 auto;
                background-color: white;
                border-radius: 15px;
                padding: 40px;
                box-shadow: 0 8px 32px rgba(0,0,0,0.15);
            }
            .title {
                font-size: 32px;
                font-weight: bold;
                text-align: center;
                color: #4682B4;
                margin-bottom: 30px;
                text-shadow: 2px 2px 4px rgba(0,0,0,0.1);
            }
            .weather-header {
                text-align: center;
                margin-bottom: 30px;
                padding: 20px;
                background-color: #e3f2fd;
                border-radius: 10px;
            }
            .city-name {
                font-size: 36px;
                font-weight: bold;
                color: #1976d2;
                margin-bottom: 10px;
            }
            .update-time {
                font-size: 14px;
                color: #7f8c8d;
            }
            .basic-info {
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 20px;
                margin: 30px 0;
                text-align: center;
            }
            .weather-main {
                grid-column: 1 / -1;
                background-color: #f0f8ff;
                padding: 30px;
                border-radius: 10px;
                border: 2px solid #87CEEB;
            }
            .weather-status {
                font-size: 24px;
                font-weight: bold;
                color: #1976d2;
                margin-bottom: 10px;
            }
            .temperature {
                font-size: 64px;
                font-weight: bold;
                color: #ff5722;
                margin: 20px 0;
            }
            .basic-details {
                display: flex;
                justify-content: space-around;
                flex-wrap: wrap;
                gap: 20px;
                margin-top: 20px;
            }
            .detail-item {
                font-size: 18px;
                color: #666;
            }
            .detail-label {
                font-weight: bold;
                color: #4682B4;
            }
            .section-title {
                font-size: 24px;
                font-weight: bold;
                color: #4682B4;
                margin: 30px 0 20px 0;
                padding-bottom: 10px;
                border-bottom: 2px solid #87CEEB;
            }
            .info-grid {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                gap: 15px;
                margin: 20px 0;
            }
            .info-item {
                background-color: #f8f9fa;
                padding: 20px;
                border-radius: 8px;
                box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            }
            .info-label {
                font-size: 14px;
                color: #7f8c8d;
                margin-bottom: 10px;
                text-transform: uppercase;
                letter-spacing: 1px;
            }
            .info-value {
                font-size: 20px;
                font-weight: bold;
                color: #2c3e50;
            }
            .life-indices {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
                gap: 20px;
                margin: 20px 0;
            }
            .index-item {
                background-color: #f0f8ff;
                padding: 20px;
                border-radius: 10px;
                box-shadow: 0 2px 8px rgba(0,0,0,0.1);
                border-left: 5px solid #87CEEB;
            }
            .index-label {
                font-size: 16px;
                font-weight: bold;
                color: #1976d2;
                margin-bottom: 10px;
            }
            .index-level {
                font-size: 18px;
                font-weight: bold;
                color: #ff5722;
                margin-bottom: 5px;
            }
            .index-brief {
                font-size: 16px;
                color: #666;
                margin-bottom: 10px;
            }
            .index-advice {
                font-size: 14px;
                color: #444;
                line-height: 1.5;
            }
            .footer {
                margin-top: 40px;
                text-align: center;
                color: #95a5a6;
                font-size: 14px;
                padding-top: 20px;
                border-top: 1px solid #ecf0f1;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1 class="title">🌤️ 天气查询结果 🌤️</h1>
            <div class="weather-header">
                <div class="city-name">{{city}}</div>
                <div class="update-time">数据更新时间：{{report_time}}</div>
            </div>
            
            <div class="basic-info">
                <div class="weather-main">
                    <div class="weather-status">{{weather}}</div>
                    <div class="temperature">{{temperature}}°C</div>
                    <div class="basic-details">
                        <div class="detail-item"><span class="detail-label">风向：</span>{{wind_direction}}</div>
                        <div class="detail-item"><span class="detail-label">风力：</span>{{wind_power}}</div>
                        <div class="detail-item"><span class="detail-label">湿度：</span>{{humidity}}%</div>
                    </div>
                </div>
            </div>
            
            <h3 class="section-title">📊 扩展气象信息</h3>
            <div class="info-grid">
                <div class="info-item">
                    <div class="info-label">体感温度</div>
                    <div class="info-value">{{feels_like}}°C</div>
                </div>
                <div class="info-item">
                    <div class="info-label">能见度</div>
                    <div class="info-value">{{visibility}} km</div>
                </div>
                <div class="info-item">
                    <div class="info-label">气压</div>
                    <div class="info-value">{{pressure}} hPa</div>
                </div>
                <div class="info-item">
                    <div class="info-label">紫外线指数</div>
                    <div class="info-value">{{uv}}</div>
                </div>
                <div class="info-item">
                    <div class="info-label">空气质量</div>
                    <div class="info-value">{{aqi}}</div>
                </div>
                <div class="info-item">
                    <div class="info-label">降水量</div>
                    <div class="info-value">{{precipitation}} mm</div>
                </div>
                <div class="info-item">
                    <div class="info-label">云量</div>
                    <div class="info-value">{{cloud}}%</div>
                </div>
            </div>
            
            <h3 class="section-title">📋 生活指数</h3>
            <div class="life-indices">
                <div class="index-item">
                    <div class="index-label">穿衣指数</div>
                    <div class="index-level">{{clothing_level}}</div>
                    <div class="index-brief">{{clothing_brief}}</div>
                    <div class="index-advice">{{clothing_advice}}</div>
                </div>
                <div class="index-item">
                    <div class="index-label">紫外线指数</div>
                    <div class="index-level">{{uv_level}}</div>
                    <div class="index-brief">{{uv_brief}}</div>
                    <div class="index-advice">{{uv_advice}}</div>
                </div>
                <div class="index-item">
                    <div class="index-label">洗车指数</div>
                    <div class="index-level">{{car_wash_level}}</div>
                    <div class="index-brief">{{car_wash_brief}}</div>
                    <div class="index-advice">{{car_wash_advice}}</div>
                </div>
                <div class="index-item">
                    <div class="index-label">晾晒指数</div>
                    <div class="index-level">{{drying_level}}</div>
                    <div class="index-brief">{{drying_brief}}</div>
                    <div class="index-advice">{{drying_advice}}</div>
                </div>
                <div class="index-item">
                    <div class="index-label">空调指数</div>
                    <div class="index-level">{{air_conditioner_level}}</div>
                    <div class="index-brief">{{air_conditioner_brief}}</div>
                    <div class="index-advice">{{air_conditioner_advice}}</div>
                </div>
                <div class="index-item">
                    <div class="index-label">感冒指数</div>
                    <div class="index-level">{{cold_risk_level}}</div>
                    <div class="index-brief">{{cold_risk_brief}}</div>
                    <div class="index-advice">{{cold_risk_advice}}</div>
                </div>
                <div class="index-item">
                    <div class="index-label">运动指数</div>
                    <div class="index-level">{{exercise_level}}</div>
                    <div class="index-brief">{{exercise_brief}}</div>
                    <div class="index-advice">{{exercise_advice}}</div>
                </div>
                <div class="index-item">
                    <div class="index-label">舒适度指数</div>
                    <div class="index-level">{{comfort_level}}</div>
                    <div class="index-brief">{{comfort_brief}}</div>
                    <div class="index-advice">{{comfort_advice}}</div>
                </div>
            </div>
            
            <div class="footer">
                查询时间：{{current_time}} | 数据来源：专业天气服务
            </div>
        </div>
    </body>
    </html>
    '''
    
    # 实时科技资讯的HTML模板
    TECH_NEWS_TEMPLATE = '''
    <!DOCTYPE html>
    <html lang="zh-CN">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>实时科技资讯</title>
        <style>
            body {
                font-family: 'Microsoft YaHei', Arial, sans-serif;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                margin: 0;
                padding: 30px;
                line-height: 1.6;
                color: #333;
            }
            .container {
                max-width: 800px;
                margin: 0 auto;
                background-color: white;
                border-radius: 15px;
                padding: 40px;
                box-shadow: 0 8px 32px rgba(0,0,0,0.15);
            }
            .title {
                font-size: 32px;
                font-weight: bold;
                text-align: center;
                color: #667eea;
                margin-bottom: 30px;
                text-shadow: 2px 2px 4px rgba(0,0,0,0.1);
            }
            .header-info {
                text-align: center;
                margin-bottom: 30px;
                padding: 20px;
                background-color: #f0f8ff;
                border-radius: 10px;
            }
            .update-time {
                font-size: 14px;
                color: #7f8c8d;
                margin-bottom: 10px;
            }
            .news-count {
                font-size: 18px;
                font-weight: bold;
                color: #667eea;
            }
            .news-list {
                margin: 20px 0;
            }
            .news-item {
                font-size: 16px;
                line-height: 1.8;
                margin: 15px 0;
                padding: 15px;
                background-color: #f8f9fa;
                border-radius: 8px;
                box-shadow: 0 2px 8px rgba(0,0,0,0.1);
                border-left: 4px solid #667eea;
            }
            .news-time {
                font-weight: bold;
                color: #667eea;
                margin-right: 15px;
            }
            .news-title {
                color: #333;
            }
            .footer {
                margin-top: 40px;
                text-align: center;
                color: #95a5a6;
                font-size: 14px;
                padding-top: 20px;
                border-top: 1px solid #ecf0f1;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1 class="title">📱 实时科技资讯 📱</h1>
            <div class="header-info">
                <div class="update-time">更新时间：{{update_time}}</div>
                <div class="news-count">共 {{news_count}} 条资讯</div>
            </div>
            
            <div class="news-list">
                {{news_items}}
            </div>
            
            <div class="footer">
                查询时间：{{current_time}} | 数据来源：专业科技资讯服务
            </div>
        </div>
    </body>
    </html>
    '''
    
    # 星座运势结果的HTML模板
    CONSTELLATION_FORTUNE_TEMPLATE = '''
    <!DOCTYPE html>
    <html lang="zh-CN">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>星座运势</title>
        <style>
            body {
                font-family: 'Microsoft YaHei', Arial, sans-serif;
                background: linear-gradient(135deg, #ff9a9e 0%, #fecfef 50%, #fecfef 100%);
                margin: 0;
                padding: 30px;
                line-height: 1.6;
                color: #333;
            }
            .container {
                max-width: 800px;
                margin: 0 auto;
                background-color: white;
                border-radius: 20px;
                padding: 40px;
                box-shadow: 0 8px 32px rgba(0,0,0,0.15);
            }
            .title {
                font-size: 36px;
                font-weight: bold;
                text-align: center;
                color: #e74c3c;
                margin-bottom: 30px;
                text-shadow: 2px 2px 4px rgba(0,0,0,0.1);
            }
            .header {
                text-align: center;
                margin-bottom: 30px;
                padding: 20px;
                background-color: #f8f9fa;
                border-radius: 10px;
            }
            .constellation-name {
                font-size: 42px;
                font-weight: bold;
                color: #3498db;
                margin-bottom: 10px;
            }
            .constellation-info {
                font-size: 18px;
                color: #666;
            }
            .section {
                margin: 30px 0;
                padding: 25px;
                background-color: #f8f9fa;
                border-radius: 15px;
                box-shadow: 0 4px 12px rgba(0,0,0,0.1);
            }
            .section-title {
                font-size: 24px;
                font-weight: bold;
                color: #2c3e50;
                margin-bottom: 15px;
                border-bottom: 2px solid #3498db;
                padding-bottom: 10px;
            }
            .info-grid {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
                gap: 20px;
                margin: 20px 0;
            }
            .info-item {
                background-color: white;
                padding: 20px;
                border-radius: 10px;
                box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            }
            .info-label {
                font-size: 14px;
                color: #7f8c8d;
                margin-bottom: 10px;
                text-transform: uppercase;
                letter-spacing: 1px;
            }
            .info-value {
                font-size: 18px;
                font-weight: bold;
                color: #2c3e50;
            }
            .fortune-grid {
                display: grid;
                grid-template-columns: repeat(2, 1fr);
                gap: 20px;
                margin: 20px 0;
            }
            .fortune-item {
                background-color: white;
                padding: 20px;
                border-radius: 10px;
                box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            }
            .fortune-label {
                font-size: 16px;
                font-weight: bold;
                color: #3498db;
                margin-bottom: 10px;
            }
            .fortune-value {
                font-size: 18px;
                color: #2c3e50;
            }
            .traits {
                display: grid;
                grid-template-columns: repeat(2, 1fr);
                gap: 20px;
                margin: 20px 0;
            }
            .trait-item {
                background-color: white;
                padding: 20px;
                border-radius: 10px;
                box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            }
            .trait-label {
                font-size: 16px;
                font-weight: bold;
                margin-bottom: 10px;
            }
            .strengths {
                color: #27ae60;
            }
            .weaknesses {
                color: #e74c3c;
            }
            .matches {
                display: grid;
                grid-template-columns: repeat(2, 1fr);
                gap: 20px;
                margin: 20px 0;
            }
            .match-item {
                background-color: white;
                padding: 20px;
                border-radius: 10px;
                box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            }
            .match-label {
                font-size: 16px;
                font-weight: bold;
                margin-bottom: 10px;
            }
            .best-match {
                color: #d35400;
            }
            .good-match {
                color: #27ae60;
            }
            .fair-match {
                color: #f39c12;
            }
            .poor-match {
                color: #e74c3c;
            }
            .lucky-info {
                display: grid;
                grid-template-columns: repeat(2, 1fr);
                gap: 20px;
                margin: 20px 0;
            }
            .lucky-item {
                background-color: white;
                padding: 20px;
                border-radius: 10px;
                box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            }
            .lucky-label {
                font-size: 16px;
                font-weight: bold;
                margin-bottom: 10px;
            }
            .advice {
                background-color: #e8f5e8;
                padding: 20px;
                border-radius: 10px;
                border-left: 5px solid #4caf50;
                margin: 20px 0;
            }
            .advice-label {
                font-size: 18px;
                font-weight: bold;
                color: #2e7d32;
                margin-bottom: 10px;
            }
            .advice-content {
                font-size: 18px;
                color: #388e3c;
            }
            .footer {
                margin-top: 40px;
                text-align: center;
                color: #95a5a6;
                font-size: 14px;
                padding-top: 20px;
                border-top: 1px solid #ecf0f1;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1 class="title">✨ 星座运势 ✨</h1>
            <div class="header">
                <div class="constellation-name">{{constellation_name}}</div>
                <div class="constellation-info">{{constellation_en}} | {{date_range}} | {{element}}元素 | 守护行星：{{ruling_planet}}</div>
            </div>
            
            <div class="section">
                <div class="section-title">基本信息</div>
                <div class="info-grid">
                    <div class="info-item">
                        <div class="info-label">英文名称</div>
                        <div class="info-value">{{constellation_en}}</div>
                    </div>
                    <div class="info-item">
                        <div class="info-label">日期范围</div>
                        <div class="info-value">{{date_range}}</div>
                    </div>
                    <div class="info-item">
                        <div class="info-label">元素属性</div>
                        <div class="info-value">{{element}}</div>
                    </div>
                    <div class="info-item">
                        <div class="info-label">守护行星</div>
                        <div class="info-value">{{ruling_planet}}</div>
                    </div>
                    <div class="info-item">
                        <div class="info-label">运势周期</div>
                        <div class="info-value">{{time_period}}</div>
                    </div>
                </div>
            </div>
            
            <div class="section">
                <div class="section-title">个性特征</div>
                <div class="traits">
                    <div class="trait-item">
                        <div class="trait-label strengths">优点</div>
                        <div class="info-value">{{strengths}}</div>
                    </div>
                    <div class="trait-item">
                        <div class="trait-label weaknesses">缺点</div>
                        <div class="info-value">{{weaknesses}}</div>
                    </div>
                </div>
            </div>
            
            <div class="section">
                <div class="section-title">配对建议</div>
                <div class="matches">
                    <div class="match-item">
                        <div class="match-label best-match">最佳配对</div>
                        <div class="info-value">{{best_match}}</div>
                    </div>
                    <div class="match-item">
                        <div class="match-label good-match">较好配对</div>
                        <div class="info-value">{{good_matches}}</div>
                    </div>
                    <div class="match-item">
                        <div class="match-label fair-match">一般配对</div>
                        <div class="info-value">{{fair_matches}}</div>
                    </div>
                    <div class="match-item">
                        <div class="match-label poor-match">较差配对</div>
                        <div class="info-value">{{poor_matches}}</div>
                    </div>
                </div>
            </div>
            
            <div class="section">
                <div class="section-title">运势详情</div>
                <div class="fortune-grid">
                    <div class="fortune-item">
                        <div class="fortune-label">综合运势</div>
                        <div class="fortune-value">{{general_fortune}}</div>
                    </div>
                    <div class="fortune-item">
                        <div class="fortune-label">爱情运势</div>
                        <div class="fortune-value">{{love_fortune}}</div>
                    </div>
                    <div class="fortune-item">
                        <div class="fortune-label">事业运势</div>
                        <div class="fortune-value">{{work_fortune}}</div>
                    </div>
                    <div class="fortune-item">
                        <div class="fortune-label">财富运势</div>
                        <div class="fortune-value">{{wealth_fortune}}</div>
                    </div>
                    <div class="fortune-item">
                        <div class="fortune-label">健康运势</div>
                        <div class="fortune-value">{{health_fortune}}</div>
                    </div>
                </div>
            </div>
            
            <div class="section">
                <div class="section-title">幸运指南</div>
                <div class="lucky-info">
                    <div class="lucky-item">
                        <div class="lucky-label">幸运颜色</div>
                        <div class="info-value">{{lucky_colors}}</div>
                    </div>
                    <div class="lucky-item">
                        <div class="lucky-label">幸运数字</div>
                        <div class="info-value">{{lucky_numbers}}</div>
                    </div>
                    <div class="lucky-item">
                        <div class="lucky-label">幸运方向</div>
                        <div class="info-value">{{lucky_direction}}</div>
                    </div>
                    <div class="lucky-item">
                        <div class="lucky-label">幸运时间</div>
                        <div class="info-value">{{lucky_time}}</div>
                    </div>
                </div>
            </div>
            
            <div class="section">
                <div class="section-title">今日建议</div>
                <div class="advice">
                    <div class="advice-content">{{love_advice}}</div>
                </div>
                <div class="advice">
                    <div class="advice-label">欲望分析</div>
                    <div class="advice-content">{{desire_analysis}}</div>
                </div>
            </div>
            
            <div class="footer">
                查询时间：{{current_time}} | 数据来源：专业星座运势服务
            </div>
        </div>
    </body>
    </html>
    '''
    
    async def text_to_image_menu_style(self, text: str) -> str:
        """使用菜单样式的HTML模板生成图片"""
        try:
            # 将文本内容转换为结构化HTML
            lines = text.split('\n')
            html_parts = []
            in_example_section = False
            
            for line in lines:
                line = line.rstrip()
                
                # 跳过标题行（已在模板中处理）
                if line == "🔧 工具箱插件菜单 🔧":
                    continue
                
                # 检测分类标题
                elif line.startswith('【') and line.endswith('】'):
                    category_name = line.strip('【】')
                    html_parts.append(f'<h2 class="category-title">{category_name}</h2>')
                    in_example_section = False
                    continue
                
                # 检测使用示例部分
                elif line.startswith('📌 使用示例：'):
                    html_parts.append(f'<div class="example-section">')
                    html_parts.append(f'<h3 class="example-title">📌 使用示例：</h3>')
                    in_example_section = True
                    continue
                
                # 检测注意事项部分
                elif line.startswith('💡 所有命令'):
                    html_parts.append(f'<div class="note-section">{line}</div>')
                    in_example_section = False
                    continue
                
                # 处理空行
                elif line.strip() == '':
                    continue
                
                # 处理示例条目
                elif in_example_section:
                    html_parts.append(f'<div class="example-item">{line}</div>')
                
                # 处理命令条目
                elif ' - ' in line:
                    # 解析命令条目
                    command_part, desc_part = line.split(' - ', 1)
                    
                    # 提取命令名称和格式
                    command_format = command_part.strip()
                    command_desc = desc_part.strip()
                    
                    # 提取命令名称（第一个空格前的内容）
                    if ' ' in command_format:
                        command_name = command_format.split(' ')[0]
                    else:
                        command_name = command_format
                    
                    # 生成HTML
                    html_parts.append(f'<div class="menu-item">')
                    html_parts.append(f'<span class="command-name">{command_name}</span> ')
                    html_parts.append(f'<span class="command-format">{command_format}</span> ')
                    html_parts.append(f'<span class="command-desc">- {command_desc}</span>')
                    html_parts.append(f'</div>')
                
                # 处理其他文本行
                else:
                    html_parts.append(f'<div class="content-line">{line}</div>')
            
            # 关闭示例部分标签
            if in_example_section:
                html_parts.append(f'</div>')
            
            # 组装最终HTML内容
            formatted_html = '\n'.join(html_parts)
            
            # 渲染HTML模板
            html_content = self.MENU_TEMPLATE.replace("{{content}}", formatted_html)
            
            # 使用html_render函数生成图片
            options = {
                "full_page": True,
                "type": "jpeg",
                "quality": 95,
            }
            
            image_url = await self.html_render(
                html_content,  # 渲染后的HTML内容
                {},  # 空数据字典
                True,  # 返回URL
                options  # 图片生成选项
            )
            
            return image_url
        except Exception as e:
            logger.error(f"菜单样式图片生成失败：{e}")
            # 回退到默认的text_to_image方法
            return await self.text_to_image(text)

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
        """王者英雄战力查询，显示四个战区数据"""
        msg = message.message_str.replace("战力查询", "").strip()
        
        if not msg:
            yield message.plain_result("缺少参数，正确示例：\n\n战力查询 小乔").use_t2i(False)
            return
        
        hero_name = msg.strip()
        api_url = "https://yunzhiapi.cn/API/wzzlcx.php"
        
        try:
            # 构造请求参数（注意API文档中的参数名是hero，但示例中写的是hreo，这里使用正确的hero）
            params = {
                "hero": hero_name,
                "type": "json"
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
                        yield message.plain_result(f"查询失败：{result.get('message', '未知错误')}").use_t2i(False)
                        return
                    
                    data = result.get("data", {})
                    if not data:
                        yield message.plain_result("未查询到该英雄的战力信息").use_t2i(False)
                        return
                    
                    hero_data = data.get("hero_data", {})
                    platforms = data.get("platforms", {})
                    
                    # 获取当前时间，用于显示在图片中
                    current_time = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S")
                    
                    # 增强数据处理，确保每个平台都有完整的数据
                    # 定义默认平台数据
                    default_platform_data = {
                        "province": "未知省",
                        "provincePower": "0",
                        "city": "未知市",
                        "cityPower": "0",
                        "area": "未知区",
                        "areaPower": "0",
                        "guobiao": "0"
                    }
                    
                    # 确保每个平台都有数据
                    aqq_data = {**default_platform_data, **platforms.get('aqq', {})}
                    awx_data = {**default_platform_data, **platforms.get('awx', {})}
                    iqq_data = {**default_platform_data, **platforms.get('iqq', {})}
                    iwx_data = {**default_platform_data, **platforms.get('iwx', {})}
                    
                    # 添加日志记录，便于调试
                    logger.info(f"战力查询数据 - 英雄: {hero_name}, 平台数据: {platforms.keys()}")
                    
                    # 准备模板数据，包含四个战区的战力信息
                    template_data = {
                        "hero_name": hero_data.get('name', hero_name),
                        "updatetime": hero_data.get('updatetime', current_time),
                        "current_time": current_time,
                        
                        # Android QQ区数据
                        "aqq_guobiao": aqq_data.get('guobiao', '0'),
                        "aqq_province": aqq_data.get('province', '未知省'),
                        "aqq_provincePower": aqq_data.get('provincePower', '0'),
                        "aqq_city": aqq_data.get('city', '未知市'),
                        "aqq_cityPower": aqq_data.get('cityPower', '0'),
                        "aqq_area": aqq_data.get('area', '未知区'),
                        "aqq_areaPower": aqq_data.get('areaPower', '0'),
                        
                        # Android 微信区数据
                        "awx_guobiao": awx_data.get('guobiao', '0'),
                        "awx_province": awx_data.get('province', '未知省'),
                        "awx_provincePower": awx_data.get('provincePower', '0'),
                        "awx_city": awx_data.get('city', '未知市'),
                        "awx_cityPower": awx_data.get('cityPower', '0'),
                        "awx_area": awx_data.get('area', '未知区'),
                        "awx_areaPower": awx_data.get('areaPower', '0'),
                        
                        # iOS QQ区数据
                        "iqq_guobiao": iqq_data.get('guobiao', '0'),
                        "iqq_province": iqq_data.get('province', '未知省'),
                        "iqq_provincePower": iqq_data.get('provincePower', '0'),
                        "iqq_city": iqq_data.get('city', '未知市'),
                        "iqq_cityPower": iqq_data.get('cityPower', '0'),
                        "iqq_area": iqq_data.get('area', '未知区'),
                        "iqq_areaPower": iqq_data.get('areaPower', '0'),
                        
                        # iOS 微信区数据
                        "iwx_guobiao": iwx_data.get('guobiao', '0'),
                        "iwx_province": iwx_data.get('province', '未知省'),
                        "iwx_provincePower": iwx_data.get('provincePower', '0'),
                        "iwx_city": iwx_data.get('city', '未知市'),
                        "iwx_cityPower": iwx_data.get('cityPower', '0'),
                        "iwx_area": iwx_data.get('area', '未知区'),
                        "iwx_areaPower": iwx_data.get('areaPower', '0')
                    }
                    
                    # 渲染HTML模板
                    html_content = self.HERO_POWER_TEMPLATE
                    for key, value in template_data.items():
                        placeholder = "{{" + key + "}}"
                        html_content = html_content.replace(placeholder, str(value))
                    
                    # 使用html_render函数生成图片
                    options = {
                        "full_page": True,
                        "type": "jpeg",
                        "quality": 95,
                    }
                    
                    image_url = await self.html_render(
                        html_content,  # 渲染后的HTML内容
                        {},  # 空数据字典
                        True,  # 返回URL
                        options  # 图片生成选项
                    )
                    
                    # 返回图片结果
                    yield message.image_result(image_url).use_t2i(False)
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
                    
                    # 获取当前时间，用于显示在图片中
                    current_time = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S")
                    
                    # 准备模板数据
                    template_data = {
                        "from_city": result.get('from', from_city),
                        "to_city": result.get('to', to_city),
                        "corese": data.get('corese', ''),
                        "distance": data.get('distance', '0'),
                        "time": data.get('time', '0'),
                        "fuelcosts": data.get('fuelcosts', '0'),
                        "bridgetoll": data.get('bridgetoll', '0'),
                        "totalcost": data.get('totalcost', '0'),
                        "roadconditions": data.get('roadconditions', '暂无数据'),
                        "current_time": current_time
                    }
                    
                    # 渲染HTML模板
                    html_content = self.ROUTE_QUERY_TEMPLATE
                    for key, value in template_data.items():
                        placeholder = "{{" + key + "}}"
                        html_content = html_content.replace(placeholder, str(value))
                    
                    # 使用html_render函数生成图片
                    options = {
                        "full_page": True,
                        "type": "jpeg",
                        "quality": 95,
                    }
                    
                    image_url = await self.html_render(
                        html_content,  # 渲染后的HTML内容
                        {},  # 空数据字典
                        True,  # 返回URL
                        options  # 图片生成选项
                    )
                    
                    # 返回图片结果
                    yield message.image_result(image_url).use_t2i(False)
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
        api_url = "https://yunzhiapi.cn//API/ks/api.php"
        
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

    @filter.command("mcs")
    async def mc_server_status(self, message: AstrMessageEvent):
        """查询Minecraft服务器状态"""
        # 提取服务器地址参数
        msg = message.message_str.replace("mcs", "").strip()
        
        if not msg:
            yield message.plain_result("缺少必要参数，正确示例：\n\nmcs 121.com").use_t2i(False)
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
                        try:
                            raw_content = await resp.text()
                            result = json.loads(raw_content)
                            yield message.plain_result(f"查询失败：{result.get('message', '未知错误')}").use_t2i(False)
                        except json.JSONDecodeError:
                            yield message.plain_result(f"查询失败：服务器返回错误状态码 {resp.status}").use_t2i(False)
                        return
                    
                    raw_content = await resp.text()
                    data = json.loads(raw_content)
                    
                    # 检查响应是否包含online字段，这是API返回的主要字段
                    if 'online' not in data:
                        yield message.plain_result(f"查询失败：服务器返回格式异常").use_t2i(False)
                        return
                    
                    # 获取当前时间，用于显示在图片中
                    current_time = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S")
                    
                    # 准备模板数据
                    online = data.get('online', False)
                    online_text = "在线" if online else "离线"
                    online_status = "online" if online else "offline"
                    
                    template_data = {
                        "server_addr": server_addr,
                        "online_text": online_text,
                        "online_status": online_status,
                        "ip": data.get('ip', '未知'),
                        "port": data.get('port', 25565),
                        "players": data.get('players', 0),
                        "max_players": data.get('max_players', 0),
                        "version": data.get('version', '未知'),
                        "current_time": current_time
                    }
                    
                    # 渲染HTML模板
                    html_content = self.MC_SERVER_TEMPLATE
                    for key, value in template_data.items():
                        placeholder = "{{" + key + "}}"
                        html_content = html_content.replace(placeholder, str(value))
                    
                    # 使用html_render函数生成图片
                    options = {
                        "full_page": True,
                        "type": "jpeg",
                        "quality": 95,
                    }
                    
                    image_url = await self.html_render(
                        html_content,  # 渲染后的HTML内容
                        {},  # 空数据字典
                        True,  # 返回URL
                        options  # 图片生成选项
                    )
                    
                    # 返回图片结果
                    yield message.image_result(image_url).use_t2i(False)
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
                    
                    # 获取当前时间，用于显示在图片中
                    current_time = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S")
                    
                    # 准备模板数据
                    template_data = {
                        "city_name": city_name,
                        "trend": qushi,
                        "oil_92": oil_prices.get('92', '未知'),
                        "oil_95": oil_prices.get('95', '未知'),
                        "oil_98": oil_prices.get('98', '未知'),
                        "oil_0": oil_prices.get('0', '未知'),
                        "current_time": current_time
                    }
                    
                    # 渲染HTML模板
                    html_content = self.OIL_PRICE_TEMPLATE
                    for key, value in template_data.items():
                        placeholder = "{{" + key + "}}"
                        html_content = html_content.replace(placeholder, str(value))
                    
                    # 使用html_render函数生成图片
                    options = {
                        "full_page": True,
                        "type": "jpeg",
                        "quality": 95,
                    }
                    
                    image_url = await self.html_render(
                        html_content,  # 渲染后的HTML内容
                        {},  # 空数据字典
                        True,  # 返回URL
                        options  # 图片生成选项
                    )
                    
                    # 返回图片结果
                    yield message.image_result(image_url).use_t2i(False)
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
                    
                    # 获取当前时间，用于显示在图片中
                    current_time = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S")
                    
                    # 准备模板数据
                    template_data = {
                        "qq_number": result.get('qq', qq_number),
                        "valuation": result.get('valuation', 0),
                        "law": result.get('law', ''),
                        "digit": result.get('digit', ''),
                        "current_time": current_time
                    }
                    
                    # 渲染HTML模板
                    html_content = self.QQ_VALUATION_TEMPLATE
                    for key, value in template_data.items():
                        placeholder = "{{" + key + "}}"
                        html_content = html_content.replace(placeholder, str(value))
                    
                    # 使用html_render函数生成图片
                    options = {
                        "full_page": True,
                        "type": "jpeg",
                        "quality": 95,
                    }
                    
                    image_url = await self.html_render(
                        html_content,  # 渲染后的HTML内容
                        {},  # 空数据字典
                        True,  # 返回URL
                        options  # 图片生成选项
                    )
                    
                    # 返回图片结果
                    yield message.image_result(image_url).use_t2i(False)
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

    @filter.command("星座运势")
    async def constellation_fortune(self, message: AstrMessageEvent):
        """查询指定星座的运势图片"""
        # 提取星座名称参数
        msg = message.message_str.replace("星座运势", "").strip()
        
        if not msg:
            yield message.plain_result("正确指令：星座运势 <星座名>\n\n示例：星座运势 白羊\n星座运势 白羊座").use_t2i(False)
            return
        
        constellation = msg.strip()
        api_url = "https://yunzhiapi.cn//API/xzyspd.php"
        
        try:
            # 构造请求参数
            params = {
                "msg": constellation,
                "time": "today",
                "type": "json"
            }
            
            timeout = aiohttp.ClientTimeout(total=30)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(api_url, params=params) as resp:
                    if resp.status != 200:
                        yield message.plain_result(f"请求星座运势失败，服务器返回错误状态码：{resp.status}").use_t2i(False)
                        return
                    
                    # 读取响应文本，解析JSON
                    raw_content = await resp.text()
                    result = json.loads(raw_content)
                    
                    # 检查API返回是否成功
                    if result.get("status") != "success":
                        yield message.plain_result(f"查询失败：{result.get('msg', '未知错误')}").use_t2i(False)
                        return
                    
                    # 获取当前时间，用于显示在图片中
                    current_time = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S")
                    
                    # 将列表类型的字段转换为字符串，以便在HTML模板中显示
                    lucky_colors = ", ".join(result.get("lucky_colors", []))
                    lucky_numbers = ", ".join(map(str, result.get("lucky_numbers", [])))
                    good_matches = ", ".join(result.get("good_matches", []))
                    fair_matches = ", ".join(result.get("fair_matches", []))
                    poor_matches = ", ".join(result.get("poor_matches", []))
                    
                    # 准备模板数据
                    template_data = {
                        "constellation_name": result.get("constellation_name", constellation),
                        "constellation_en": result.get("constellation_en", ""),
                        "date_range": result.get("date_range", ""),
                        "element": result.get("element", ""),
                        "ruling_planet": result.get("ruling_planet", ""),
                        "strengths": result.get("strengths", ""),
                        "weaknesses": result.get("weaknesses", ""),
                        "best_match": result.get("best_match", ""),
                        "best_match_en": result.get("best_match_en", ""),
                        "good_matches": good_matches,
                        "fair_matches": fair_matches,
                        "poor_matches": poor_matches,
                        "lucky_colors": lucky_colors,
                        "lucky_numbers": lucky_numbers,
                        "time_period": result.get("time_period", "today"),
                        "love_advice": result.get("love_advice", ""),
                        "general_fortune": result.get("general_fortune", ""),
                        "love_fortune": result.get("love_fortune", ""),
                        "work_fortune": result.get("work_fortune", ""),
                        "wealth_fortune": result.get("wealth_fortune", ""),
                        "health_fortune": result.get("health_fortune", ""),
                        "desire_analysis": result.get("desire_analysis", ""),
                        "lucky_direction": result.get("lucky_direction", ""),
                        "lucky_time": result.get("lucky_time", ""),
                        "current_time": current_time
                    }
                    
                    # 渲染HTML模板
                    html_content = self.CONSTELLATION_FORTUNE_TEMPLATE
                    for key, value in template_data.items():
                        placeholder = "{{" + key + "}}"
                        html_content = html_content.replace(placeholder, str(value))
                    
                    # 使用html_render函数生成图片
                    options = {
                        "full_page": True,
                        "type": "jpeg",
                        "quality": 95,
                    }
                    
                    image_url = await self.html_render(
                        html_content,  # 渲染后的HTML内容
                        {},  # 空数据字典
                        True,  # 返回URL
                        options  # 图片生成选项
                    )
                    
                    # 返回图片结果
                    yield message.image_result(image_url).use_t2i(False)
                    return
                        
        except aiohttp.ClientError as e:
            logger.error(f"网络连接错误：{e}")
            yield message.plain_result(f"无法连接到星座运势服务器：{str(e)}").use_t2i(False)
            return
        except asyncio.TimeoutError:
            logger.error("请求超时")
            yield message.plain_result("请求超时，请稍后重试").use_t2i(False)
            return
        except json.JSONDecodeError as e:
            logger.error(f"JSON解析错误：{e}")
            yield message.plain_result(f"服务器返回数据格式错误：{str(e)}").use_t2i(False)
            return
        except Exception as e:
            logger.error(f"请求星座运势时发生错误：{e}")
            yield message.plain_result(f"请求星座运势时发生错误：{str(e)}").use_t2i(False)
            return
    
    @filter.command("天气")
    async def weather(self, message: AstrMessageEvent):
        """查询指定城市的天气信息"""
        # 提取城市名称参数
        msg = message.message_str.replace("天气", "").strip()
        
        if not msg:
            yield message.plain_result("正确指令：天气 <城市名>\n\n示例：天气 长沙").use_t2i(False)
            return
        
        city = msg.strip()
        api_url = "https://uapis.cn/api/v1/misc/weather"
        
        try:
            # 构造请求参数
            params = {
                "city": city,
                "extended": "true",
                "indices": "true"
            }
            
            timeout = aiohttp.ClientTimeout(total=30)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(api_url, params=params) as resp:
                    if resp.status != 200:
                        try:
                            raw_content = await resp.text()
                            result = json.loads(raw_content)
                            yield message.plain_result(f"天气查询失败：{result.get('message', '未知错误')}").use_t2i(False)
                        except json.JSONDecodeError:
                            yield message.plain_result(f"天气查询失败：服务器返回错误状态码 {resp.status}").use_t2i(False)
                        return
                    
                    # 读取响应文本，解析JSON
                    raw_content = await resp.text()
                    result = json.loads(raw_content)
                    
                    # 获取当前时间，用于显示在图片中
                    current_time = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S")
                    
                    # 准备模板数据
                    template_data = {
                        "city": result.get("city", city),
                        "report_time": result.get("report_time", ""),
                        "weather": result.get("weather", ""),
                        "temperature": result.get("temperature", 0),
                        "wind_direction": result.get("wind_direction", ""),
                        "wind_power": result.get("wind_power", ""),
                        "humidity": result.get("humidity", 0),
                        "feels_like": result.get("feels_like", 0),
                        "visibility": result.get("visibility", 0),
                        "pressure": result.get("pressure", 0),
                        "uv": result.get("uv", 0),
                        "aqi": result.get("aqi", 0),
                        "precipitation": result.get("precipitation", 0),
                        "cloud": result.get("cloud", 0),
                        "current_time": current_time
                    }
                    
                    # 处理生活指数数据
                    life_indices = result.get("life_indices", {})
                    
                    # 穿衣指数
                    clothing = life_indices.get("clothing", {})
                    template_data["clothing_level"] = clothing.get("level", "")
                    template_data["clothing_brief"] = clothing.get("brief", "")
                    template_data["clothing_advice"] = clothing.get("advice", "")
                    
                    # 紫外线指数
                    uv_index = life_indices.get("uv", {})
                    template_data["uv_level"] = uv_index.get("level", "")
                    template_data["uv_brief"] = uv_index.get("brief", "")
                    template_data["uv_advice"] = uv_index.get("advice", "")
                    
                    # 洗车指数
                    car_wash = life_indices.get("car_wash", {})
                    template_data["car_wash_level"] = car_wash.get("level", "")
                    template_data["car_wash_brief"] = car_wash.get("brief", "")
                    template_data["car_wash_advice"] = car_wash.get("advice", "")
                    
                    # 晾晒指数
                    drying = life_indices.get("drying", {})
                    template_data["drying_level"] = drying.get("level", "")
                    template_data["drying_brief"] = drying.get("brief", "")
                    template_data["drying_advice"] = drying.get("advice", "")
                    
                    # 空调指数
                    air_conditioner = life_indices.get("air_conditioner", {})
                    template_data["air_conditioner_level"] = air_conditioner.get("level", "")
                    template_data["air_conditioner_brief"] = air_conditioner.get("brief", "")
                    template_data["air_conditioner_advice"] = air_conditioner.get("advice", "")
                    
                    # 感冒指数
                    cold_risk = life_indices.get("cold_risk", {})
                    template_data["cold_risk_level"] = cold_risk.get("level", "")
                    template_data["cold_risk_brief"] = cold_risk.get("brief", "")
                    template_data["cold_risk_advice"] = cold_risk.get("advice", "")
                    
                    # 运动指数
                    exercise = life_indices.get("exercise", {})
                    template_data["exercise_level"] = exercise.get("level", "")
                    template_data["exercise_brief"] = exercise.get("brief", "")
                    template_data["exercise_advice"] = exercise.get("advice", "")
                    
                    # 舒适度指数
                    comfort = life_indices.get("comfort", {})
                    template_data["comfort_level"] = comfort.get("level", "")
                    template_data["comfort_brief"] = comfort.get("brief", "")
                    template_data["comfort_advice"] = comfort.get("advice", "")
                    
                    # 渲染HTML模板
                    html_content = self.WEATHER_TEMPLATE
                    for key, value in template_data.items():
                        placeholder = "{{" + key + "}}"
                        html_content = html_content.replace(placeholder, str(value))
                    
                    # 使用html_render函数生成图片
                    options = {
                        "full_page": True,
                        "type": "jpeg",
                        "quality": 95,
                    }
                    
                    image_url = await self.html_render(
                        html_content,  # 渲染后的HTML内容
                        {},  # 空数据字典
                        True,  # 返回URL
                        options  # 图片生成选项
                    )
                    
                    # 返回图片结果
                    yield message.image_result(image_url).use_t2i(False)
                    return
                        
        except aiohttp.ClientError as e:
            logger.error(f"网络连接错误：{e}")
            yield message.plain_result(f"无法连接到天气查询服务器：{str(e)}").use_t2i(False)
            return
        except asyncio.TimeoutError:
            logger.error("请求超时")
            yield message.plain_result("请求超时，请稍后重试").use_t2i(False)
            return
        except json.JSONDecodeError as e:
            logger.error(f"JSON解析错误：{e}")
            yield message.plain_result(f"服务器返回数据格式错误：{str(e)}").use_t2i(False)
            return
        except Exception as e:
            logger.error(f"请求天气查询时发生错误：{e}")
            yield message.plain_result(f"请求天气查询时发生错误：{str(e)}").use_t2i(False)
            return
    
    @filter.command("实时科技资讯")
    async def tech_news(self, message: AstrMessageEvent):
        """获取实时科技资讯，显示最新科技新闻"""
        api_url = "https://api.pearktrue.cn/api/sciencenews/"
        
        try:
            timeout = aiohttp.ClientTimeout(total=30)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(api_url) as resp:
                    if resp.status != 200:
                        yield message.plain_result(f"请求实时科技资讯失败，服务器返回错误状态码 {resp.status}").use_t2i(False)
                        return
                    
                    # 读取响应文本，解析JSON
                    raw_content = await resp.text()
                    result = json.loads(raw_content)
                    
                    # 检查API返回是否成功
                    if result.get("code") != 200:
                        yield message.plain_result(f"实时科技资讯获取失败：{result.get('msg', '未知错误')}").use_t2i(False)
                        return
                    
                    # 获取当前时间，用于显示在图片中
                    current_time = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S")
                    
                    # 准备模板数据
                    update_time = result.get("更新", "")
                    news_count = result.get("伯爵", "0")
                    
                    # 生成新闻列表HTML
                    news_items = result.get("数据", [])
                    news_html = ""
                    for news in news_items:
                        if isinstance(news, dict):
                            news_time = news.get("time", "")
                            news_title = news.get("title", "")
                            if news_title:
                                news_html += f'<div class="news-item"><span class="news-time">{news_time}</span><span class="news-title">{news_title}</span></div>'
                    
                    # 渲染HTML模板
                    html_content = self.TECH_NEWS_TEMPLATE
                    html_content = html_content.replace("{{update_time}}", update_time)
                    html_content = html_content.replace("{{news_count}}", news_count)
                    html_content = html_content.replace("{{news_items}}", news_html)
                    html_content = html_content.replace("{{current_time}}", current_time)
                    
                    # 使用html_render函数生成图片
                    options = {
                        "full_page": True,
                        "type": "jpeg",
                        "quality": 95,
                    }
                    
                    image_url = await self.html_render(
                        html_content,  # 渲染后的HTML内容
                        {},  # 空数据字典
                        True,  # 返回URL
                        options  # 图片生成选项
                    )
                    
                    # 返回图片结果
                    yield message.image_result(image_url).use_t2i(False)
                    return
                        
        except aiohttp.ClientError as e:
            logger.error(f"网络连接错误：{e}")
            yield message.plain_result(f"无法连接到科技资讯服务器：{str(e)}").use_t2i(False)
            return
        except asyncio.TimeoutError:
            logger.error("请求超时")
            yield message.plain_result("请求超时，请稍后重试").use_t2i(False)
            return
        except json.JSONDecodeError as e:
            logger.error(f"JSON解析错误：{e}")
            yield message.plain_result(f"服务器返回数据格式错误：{str(e)}").use_t2i(False)
            return
        except Exception as e:
            logger.error(f"请求实时科技资讯时发生错误：{e}")
            yield message.plain_result(f"请求实时科技资讯时发生错误：{str(e)}").use_t2i(False)
            return

    @filter.command("加密")
    async def shouyu_encrypt(self, message: AstrMessageEvent):
        """兽语在线加密功能"""
        # 提取加密内容参数
        # 支持多种格式："加密 内容" 和 "/加密 内容" 以及被@的情况
        msg = message.message_str
        # 移除命令前缀（支持带斜杠和不带斜杠）
        msg = msg.replace("加密", "").replace("/加密", "").strip()
        # 移除@机器人的部分
        import re
        msg = re.sub(r'\[At:\d+\]', '', msg).strip()
        
        if not msg:
            yield message.plain_result("正确指令：加密 <内容>\n\n示例：加密 121").use_t2i(False)
            return
        
        encrypt_content = msg.strip()
        api_url = "https://yunzhiapi.cn//API/shouyu/api.php"
        
        try:
            # 构造请求参数
            params = {
                "msg": encrypt_content,
                "type": "json"
                # 默认format为空，即加密模式
            }
            
            timeout = aiohttp.ClientTimeout(total=30)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(api_url, params=params) as resp:
                    if resp.status != 200:
                        yield message.plain_result(f"请求加密失败，服务器返回错误状态码：{resp.status}").use_t2i(False)
                        return
                    
                    # 读取响应文本，解析JSON
                    raw_content = await resp.text()
                    result = json.loads(raw_content)
                    
                    # 检查API返回是否成功
                    if result.get("code") != 1:
                        yield message.plain_result(f"加密失败：{result.get('text', '未知错误')}").use_t2i(False)
                        return
                    
                    # 提取加密结果
                    encrypted_text = result.get("data", {}).get("Message", "")
                    if not encrypted_text:
                        yield message.plain_result("加密失败：返回结果为空").use_t2i(False)
                        return
                    
                    # 返回加密结果
                    yield message.plain_result(f"加密结果：{encrypted_text}").use_t2i(False)
                    return
                        
        except aiohttp.ClientError as e:
            logger.error(f"网络连接错误：{e}")
            yield message.plain_result(f"无法连接到加密服务器：{str(e)}").use_t2i(False)
            return
        except asyncio.TimeoutError:
            logger.error("请求超时")
            yield message.plain_result("请求超时，请稍后重试").use_t2i(False)
            return
        except json.JSONDecodeError as e:
            logger.error(f"JSON解析错误：{e}")
            yield message.plain_result(f"服务器返回数据格式错误：{str(e)}").use_t2i(False)
            return
        except Exception as e:
            logger.error(f"请求加密时发生错误：{e}")
            yield message.plain_result(f"请求加密时发生错误：{str(e)}").use_t2i(False)
            return
    
    @filter.command("解密")
    async def shouyu_decrypt(self, message: AstrMessageEvent):
        """兽语在线解密功能"""
        # 提取解密内容参数
        # 支持多种格式："解密 内容" 和 "/解密 内容" 以及被@的情况
        msg = message.message_str
        # 移除命令前缀（支持带斜杠和不带斜杠）
        msg = msg.replace("解密", "").replace("/解密", "").strip()
        # 移除@机器人的部分
        import re
        msg = re.sub(r'\[At:\d+\]', '', msg).strip()
        
        if not msg:
            yield message.plain_result("正确指令：解密 <内容>\n\n示例：解密 嗷～嗷啊").use_t2i(False)
            return
        
        decrypt_content = msg.strip()
        api_url = "https://yunzhiapi.cn/API/shouyu/api.php"
        
        try:
            # 构造请求参数
            params = {
                "msg": decrypt_content,
                "type": "json",
                "format": 1  # format=1表示解密模式
            }
            
            timeout = aiohttp.ClientTimeout(total=30)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(api_url, params=params) as resp:
                    if resp.status != 200:
                        yield message.plain_result(f"请求解密失败，服务器返回错误状态码：{resp.status}").use_t2i(False)
                        return
                    
                    # 读取响应文本，解析JSON
                    raw_content = await resp.text()
                    result = json.loads(raw_content)
                    
                    # 检查API返回是否成功
                    if result.get("code") != 1:
                        yield message.plain_result(f"解密失败：{result.get('text', '未知错误')}").use_t2i(False)
                        return
                    
                    # 提取解密结果
                    decrypted_text = result.get("data", {}).get("Message", "")
                    if not decrypted_text:
                        yield message.plain_result("解密失败：返回结果为空").use_t2i(False)
                        return
                    
                    # AI审核步骤
                    ai_api_url = "https://api.jkyai.top/API/depsek3.2.php"
                    ai_system_prompt = "你是一个专业的合规内容审核助手，请严格检测以下文本中是否包含违规内容。\n\n违规词范围包括但不限于：\n\n暴力、血腥、恐怖内容\n\n仇恨、歧视、人身攻击言论\n\n违法、违禁品或行为引导\n\n政治敏感、不当言论\n\n色情、低俗、性暗示内容\n\n虚假信息、不实谣言\n\n诈骗、广告、恶意推广\n\n泄露隐私、他人信息\n\n链接一概不允许\n\n其他违反公序良俗的内容\n\n请按以下步骤处理：\n\n1. 逐句或分段分析文本内容；\n2. 如发现疑似违规词或内容则输出：false\n3. 如果内容安全则输出：true\n4. 并且给出拦截原因，比如如果是链接就输出：包含链接！！\n   如果是骂人则输出：不当言论！！\n   如果是骂人和链接一起就输出：包含链接和不当言论！！\n5. 并且按照恶劣程度给出违规分数，1-10分\n\n输出格式要求：\n<安全状态>\n<拦截原因（如果安全则为空）>\n<违规分数（如果安全则为0）>\n\n例如：\nfalse\n不当言论！！\n8\n\n或：\ntrue\n\n0"
                    
                    ai_question = f"{ai_system_prompt}\n\n需要审核的文本：\n{decrypted_text}"
                    
                    try:
                        # 调用AI审核API
                        ai_params = {
                            "question": ai_question,
                            "type": "text"
                        }
                        
                        async with session.get(ai_api_url, params=ai_params) as ai_resp:
                            if ai_resp.status != 200:
                                # AI审核失败，仍返回解密结果
                                logger.warning(f"AI审核失败，状态码：{ai_resp.status}")
                                yield message.plain_result(f"解密结果：{decrypted_text}").use_t2i(False)
                                return
                            
                            ai_result = await ai_resp.text()
                            ai_result = ai_result.strip()
                            
                            # 解析AI结果
                            try:
                                ai_lines = ai_result.split('\n')
                                if len(ai_lines) < 1:
                                    # 结果格式异常，仍返回解密结果
                                    logger.warning(f"AI审核结果格式异常：{ai_result}")
                                    yield message.plain_result(f"解密结果：{decrypted_text}").use_t2i(False)
                                    return
                                
                                # 提取安全状态
                                safety_status = ai_lines[0].strip().lower()
                                
                                # 提取拦截原因（如果存在）
                                intercept_reason = ""
                                if len(ai_lines) > 1:
                                    intercept_reason = ai_lines[1].strip()
                                
                                # 提取违规分数（如果存在）
                                violation_score = 0
                                if len(ai_lines) > 2:
                                    try:
                                        violation_score = int(ai_lines[2].strip())
                                    except ValueError:
                                        violation_score = 0
                                
                                # 计算违规程度
                                if violation_score >= 7:
                                    severity = "非常恶劣"
                                elif violation_score >= 4:
                                    severity = "中度恶劣"
                                elif violation_score >= 1:
                                    severity = "轻度恶劣"
                                else:
                                    severity = "无"
                                
                                # 检查AI审核结果
                                if safety_status == "false":
                                    # 内容违规，返回违规提示
                                    if intercept_reason:
                                        response = f"您提供的密文解析后遭到QQ安全中心检测系统拦截，不予放行!!!\n\n违规内容含：{intercept_reason}\n违规程度：{violation_score}分<{severity}>"
                                    else:
                                        response = f"您提供的密文解析后遭到QQ安全中心检测系统拦截，不予放行!!!\n\n违规程度：{violation_score}分<{severity}>"
                                    
                                    # 记录违规分数到日志
                                    logger.warning(f"解密内容违规，原因：{intercept_reason}，违规分数：{violation_score}，违规程度：{severity}")
                                    
                                    yield message.plain_result(response).use_t2i(False)
                                    return
                                elif safety_status == "true":
                                    # 内容安全，返回解密结果
                                    yield message.plain_result(f"解密结果：{decrypted_text}").use_t2i(False)
                                    return
                                else:
                                    # 结果格式异常，仍返回解密结果
                                    logger.warning(f"AI审核结果格式异常：{ai_result}")
                                    yield message.plain_result(f"解密结果：{decrypted_text}").use_t2i(False)
                                    return
                            except Exception as parse_e:
                                # 解析AI结果失败，仍返回解密结果
                                logger.error(f"解析AI审核结果时发生错误：{parse_e}")
                                yield message.plain_result(f"解密结果：{decrypted_text}").use_t2i(False)
                                return
                    except Exception as ai_e:
                        # AI审核过程中发生异常，仍返回解密结果
                        logger.error(f"AI审核过程中发生错误：{ai_e}")
                        yield message.plain_result(f"解密结果：{decrypted_text}").use_t2i(False)
                        return
                    
                    # 返回解密结果
                    yield message.plain_result(f"解密结果：{decrypted_text}").use_t2i(False)
                    return
                        
        except aiohttp.ClientError as e:
            logger.error(f"网络连接错误：{e}")
            yield message.plain_result(f"无法连接到解密服务器：{str(e)}").use_t2i(False)
            return
        except asyncio.TimeoutError:
            logger.error("请求超时")
            yield message.plain_result("请求超时，请稍后重试").use_t2i(False)
            return
        except json.JSONDecodeError as e:
            logger.error(f"JSON解析错误：{e}")
            yield message.plain_result(f"服务器返回数据格式错误：{str(e)}").use_t2i(False)
            return
        except Exception as e:
            logger.error(f"请求解密时发生错误：{e}")
            yield message.plain_result(f"请求解密时发生错误：{str(e)}").use_t2i(False)
            return
    
    @filter.command("AES加密")
    async def aes_encrypt(self, message: AstrMessageEvent):
        """AES高级加密，支持多种模式和填充方式"""
        # 提取命令参数
        msg = message.message_str.replace("AES加密", "").strip()
        
        if not msg:
            yield message.plain_result("缺少参数，正确示例：\n\nAES加密 加密密钥 加密内容").use_t2i(False)
            return
        
        # 解析加密密钥和加密内容
        parts = msg.split()
        if len(parts) < 2:
            yield message.plain_result("参数格式错误，请输入加密密钥和加密内容\n\n正确示例：\nAES加密 mykey Hello World").use_t2i(False)
            return
        
        # 提取加密密钥和加密内容
        key = parts[0]
        text = " ".join(parts[1:])
        
        api_url = "https://uapis.cn/api/v1/text/aes/encrypt-advanced"
        
        try:
            # 构造请求体
            payload = {
                "text": text,
                "key": key,
                "mode": "GCM",
                "padding": "PKCS7",
                "output_format": "base64"
            }
            
            timeout = aiohttp.ClientTimeout(total=30)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(api_url, json=payload) as resp:
                    if resp.status != 200:
                        raw_content = await resp.text()
                        try:
                            error_result = json.loads(raw_content)
                            error_msg = error_result.get("error", f"服务器返回错误状态码：{resp.status}")
                        except json.JSONDecodeError:
                            error_msg = f"服务器返回错误状态码：{resp.status}"
                        yield message.plain_result(f"AES加密失败：{error_msg}").use_t2i(False)
                        return
                    
                    # 读取响应文本，解析JSON
                    raw_content = await resp.text()
                    result = json.loads(raw_content)
                    
                    # 提取加密结果
                    ciphertext = result.get("ciphertext", "")
                    mode = result.get("mode", "")
                    padding = result.get("padding", "")
                    
                    if not ciphertext:
                        yield message.plain_result("AES加密失败：返回结果为空").use_t2i(False)
                        return
                    
                    # 构造响应消息
                    response = f"密文：{ciphertext}\n模式：{mode}\n填充：{padding}\n\n注意！！保护好你的密文和加密密钥，解密需要加密密钥和密文"
                    
                    # 返回加密结果
                    yield message.plain_result(response).use_t2i(False)
                    return
                        
        except aiohttp.ClientError as e:
            logger.error(f"网络连接错误：{e}")
            yield message.plain_result(f"无法连接到AES加密服务器：{str(e)}").use_t2i(False)
            return
        except asyncio.TimeoutError:
            logger.error("请求超时")
            yield message.plain_result("请求超时，请稍后重试").use_t2i(False)
            return
        except json.JSONDecodeError as e:
            logger.error(f"JSON解析错误：{e}")
            yield message.plain_result(f"服务器返回数据格式错误：{str(e)}").use_t2i(False)
            return
        except Exception as e:
            logger.error(f"请求AES加密时发生错误：{e}")
            yield message.plain_result(f"请求AES加密时发生错误：{str(e)}").use_t2i(False)
            return
    
    @filter.command("AES解密")
    async def aes_decrypt(self, message: AstrMessageEvent):
        """AES高级解密，支持多种模式和填充方式"""
        # 提取命令参数
        msg = message.message_str.replace("AES解密", "").strip()
        
        if not msg:
            yield message.plain_result("缺少参数，正确示例：\n\nAES解密 解密密钥 加密内容").use_t2i(False)
            return
        
        # 解析解密密钥和加密内容
        parts = msg.split()
        if len(parts) < 2:
            yield message.plain_result("参数格式错误，请输入解密密钥和加密内容\n\n正确示例：\nAES解密 mykey fPtix07ODh3sn9evllHAqK/XYQXIamidUA22JL6zhg==").use_t2i(False)
            return
        
        # 提取解密密钥和加密内容
        key = parts[0]
        ciphertext = " ".join(parts[1:])
        
        api_url = "https://uapis.cn/api/v1/text/aes/decrypt-advanced"
        
        try:
            # 构造请求体
            payload = {
                "text": ciphertext,
                "key": key,
                "mode": "GCM",
                "padding": "PKCS7"
            }
            
            timeout = aiohttp.ClientTimeout(total=30)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(api_url, json=payload) as resp:
                    if resp.status != 200:
                        raw_content = await resp.text()
                        try:
                            error_result = json.loads(raw_content)
                            error_msg = error_result.get("error", f"服务器返回错误状态码：{resp.status}")
                        except json.JSONDecodeError:
                            error_msg = f"服务器返回错误状态码：{resp.status}"
                        yield message.plain_result(f"AES解密失败：{error_msg}").use_t2i(False)
                        return
                    
                    # 读取响应文本，解析JSON
                    raw_content = await resp.text()
                    result = json.loads(raw_content)
                    
                    # 提取解密结果
                    plaintext = result.get("plaintext", "")
                    
                    if plaintext is None or plaintext == "":
                        yield message.plain_result("AES解密失败：返回结果为空").use_t2i(False)
                        return
                    
                    # AI审核步骤
                    ai_api_url = "https://api.jkyai.top/API/depsek3.2.php"
                    ai_system_prompt = "你是一个专业的合规内容审核助手，请严格检测以下文本中是否包含违规内容。\n\n违规词范围包括但不限于：\n\n暴力、血腥、恐怖内容\n\n仇恨、歧视、人身攻击言论\n\n违法、违禁品或行为引导\n\n政治敏感、不当言论\n\n色情、低俗、性暗示内容\n\n虚假信息、不实谣言\n\n诈骗、广告、恶意推广\n\n泄露隐私、他人信息\n\n链接一概不允许\n\n其他违反公序良俗的内容\n\n请按以下步骤处理：\n\n1. 逐句或分段分析文本内容；\n2. 如发现疑似违规词或内容则输出：false\n3. 如果内容安全则输出：true\n4. 并且给出拦截原因，比如如果是链接就输出：包含链接！！\n   如果是骂人则输出：不当言论！！\n   如果是骂人和链接一起就输出：包含链接和不当言论！！\n5. 并且按照恶劣程度给出违规分数，1-10分\n\n输出格式要求：\n<安全状态>\n<拦截原因（如果安全则为空）>\n<违规分数（如果安全则为0）>\n\n例如：\nfalse\n不当言论！！\n8\n\n或：\ntrue\n\n0"
                    
                    ai_question = f"{ai_system_prompt}\n\n需要审核的文本：\n{plaintext}"
                    
                    try:
                        # 调用AI审核API
                        ai_params = {
                            "question": ai_question,
                            "type": "text"
                        }
                        
                        async with session.get(ai_api_url, params=ai_params) as ai_resp:
                            if ai_resp.status != 200:
                                # AI审核失败，仍返回解密结果
                                logger.warning(f"AI审核失败，状态码：{ai_resp.status}")
                                response = f"解密成功！\n\n内容：{plaintext}"
                                yield message.plain_result(response).use_t2i(False)
                                return
                            
                            ai_result = await ai_resp.text()
                            ai_result = ai_result.strip()
                            
                            # 解析AI结果
                            try:
                                ai_lines = ai_result.split('\n')
                                if len(ai_lines) < 1:
                                    # 结果格式异常，仍返回解密结果
                                    logger.warning(f"AI审核结果格式异常：{ai_result}")
                                    response = f"解密成功！\n\n内容：{plaintext}"
                                    yield message.plain_result(response).use_t2i(False)
                                    return
                                
                                # 提取安全状态
                                safety_status = ai_lines[0].strip().lower()
                                
                                # 提取拦截原因（如果存在）
                                intercept_reason = ""
                                if len(ai_lines) > 1:
                                    intercept_reason = ai_lines[1].strip()
                                
                                # 提取违规分数（如果存在）
                                violation_score = 0
                                if len(ai_lines) > 2:
                                    try:
                                        violation_score = int(ai_lines[2].strip())
                                    except ValueError:
                                        violation_score = 0
                                
                                # 计算违规程度
                                if violation_score >= 7:
                                    severity = "非常恶劣"
                                elif violation_score >= 4:
                                    severity = "中度恶劣"
                                elif violation_score >= 1:
                                    severity = "轻度恶劣"
                                else:
                                    severity = "无"
                                
                                # 检查AI审核结果
                                if safety_status == "false":
                                    # 内容违规，返回违规提示
                                    if intercept_reason:
                                        response = f"您提供的密文解析后遭到QQ安全中心检测系统拦截，不予放行!!!\n\n违规内容含：{intercept_reason}\n违规程度：{violation_score}分<{severity}>"
                                    else:
                                        response = f"您提供的密文解析后遭到QQ安全中心检测系统拦截，不予放行!!!\n\n违规程度：{violation_score}分<{severity}>"
                                    
                                    # 记录违规分数到日志
                                    logger.warning(f"AES解密内容违规，原因：{intercept_reason}，违规分数：{violation_score}，违规程度：{severity}")
                                    
                                    yield message.plain_result(response).use_t2i(False)
                                    return
                                elif safety_status == "true":
                                    # 内容安全，返回解密结果
                                    response = f"解密成功！\n\n内容：{plaintext}"
                                    yield message.plain_result(response).use_t2i(False)
                                    return
                                else:
                                    # 结果格式异常，仍返回解密结果
                                    logger.warning(f"AI审核结果格式异常：{ai_result}")
                                    response = f"解密成功！\n\n内容：{plaintext}"
                                    yield message.plain_result(response).use_t2i(False)
                                    return
                            except Exception as parse_e:
                                # 解析AI结果失败，仍返回解密结果
                                logger.error(f"解析AI审核结果时发生错误：{parse_e}")
                                response = f"解密成功！\n\n内容：{plaintext}"
                                yield message.plain_result(response).use_t2i(False)
                                return
                    except Exception as ai_e:
                        # AI审核过程中发生异常，仍返回解密结果
                        logger.error(f"AI审核过程中发生错误：{ai_e}")
                        response = f"解密成功！\n\n内容：{plaintext}"
                        yield message.plain_result(response).use_t2i(False)
                        return
                    
                    # 返回解密结果
                    response = f"解密成功！\n\n内容：{plaintext}"
                    yield message.plain_result(response).use_t2i(False)
                    return
                        
        except aiohttp.ClientError as e:
            logger.error(f"网络连接错误：{e}")
            yield message.plain_result(f"无法连接到AES解密服务器：{str(e)}").use_t2i(False)
            return
        except asyncio.TimeoutError:
            logger.error("请求超时")
            yield message.plain_result("请求超时，请稍后重试").use_t2i(False)
            return
        except json.JSONDecodeError as e:
            logger.error(f"JSON解析错误：{e}")
            yield message.plain_result(f"服务器返回数据格式错误：{str(e)}").use_t2i(False)
            return
        except Exception as e:
            logger.error(f"请求AES解密时发生错误：{e}")
            yield message.plain_result(f"请求AES解密时发生错误：{str(e)}").use_t2i(False)
            return
    
    @filter.command("工具箱菜单")
    async def toolbox_menu(self, message: AstrMessageEvent):
        """显示工具箱插件的所有可用命令"""
        menu_text = """🔧 工具箱插件菜单 🔧

【日常功能】
📅 早安 / 晚安 - 记录睡眠时间，计算睡眠时长

【游戏相关】
🎮 战力查询 <英雄名> - 查询王者荣耀英雄战力，显示四个战区数据
🌍 mcs <服务器地址> - 查询Minecraft服务器状态

【生活服务】
🗺️ 路线查询 <出发地> <目的地> - 查询城际路线
⛽ 油价查询 <城市名> - 查询指定城市油价
🌤️ 天气 <城市名> - 查询指定城市天气
💰 qq估价 <QQ号> - 查询QQ号估价

【AI功能】
🎨 绘画 <提示词> - AI绘画生成

【网络工具】
🌐 代理ip - 获取socks5代理IP
🔒 AES加密 <密钥> <内容> - 高级AES加密
🔓 AES解密 <密钥> <密文> - 高级AES解密

【娱乐功能】
✨ 星座运势 <星座名> - 查询星座运势图片
📱 实时科技资讯 - 获取最新科技新闻图片
🔒 加密 <内容> - 兽语在线加密
🔓 解密 <内容> - 兽语在线解密（含AI安全审核）

📌 使用示例：
战力查询 小乔
路线查询 广州 深圳
绘画 一只可爱的猫
加密 121
解密 嗷～嗷啊
AES加密 mykey Hello World
AES解密 mykey <密文>
天气 长沙
mcs 121.com

💡 所有命令支持群聊和私聊使用"""
        
        # 使用自定义的菜单样式图片生成方法
        image_url = await self.text_to_image_menu_style(menu_text)
        
        yield message.image_result(image_url).use_t2i(False)

    async def terminate(self):
        """插件卸载/重载时调用"""
        pass
