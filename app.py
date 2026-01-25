from flask import Flask, render_template, request, jsonify, g, session, Response, send_file
from datetime import datetime, timedelta
import os
import threading
import subprocess
import time
import requests
from collections import deque
import json
from urllib.parse import unquote
from flask_cors import CORS
from config.languages import LANGUAGES
from models.sim_resource import db, SimResource
from modules.sim_resources.routes import sim_resources_bp
from modules.montnet_api import MontNetAPI
from modules.quadcell_api import QuadcellAPI
from modules.simlessly_api import SimlesslyAPI
from modules.worldmove_api import WorldMoveAPI
from modules.sim_resources.manager import SimResourceManager
from config.sim_resource import LOW_STOCK_THRESHOLD

app = Flask(__name__)
app.secret_key = 'QB($67:;P2G-h4qGo|f?'
CORS(app)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size


# 确保上传目录存在
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# 回调日志目录
CALLBACK_LOG_DIR = "CallbackLogs"
os.makedirs(CALLBACK_LOG_DIR, exist_ok=True)

# 存储最近的回调数据（最多100条）
recent_callbacks = deque(maxlen=100)
callback_lock = threading.Lock()

# Ngrok进程和公网URL
ngrok_process = None
public_url = None

# 配置数据库
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://postgres:123456@192.168.1.104:5432/sim_management_db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# 數據庫連接池配置 (解決 server closed the connection unexpectedly 問題)
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_pre_ping': True,       # 關鍵設置：每次獲取連接前自動檢測有效性
    'pool_recycle': 3600,        # 每小時自動回收重置連接，防止連接過舊
    'pool_size': 10,             # 連接池大小
    'max_overflow': 20           # 當連接池滿時，允許額外創建的連接數
}

db.init_app(app)

# 注册蓝图
app.register_blueprint(sim_resources_bp)

# 上下文处理器，提供当前年份给所有模板
@app.context_processor
def inject_current_year():
    return {'current_year': datetime.now().year}

# 注册为全局函数
@app.context_processor
def utility_processor():
    def _(key):
        return LANGUAGES.get(g.language, {}).get(key, key)
    return {'_': _}

@app.before_request
def before_request():
    # 设置默认语言
    if 'language' not in session:
        session['language'] = 'zh-TW'  # Default繁體中文
    g.language = session['language']
    g.languages = LANGUAGES

# 添加语言切换路由
@app.route('/set_language/<language>')
def set_language(language):
    if language in LANGUAGES:
        session['language'] = language
    return '', 204

# 在 app.py 中添加模板过滤器
@app.template_filter('translate')
def translate_filter(key):
    """模板过滤器用于翻译文本"""
    return LANGUAGES.get(g.language, {}).get(key, key)

# UTC to HK time
@app.template_filter('hk_time')
def hk_time_filter(dt):
    if dt is None:
        return '-'
    
    # 直接加 8 小時轉換為香港時間
    hk_dt = dt + timedelta(hours=8)
    
    # 格式化為 YYYY-MM-DD HH:MM
    return hk_dt.strftime('%Y-%m-%d %H:%M')

# 启动Ngrok隧道
def start_ngrok():
    global ngrok_process, public_url
    
    try:
        # 启动Ngrok隧道
        ngrok_process = subprocess.Popen(
            ['ngrok', 'http', '5000'],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        
        # 等待Ngrok启动并获取公网URL
        time.sleep(3)  # 给Ngrok一些启动时间
        
        # 获取Ngrok隧道信息

        response = requests.get('http://localhost:4040/api/tunnels')
        tunnels = response.json().get('tunnels', [])
        
        if tunnels:
            public_url = tunnels[0].get('public_url')
            print(f"Ngrok tunnel established: {public_url}")
            
            # 打印回调URL供WorldMove使用
            print("\nWorldMove回调URL:")
            print(f"eSIM订单回调: {public_url}/Api/SOrder/eSIMOrderCallback")
            print(f"eSIM订单和兑换回调: {public_url}/Api/SOrder/eSIMOrderandRedeemCallback")
            print(f"兑换码兑换回调: {public_url}/Api/OrderRedemption/RedeemRedemptionCodeCallback")
            print(f"充值回调: {public_url}/Api/SOrder/TopUpCallback")
            print("\n请将这些URL提供给WorldMove技术支持")
        else:
            print("Failed to establish Ngrok tunnel")
            public_url = None
            
    except Exception as e:
        print(f"Error starting Ngrok: {str(e)}")
        public_url = None

# 停止Ngrok隧道
def stop_ngrok():
    global ngrok_process
    if ngrok_process:
        ngrok_process.terminate()
        ngrok_process = None
        print("Ngrok tunnel stopped")
        
# 记录回调日志
def log_callback(endpoint, data):
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    filename = f"{endpoint.replace('/', '_')}_{timestamp}.json"
    filepath = os.path.join(CALLBACK_LOG_DIR, filename)
    
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    # 将回调数据添加到最近回调列表
    callback_data = {
        'endpoint': endpoint,
        'timestamp': timestamp,
        'filename': filename,
        'data': data
    }
    
    with callback_lock:
        recent_callbacks.appendleft(callback_data)
    
    print(f"Callback received from {endpoint} and saved to {filepath}")
    print(f"Callback data: {json.dumps(data, ensure_ascii=False, indent=2)}")
    
    return callback_data      

# 添加获取最近回调数据的API端点
@app.route('/api/worldmove/callback/recent')
def get_recent_callbacks():
    """获取最近的回调数据"""
    with callback_lock:
        # 转换为列表并返回
        return jsonify(list(recent_callbacks))

# 主页面路由
@app.route('/')
def index():
    """主頁面 - 依供應商分組顯示 SIM 庫存（含低庫存警告）"""
    from sqlalchemy import func

    # 查詢數據：按 Supplier 和 Type 分組統計數量
    # 結果類似: [('MontNet', 'Physical SIM', 1000), ('MontNet', 'eSIM', 880), ...]
    inventory_counts = db.session.query(
        SimResource.supplier,
        SimResource.type,
        func.count(SimResource.id)
    ).filter(
        SimResource.status == 'Available'  # <--- 只統計可用庫存
    ).group_by(SimResource.supplier, SimResource.type).all()
    
    inventory_data = {}
    for supplier, card_type, count in inventory_counts:
        if not supplier: # 處理供應商為空的情況
            supplier = "Unknown"
        if supplier not in inventory_data:
            inventory_data[supplier] = {}
        inventory_data[supplier][card_type] = count
    
    # 對供應商名稱進行排序 (可選，讓顯示順序固定)
    sorted_inventory = dict(sorted(inventory_data.items()))
    
    return render_template('index.html',
                           inventory_data=sorted_inventory,
                           low_stock_threshold=LOW_STOCK_THRESHOLD,
                           full_width=False)

# 供應商頁面
@app.route('/api/<vendor>')
def vendor_page(vendor):
    """供應商特定頁面"""
    vendors = {
        'quadcell': 'Quadcell',
        'montnet': 'MontNet',
        'simlessly': 'Simlessly',
        'worldmove': 'WorldMove'
    }
    
    if vendor not in vendors:
        return "供應商不存在", 404
        
    # 為不同供應商提供端點列表
    endpoints = []
    companies = []
    if vendor == 'montnet':
        try:
            api = MontNetAPI()
            endpoints = api.get_endpoints()
        except Exception as e:
            print(f"Error getting endpoints: {e}")
            endpoints = []
    elif vendor == 'quadcell':
        try:
            api = QuadcellAPI()
            endpoints = api.get_endpoints()
            companies = api.load_company_mappings()
        except Exception as e:
            print(f"Error getting endpoints: {e}")
            endpoints = []
    elif vendor == 'worldmove':
        try:
            api = WorldMoveAPI()
            endpoints = api.get_endpoints()
        except Exception as e:
            print(f"Error getting endpoints: {e}")
            endpoints = []
    elif vendor == 'simlessly':
        try:
            api = SimlesslyAPI()
            endpoints = api.get_endpoints()
        except Exception as e:
            print(f"Error getting endpoints: {e}")
            endpoints = []            
    
    return render_template(f'{vendor}.html', 
                         vendor_name=vendors[vendor], 
                         endpoints=endpoints,
                         companies=companies,
                         montnet_auth_key=MontNetAPI.FIXED_AUTH_KEY if vendor == 'montnet' else '',
                         quadcell_auth_key=QuadcellAPI.DEFAULT_AUTH_KEY if vendor == 'quadcell' else '',
                         full_width=False)

# MontNet路由
@app.route('/api/montnet/single', methods=['POST'])
def montnet_single():
    """处理MontNet单条请求"""
    try:
        endpoint = request.form.get('endpoint')
        payload = {}
        
        # 构建payload，排除endpoint字段
        for key in request.form:
            if key != 'endpoint':
                payload[key] = request.form.get(key)
        
        # 添加固定authKey
        payload['authKey'] = MontNetAPI.FIXED_AUTH_KEY
        
        # 发送请求
        api = MontNetAPI()
        response = api.single_request(endpoint, payload)
        
        return jsonify(response)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    
@app.route('/api/montnet/batch', methods=['POST'])
def montnet_batch():
    """处理MontNet批量请求"""
    try:
        # 检查文件上传
        if 'file' not in request.files:
            return jsonify({'error': '没有上传文件'}), 400
            
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': '没有选择文件'}), 400
        
        # 检查文件扩展名
        if not file.filename.lower().endswith(('.xlsx', '.xls')):
            return jsonify({'error': '只支持Excel文件(.xlsx, .xls)'}), 400
            
        # 保存上传的文件
        filename = f"montnet_{datetime.now().strftime('%Y%m%d_%H%M%S')}{os.path.splitext(file.filename)[1]}"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        
        # 获取延迟参数
        delay = float(request.form.get('delay', 0.5))
        
        # 处理请求
        api = MontNetAPI()
        result_path = api.batch_process(filepath, delay)
        
        # 确保文件存在
        if not os.path.exists(result_path):
            return jsonify({'error': '结果文件生成失败'}), 500
            
        # 返回结果文件名（前端将使用此文件名下载）
        result_filename = os.path.basename(result_path)
        return jsonify({
            'success': True,
            'filename': result_filename,
            'message': f'处理完成，共处理了{api.processed_count}条请求'
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    
@app.route('/api/montnet/endpoint/<path:endpoint>/params')
def montnet_endpoint_params(endpoint):
    """获取MontNet端点的参数信息，支持多语言"""
    try:
        # 解码URL编码的端点
        endpoint = unquote(endpoint)
        print(f"Getting params for endpoint: {endpoint}")
        
        # 获取当前语言
        language = g.language
        
        api = MontNetAPI()
        raw_params = api.get_endpoint_params(endpoint)
        
        if not raw_params:
            return jsonify({'error': f'Endpoint {endpoint} not found'}), 404
        
        # 应用多语言翻译到参数描述
        translated_params = []
        for param in raw_params:
            translated_param = param.copy()
            description_key = param.get('description_key', '')
            if description_key:
                # 从语言配置中获取翻译
                translated_param['description'] = LANGUAGES.get(language, {}).get(description_key, description_key)
            # 移除description_key，前端不需要
            if 'description_key' in translated_param:
                del translated_param['description_key']
            translated_params.append(translated_param)
            
        return jsonify(translated_params)
    except Exception as e:
        print(f"Error getting params for {endpoint}: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500
    
# Quadcell路由
@app.route('/api/quadcell/batch', methods=['POST'])
def quadcell_batch():
    """处理Quadcell批量请求"""
    try:
        # 检查文件上传
        if 'file' not in request.files:
            return jsonify({'error': '没有上传文件'}), 400
            
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': '没有选择文件'}), 400
        
        # 检查文件扩展名
        if not file.filename.lower().endswith(('.xlsx', '.xls')):
            return jsonify({'error': '只支持Excel文件(.xlsx, .xls)'}), 400
            
        # 保存上传的文件
        filename = f"quadcell_{datetime.now().strftime('%Y%m%d_%H%M%S')}{os.path.splitext(file.filename)[1]}"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        
        # 获取延迟参数和公司名称
        delay = float(request.form.get('delay', 0.5))
        company_name = request.form.get('companyName')
        
        # 处理请求
        api = QuadcellAPI()
        result_path = api.batch_process(filepath, delay, company_name)
        
        # 确保文件存在
        if not os.path.exists(result_path):
            return jsonify({'error': '结果文件生成失败'}), 500
            
        # 返回结果文件名（前端将使用此文件名下载）
        result_filename = os.path.basename(result_path)
        return jsonify({
            'success': True,
            'filename': result_filename,
            'message': f'处理完成，共处理了{api.processed_count}条请求'
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/quadcell/single', methods=['POST'])
def quadcell_single():
    """處理Quadcell單條請求"""
    try:
        endpoint = request.form.get('endpoint')
        company_name = request.form.get('companyName')
        debug_mode = request.form.get('debug', 'false').lower() == 'true'  # 新增調試模式參數
        payload = {}
        
        # 構建payload，排除endpoint、companyName和debug字段
        for key in request.form:
            if key not in ['endpoint', 'companyName', 'debug']:
                payload[key] = request.form.get(key)
        
        # 根據公司名稱獲取authKey（優先級最高）
        if company_name:
            api = QuadcellAPI()
            company_auth_key = api.get_company_authkey(company_name)
            if company_auth_key:
                payload['authKey'] = company_auth_key
                print(f"Using authKey from company: {company_name}")
        
        # 如果沒有提供authKey，使用默認值
        if 'authKey' not in payload:
            payload['authKey'] = QuadcellAPI.DEFAULT_AUTH_KEY
            print("Using default authKey")
        
        # 發送請求，傳遞調試模式參數
        api = QuadcellAPI()
        response = api.single_request(endpoint, payload, debug=debug_mode)
        
        return jsonify(response)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    
@app.route('/api/quadcell/endpoint/<path:endpoint>/params')
def quadcell_endpoint_params(endpoint):
    """获取Quadcell端点的参数信息，支持多语言"""
    try:
        # 解码URL编码的端点
        endpoint = unquote(endpoint)
        print(f"Getting params for endpoint: {endpoint}")
        
        # 获取当前语言
        language = g.language
        
        api = QuadcellAPI()
        raw_params = api.get_endpoint_params(endpoint)
        
        if not raw_params:
            return jsonify({'error': f'Endpoint {endpoint} not found'}), 404
        
        # 应用多语言翻译到参数描述
        translated_params = []
        for param in raw_params:
            translated_param = param.copy()
            description_key = param.get('description_key', '')
            if description_key:
                # 从语言配置中获取翻译
                translated_param['description'] = LANGUAGES.get(language, {}).get(description_key, description_key)
            # 移除description_key，前端不需要
            if 'description_key' in translated_param:
                del translated_param['description_key']
            translated_params.append(translated_param)
            
        return jsonify(translated_params)
    except Exception as e:
        print(f"Error getting params for {endpoint}: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500 

# 添加公司映射管理路由
@app.route('/api/quadcell/companies')
def get_quadcell_companies():
    """获取所有公司映射"""
    try:
        api = QuadcellAPI()
        companies = api.load_company_mappings()
        return jsonify(companies)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/quadcell/companies', methods=['POST'])
def add_quadcell_company():
    """添加公司映射"""
    try:
        data = request.get_json()
        company_name = data.get('companyName')
        auth_key = data.get('authKey')
        
        if not company_name or not auth_key:
            return jsonify({'error': 'companyName and authKey are required'}), 400
        
        api = QuadcellAPI()
        companies = api.load_company_mappings()
        
        # 检查是否已存在
        for company in companies:
            if company['companyName'] == company_name:
                return jsonify({'error': 'Company already exists'}), 400
        
        # 添加新公司
        companies.append({
            'companyName': company_name,
            'authKey': auth_key
        })
        
        api.save_company_mappings(companies)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/quadcell/companies/<company_name>', methods=['PUT'])
def update_quadcell_company(company_name):
    """更新公司映射"""
    try:
        company_name = unquote(company_name)
        data = request.get_json()
        new_auth_key = data.get('authKey')
        
        if not new_auth_key:
            return jsonify({'error': 'authKey is required'}), 400
        
        api = QuadcellAPI()
        companies = api.load_company_mappings()
        
        # 查找并更新
        for company in companies:
            if company['companyName'] == company_name:
                company['authKey'] = new_auth_key
                api.save_company_mappings(companies)
                return jsonify({'success': True})
        
        return jsonify({'error': 'Company not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/quadcell/companies/<company_name>', methods=['DELETE'])
def delete_quadcell_company(company_name):
    """删除公司映射"""
    try:
        company_name = unquote(company_name)
        api = QuadcellAPI()
        companies = api.load_company_mappings()
        
        # 过滤掉要删除的公司
        updated_companies = [c for c in companies if c['companyName'] != company_name]
        
        if len(updated_companies) == len(companies):
            return jsonify({'error': 'Company not found'}), 404
        
        api.save_company_mappings(updated_companies)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500    
    
# Simlessly路由
@app.route('/api/simlessly/endpoint/<path:endpoint>/params')
def simlessly_endpoint_params(endpoint):
    """获取Simlessly端点的参数信息，支持多语言"""
    try:
        # 解码URL编码的端点
        endpoint = unquote(endpoint)
        print(f"Getting params for endpoint: {endpoint}")
        
        # 获取当前语言
        language = g.language
        
        api = SimlesslyAPI()
        raw_params = api.get_endpoint_params(endpoint)
        
        if not raw_params:
            return jsonify({'error': f'Endpoint {endpoint} not found'}), 404
        
        # 应用多语言翻译到参数描述
        translated_params = []
        for param in raw_params:
            translated_param = param.copy()
            description_key = param.get('description_key', '')
            if description_key:
                # 从语言配置中获取翻译
                translated_param['description'] = LANGUAGES.get(language, {}).get(description_key, description_key)
            # 移除description_key，前端不需要
            if 'description_key' in translated_param:
                del translated_param['description_key']
            translated_params.append(translated_param)
            
        return jsonify(translated_params)
    except Exception as e:
        print(f"Error getting params for {endpoint}: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/simlessly/batch', methods=['POST'])
def simlessly_batch():
    """处理Simlessly批量请求"""
    try:
        # 检查文件上传
        if 'file' not in request.files:
            return jsonify({'error': '没有上传文件'}), 400
            
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': '没有选择文件'}), 400
        
        # 检查文件扩展名
        if not file.filename.lower().endswith(('.xlsx', '.xls')):
            return jsonify({'error': '只支持Excel文件(.xlsx, .xls)'}), 400
            
        # 保存上传的文件
        filename = f"simlessly_{datetime.now().strftime('%Y%m%d_%H%M%S')}{os.path.splitext(file.filename)[1]}"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        
        # 获取延迟参数
        delay = float(request.form.get('delay', 0.5))
        
        # 处理请求
        api = SimlesslyAPI()
        result_path = api.batch_process(filepath, delay)
        
        # 确保文件存在
        if not os.path.exists(result_path):
            return jsonify({'error': '结果文件生成失败'}), 500
            
        # 返回结果文件名（前端将使用此文件名下载）
        result_filename = os.path.basename(result_path)
        return jsonify({
            'success': True,
            'filename': result_filename,
            'message': f'处理完成，共处理了{api.processed_count}条请求'
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/simlessly/single', methods=['POST'])
def simlessly_single():
    """处理Simlessly单条请求"""
    try:
        endpoint = request.form.get('endpoint')
        payload = {}
        
        # 构建payload，排除endpoint字段
        for key in request.form:
            if key != 'endpoint':
                value = request.form.get(key)
                payload[key] = value
        
        # 发送请求
        api = SimlesslyAPI()
        response = api.single_request(endpoint, payload)
        
        return jsonify(response)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# WorldMove路由
@app.route('/api/worldmove/batch', methods=['POST'])
def worldmove_batch():
    """处理WorldMove批量请求"""
    try:
        # 检查文件上传
        if 'file' not in request.files:
            return jsonify({'error': '没有上传文件'}), 400
            
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': '没有选择文件'}), 400
        
        # 检查文件扩展名
        if not file.filename.lower().endswith(('.xlsx', '.xls')):
            return jsonify({'error': '只支持Excel文件(.xlsx, .xls)'}), 400
            
        # 保存上传的文件
        filename = f"worldmove_{datetime.now().strftime('%Y%m%d_%H%M%S')}{os.path.splitext(file.filename)[1]}"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        
        # 获取延迟参数
        delay = float(request.form.get('delay', 0.5))
        
        # 处理请求
        api = WorldMoveAPI()
        result_path = api.batch_process(filepath, delay)
        
        # 确保文件存在
        if not os.path.exists(result_path):
            return jsonify({'error': '结果文件生成失败'}), 500
            
        # 返回结果文件名（前端将使用此文件名下载）
        result_filename = os.path.basename(result_path)
        return jsonify({
            'success': True,
            'filename': result_filename,
            'message': f'处理完成，共处理了{api.processed_count}条请求'
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/worldmove/single', methods=['POST'])
def worldmove_single():
    """处理WorldMove单条请求"""
    try:
        endpoint = request.form.get('endpoint')
        payload = {}
        
        # 构建payload，处理所有参数
        for key in request.form:
            if key != 'endpoint':
                value = request.form.get(key)
                
                # 尝试解析数组参数
                if '[' in key and ']' in key:
                    # 解析数组参数格式: paramName[index][fieldName]
                    import re
                    match = re.match(r'(\w+)\[(\d+)\]\[(\w+)\]', key)
                    if match:
                        base_name = match.group(1)
                        index = int(match.group(2))
                        field_name = match.group(3)
                        
                        if base_name not in payload:
                            payload[base_name] = []
                        
                        # 确保数组足够大
                        while len(payload[base_name]) <= index:
                            payload[base_name].append({})
                        
                        # 设置字段值
                        payload[base_name][index][field_name] = value
                    else:
                        # 如果不是数组格式，作为普通参数处理
                        payload[key] = value
                else:
                    # 普通参数
                    payload[key] = value
        
        # 打印调试信息
        print(f"Endpoint: {endpoint}")
        print(f"Payload: {json.dumps(payload, indent=2)}")
        
        # 发送请求
        api = WorldMoveAPI()
        response = api.single_request(endpoint, payload)
        
        return jsonify(response)
        
    except Exception as e:
        print(f"Error in worldmove_single: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

# WorldMove回调路由
@app.route('/Api/SOrder/eSIMOrderCallback', methods=['POST'])
def handle_esim_order_callback():
    data = request.get_json()
    log_callback('SOrder/eSIMOrderCallback', data)
    return Response("1", content_type='text/plain')

@app.route('/Api/SOrder/eSIMOrderandRedeemCallback', methods=['POST'])
def handle_esim_order_redeem_callback():
    data = request.get_json()
    log_callback('SOrder/eSIMOrderandRedeemCallback', data)
    return Response("1", content_type='text/plain')

@app.route('/Api/OrderRedemption/RedeemRedemptionCodeCallback', methods=['POST'])
def handle_redeem_redemption_code_callback():
    data = request.get_json()
    log_callback('OrderRedemption/RedeemRedemptionCodeCallback', data)
    return Response("1", content_type='text/plain')

@app.route('/Api/SOrder/TopUpCallback', methods=['POST'])
def handle_top_up_callback():
    data = request.get_json()
    log_callback('SOrder/TopUpCallback', data)
    return Response("1", content_type='text/plain')

# 获取Ngrok状态的路由
@app.route('/api/ngrok/status')
def ngrok_status():
    return jsonify({
        'active': ngrok_process is not None,
        'public_url': public_url,
        'callback_urls': {
            'esim_order': f"{public_url}/Api/SOrder/eSIMOrderCallback" if public_url else None,
            'esim_order_redeem': f"{public_url}/Api/SOrder/eSIMOrderandRedeemCallback" if public_url else None,
            'redemption_code': f"{public_url}/Api/OrderRedemption/RedeemRedemptionCodeCallback" if public_url else None,
            'top_up': f"{public_url}/Api/SOrder/TopUpCallback" if public_url else None
        }
    })

# 启动Ngrok隧道的路由
@app.route('/api/ngrok/start')
def start_ngrok_tunnel():
    try:
        if ngrok_process is None:
            # 在新线程中启动Ngrok，避免阻塞主线程
            thread = threading.Thread(target=start_ngrok)
            thread.daemon = True
            thread.start()
            return jsonify({'success': True, 'message': 'Starting Ngrok tunnel'})
        else:
            return jsonify({'success': False, 'message': 'Ngrok tunnel is already running'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

# 停止Ngrok隧道的路由
@app.route('/api/ngrok/stop')
def stop_ngrok_tunnel():
    try:
        stop_ngrok()
        return jsonify({'success': True, 'message': 'Stopped Ngrok tunnel'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/worldmove/endpoint/<path:endpoint>/params')
def worldmove_endpoint_params(endpoint):
    """获取WorldMove端点的参数信息，支持多语言"""
    try:
        # 解码URL编码的端点
        endpoint = unquote(endpoint)
        print(f"Getting params for endpoint: {endpoint}")
        
        # 获取当前语言
        language = g.language
        
        api = WorldMoveAPI()
        raw_params = api.get_endpoint_params(endpoint)
        
        if not raw_params:
            return jsonify({'error': f'Endpoint {endpoint} not found'}), 404
        
        # 应用多语言翻译到参数描述
        translated_params = []
        for param in raw_params:
            translated_param = param.copy()
            description_key = param.get('description_key', '')
            if description_key:
                # 从语言配置中获取翻译
                translated_param['description'] = LANGUAGES.get(language, {}).get(description_key, description_key)
            # 移除description_key，前端不需要
            if 'description_key' in translated_param:
                del translated_param['description_key']
            translated_params.append(translated_param)
            
        return jsonify(translated_params)
    except Exception as e:
        print(f"Error getting params for {endpoint}: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

# 修改WorldMove回调信息页面
@app.route('/api/worldmove/callbacks')
def worldmove_callbacks():
    """显示WorldMove回调信息"""
    # 获取Ngrok状态
    ngrok_active = ngrok_process is not None
    callback_urls = {
        'esim_order': f"{public_url}/Api/SOrder/eSIMOrderCallback" if public_url else None,
        'esim_order_redeem': f"{public_url}/Api/SOrder/eSIMOrderandRedeemCallback" if public_url else None,
        'redemption_code': f"{public_url}/Api/OrderRedemption/RedeemRedemptionCodeCallback" if public_url else None,
        'top_up': f"{public_url}/Api/SOrder/TopUpCallback" if public_url else None
    }
    
    return render_template('worldmove_callbacks.html', 
                         public_url=public_url,
                         ngrok_active=ngrok_active,
                         callback_urls=callback_urls)
    
# 添加获取回调日志文件列表的API端点
@app.route('/api/worldmove/callback/files')
def get_callback_files():
    """获取所有回调日志文件"""
    try:
        files = []
        for filename in os.listdir(CALLBACK_LOG_DIR):
            filepath = os.path.join(CALLBACK_LOG_DIR, filename)
            if os.path.isfile(filepath):
                stat = os.stat(filepath)
                files.append({
                    'name': filename,
                    'size': f"{stat.st_size / 1024:.1f} KB",
                    'mtime': datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
                })
        
        # 按修改时间倒序排序
        files.sort(key=lambda x: x['mtime'], reverse=True)
        return jsonify(files)
    except Exception as e:
        return jsonify({'error': str(e)}), 500    
    
# 添加下载回调日志文件的API端点
@app.route('/api/worldmove/callback/file/<filename>')
def download_callback_file(filename):
    """下载回调日志文件"""
    try:
        # 安全地获取文件路径
        safe_filename = os.path.basename(filename)
        file_path = os.path.join(CALLBACK_LOG_DIR, safe_filename)
        
        # 检查文件是否存在
        if not os.path.exists(file_path):
            return jsonify({'error': '文件不存在'}), 404
            
        # 返回文件
        return send_file(
            file_path,
            as_attachment=True,
            download_name=safe_filename,
            mimetype='application/json'
        )
    except Exception as e:
        return jsonify({'error': str(e)}), 500    

# 通用下载路由
@app.route('/api/download/<vendor>/<filename>')
def download_file(vendor, filename):
    """下载处理结果文件"""
    try:
        # 安全地获取文件路径
        safe_filename = os.path.basename(filename)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], "Log", safe_filename)
        
        # 检查文件是否存在
        if not os.path.exists(file_path):
            return jsonify({'error': '文件不存在'}), 404
            
        # 返回文件
        return send_file(
            file_path,
            as_attachment=True,
            download_name=f"{vendor}_result_{safe_filename}",
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# 批量处理 - 通用模板下载路由
@app.route('/api/template/<vendor>')
def download_vendor_template(vendor):
    """下载供应商Excel模板"""
    try:
        # 支持的供应商列表
        valid_vendors = ['quadcell', 'montnet', 'simlessly', 'worldmove']
        
        if vendor not in valid_vendors:
            return jsonify({'error': '不支持的供应商'}), 404
        
        template_filename = f"{vendor.capitalize()}_Request_Template.xlsx"
        template_path = os.path.join("ExcelTemplate", template_filename)
        
        # 检查模板文件是否存在
        if not os.path.exists(template_path):
            return jsonify({'error': f'{vendor} 模板文件不存在'}), 404
            
        return send_file(
            template_path,
            as_attachment=True,
            download_name=template_filename,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    
@app.route('/api/template/sim_resources')
def download_sim_template():
    """下載 SIM 資源匯入範本"""
    try:
        template_path = os.path.join("ExcelTemplate", "SIM_Resource_Import_Template.xlsx")
        
        if not os.path.exists(template_path):
            return jsonify({'error': '範本檔案不存在'}), 404
            
        return send_file(
            template_path,
            as_attachment=True,
            download_name="SIM_Resource_Import_Template.xlsx",
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
    except Exception as e:
        return jsonify({'error': str(e)}), 500    

if __name__ == '__main__':
    
    app.run(host='0.0.0.0', port=5000, debug=True)
