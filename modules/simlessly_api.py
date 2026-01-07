import hmac
import hashlib
import uuid
import requests
import json
import pandas as pd
import time
import os
import re
from datetime import datetime
from tqdm import tqdm
from config.simlessly_config import SIMLESSLY_ENDPOINT_CONFIG, SIMLESSLY_ENDPOINT_DESCRIPTIONS

class HmacApiClient:
    """
    HMAC-SHA256 API Client
    Handles HMAC-SHA256 authentication for APIs
    """
    
    # Fixed credentials
    ACCESS_KEY = "18ff98cb24944b35beb60095ea907849"
    SECRET_KEY = "a122095fd86d412dbb202760ae206c5d"
    
    @staticmethod
    def get_endpoints():
        """获取所有可用的端点"""
        return list(SIMLESSLY_ENDPOINT_CONFIG.keys())

    @staticmethod
    def get_endpoint_params(endpoint):
        """获取指定端点的参数信息"""
        if endpoint in SIMLESSLY_ENDPOINT_CONFIG:
            return SIMLESSLY_ENDPOINT_CONFIG[endpoint]["params"]
        return []
    
    @staticmethod
    def get_endpoint_description_key(endpoint):
        """获取端点的描述键"""
        return SIMLESSLY_ENDPOINT_DESCRIPTIONS.get(endpoint, "")    
    
    @staticmethod
    def generate_signature(data, secret_key):
        """
        Generate HMAC-SHA256 signature
        :param data: Data to sign (string)
        :param secret_key: Secret key (string)
        :return: Signature in uppercase hex
        """
        # Convert data and secret to bytes
        data_bytes = data.encode('utf-8')
        secret_bytes = secret_key.encode('utf-8')
        
        # Generate HMAC-SHA256
        signature = hmac.new(secret_bytes, data_bytes, hashlib.sha256).digest()
        
        # Convert to hex and uppercase
        return signature.hex().upper()
    
    @staticmethod
    def do_hmac_post(base_url, endpoint, request_body, 
                    request_id=None, timestamp=None, verbose=True):
        """
        Send POST request with HMAC-SHA256 authentication
        :param base_url: Base API URL
        :param endpoint: API endpoint
        :param request_body: JSON request payload
        :param verbose: Whether to print detailed logs
        :return: JSON response
        """
        # Generate timestamp and request ID if not provided
        timestamp = timestamp or str(int(time.time() * 1000))
        request_id = request_id or str(uuid.uuid4())
        
        # Create signData: Timestamp + RequestID + AccessKey + RequestBody
        sign_data = f"{timestamp}{request_id}{HmacApiClient.ACCESS_KEY}{request_body}"
        
        if verbose:
            print(f"[Sign Data] {sign_data}")
        
        # Generate signature
        signature = HmacApiClient.generate_signature(sign_data, HmacApiClient.SECRET_KEY)
        
        # Construct full URL
        full_url = f"{base_url.rstrip('/')}/{endpoint.lstrip('/')}"
        
        if verbose:
            print(f"[HMAC-Send] {full_url}")
            print(f"[HMAC-Send] {request_body}")
            print(f"[HMAC-Signature] {signature}")
        
        # Set request headers
        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'Timestamp': timestamp,
            'RequestID': request_id,
            'AccessKey': HmacApiClient.ACCESS_KEY,
            'Signature': signature
        }
        
        try:
            # Send HTTP POST request
            response = requests.post(
                full_url, 
                data=request_body, 
                headers=headers,
                timeout=30
            )
            
            if verbose:
                print(f"[HTTP Status] {response.status_code}")
                print(f"[Response] {response.text}")
            
            # Try to parse JSON if possible, otherwise return text
            try:
                return response.json()
            except:
                return response.text
        
        except Exception as e:
            if verbose:
                print(f"Request failed: {str(e)}")
            raise

class HttpApiClient:
    """
    HTTP API Client for HMAC-SHA256 APIs
    """
    
    # Fixed base URL
    BASE_URL = "https://rsp.simlessly.com/api/v1/"
    
    @staticmethod
    def do_post(endpoint, http_req, verbose=True):
        """
        Sends HMAC-SHA256 authenticated POST request
        :param endpoint: API endpoint path
        :param http_req: JSON request payload
        :param verbose: Whether to print detailed logs
        :return: JSON response or raw response
        """
        return HmacApiClient.do_hmac_post(
            base_url=HttpApiClient.BASE_URL,
            endpoint=endpoint,
            request_body=http_req,
            verbose=verbose
        )

def build_nested_dict(flat_dict):
    """
    Convert a flat dictionary with dot notation keys into a nested dictionary
    :param flat_dict: Dictionary with keys like 'parent.child'
    :return: Nested dictionary
    """
    nested_dict = {}
    for key, value in flat_dict.items():
        # Split key by dots to create nested structure
        parts = key.split('.')
        current_level = nested_dict
        
        # Traverse through the key parts
        for i, part in enumerate(parts):
            # If this is the last part, set the value
            if i == len(parts) - 1:
                current_level[part] = value
            else:
                # If the next level doesn't exist, create it
                if part not in current_level:
                    current_level[part] = {}
                current_level = current_level[part]
    
    return nested_dict

def get_key_from_response(response, key_paths):
    """
    Try to extract a value from response using multiple possible key paths
    :param response: API response (dict)
    :param key_paths: List of possible key paths to try
    :return: Found value or None
    """
    for path in key_paths:
        keys = path.split('.')
        value = response
        found = True
        
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            elif isinstance(value, list) and len(value) > 0 and key.isdigit():
                index = int(key)
                if index < len(value):
                    value = value[index]
                else:
                    found = False
                    break
            else:
                found = False
                break
        
        if found:
            return value
    
    return None

class SimlesslyAPI:
    """Simlessly API 封装类"""
    
    # Fixed base URL
    BASE_URL = "https://rsp.simlessly.com/api/v1/"

    def get_endpoints(self):
        """获取所有可用的端点"""
        return HmacApiClient.get_endpoints()
    
    def get_endpoint_params(self, endpoint):
        """获取指定端点的参数信息"""
        return HmacApiClient.get_endpoint_params(endpoint)
    
    def get_endpoint_description_key(self, endpoint):
        """获取端点的描述键"""
        return HmacApiClient.get_endpoint_description_key(endpoint)
    
    def __init__(self):
        self.client = HttpApiClient()
        self.processed_count = 0
    
    def single_request(self, endpoint, payload_dict):
        """发送单条API请求"""
        try:
            # 处理列表类型的参数（将字符串转换为JSON数组）
            list_params = ['hplmnList', 'ehplmnList', 'oplmnList', 'fplmnList', 'multiImsiDataList']
            
            for param in list_params:
                if param in payload_dict and payload_dict[param]:
                    try:
                        # 尝试解析JSON字符串
                        if isinstance(payload_dict[param], str):
                            payload_dict[param] = json.loads(payload_dict[param])
                    except json.JSONDecodeError:
                        # 如果解析失败，保持原样（让API返回错误）
                        pass
            
            # 构建嵌套的payload
            nested_payload = build_nested_dict(payload_dict)
            payload_json = json.dumps(nested_payload, ensure_ascii=False)
            
            response = self.client.do_post(
                endpoint, 
                payload_json, 
                verbose=False  # 设置为False关闭详细日志
            )
            return response
        except Exception as e:
            return {"error": str(e)}
    
    def batch_process(self, input_path, delay=0.5):
        """批量处理Excel文件中的请求"""
        # 重置处理计数
        self.processed_count = 0
        
        # 读取Excel数据
        df = pd.read_excel(input_path)
        
        # 扩展ICCID范围
        expanded_df = self.expand_iccid_ranges(df)
        
        # 准备结果目录
        log_dir = os.path.join(os.path.dirname(input_path), "Log")
        os.makedirs(log_dir, exist_ok=True)
        
        # 生成输出文件名
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        output_path = os.path.join(log_dir, f"{timestamp}.xlsx")
        
        # 准备结果列表
        results = []
        
        # 显示处理信息
        print(f"▶ Processing {len(expanded_df)} requests with {delay}s delay...")
        
        # 处理每个请求，使用tqdm显示进度条
        for index, row in tqdm(expanded_df.iterrows(), total=len(expanded_df)):
            # 构建flat payload字典
            flat_payload = {}
            
            # 添加非空列
            for col in expanded_df.columns:
                if col == "endpoint":
                    continue
                
                if pd.isna(row[col]) or (isinstance(row[col], str) and row[col].strip() == ""):
                    continue
                
                flat_payload[col] = row[col]
            
            # 转换为嵌套结构
            nested_payload = build_nested_dict(flat_payload)
            
            # 发送请求
            try:
                response = self.client.do_post(
                    endpoint=row['endpoint'],
                    http_req=json.dumps(nested_payload, ensure_ascii=False),
                    verbose=False
                )
                
                # 定义可能的响应字段路径
                success_paths = ['success']
                
                iccid_paths = [
                    'obj.iccid',
                    'obj.profileLogs.0.iccid'
                ]
                
                status_paths = [
                    'obj.status',
                    'obj.profileLogs.0.status'
                ]
                
                device_name_paths = [
                    'obj.deviceName',
                    'obj.profileLogs.0.deviceName'
                ]
                
                install_location_paths = [
                    'obj.installLocation',
                    'obj.profileLogs.0.installLocation'
                ]
                
                # 提取值
                success = get_key_from_response(response, success_paths)
                
                # 为日志文件创建完整消息
                full_message = json.dumps(response, indent=2, ensure_ascii=False)
                
                status_flag = "SUCCESS" if success else "FAILED"
                
                # 记录完整响应
                response_record = full_message
                
            except Exception as e:
                error_msg = f"ERROR: {str(e)}"
                status_flag = "FAILED"
                response_record = error_msg
                success = False
            
            # 记录结果
            results.append({
                "Endpoint": row['endpoint'],
                "JSON": json.dumps(nested_payload, ensure_ascii=False),
                "Response": response_record,
                "Status": status_flag,
                "Success": success
            })
            
            # 增加处理计数
            self.processed_count += 1
            
            time.sleep(delay)
        
        # 保存结果
        result_df = pd.DataFrame(results, columns=["Endpoint", "JSON", "Response", "Status", "Success"])
        
        # 使用ExcelWriter确保正确关闭文件
        with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
            result_df.to_excel(writer, index=False, sheet_name='Results')
            
            # 添加摘要信息
            success_count = sum(1 for r in results if r["Status"] == "SUCCESS")
            summary_data = {
                '总请求数': [len(expanded_df)],
                '成功数': [success_count],
                '失败数': [len(expanded_df) - success_count],
                '处理时间': [datetime.now().strftime("%Y-%m-%d %H:%M:%S")]
            }
            summary_df = pd.DataFrame(summary_data)
            summary_df.to_excel(writer, index=False, sheet_name='Summary')
        
        return output_path
    
    @staticmethod
    def expand_iccid_ranges(df):
        """扩展ICCID范围"""
        expanded_rows = []
        range_column = None
        
        # 查找ICCID列
        for col in df.columns:
            if "iccid" in col.lower():
                range_column = col
                break
        
        if range_column is None:
            return df
        
        # 处理每一行
        for index, row in df.iterrows():
            iccid_value = row[range_column]
            
            # 检查是否为范围格式
            if isinstance(iccid_value, str) and re.match(r'^\d+-\d+$', iccid_value.strip()):
                try:
                    start, end = map(int, iccid_value.split('-'))
                    
                    # 为范围内的每个ICCID创建新行
                    for iccid in range(start, end + 1):
                        new_row = row.copy()
                        new_row[range_column] = str(iccid)
                        expanded_rows.append(new_row)
                    
                    continue
                except Exception as e:
                    print(f"Error expanding ICCID range: {str(e)}")
            
            # 非范围值直接添加
            expanded_rows.append(row)
        
        return pd.DataFrame(expanded_rows)