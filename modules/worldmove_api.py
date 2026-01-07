import requests
import json
import random
import pandas as pd
import time
import os
import re
import hashlib
from datetime import datetime
from tqdm import tqdm
from config.worldmove_config import WORLDMOVE_ENDPOINT_CONFIG, WORLDMOVE_ENDPOINT_DESCRIPTIONS, WORLDMOVE_ENCRYPTION_CONFIG
import urllib3
# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class Sha1ApiClient:
    # 使用加密配置
    ENDPOINT_CONFIG = WORLDMOVE_ENCRYPTION_CONFIG
    
    # Fixed parameters values
    FIXED_PARAM_VALUES = {
        "merchantId": "b00008a",
        "deptId": "0000a0",
        "token": "f3d9dcba278dd2f8494ac507d82c2628"
    }
    
    # Base URL
    BASE_URL = "https://tfmshippingsys.fastmove.com.tw/Api"
    
    @staticmethod
    def get_endpoints():
        """获取所有可用的端点"""
        return list(Sha1ApiClient.ENDPOINT_CONFIG.keys())

    @staticmethod
    def get_endpoint_params(endpoint):
        """获取指定端点的参数信息"""
        if endpoint in WORLDMOVE_ENDPOINT_CONFIG:
            return WORLDMOVE_ENDPOINT_CONFIG[endpoint]["params"]
        return []
    
    @staticmethod
    def get_endpoint_description_key(endpoint):
        """获取端点的描述键"""
        return WORLDMOVE_ENDPOINT_DESCRIPTIONS.get(endpoint, "")    

    # compute_signature 方法保持不变，使用 Sha1ApiClient.ENDPOINT_CONFIG
    @staticmethod
    def compute_signature(endpoint, payload):
        """
        Compute SHA1 signature for the API request based on endpoint-specific rules
        :param endpoint: API endpoint to determine encryption rules
        :param payload: Request payload to extract parameters from
        :return: SHA1 hash as hex string
        """
        if endpoint not in Sha1ApiClient.ENDPOINT_CONFIG:
            raise ValueError(f"Unknown endpoint: {endpoint}")
        
        config = Sha1ApiClient.ENDPOINT_CONFIG[endpoint]
        enc_params = config["enc_params"]
        
        # Debug output
        print(f"Computing signature for endpoint: {endpoint}")
        print(f"Encryption parameters: {enc_params}")
        print(f"Payload: {json.dumps(payload, indent=2)}")
        
        # Build the signature string based on the encryption parameters
        signature_parts = []
        
        for param in enc_params:
            print(f"Processing parameter: {param}")
            
            # Handle fixed parameters - always use fixed values
            if param in Sha1ApiClient.FIXED_PARAM_VALUES:
                signature_parts.append(Sha1ApiClient.FIXED_PARAM_VALUES[param])
                print(f"Added fixed parameter {param}: {Sha1ApiClient.FIXED_PARAM_VALUES[param]}")
            # Handle special list parameters
            elif param == "prodList" and param in payload:
                prod_list = payload[param]
                if isinstance(prod_list, list):
                    # For each product in the list, add the specified fields in order
                    for i, product in enumerate(prod_list):
                        print(f"Processing product {i}: {product}")
                        
                        if "wmproductId+qty" in config.get("prodList_format", ""):
                            # 确保字段存在，否则使用空字符串
                            wmproductId = str(product.get("wmproductId", ""))
                            qty = str(product.get("qty", ""))
                            signature_parts.append(wmproductId)
                            signature_parts.append(qty)
                            print(f"Added wmproductId: {wmproductId}, qty: {qty}")
                        elif "productid+productName+qty" in config.get("prodList_format", ""):
                            productId = str(product.get("productId", ""))
                            productName = str(product.get("productName", ""))
                            qty = str(product.get("qty", ""))
                            signature_parts.append(productId)
                            signature_parts.append(productName)
                            signature_parts.append(qty)
                            print(f"Added productId: {productId}, productName: {productName}, qty: {qty}")
                        elif "wmproductId+day+simNum" in config.get("prodList_format", ""):
                            wmproductId = str(product.get("wmproductId", ""))
                            day = str(product.get("day", ""))
                            simNum = str(product.get("simNum", ""))
                            signature_parts.append(wmproductId)
                            signature_parts.append(day)
                            signature_parts.append(simNum)
                            print(f"Added wmproductId: {wmproductId}, day: {day}, simNum: {simNum}")
            elif param == "itemList" and param in payload:
                item_list = payload[param]
                if isinstance(item_list, list):
                    # For each item in the list, add the specified fields in order
                    for i, item in enumerate(item_list):
                        print(f"Processing item {i}: {item}")
                        
                        if "iccid+productName+redemptionCode" in config.get("itemList_format", ""):
                            iccid = str(item.get("iccid", ""))
                            productName = str(item.get("productName", ""))
                            redemptionCode = str(item.get("redemptionCode", ""))
                            signature_parts.append(iccid)
                            signature_parts.append(productName)
                            signature_parts.append(redemptionCode)
                            print(f"Added iccid: {iccid}, productName: {productName}, redemptionCode: {redemptionCode}")
                        elif "iccid+productName+rcode+qrcodeType+qrcode" in config.get("itemList_format", ""):
                            iccid = str(item.get("iccid", ""))
                            productName = str(item.get("productName", ""))
                            rcode = str(item.get("rcode", ""))
                            qrcodeType = str(item.get("qrcodeType", ""))
                            qrcode = str(item.get("qrcode", ""))
                            signature_parts.append(iccid)
                            signature_parts.append(productName)
                            signature_parts.append(rcode)
                            signature_parts.append(qrcodeType)
                            signature_parts.append(qrcode)
                            print(f"Added iccid: {iccid}, productName: {productName}, rcode: {rcode}, qrcodeType: {qrcodeType}, qrcode: {qrcode}")
                        elif "wmproductId+day+simNum" in config.get("itemList_format", ""):
                            wmproductId = str(item.get("wmproductId", ""))
                            day = str(item.get("day", ""))
                            simNum = str(item.get("simNum", ""))
                            signature_parts.append(wmproductId)
                            signature_parts.append(day)
                            signature_parts.append(simNum)
                            print(f"Added wmproductId: {wmproductId}, day: {day}, simNum: {simNum}")
            # Handle regular parameters from payload (excluding non-encryption parameters)
            elif param in payload and param not in config.get("non_enc_params", []):
                value = str(payload[param])
                signature_parts.append(value)
                print(f"Added regular parameter {param}: {value}")
        
        # Concatenate all parts
        signature_string = "".join(signature_parts)
        
        # Debug output
        print(f"Signature string: {signature_string}")
        
        # Compute SHA1 hash
        hash_object = hashlib.sha1(signature_string.encode())
        hex_dig = hash_object.hexdigest()
        
        print(f"Computed signature: {hex_dig}")
        
        return hex_dig

    @staticmethod
    def do_post_request(endpoint, payload, verbose=True):
        """
        Sends POST request to the API with SHA1 signature
        :param endpoint: API endpoint path
        :param payload: JSON request payload
        :param verbose: Whether to print detailed logs
        :return: JSON response or raw response for non-200 status
        """
        # Construct full URL
        full_url = f"{Sha1ApiClient.BASE_URL}/{endpoint}"
        
        # Compute signature
        signature = Sha1ApiClient.compute_signature(endpoint, payload)
        
        # Create the final payload with the signature
        full_payload = {
            **payload,  # Include the original payload
            "encStr": signature  # Add the computed signature
        }
        
        # Add fixed parameters if they are required by the endpoint
        config = Sha1ApiClient.ENDPOINT_CONFIG[endpoint]
        for param in config["enc_params"]:
            if param in Sha1ApiClient.FIXED_PARAM_VALUES:
                full_payload[param] = Sha1ApiClient.FIXED_PARAM_VALUES[param]
        
        if verbose:
            print(f"[API-Send] {full_url}")
            print(f"[API-Send] {json.dumps(full_payload, indent=2)}")
        
        try:
            # Set request headers
            headers = {
                'Content-Type': 'application/json',
                'Accept': 'application/json'
            }
            
            # Send HTTP POST request with SSL verification disabled
            response = requests.post(
                full_url, 
                data=json.dumps(full_payload), 
                headers=headers,
                timeout=30,
                verify=False  # Disable SSL verification
            )
            
            if verbose:
                print(f"[HTTP Status] {response.status_code}")
                print(f"[Raw Response] {response.text}")
            
            # Handle response
            if response.status_code == 200:
                try:
                    return response.json()
                except json.JSONDecodeError:
                    return response.text
            return response.text
        
        except Exception as e:
            if verbose:
                print(f"Request failed: {str(e)}")
            raise

class WorldMoveAPI:
    """WorldMove API 封装类"""
    
    def __init__(self):
        self.client = Sha1ApiClient()
        self.processed_count = 0
        
    def get_endpoints():
        """获取所有可用的端点"""
        return Sha1ApiClient.get_endpoints()
    
    def get_endpoint_params(self, endpoint):
        """获取指定端点的参数信息"""
        return Sha1ApiClient.get_endpoint_params(endpoint)
    
    def get_endpoint_description_key(self, endpoint):
        """获取端点的描述键"""
        return Sha1ApiClient.get_endpoint_description_key(endpoint)
    
    def single_request(self, endpoint, payload_dict):
        """发送单条API请求"""
        try:
            # 验证prodList参数
            if "prodList" in payload_dict:
                prod_list = payload_dict["prodList"]
                if isinstance(prod_list, list) and len(prod_list) > 0:
                    # 检查第一个元素是否为字典
                    if not isinstance(prod_list[0], dict):
                        return {"error": "prodList must be an array of objects with wmproductId and qty fields"}
                    
                    # 检查必需字段
                    for i, product in enumerate(prod_list):
                        if "wmproductId" not in product or "qty" not in product:
                            return {"error": f"Product at index {i} is missing required fields (wmproductId, qty)"}
            
            response = self.client.do_post_request(
                endpoint, 
                payload_dict, 
                verbose=True  # 启用详细日志以便调试
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
        
        # 检查endpoint列是否存在
        if 'endpoint' not in df.columns:
            raise ValueError("Excel文件必须包含'endpoint'列")
        
        # 扩展IMSI范围
        expanded_df = self.expand_imsi_ranges(df)
        
        # 准备结果目录
        log_dir = os.path.join(os.path.dirname(input_path), "Log")
        os.makedirs(log_dir, exist_ok=True)
        
        # 生成输出文件名
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        output_path = os.path.join(log_dir, f"worldmove_result_{timestamp}.xlsx")
        
        # 准备结果列表
        results = []
        
        print(f"▶ Processing {len(expanded_df)} requests with {delay}s delay...")
        
        # 处理每个请求
        for index, row in tqdm(expanded_df.iterrows(), total=len(expanded_df)):
            # 构建payload
            payload = {}
            
            # 添加非空列
            for col in expanded_df.columns:
                if col == "endpoint":
                    continue
                
                if pd.isna(row[col]) or (isinstance(row[col], str) and row[col].strip() == ""):
                    continue
                
                payload[col] = row[col]
            
            # 发送请求
            try:
                response = self.client.do_post_request(
                    endpoint=row['endpoint'],
                    payload=payload,
                    verbose=True  # 启用详细日志以便调试
                )
                
                # 提取响应信息
                if isinstance(response, dict):
                    message = response.get("message", "No message")
                    status_code = response.get("statusCode", "No status code")
                else:
                    message = str(response)
                    status_code = "N/A"
                
                status = "SUCCESS"
                response_record = str(response)
                
            except Exception as e:
                error_msg = f"ERROR: {str(e)}"
                status = "FAILED"
                status_code = "N/A"
                response_record = error_msg
            
            # 记录结果
            results.append({
                "Endpoint": row['endpoint'],
                "Payload": json.dumps(payload, ensure_ascii=False),
                "Response": response_record,
                "Status": status,
                "StatusCode": status_code
            })
            
            # 增加处理计数
            self.processed_count += 1
            
            time.sleep(delay)
        
        # 保存结果
        result_df = pd.DataFrame(results, columns=["Endpoint", "Payload", "Response", "Status", "StatusCode"])
        
        # 使用ExcelWriter确保正确关闭文件
        with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
            result_df.to_excel(writer, index=False, sheet_name='Results')
            
            # 添加摘要信息
            summary_data = {
                '总请求数': [len(expanded_df)],
                '成功数': [sum(1 for r in results if r["Status"] == "SUCCESS")],
                '失败数': [sum(1 for r in results if r["Status"] == "FAILED")],
                '处理时间': [datetime.now().strftime("%Y-%m-%d %H:%M:%S")]
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
    
    @staticmethod
    def get_endpoints():
        """获取所有可用的端点"""
        return list(Sha1ApiClient.ENDPOINT_CONFIG.keys())

# 以下代码保留用于命令行操作，但在Flask应用中不会使用
def select_endpoint():
    """
    Display available endpoints and let user select one
    :return: Selected endpoint
    """
    print("\nAvailable Endpoints:")
    endpoints = list(Sha1ApiClient.ENDPOINT_CONFIG.keys())
    for i, endpoint in enumerate(endpoints, 1):
        print(f"{i}. {endpoint}")
    
    while True:
        try:
            choice = int(input("\nSelect endpoint by number: "))
            if 1 <= choice <= len(endpoints):
                return endpoints[choice - 1]
            else:
                print("Invalid selection. Please try again.")
        except ValueError:
            print("Please enter a valid number.")

def get_user_input(endpoint):
    """
    Get additional JSON fields from user input based on endpoint
    :param endpoint: Selected endpoint to determine required fields
    :return: JSON payload
    """
    print(f"\nEnter parameters for {endpoint}:")
    
    # Initialize empty payload
    payload = {}
    
    # Get endpoint-specific parameters
    config = Sha1ApiClient.ENDPOINT_CONFIG[endpoint]
    enc_params = config["enc_params"]
    non_enc_params = config.get("non_enc_params", [])
    
    # Ask for parameters that are not fixed
    for param in enc_params:
        if param not in Sha1ApiClient.FIXED_PARAM_VALUES:
            # Handle special list parameters
            if param == "prodList":
                prod_list = []
                print(f"\nEnter {param} details (empty product ID to finish):")
                while True:
                    if "wmproductId+qty" in config.get("prodList_format", ""):
                        product_id = input("Product ID: ").strip()
                        if not product_id:
                            break
                        try:
                            quantity = int(input("Quantity: ").strip())
                            prod_list.append({
                                "wmproductId": product_id,
                                "qty": quantity
                            })
                        except ValueError:
                            print("Quantity must be a number. Please try again.")
                    elif "productid+productName+qty" in config.get("prodList_format", ""):
                        product_id = input("Product ID: ").strip()
                        if not product_id:
                            break
                        product_name = input("Product Name: ").strip()
                        try:
                            quantity = int(input("Quantity: ").strip())
                            prod_list.append({
                                "productId": product_id,
                                "productName": product_name,
                                "qty": quantity
                            })
                        except ValueError:
                            print("Quantity must be a number. Please try again.")
                    elif "wmproductId+day+simNum" in config.get("prodList_format", ""):
                        product_id = input("Product ID: ").strip()
                        if not product_id:
                            break
                        try:
                            day = int(input("Day: ").strip())
                            sim_num = input("SIM Number: ").strip()
                            prod_list.append({
                                "wmproductId": product_id,
                                "day": day,
                                "simNum": sim_num
                            })
                        except ValueError:
                            print("Day must be a number. Please try again.")
                
                if prod_list:
                    payload[param] = prod_list
            elif param == "itemList":
                item_list = []
                print(f"\nEnter {param} details (empty to finish):")
                while True:
                    if "iccid+productName+redemptionCode" in config.get("itemList_format", ""):
                        iccid = input("ICCID: ").strip()
                        if not iccid:
                            break
                        product_name = input("Product Name: ").strip()
                        redemption_code = input("Redemption Code: ").strip()
                        item_list.append({
                            "iccid": iccid,
                            "productName": product_name,
                            "redemptionCode": redemption_code
                        })
                    elif "iccid+productName+rcode+qrcodeType+qrcode" in config.get("itemList_format", ""):
                        iccid = input("ICCID: ").strip()
                        if not iccid:
                            break
                        product_name = input("Product Name: ").strip()
                        rcode = input("RCode: ").strip()
                        qrcode_type = input("QR Code Type: ").strip()
                        qrcode = input("QR Code: ").strip()
                        item_list.append({
                            "iccid": iccid,
                            "productName": product_name,
                            "rcode": rcode,
                            "qrcodeType": qrcode_type,
                            "qrcode": qrcode
                        })
                    elif "wmproductId+day+simNum" in config.get("itemList_format", ""):
                        product_id = input("Product ID: ").strip()
                        if not product_id:
                            break
                        try:
                            day = int(input("Day: ").strip())
                            sim_num = input("SIM Number: ").strip()
                            item_list.append({
                                "wmproductId": product_id,
                                "day": day,
                                "simNum": sim_num
                            })
                        except ValueError:
                            print("Day must be a number. Please try again.")
                
                if item_list:
                    payload[param] = item_list
            else:
                value = input(f"{param}: ").strip()
                if value:
                    # Try to convert numeric values
                    if value.isdigit():
                        value = int(value)
                    elif value.replace('.', '', 1).isdigit() and value.count('.') < 2:
                        value = float(value)
                    payload[param] = value
    
    # Ask for non-encryption parameters
    for param in non_enc_params:
        value = input(f"{param} : ").strip()
        if value:
            # Try to convert numeric values
            if value.isdigit():
                value = int(value)
            elif value.replace('.', '', 1).isdigit() and value.count('.') < 2:
                value = float(value)
            payload[param] = value
    
    return payload

def expand_imsi_ranges(df):
    """
    Expands IMSI ranges in the DataFrame
    :param df: Original DataFrame
    :return: Expanded DataFrame with individual IMSI values
    """
    expanded_rows = []
    range_column = None
    
    # Find the IMSI column (case-insensitive)
    for col in df.columns:
        if "imsi" in col.lower():
            range_column = col
            break
    
    if range_column is None:
        print("⚠️ No IMSI column found. Processing without range expansion.")
        return df
    
    print(f"🔍 Found IMSI column: {range_column}")
    
    # Process each row
    for index, row in df.iterrows():
        imsi_value = row[range_column]
        
        # Check if it's a range (format: start-end)
        if isinstance(imsi_value, str) and re.match(r'^\d+-\d+$', imsi_value.strip()):
            try:
                start, end = map(int, imsi_value.split('-'))
                count = end - start + 1
                
                # Safety check for large ranges
                if count > 1000:
                    print(f"⚠️ Large IMSI range detected: {count} values. Processing anyway.")
                
                print(f"🔢 Expanding IMSI range: {start} to {end} ({count} values)")
                
                # Create a row for each IMSI in the range
                for imsi in range(start, end + 1):
                    new_row = row.copy()
                    new_row[range_column] = str(imsi)
                    expanded_rows.append(new_row)
                
                continue  # Skip adding original row
            except Exception as e:
                print(f"⚠️ Error expanding IMSI range: {str(e)}")
        
        # For non-range values, add the row as-is
        expanded_rows.append(row)
    
    # Create new DataFrame from expanded rows
    expanded_df = pd.DataFrame(expanded_rows)
    expanded_df.reset_index(drop=True, inplace=True)
    
    print(f"📊 Expanded from {len(df)} to {len(expanded_df)} requests")
    return expanded_df

def batch_process():
    """
    Process API requests in batch mode from Excel file
    Reads input from Excel, sends requests, and saves results
    """
    print("\n" + "=" * 40)
    print("SHA1 API Client - Batch Processing Mode")
    print("=" * 40)
    
    # Get current working directory
    current_dir = os.getcwd()
    print(f"Current working directory: {current_dir}")
    
    # Get input file name
    input_filename = input("\nEnter input Excel filename [default: API_Requests.xlsx]: ").strip()
    if not input_filename:
        input_filename = "API_Requests.xlsx"
    
    # Set input path to current directory
    input_path = os.path.join(current_dir, input_filename)
    print(f"Input file path: {input_path}")
    
    # Create Log directory if not exists
    log_dir = os.path.join(current_dir, "Log")
    os.makedirs(log_dir, exist_ok=True)
    
    # Generate timestamped output filename
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    output_filename = f"{timestamp}.xlsx"
    
    # Set output path to Log directory
    output_path = os.path.join(log_dir, output_filename)
    print(f"Result file path: {output_path}")
    
    # Get delay setting
    delay = float(input("Enter delay between requests (seconds) [default: 0.5]: ").strip() or 0.5)
    
    try:
        # Read Excel data
        df = pd.read_excel(input_path)
        
        # Check if endpoint column exists
        if 'endpoint' not in df.columns:
            raise ValueError("Excel file must contain an 'endpoint' column")
        
        # Expand IMSI ranges if needed
        expanded_df = expand_imsi_ranges(df)
        
        # Prepare results list
        results = []
        
        print(f"\n▶ Processing {len(expanded_df)} requests with {delay}s delay...")
        
        # Process each row with progress bar
        for index, row in tqdm(expanded_df.iterrows(), total=len(expanded_df)):
            # Build payload from row data
            payload = {}
            
            # Add all columns (excluding endpoint)
            for col in expanded_df.columns:
                # Skip endpoint column
                if col == "endpoint":
                    continue
                
                # Skip if value is NaN or empty string
                if pd.isna(row[col]) or (isinstance(row[col], str) and row[col].strip() == ""):
                    continue
                
                payload[col] = row[col]
            
            # Send API request with verbose=False to reduce logs
            try:
                response = Sha1ApiClient.do_post_request(
                    endpoint=row['endpoint'],
                    payload=payload,
                    verbose=False  # Disable detailed logs
                )
                
                # Extract key response info
                if isinstance(response, dict):
                    message = response.get("message", "No message")
                    status_code = response.get("statusCode", "No status code")
                else:
                    message = str(response)
                    status_code = "N/A"
                
                status = "SUCCESS"
                
                # Print only message (max 200 characters)
                truncated_message = message[:200] + ('...' if len(message) > 200 else '')
                print(f"\n[Request {index+1}/{len(expanded_df)}] Status: {status_code}, Message: {truncated_message}")
                
                # Record response for result file
                response_record = str(response)
                
            except Exception as e:
                error_msg = f"ERROR: {str(e)}"
                status = "FAILED"
                status_code = "N/A"
                # Truncate error message to 200 characters
                truncated_error = error_msg[:200] + ('...' if len(error_msg) > 200 else '')
                print(f"\n❌ [Request {index+1}/{len(expanded_df)}] {truncated_error}")
                response_record = error_msg
            
            # Record results in required format
            results.append({
                "Endpoint": row['endpoint'],
                "Payload": json.dumps(payload),
                "Response": response_record,
                "Status": status,
                "StatusCode": status_code
            })
            
            time.sleep(delay)  # Delay between requests
        
        # Create results DataFrame with specific columns
        result_df = pd.DataFrame(results, columns=["Endpoint", "Payload", "Response", "Status", "StatusCode"])
        
        # Save results to Excel
        result_df.to_excel(output_path, index=False)
        
        # Print summary
        success_count = sum(1 for r in results if r["Status"] == "SUCCESS")
        print(f"\n✅ Batch processing completed!")
        print(f"   Success: {success_count}/{len(expanded_df)}")
        print(f"   Failed: {len(expanded_df) - success_count}/{len(expanded_df)}")
        print(f"   Results saved to: {output_path}")
    
    except Exception as e:
        print(f"\n❌ Batch processing failed: {str(e)}")
        raise