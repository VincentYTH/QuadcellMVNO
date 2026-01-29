import os
import time
import shutil
import subprocess
import pandas as pd
from sqlalchemy import create_engine
from datetime import datetime

# ================= 配置區域 =================
# 1. 數據庫配置
DB_HOST = "192.168.1.104"
DB_PORT = "5432"
DB_NAME = "sim_management_db"
DB_USER = "postgres"
DB_PASSWORD = "123456"

# 2. PostgreSQL 安裝路徑 (pg_dump.exe 的位置)
PG_DUMP_PATH = r"C:\Program Files\PostgreSQL\16\bin\pg_dump.exe"

# 3. 備份路徑配置 (先存本地，再複製到網絡硬碟，比較穩定)
LOCAL_BACKUP_DIR = os.path.join(os.path.dirname(__file__), "db_backups")

# Share Drive 路徑
NETWORK_BACKUP_DIR = r"\\192.168.1.118\Quadcell_2022\SIM INFO\BackUp_DB"

# 4. 保留策略 (保留最近多少天的備份)
RETENTION_DAYS = 30
# ===========================================

def log(message):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}")

def ensure_dir(directory):
    if not os.path.exists(directory):
        os.makedirs(directory)

def backup_sql(timestamp):
    """執行 pg_dump 進行 SQL 備份 (包含所有欄位和結構，用於災難恢復)"""
    filename = f"{DB_NAME}_{timestamp}.sql"
    local_filepath = os.path.join(LOCAL_BACKUP_DIR, filename)

    log(f"--- 開始 SQL 備份 ---")
    
    env = os.environ.copy()
    env['PGPASSWORD'] = DB_PASSWORD

    # pg_dump 會自動備份所有欄位，包括 imsi_num 等優化欄位，這是正確的
    cmd = [
        PG_DUMP_PATH,
        "-h", DB_HOST,
        "-p", DB_PORT,
        "-U", DB_USER,
        "-F", "p", 
        "-c",
        "--if-exists",
        "-f", local_filepath,
        DB_NAME
    ]

    try:
        subprocess.run(cmd, env=env, check=True)
        log(f"SQL 備份成功: {filename}")
        return local_filepath
    except Exception as e:
        log(f"SQL 備份失敗: {e}")
        return None

def backup_excel(timestamp):
    """使用 Pandas 讀取數據並導出為 Excel (僅保留供人類閱讀的欄位)"""
    filename = f"{DB_NAME}_{timestamp}.xlsx"
    local_filepath = os.path.join(LOCAL_BACKUP_DIR, filename)
    
    log(f"--- 開始 Excel 備份 ---")
    
    # 建立數據庫連接字符串
    db_uri = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    
    try:
        # 建立連接引擎
        engine = create_engine(db_uri)
        
        # 讀取主要數據表
        query = "SELECT * FROM sim_resources ORDER BY id ASC"
        
        # 使用 pandas 讀取數據
        df = pd.read_sql(query, engine)
        
        # [Optimize] 移除僅供系統優化使用的純數字欄位
        # 這些欄位是為了 SQL 索引加速存在的，內部查閱不需要看到兩份同樣的號碼
        cols_to_exclude = ['imsi_num', 'iccid_num', 'msisdn_num','id']
        
        # errors='ignore' 確保即使數據庫還沒更新這幾個欄位，備份腳本也不會報錯
        df.drop(columns=cols_to_exclude, inplace=True, errors='ignore')
        
        # 導出到 Excel
        df.to_excel(local_filepath, index=False, engine='openpyxl')
        
        log(f"Excel 備份成功: {filename} (共 {len(df)} 筆數據)")
        return local_filepath
        
    except Exception as e:
        log(f"Excel 備份失敗: {e}")
        return None

def copy_to_network(local_path):
    """複製文件到 Share Drive"""
    if not local_path:
        return

    filename = os.path.basename(local_path)
    
    if os.path.exists(NETWORK_BACKUP_DIR):
        try:
            network_filepath = os.path.join(NETWORK_BACKUP_DIR, filename)
            shutil.copy2(local_path, network_filepath)
            log(f"複製到 Share Drive 成功: {filename}")
        except Exception as e:
            log(f"複製到 Share Drive 失敗: {e}")
    else:
        log(f"警告: 找不到 Share Drive 路徑 {NETWORK_BACKUP_DIR}，略過複製。")

def clean_old_backups(directory):
    """清理舊備份"""
    log(f"檢查過期備份: {directory}")
    now = time.time()
    cutoff = now - (RETENTION_DAYS * 86400)

    if not os.path.exists(directory):
        return

    for filename in os.listdir(directory):
        filepath = os.path.join(directory, filename)
        # 同時清理 .sql 和 .xlsx
        if os.path.isfile(filepath) and (filename.endswith(".sql") or filename.endswith(".xlsx")):
            file_ctime = os.path.getctime(filepath)
            if file_ctime < cutoff:
                try:
                    os.remove(filepath)
                    log(f"已刪除過期備份: {filename}")
                except Exception as e:
                    log(f"刪除失敗 {filename}: {e}")

if __name__ == "__main__":
    ensure_dir(LOCAL_BACKUP_DIR)
    
    current_timestamp = datetime.now().strftime("%Y%m%d")
    
    # 1. 執行 SQL 備份 (完整結構)
    sql_path = backup_sql(current_timestamp)
    copy_to_network(sql_path)
    
    # 2. 執行 Excel 備份 (過濾後的人類可讀版本)
    excel_path = backup_excel(current_timestamp)
    copy_to_network(excel_path)
    
    # 3. 清理舊文件
    clean_old_backups(LOCAL_BACKUP_DIR)
    clean_old_backups(NETWORK_BACKUP_DIR)
        
    log("=== 所有備份任務完成 ===")