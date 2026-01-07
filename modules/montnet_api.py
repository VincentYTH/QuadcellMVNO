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
from config.montnet_config import MONTNET_ENDPOINT_CONFIG, MONTNET_ENDPOINT_DESCRIPTIONS

class MHttpApiClient:
    """
    HTTP API Client for Montnets VMS Integration
    Handles encrypted communication with Montnets API
    """
    
    # Fixed base URL
    BASE_URL = "https://gtsapi.int-montnets.com/httpApi/v1/quadcell"
    
    # Fixed authKey
    FIXED_AUTH_KEY = "A10000000167"

    @staticmethod
    def get_endpoints():
        """获取所有可用的端点"""
        return list(MONTNET_ENDPOINT_CONFIG.keys())

    @staticmethod
    def get_endpoint_params(endpoint):
        """获取指定端点的参数信息"""
        if endpoint in MONTNET_ENDPOINT_CONFIG:
            return MONTNET_ENDPOINT_CONFIG[endpoint]["params"]
        return []
    
    @staticmethod
    def get_endpoint_description_key(endpoint):
        """获取端点的描述键"""
        return MONTNET_ENDPOINT_DESCRIPTIONS.get(endpoint, "")
    
    @staticmethod
    def do_encrypt_post(endpoint, http_req, verbose=True):
        """
        Sends encrypted POST request to Montnets API
        :param endpoint: API endpoint path (e.g. "IMC/heartbeat")
        :param http_req: JSON request payload (must include authKey)
        :param verbose: Whether to print detailed logs
        :return: Decrypted JSON response or raw response for non-200 status
        """
        # Construct full URL
        full_url = f"{MHttpApiClient.BASE_URL}/{endpoint.lstrip('/')}"
        if verbose:
            print(f"[HttpApi-Send] {full_url}")
            print(f"[HttpApi-Send] {http_req}")
        
        try:
            # Encrypt request payload
            encrypted_req = HttpApiCodec.encode(http_req)
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
            
            # Handle response
            if response.status_code == 200:
                decrypted_ret = HttpApiCodec.decode(response.text)
                if verbose:
                    print(f"[Decrypted Response] {decrypted_ret}")
                return decrypted_ret
            return response.text
        
        except Exception as e:
            if verbose:
                print(f"Request failed: {str(e)}")
            raise

class HttpApiCodec:
    """Handles encryption/decryption for Montnets API communication"""
    
    # Pre-shared secret keys for 3DES encryption
    SECRET_KEY_POOL = [
        "93219498004643AAB077B0DCBF69C637",
        "5F7FE592F5464E0FAC5C5DA731667CF4",
        "ABB790F9286444A69FC178C4457C03CF",
        "35A5B770D940475E937C31B3A45AC168",
        "0B58DFDB932F4D989F58DAE4C38111B6"
    ]

    @staticmethod
    def encode(plain_text, hex_sec_idx=None):
        """
        Encrypts plain text using random or specified key index
        :param plain_text: JSON payload to encrypt
        :param hex_sec_idx: Optional key index in hex (01-05)
        :return: Encrypted message in hex format
        """
        # Generate random key index if not provided
        if hex_sec_idx is None:
            hex_sec_idx = format(random.randint(1, 5), '02X')
        
        # Get secret key based on index
        secret_key = HttpApiCodec.get_secret_key(hex_sec_idx)
        
        # Encrypt payload
        hex_encrypted = HttpApiCodec.encrypt_text(plain_text, secret_key)
        
        # Generate MAC for message integrity
        hex_mac = HttpApiCodec.gen_mac(hex_sec_idx, secret_key, hex_encrypted)
        
        # Calculate message length: key index (1 byte) + cipher text + MAC (8 bytes)
        length = 1 + (len(hex_encrypted) // 2) + 8
        hex_length = format(length, '04X')
        
        # Format: [length][key index][cipher text][MAC]
        return hex_length + hex_sec_idx + hex_encrypted + hex_mac

    @staticmethod
    def decode(hex_encoded):
        """
        Decrypts Montnets API response
        :param hex_encoded: Encrypted response from API
        :return: Decrypted JSON response
        """
        # Minimum length check (2B length + 1B index + 8B MAC = 11B = 22 hex chars)
        if len(hex_encoded) < 22:
            raise ValueError("Invalid message length")
        
        # Parse message length (first 4 hex chars = 2 bytes)
        hex_length = hex_encoded[0:4]
        length = int(hex_length, 16)
        
        # Validate actual length
        actual_length = (len(hex_encoded) - 4) // 2
        if length != actual_length:
            raise ValueError(f"Message length mismatch. Expected: {length}, Actual: {actual_length}")
        
        # Parse key index (1 byte after length)
        hex_sec_idx = hex_encoded[4:6]
        key_index = int(hex_sec_idx, 16) - 1
        
        if key_index < 0 or key_index > 4:
            raise ValueError(f"Invalid key index: {key_index + 1}")
        
        # Parse MAC (last 16 hex chars = 8 bytes)
        hex_mac = hex_encoded[-16:]
        
        # Parse encrypted content (middle section)
        hex_encrypted = hex_encoded[6:-16]
        
        # Verify MAC integrity
        secret_key = HttpApiCodec.SECRET_KEY_POOL[key_index]
        computed_mac = HttpApiCodec.gen_mac(hex_sec_idx, secret_key, hex_encrypted)
        
        if computed_mac != hex_mac:
            raise ValueError("MAC verification failed")
        
        # Decrypt content
        return HttpApiCodec.decrypt_text(hex_encrypted, secret_key)

    @staticmethod
    def encrypt_text(plain_text, secret_key):
        """
        Encrypts UTF-8 text using 3DES-ECB
        :param plain_text: Text to encrypt
        :param secret_key: 16-byte hex secret key
        :return: Encrypted hex string
        """
        # Convert to bytes and add custom 0xFF padding
        input_bytes = plain_text.encode('utf-8')
        padded_bytes = HttpApiCodec.custom_pad(input_bytes)
        
        # Perform 3DES encryption
        key_bytes = HttpApiCodec.expand_key(bytes.fromhex(secret_key))
        cipher = DES3.new(key_bytes, DES3.MODE_ECB)
        encrypted = cipher.encrypt(padded_bytes)
        
        return encrypted.hex().upper()

    @staticmethod
    def decrypt_text(hex_encrypted, secret_key):
        """
        Decrypts content to UTF-8 string
        :param hex_encrypted: Encrypted hex string
        :param secret_key: 16-byte hex secret key
        :return: Decrypted text
        """
        # Convert hex to bytes
        encrypted_bytes = bytes.fromhex(hex_encrypted)
        
        # Perform 3DES decryption
        key_bytes = HttpApiCodec.expand_key(bytes.fromhex(secret_key))
        cipher = DES3.new(key_bytes, DES3.MODE_ECB)
        decrypted = cipher.decrypt(encrypted_bytes)
        
        # Remove custom 0xFF padding
        unpadded = HttpApiCodec.custom_unpad(decrypted)
        
        return unpadded.decode('utf-8')

    @staticmethod
    def gen_mac(secret_idx, secret_key, hex_encrypted):
        """
        Generates MAC for message authentication
        :param secret_idx: Key index hex
        :param secret_key: Secret key
        :param hex_encrypted: Encrypted content
        :return: MAC hex string
        """
        # Combine key index and encrypted data
        data = secret_idx + hex_encrypted
        input_bytes = bytes.fromhex(data)
        
        # Add custom padding
        padded_bytes = HttpApiCodec.custom_pad(input_bytes)
        
        # Encrypt and take last 8 bytes as MAC
        key_bytes = HttpApiCodec.expand_key(bytes.fromhex(secret_key))
        cipher = DES3.new(key_bytes, DES3.MODE_ECB)
        encrypted = cipher.encrypt(padded_bytes)
        mac = encrypted[-8:]
        
        return mac.hex().upper()

    @staticmethod
    def expand_key(key_bytes):
        """
        Expands 16-byte key to 24-byte 3DES key (K1 + K2 + K1)
        :param key_bytes: Original key bytes
        :return: Expanded 24-byte key
        """
        if len(key_bytes) == 16:
            # K1 + K2 + K1
            return key_bytes + key_bytes[:8]
        return key_bytes

    @staticmethod
    def get_secret_key(hex_sec_idx):
        """
        Gets secret key from pool by index
        :param hex_sec_idx: Key index in hex (01-05)
        :return: Secret key hex string
        """
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

class MontNetAPI:
    """MontNet API 封装类"""
    
    FIXED_AUTH_KEY = MHttpApiClient.FIXED_AUTH_KEY
    BASE_URL = MHttpApiClient.BASE_URL
    
    def __init__(self):
        self.client = MHttpApiClient()
        self.processed_count = 0
    
    def get_endpoints(self):
        """获取所有可用的端点"""
        return MHttpApiClient.get_endpoints()
    
    def get_endpoint_params(self, endpoint):
        """获取指定端点的参数信息"""
        return MHttpApiClient.get_endpoint_params(endpoint)
    
    def get_endpoint_description_key(self, endpoint):
        """获取端点的描述键"""
        return MHttpApiClient.get_endpoint_description_key(endpoint)
    
    def single_request(self, endpoint, payload_dict):
        """发送单条API请求"""
        try:
            # 确保包含authKey
            if 'authKey' not in payload_dict:
                payload_dict['authKey'] = MHttpApiClient.FIXED_AUTH_KEY
                
            payload_json = json.dumps(payload_dict)
            response = MHttpApiClient.do_encrypt_post(endpoint, payload_json, verbose=False)
            return response
        except Exception as e:
            return {"error": str(e)}
    
    def batch_process(self, input_path, delay=0.5):
        """批量处理Excel文件中的请求"""
        # 重置处理计数
        self.processed_count = 0
        
        # 读取Excel数据
        df = pd.read_excel(input_path)
        
        # 扩展IMSI范围
        expanded_df = self.expand_imsi_ranges(df)
        
        # 准备结果目录
        log_dir = os.path.join(os.path.dirname(input_path), "Log")
        os.makedirs(log_dir, exist_ok=True)
        
        # 生成输出文件名
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        output_path = os.path.join(log_dir, f"{timestamp}.xlsx")
        
        # 准备结果列表
        results = []
        
        # 只显示基本的开始信息
        print(f"▶ MontNet批量处理开始: {len(expanded_df)}条请求, 间隔{delay}秒")
        print(f"▶ 使用API: MontNet, AuthKey: {MHttpApiClient.FIXED_AUTH_KEY}")
        
        # 处理每个请求
        for index, row in tqdm(expanded_df.iterrows(), total=len(expanded_df)):
            # 构建payload - 确保使用MontNet的authKey
            payload = {}
            
            # 添加非空列
            for col in expanded_df.columns:
                if col == "endpoint":
                    continue
                
                if pd.isna(row[col]) or (isinstance(row[col], str) and row[col].strip() == ""):
                    continue
                
                payload[col] = row[col]
            
            # 确保包含MontNet的authKey
            payload['authKey'] = MHttpApiClient.FIXED_AUTH_KEY
            
            # 发送请求 - 关闭详细日志
            try:
                payload_json = json.dumps(payload, ensure_ascii=False)
                response = MHttpApiClient.do_encrypt_post(
                    endpoint=row['endpoint'],
                    http_req=payload_json,
                    verbose=False  # 关闭详细日志输出
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
        
        # 计算统计信息
        success_count = sum(1 for r in results if r["Status"] == "SUCCESS")
        failed_count = sum(1 for r in results if r["Status"] == "FAILED")
        
        # 只显示最终统计信息
        print(f"✅ MontNet批量处理完成!")
        print(f"   成功: {success_count}条")
        print(f"   失败: {failed_count}条")
        print(f"   结果文件: {output_path}")
        
        # 保存结果
        result_df = pd.DataFrame(results, columns=["Endpoint", "JSON", "Response", "Status"])
        
        # 使用ExcelWriter确保正确关闭文件
        with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
            result_df.to_excel(writer, index=False, sheet_name='Results')
            
            # 添加摘要信息
            summary_data = {
                '总请求数': [len(expanded_df)],
                '成功数': [success_count],
                '失败数': [failed_count],
                '处理时间': [datetime.now().strftime("%Y-%m-%d %H:%M:%S")],
                '使用的API': ['MontNet'],
                'Base URL': [MHttpApiClient.BASE_URL]
            }
            summary_df = pd.DataFrame(summary_data)
            summary_df.to_excel(writer, index=False, sheet_name='Summary')
        
        return output_path
    
    @staticmethod
    def expand_imsi_ranges(df):
        """扩展IMSI范围"""
        expanded_rows = []
        range_column = None
        
        # 查找IMSI列
        for col in df.columns:
            if "imsi" in col.lower():
                range_column = col
                break
        
        if range_column is None:
            return df
        
        # 处理每一行
        for index, row in df.iterrows():
            imsi_value = row[range_column]
            
            # 检查是否为范围格式
            if isinstance(imsi_value, str) and re.match(r'^\d+-\d+$', imsi_value.strip()):
                try:
                    start, end = map(int, imsi_value.split('-'))
                    
                    # 为范围内的每个IMSI创建新行
                    for imsi in range(start, end + 1):
                        new_row = row.copy()
                        new_row[range_column] = str(imsi)
                        expanded_rows.append(new_row)
                    
                    continue
                except Exception as e:
                    print(f"Error expanding IMSI range: {str(e)}")
            
            # 非范围值直接添加
            expanded_rows.append(row)
        
        return pd.DataFrame(expanded_rows)