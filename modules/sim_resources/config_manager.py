import json
import os
from flask import current_app
from models.sim_resource import SimResource, db

class SimConfigManager:
    CONFIG_FILE = 'config/sim_general_config.json'
    
    @staticmethod
    def _get_initial_config_from_db():
        """初始化時，從數據庫掃描現有的數據，生成 3 層 Mapping"""
        try:
            # 獲取基礎列表
            existing_providers = [r[0] for r in db.session.query(SimResource.supplier).distinct().all() if r[0]]
            existing_types = [r[0] for r in db.session.query(SimResource.type).distinct().all() if r[0]]
            existing_resources = [r[0] for r in db.session.query(SimResource.resources_type).distinct().all() if r[0]]
            
            # 生成 3 層 Mapping: Provider -> CardType -> ResourceTypes
            # 結構: { "Montnet": { "eSIM": ["45412_H"], "Physical SIM": ["45412_C"] } }
            mapping = {}
            
            # 查詢所有存在的組合
            combinations = db.session.query(
                SimResource.supplier, 
                SimResource.type, 
                SimResource.resources_type
            ).distinct().all()
            
            for provider, card_type, res_type in combinations:
                if not provider or not card_type or not res_type:
                    continue
                    
                if provider not in mapping:
                    mapping[provider] = {}
                
                if card_type not in mapping[provider]:
                    mapping[provider][card_type] = []
                    
                if res_type not in mapping[provider][card_type]:
                    mapping[provider][card_type].append(res_type)
            
            # 默認值 (如果數據庫是空的，提供一些範例)
            default_providers = sorted(list(set(existing_providers + ["CUHK", "CHKT", "CTG", "Montnet"])))
            default_card_types = sorted(list(set(existing_types + ["Physical SIM", "eSIM", "Soft Profile"])))
            default_res_types = sorted(list(set(existing_resources)))
            
            return {
                "providers": default_providers,
                "card_types": default_card_types,
                "resources_types": default_res_types,
                "provider_mapping": mapping, # 新結構
                "low_stock_threshold": 1000
            }
        except Exception as e:
            print(f"DB Init Warning: {e}")
            return {
                "providers": [], "card_types": [], "resources_types": [], 
                "provider_mapping": {}, "low_stock_threshold": 1000
            }

    @staticmethod
    def load_config():
        """加載配置，含自動遷移邏輯"""
        if not os.path.exists(SimConfigManager.CONFIG_FILE):
            initial_config = SimConfigManager._get_initial_config_from_db()
            SimConfigManager.save_config(initial_config)
            return initial_config
        
        try:
            with open(SimConfigManager.CONFIG_FILE, 'r', encoding='utf-8') as f:
                config = json.load(f)
                
            # 如果發現 Mapping 的值是 List (舊結構)，則強制重置為 DB 現狀 (新結構)
            mapping = config.get('provider_mapping', {})
            for prov, value in mapping.items():
                if isinstance(value, list): # 舊結構偵測
                    print("Detected old config format, regenerating from DB...")
                    new_config = SimConfigManager._get_initial_config_from_db()
                    # 保留用戶設置的閾值
                    new_config['low_stock_threshold'] = config.get('low_stock_threshold', 1000)
                    SimConfigManager.save_config(new_config)
                    return new_config
                    
            return config
        except Exception as e:
            print(f"Config load error: {e}")
            return SimConfigManager._get_initial_config_from_db()

    @staticmethod
    def save_config(config_data):
        os.makedirs(os.path.dirname(SimConfigManager.CONFIG_FILE), exist_ok=True)
        with open(SimConfigManager.CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config_data, f, ensure_ascii=False, indent=2)

    @staticmethod
    def check_usage(category, value):
        if not value: return False
        value = value.strip()
        
        if category == 'provider':
            return SimResource.query.filter(SimResource.supplier == value).count() > 0
        elif category == 'card_type':
            return SimResource.query.filter(SimResource.type == value).count() > 0
        elif category == 'resources_type':
            return SimResource.query.filter(SimResource.resources_type == value).count() > 0
        return False