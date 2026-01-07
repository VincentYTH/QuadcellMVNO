from flask import Flask, request, Response
import json
import os
from datetime import datetime

class WorldMoveCallback:
    """WorldMove回调处理器"""
    
    def __init__(self, app=None):
        self.app = app
        self.log_dir = "CallbackLogs"
        os.makedirs(self.log_dir, exist_ok=True)
        
        if app is not None:
            self.init_app(app)
    
    def init_app(self, app):
        """初始化Flask应用"""
        self.app = app
        self.register_routes()
    
    def register_routes(self):
        """注册回调路由"""
        @self.app.route('/Api/SOrder/eSIMOrderCallback', methods=['POST'])
        def handle_esim_order_callback():
            data = request.get_json()
            self.log_callback('SOrder/eSIMOrderCallback', data)
            return Response("1", content_type='text/plain')
        
        @self.app.route('/Api/SOrder/eSIMOrderandRedeemCallback', methods=['POST'])
        def handle_esim_order_redeem_callback():
            data = request.get_json()
            self.log_callback('SOrder/eSIMOrderandRedeemCallback', data)
            return Response("1", content_type='text/plain')
        
        @self.app.route('/Api/OrderRedemption/RedeemRedemptionCodeCallback', methods=['POST'])
        def handle_redeem_redemption_code_callback():
            data = request.get_json()
            self.log_callback('OrderRedemption/RedeemRedemptionCodeCallback', data)
            return Response("1", content_type='text/plain')
        
        @self.app.route('/Api/SOrder/TopUpCallback', methods=['POST'])
        def handle_top_up_callback():
            data = request.get_json()
            self.log_callback('SOrder/TopUpCallback', data)
            return Response("1", content_type='text/plain')
    
    def log_callback(self, endpoint, data):
        """记录回调日志"""
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        filename = f"{endpoint.replace('/', '_')}_{timestamp}.json"
        filepath = os.path.join(self.log_dir, filename)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        print(f"Callback received from {endpoint} and saved to {filepath}")
        print(f"Callback data: {json.dumps(data, ensure_ascii=False, indent=2)}")