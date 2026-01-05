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
                font-size: 20px;
            }
            .command-format {
                color: #333;
                font-weight: normal;
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
    
    # 战力查询结果的HTML模板
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
                color: #e74c3c;
                margin-bottom: 30px;
                text-shadow: 2px 2px 4px rgba(0,0,0,0.1);
            }
            .hero-name {
                font-size: 36px;
                font-weight: bold;
                text-align: center;
                color: #3498db;
                margin-bottom: 30px;
                padding: 15px;
                background-color: #ecf0f1;
                border-radius: 10px;
            }
            .power-item {
                display: flex;
                justify-content: space-between;
                align-items: center;
                background-color: #f8f9fa;
                padding: 15px 20px;
                margin: 15px 0;
                border-radius: 8px;
                border-left: 5px solid #3498db;
                box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            }
            .power-label {
                font-size: 18px;
                font-weight: bold;
                color: #2c3e50;
            }
            .power-value {
                font-size: 22px;
                font-weight: bold;
                color: #e67e22;
            }
            .region {
                font-size: 14px;
                color: #7f8c8d;
                margin-left: 10px;
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
            <div class="hero-name">{{hero_name}}</div>
            <div class="power-item">
                <div class="power-label">国服最低战力<span class="region">全服</span></div>
                <div class="power-value">{{guobiao}}</div>
            </div>
            <div class="power-item">
                <div class="power-label">省标最低战力<span class="region">{{province}}</span></div>
                <div class="power-value">{{provincePower}}</div>
            </div>
            <div class="power-item">
                <div class="power-label">市标最低战力<span class="region">{{city}}</span></div>
                <div class="power-value">{{cityPower}}</div>
            </div>
            <div class="power-item">
                <div class="power-label">区标最低战力<span class="region">{{area}}</span></div>
                <div class="power-value">{{areaPower}}</div>
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
        """王者英雄战力查询，支持双区双系统"""
        msg = message.message_str.replace("战力查询", "").strip()
        
        if not msg:
            yield message.plain_result("缺少参数，正确示例：\n\n战力查询 安卓qq 小乔\n战力查询 苹果微信 李白").use_t2i(False)
            return
        
        # 解析区服类型和英雄名
        parts = msg.split()
        if len(parts) < 2:
            yield message.plain_result("参数格式错误，请输入区服类型和英雄名\n\n正确示例：\n战力查询 安卓qq 小乔\n战力查询 苹果微信 李白").use_t2i(False)
            return
        
        # 区服类型映射关系
        server_type_map = {
            "安卓qq": "aqq",
            "安卓微信": "awx",
            "苹果qq": "iqq",
            "苹果微信": "iwx"
        }
        
        # 提取区服类型和英雄名
        server_type_input = parts[0]
        hero_name = " ".join(parts[1:])
        
        # 验证区服类型
        if server_type_input not in server_type_map:
            yield message.plain_result(f"区服类型错误，请输入以下区服类型之一：\n{', '.join(server_type_map.keys())}\n\n正确示例：\n战力查询 安卓qq 小乔").use_t2i(False)
            return
        
        # 获取API使用的区服类型
        api_server_type = server_type_map[server_type_input]
        api_url = "https://www.sapi.run/hero/select.php"
        
        try:
            # 构造请求参数
            params = {
                "hero": hero_name,
                "type": api_server_type
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
                    
                    # 获取当前时间，用于显示在图片中
                    current_time = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S")
                    
                    # 准备模板数据
                    template_data = {
                        "hero_name": data.get('name', hero_name),
                        "guobiao": data.get('guobiao', '0'),
                        "province": data.get('province', '未知省'),
                        "provincePower": data.get('provincePower', '0'),
                        "city": data.get('city', '未知市'),
                        "cityPower": data.get('cityPower', '0'),
                        "area": data.get('area', '未知区'),
                        "areaPower": data.get('areaPower', '0'),
                        "current_time": current_time
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
        api_url = "https://api.jkyai.top/API/xzyspd.php"
        
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

    @filter.command("/加密")
    async def shouyu_encrypt(self, message: AstrMessageEvent):
        """兽语在线加密功能"""
        # 提取加密内容参数
        msg = message.message_str.replace("/加密", "").strip()
        
        if not msg:
            yield message.plain_result("正确指令：/加密 <内容>\n\n示例：/加密 121").use_t2i(False)
            return
        
        encrypt_content = msg.strip()
        api_url = "https://api.jkyai.top/API/shouyu/api.php"
        
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
    
    @filter.command("/解密")
    async def shouyu_decrypt(self, message: AstrMessageEvent):
        """兽语在线解密功能"""
        # 提取解密内容参数
        msg = message.message_str.replace("/解密", "").strip()
        
        if not msg:
            yield message.plain_result("正确指令：/解密 <内容>\n\n示例：/解密 嗷～嗷啊").use_t2i(False)
            return
        
        decrypt_content = msg.strip()
        api_url = "https://api.jkyai.top/API/shouyu/api.php"
        
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
    
    @filter.command("工具箱菜单")
    async def toolbox_menu(self, message: AstrMessageEvent):
        """显示工具箱插件的所有可用命令"""
        menu_text = """🔧 工具箱插件菜单 🔧

【日常功能】
📅 早安 / 晚安 - 记录睡眠时间，计算睡眠时长

【游戏相关】
🎮 战力查询 <英雄名> - 查询王者荣耀英雄战力
🌍 mc服务器 <服务器地址> - 查询Minecraft服务器状态

【生活服务】
🗺️ 路线查询 <出发地> <目的地> - 查询城际路线
⛽ 油价查询 <城市名> - 查询指定城市油价
💰 qq估价 <QQ号> - 查询QQ号估价

【AI功能】
🎨 绘画 <提示词> - AI绘画生成

【网络工具】
🌐 代理ip - 获取socks5代理IP

【娱乐功能】
✨ 星座运势 <星座名> - 查询星座运势图片
🔒 /加密 <内容> - 兽语在线加密
🔓 /解密 <内容> - 兽语在线解密

📌 使用示例：
战力查询 小乔
路线查询 广州 深圳
绘画 一只可爱的猫
/加密 121
/解密 嗷～嗷啊

💡 所有命令支持群聊和私聊使用"""
        
        # 使用自定义的菜单样式图片生成方法
        image_url = await self.text_to_image_menu_style(menu_text)
        
        yield message.image_result(image_url).use_t2i(False)

    async def terminate(self):
        """插件卸载/重载时调用"""
        pass
