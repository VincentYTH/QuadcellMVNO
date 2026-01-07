import requests
import json
import random
import pandas as pd
import time
import os
import re
from datetime import datetime
from Crypto.Cipher import DES3
from Crypto.Util.Padding import pad, unpad
from tqdm import tqdm
from config.quadcell_config import QUADCELL_ENDPOINT_CONFIG, QUADCELL_ENDPOINT_DESCRIPTIONS

class HttpApiClient:
    """
    HTTP API Client for Quadcell VMS Integration
    Handles encrypted communication with Quadcell API
    """
    
    # Fixed base URL
    BASE_URL = "https://srservice.quadcell.com/qccl/v2"
    # BASE_URL = "https://apiv2.imc-networks.com.hk/qccl/v2" ## UAT
    # BASE_URL = "http://api.quadcell.com:8080/v2" ## SaiYun

    @staticmethod
    def get_endpoints():
        """获取所有可用的端点"""
        return list(QUADCELL_ENDPOINT_CONFIG.keys())

    @staticmethod
    def get_endpoint_params(endpoint):
        """获取指定端点的参数信息"""
        if endpoint in QUADCELL_ENDPOINT_CONFIG:
            return QUADCELL_ENDPOINT_CONFIG[endpoint]["params"]
        return []
    
    @staticmethod
    def get_endpoint_description_key(endpoint):
        """获取端点的描述键"""
        return QUADCELL_ENDPOINT_DESCRIPTIONS.get(endpoint, "")    
    
    @staticmethod
    def do_encrypt_post(endpoint, http_req, verbose=True, suppress_decrypt_logs=False):
        """
        Sends encrypted POST request to Quadcell API
        :param endpoint: API endpoint path (e.g. "IMC/heartbeat")
        :param http_req: JSON request payload
        :param verbose: Whether to print detailed logs
        :param suppress_decrypt_logs: Whether to suppress decryption debug logs
        :return: Decrypted JSON response or raw response for non-200 status
        """
        # Construct full URL
        full_url = f"{HttpApiClient.BASE_URL}/{endpoint.lstrip('/')}"
        if verbose:
            print(f"[HttpApi-Send] {full_url}")
            print(f"[HttpApi-Send] {http_req}")
        
        try:
            # Encrypt request payload using fixed key index '05'
            encrypted_req = HttpApiCodec.encode(http_req, hex_sec_idx='05')
            if verbose:
                print(f"[Encrypted Request] {encrypted_req}")
            
            # Set request headers
            headers = {
                'Content-Type': 'application/json',
                'Accept': 'application/json'
            }
            
            # Send HTTP POST request
            response = requests.post(
                full_url, 
                data=encrypted_req, 
                headers=headers,
                timeout=30
            )
            
            if verbose:
                print(f"[HTTP Status] {response.status_code}")
                print(f"[Raw Response] {response.text}")
            
            # Handle response - support both encrypted and plaintext responses
            if response.status_code == 200:
                # First try to parse as JSON (plaintext error responses)
                try:
                    json_response = response.json()
                    if verbose:
                        print(f"[API Plaintext Response] {json_response}")
                    return json_response
                except:
                    # If not JSON, try to decrypt using fixed key index
                    try:
                        decrypted_ret = HttpApiCodec.decode(
                            response.text, 
                            force_key_idx=0,
                            verbose=not suppress_decrypt_logs  # Control debug logs
                        )
                        if verbose:
                            print(f"[Decrypted Response] {decrypted_ret}")
                        return decrypted_ret
                    except Exception as e:
                        if verbose:
                            print(f"Decryption failed but returning raw response: {str(e)}")
                        return response.text
            return response.text
        
        except Exception as e:
            if verbose:
                print(f"Request failed: {str(e)}")
            raise

class HttpApiCodec:
    """Handles encryption/decryption for Quadcell API communication"""
    
    # Corrected key format - removed 0x prefix
    SECRET_KEY_POOL = [
        "F24D971DA7174DA9AA0252F861447177725A02B6274A44E7",  # key01
        "498B731F89B14501AAAE8BA77DBD57E85EA6CF6CEE914868",  # key02
        "0C9B507A39F14363BCDE00AEE8FB95AE149A92F359AE42DE",  # key03
        "B0F49A91EDFE4A3F9F0AB860ED1EB006A76DA99594FF445F",  # key04
        "64167CB3F30E44D1ABF6F62C800D98C9F2E882A0004746F0"   # key05
    ]

    @staticmethod
    def encode(plain_text, hex_sec_idx=None):
        """
        Encrypts plain text using specified key index
        :param plain_text: JSON payload to encrypt
        :param hex_sec_idx: Optional key index in hex (01-05)
        :return: Encrypted message in hex format
        """
        # Use specified key index or default to '01'
        if hex_sec_idx is None:
            hex_sec_idx = '01'
        
        # Get secret key
        secret_key = HttpApiCodec.get_secret_key(hex_sec_idx)
        key_bytes = HttpApiCodec.expand_key(bytes.fromhex(secret_key))
        
        # Step 1: Convert JSON to HEX
        hex_data = plain_text.encode('utf-8').hex().upper()
        
        # Step 2: Apply custom padding
        data_bytes = bytes.fromhex(hex_data)
        padded_data = HttpApiCodec.custom_pad(data_bytes)
        
        # Step 3: 3DES-ECB encryption
        cipher = DES3.new(key_bytes, DES3.MODE_ECB)
        encrypted_body = cipher.encrypt(padded_data)
        hex_encrypted = encrypted_body.hex().upper()
        
        # Step 4: Generate MAC
        # Take last byte of encrypted body
        last_byte = encrypted_body[-1:]
        # Create MAC block: last_byte + 7 * 0xFF
        mac_block = last_byte + b'\xFF' * 7
        cipher_mac = DES3.new(key_bytes, DES3.MODE_ECB)
        encrypted_mac = cipher_mac.encrypt(mac_block)
        hex_mac = encrypted_mac.hex().lower()  # Note: MAC is lowercase in examples
        
        # Step 5: Prepare Header
        # Calculate total length = 1 (key ID) + len(encrypted_body) + 8 (MAC)
        total_len = 1 + len(encrypted_body) + 8
        hex_length = format(total_len, '04X')  # 2-byte length
        
        # Step 6: Combine all components
        return hex_length + hex_sec_idx + hex_encrypted + hex_mac

    @staticmethod
    def decode(hex_encoded, force_key_idx=None, verbose=True):
        """
        Decrypts Quadcell API response
        :param hex_encoded: Encrypted response from API
        :param force_key_idx: Force specific key index (0-4) for decryption
        :param verbose: Whether to print debug information during decryption
        :return: Decrypted JSON response
        """
        # Handle plaintext JSON responses directly
        if hex_encoded.strip().startswith("{"):
            try:
                return json.loads(hex_encoded)
            except:
                return hex_encoded
        
        # Minimum length check
        if len(hex_encoded) < 22:
            raise ValueError("Invalid message length")
        
        # Parse message length (first 4 characters)
        hex_length = hex_encoded[0:4]
        length = int(hex_length, 16)
        
        # Verify actual length
        total_bytes = (len(hex_encoded) - 4) // 2  # Excluding length field
        if length != total_bytes:
            raise ValueError(f"Message length mismatch. Expected: {length}, Actual: {total_bytes}")
        
        # Parse key index (characters 5-6)
        hex_sec_idx = hex_encoded[4:6]
        
        # Use forced key index if specified
        if force_key_idx is not None:
            key_index = force_key_idx
            if verbose:
                print(f"⚠️ Using forced key index: {key_index} (ignoring header index {hex_sec_idx})")
        else:
            key_index = int(hex_sec_idx, 16) - 1
        
        if key_index < 0 or key_index > 4:
            raise ValueError(f"Invalid key index: {key_index + 1}")
        
        # Get secret key
        secret_key = HttpApiCodec.SECRET_KEY_POOL[key_index]
        key_bytes = HttpApiCodec.expand_key(bytes.fromhex(secret_key))
        
        # Parse encrypted body and MAC
        # MAC is last 16 characters (8 bytes)
        hex_mac = hex_encoded[-16:]
        # Encrypted body is middle section (characters 6 to last 17)
        hex_encrypted = hex_encoded[6:-16]
        encrypted_bytes = bytes.fromhex(hex_encrypted)
        
        # Verify MAC
        # Take last byte of encrypted body
        last_byte = encrypted_bytes[-1:]
        # Create MAC block: last_byte + 7 * 0xFF
        mac_block = last_byte + b'\xFF' * 7
        cipher_mac = DES3.new(key_bytes, DES3.MODE_ECB)
        computed_mac = cipher_mac.encrypt(mac_block).hex().lower()
        
        # Print debug info only if verbose
        if verbose:
            print(f"Computed MAC: {computed_mac}")
            print(f"Received MAC: {hex_mac}")
            print(f"Key used: {secret_key}")
            print(f"Key index: {key_index}")
            print(f"Encrypted body: {hex_encrypted}")
        
        if computed_mac != hex_mac:
            raise ValueError("MAC verification failed")
        
        # Decrypt content
        cipher = DES3.new(key_bytes, DES3.MODE_ECB)
        decrypted = cipher.decrypt(encrypted_bytes)
        
        # Remove padding
        unpadded = HttpApiCodec.custom_unpad(decrypted)
        
        # Convert HEX back to original JSON
        try:
            # Convert HEX back to original bytes
            original_bytes = bytes.fromhex(unpadded.hex())
            return original_bytes.decode('utf-8')
        except Exception as e:
            raise ValueError(f"HEX to JSON conversion failed: {str(e)}")

    @staticmethod
    def expand_key(key_bytes):
        """Expands 16-byte key to 24-byte 3DES key (K1 + K2 + K1)"""
        if len(key_bytes) == 16:
            return key_bytes + key_bytes[:8]
        return key_bytes

    @staticmethod
    def get_secret_key(hex_sec_idx):
        """Gets secret key from pool by index"""
        index = int(hex_sec_idx, 16) - 1
        if index < 0 or index >= len(HttpApiCodec.SECRET_KEY_POOL):
            raise ValueError("Invalid secret key index")
        return HttpApiCodec.SECRET_KEY_POOL[index]

    @staticmethod
    def custom_pad(data):
        """Custom padding with 0xFF to 8-byte boundary"""
        padding_len = (8 - (len(data) % 8)) % 8
        return data + bytes([0xFF] * padding_len)

    @staticmethod
    def custom_unpad(data):
        """Remove custom 0xFF padding"""
        # Find last non-0xFF byte
        end_index = len(data)
        while end_index > 0 and data[end_index - 1] == 0xFF:
            end_index -= 1
        return data[:end_index]

class QuadcellAPI:
    """Quadcell API 封装类"""
    
    # Fixed base URL
    BASE_URL = "https://srservice.quadcell.com/qccl/v2"
    
    # Default authKey
    DEFAULT_AUTH_KEY = "SYtest21"
    
    # 公司映射文件路径
    COMPANY_MAPPINGS_FILE = "config/company_mappings.json"
    
    def get_endpoint_params(self, endpoint):
        """获取指定端点的参数信息"""
        return HttpApiClient.get_endpoint_params(endpoint)

    def get_endpoint_description_key(self, endpoint):
        """获取端点的描述键"""
        return HttpApiClient.get_endpoint_description_key(endpoint)    
    
    @classmethod
    def load_company_mappings(cls):
        """加载公司映射并按公司名称排序"""
        if os.path.exists(cls.COMPANY_MAPPINGS_FILE):
            try:
                with open(cls.COMPANY_MAPPINGS_FILE, 'r', encoding='utf-8') as f:
                    companies = json.load(f)
                    # 按公司名称排序（不区分大小写）
                    companies.sort(key=lambda x: x["companyName"].lower())
                    return companies
            except:
                return []
        return []
    
    @classmethod
    def save_company_mappings(cls, mappings):
        """保存公司映射并保持排序"""
        # 保存前先排序
        mappings.sort(key=lambda x: x["companyName"].lower())
        with open(cls.COMPANY_MAPPINGS_FILE, 'w', encoding='utf-8') as f:
            json.dump(mappings, f, ensure_ascii=False, indent=2)
    
    @classmethod
    def get_company_authkey(cls, company_name):
        """根据公司名称获取authKey"""
        mappings = cls.load_company_mappings()
        for mapping in mappings:
            if mapping["companyName"] == company_name:
                return mapping["authKey"]
        return None
    
    @classmethod
    def get_all_companies(cls):
        """获取所有公司名称"""
        mappings = cls.load_company_mappings()
        return [mapping["companyName"] for mapping in mappings]    
    
    def get_endpoints(self):
        """获取所有可用的端点"""
        return self.client.get_endpoints()
    
    def get_endpoint_params(self, endpoint):
        """获取指定端点的参数信息"""
        return self.client.get_endpoint_params(endpoint)
    
    def __init__(self):
        self.client = HttpApiClient()
        self.processed_count = 0
    
    def single_request(self, endpoint, payload_dict, debug=False):
        """發送單條API請求，支持調試模式"""
        try:
            payload_json = json.dumps(payload_dict, ensure_ascii=False)
            
            if debug:
                # 調試模式下返回詳細資訊
                # 獲取完整URL
                full_url = f"{HttpApiClient.BASE_URL}/{endpoint.lstrip('/')}"
                
                # 模擬加密過程獲取加密後的JSON
                import sys
                sys.path.append('.')  # 確保可以導入當前目錄的模組
                from modules.quadcell_api import HttpApiCodec
                
                try:
                    # 嘗試獲取加密後的請求
                    encrypted_req = HttpApiCodec.encode(payload_json, hex_sec_idx='05')
                except Exception as e:
                    encrypted_req = f"加密失敗: {str(e)}"
                
                # 正常發送請求
                response = self.client.do_encrypt_post(
                    endpoint, 
                    payload_json, 
                    verbose=False,
                    suppress_decrypt_logs=True
                )
                
                # 嘗試獲取加密後的響應（如果有的話）
                # 注意：實際響應可能已經是解密的，我們需要原始響應
                # 由於 HttpApiClient 內部處理，我們需要稍微修改客戶端以獲取原始響應
                # 暫時先返回基本資訊
                
                debug_info = {
                    "debug_mode": True,
                    "api_url": full_url,
                    "request_json": payload_dict,
                    "request_json_string": payload_json,
                    "encrypted_request": encrypted_req,
                    "response_raw": str(response) if not isinstance(response, dict) else response,
                    "response_type": type(response).__name__,
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }
                
                return debug_info
                
            else:
                # 正常模式
                response = self.client.do_encrypt_post(
                    endpoint, 
                    payload_json, 
                    verbose=False,
                    suppress_decrypt_logs=True
                )
                return response
                
        except Exception as e:
            if debug:
                return {
                    "debug_mode": True,
                    "error": str(e),
                    "api_url": f"{HttpApiClient.BASE_URL}/{endpoint.lstrip('/')}" if endpoint else "未知",
                    "request_json": payload_dict,
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }
            else:
                return {"error": str(e)}
    
    def batch_process(self, input_path, delay=0.5, company_name=None):
        """批量处理Excel文件中的请求"""
        # 重置处理计数
        self.processed_count = 0
        
        # 根据优先级确定authKey
        default_auth_key = self.DEFAULT_AUTH_KEY
        company_auth_key = self.get_company_authkey(company_name) if company_name else None
        
        # 读取Excel数据
        df = pd.read_excel(input_path)
        
        # 检查Excel中是否有authKey列
        has_authkey_in_excel = any(col.lower() == 'authkey' for col in df.columns)
        
        # 扩展IMSI、ICCID和MSISDN范围
        expanded_df = self.expand_sim_ranges(df)
        
        # 准备结果目录
        log_dir = os.path.join(os.path.dirname(input_path), "Log")
        os.makedirs(log_dir, exist_ok=True)
        
        # 生成输出文件名
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        output_path = os.path.join(log_dir, f"{timestamp}.xlsx")
        
        # 准备结果列表
        results = []
        
        print(f"▶ Processing {len(expanded_df)} requests with {delay}s delay...")
        if company_name:
            print(f"▶ Using authKey from company: {company_name}")
        elif has_authkey_in_excel:
            print("▶ Using authKey from Excel file")
        else:
            print(f"▶ Using default authKey: {default_auth_key}")
        
        # 处理每个请求
        for index, row in tqdm(expanded_df.iterrows(), total=len(expanded_df)):
            # 构建payload
            payload = {}
            
            # 定义需要保持为字符串类型的字段
            string_fields = ['packCode', 'imsi', 'iccid', 'msisdn', 'extOrderId', 'remark']
            
            # 添加非空列
            for col in expanded_df.columns:
                if col == "endpoint" or col == "QC packCode":
                    continue
                
                if pd.isna(row[col]) or (isinstance(row[col], str) and row[col].strip() == ""):
                    continue
                
                # 特殊处理：确保特定字段作为字符串发送
                if col.lower() in [field.lower() for field in string_fields]:
                    # 确保转换为字符串，同时去除可能的空格
                    val = row[col]
                    if isinstance(val, (int, float)):
                        # 对于数值类型，转换为字符串但不保留小数位（如果原本是整数）
                        if isinstance(val, float) and val.is_integer():
                            val = str(int(val))
                        else:
                            val = str(val)
                    else:
                        val = str(val).strip()
                    payload[col] = val
                else:
                    payload[col] = row[col]
            
            # 根据优先级设置authKey
            if company_auth_key:
                # 优先级1: 使用公司映射的authKey
                payload["authKey"] = company_auth_key
            elif "authKey" not in payload and not has_authkey_in_excel:
                # 优先级3: 使用默认authKey (优先级2在Excel中已有authKey时自动使用)
                payload["authKey"] = default_auth_key
            
            # 发送请求
            try:
                response = self.client.do_encrypt_post(
                    endpoint=row['endpoint'],
                    http_req=json.dumps(payload, ensure_ascii=False),
                    verbose=False,
                    suppress_decrypt_logs=True
                )
                
                # 提取响应信息
                if isinstance(response, dict):
                    message = response.get("message", "No message")
                else:
                    message = str(response)
                
                status = "SUCCESS"
                response_record = str(response)
                
            except Exception as e:
                error_msg = f"ERROR: {str(e)}"
                status = "FAILED"
                response_record = error_msg
            
            # 记录结果
            results.append({
                "Endpoint": row['endpoint'],
                "JSON": json.dumps(payload, ensure_ascii=False),
                "Response": response_record,
                "Status": status
            })
            
            # 增加处理计数
            self.processed_count += 1
            
            time.sleep(delay)
        
        # 保存结果
        result_df = pd.DataFrame(results, columns=["Endpoint", "JSON", "Response", "Status"])
        
        # 使用ExcelWriter确保正确关闭文件
        with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
            result_df.to_excel(writer, index=False, sheet_name='Results')
            
            # 添加摘要信息
            summary_data = {
                '总请求数': [len(expanded_df)],
                '成功数': [sum(1 for r in results if r["Status"] == "SUCCESS")],
                '失败数': [sum(1 for r in results if r["Status"] == "FAILED")],
                '处理时间': [datetime.now().strftime("%Y-%m-%d %H:%M:%S")],
                '使用的AuthKey来源': [f"公司: {company_name}" if company_name else 
                                ("Excel文件" if has_authkey_in_excel else "默认值")]
            }
            summary_df = pd.DataFrame(summary_data)
            summary_df.to_excel(writer, index=False, sheet_name='Summary')
        
        return output_path
    
    @staticmethod
    def expand_sim_ranges(df):
        """扩展IMSI、ICCID和MSISDN范围"""
        expanded_rows = []
        
        # 定义需要检查的范围字段及其最大长度
        range_columns = {
            'imsi': None,  # 长度不固定
            'iccid': 20,   # 最多20位
            'msisdn': 15   # 最多15位
        }
        
        # 查找数据框中存在的范围字段
        found_range_columns = {}
        for col_name in range_columns.keys():
            for df_col in df.columns:
                if col_name in df_col.lower():
                    found_range_columns[col_name] = df_col
                    break
        
        # 如果没有找到任何范围字段，直接返回原始数据框
        if not found_range_columns:
            return df
        
        # 处理每一行
        for index, row in df.iterrows():
            # 检查每个可能存在的范围字段
            expanded = False
            
            for col_type, col_name in found_range_columns.items():
                value = row[col_name]
                
                # 检查是否为范围格式 (数字-数字)
                if isinstance(value, str) and re.match(r'^\d+-\d+$', value.strip()):
                    try:
                        start, end = map(int, value.split('-'))
                        max_length = range_columns[col_type]
                        
                        # 为范围内的每个值创建新行
                        for num in range(start, end + 1):
                            new_row = row.copy()
                            # 确保数字长度不超过最大限制
                            num_str = str(num)
                            if max_length and len(num_str) > max_length:
                                print(f"Warning: {col_type} value {num_str} exceeds maximum length {max_length}")
                                continue
                            
                            new_row[col_name] = num_str
                            expanded_rows.append(new_row)
                        
                        expanded = True
                        break  # 一次只处理一个范围字段
                    except Exception as e:
                        print(f"Error expanding {col_type} range: {str(e)}")
            
            # 如果没有找到范围值，直接添加原行
            if not expanded:
                expanded_rows.append(row)
        
        return pd.DataFrame(expanded_rows)