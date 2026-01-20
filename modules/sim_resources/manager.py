from datetime import datetime
import pandas as pd
from sqlalchemy import asc, desc, func
from models.sim_resource import SimResource, db
from config.sim_resource import (
    PROVIDER_OPTIONS, 
    CARD_TYPE_OPTIONS, 
    RESOURCES_TYPE_OPTIONS,
    LOW_STOCK_THRESHOLD
)

class SimResourceManager:
    """SIM资源管理核心逻辑"""
    
    # 从配置文件导入选项
    PROVIDER_OPTIONS = PROVIDER_OPTIONS
    CARD_TYPE_OPTIONS = CARD_TYPE_OPTIONS
    RESOURCES_TYPE_OPTIONS = RESOURCES_TYPE_OPTIONS
    
    @staticmethod
    def get_all_resources(query_params, page=1, per_page=50):
        """获取SIM资源列表（带搜索和排序）"""
        # 构建查询
        query = SimResource.query
        
        # 应用搜索条件
        query = SimResourceManager._apply_search_filters(query, query_params)
        
        # 应用排序
        query = SimResourceManager._apply_sorting(query, query_params)
        
        # 分页
        return query.paginate(page=page, per_page=per_page, error_out=False)
    
    @staticmethod
    def _apply_search_filters(query, params):
        """應用搜尋過濾器 (增強版)"""
        
        # 1. 精確/模糊匹配欄位
        if params.get('provider'):
            query = query.filter(SimResource.supplier.ilike(f'%{params["provider"]}%'))
        if params.get('card_type'):
            query = query.filter(SimResource.type.ilike(f'%{params["card_type"]}%'))
        if params.get('resources_type'):
            query = query.filter(SimResource.resources_type.ilike(f'%{params["resources_type"]}%'))
        if params.get('batch'):
            query = query.filter(SimResource.batch.ilike(f'%{params["batch"]}%'))
        if params.get('received_date'):
            query = query.filter(SimResource.received_date.ilike(f'%{params["received_date"]}%'))
            
        # 2. 新增欄位搜尋
        if params.get('status'):
            query = query.filter(SimResource.status == params['status'])  # 精確匹配
            
        if params.get('customer'):
            query = query.filter(SimResource.customer.ilike(f'%{params["customer"]}%')) # 模糊匹配
            
        # 3. 分配日期範圍搜尋
        start_date = params.get('assigned_date_start')
        end_date = params.get('assigned_date_end')
        if start_date and end_date:
            # 假設資料庫存的是字串 YYYY-MM-DD，可以直接字串比較
            query = query.filter(SimResource.assigned_date >= start_date, SimResource.assigned_date <= end_date)
        elif start_date:
            query = query.filter(SimResource.assigned_date >= start_date)
        elif end_date:
            query = query.filter(SimResource.assigned_date <= end_date)

        # 4. 段落搜尋 (IMSI, ICCID, MSISDN)
        # 邏輯：如果有 "-" 則視為範圍，否則視為模糊搜尋
        
        def apply_range_or_like(q, field, value):
            if not value:
                return q
            
            value = value.strip()
            if '-' in value:
                # 嘗試解析範圍
                parts = value.split('-')
                if len(parts) == 2:
                    start, end = parts[0].strip(), parts[1].strip()
                    # 確保兩者都是數字 (簡單驗證)
                    if start.isdigit() and end.isdigit():
                        return q.filter(field >= start, field <= end)
            
            # 默認模糊搜尋
            return q.filter(field.ilike(f'%{value}%'))

        query = apply_range_or_like(query, SimResource.imsi, params.get('imsi'))
        query = apply_range_or_like(query, SimResource.iccid, params.get('iccid'))
        query = apply_range_or_like(query, SimResource.msisdn, params.get('msisdn'))
            
        return query
    
    @staticmethod
    def _apply_sorting(query, params):
        """应用排序"""
        from sqlalchemy import asc, desc
        
        sort_field = params.get('sort', 'updated_at')
        sort_order = params.get('order', 'desc')
        
        # 验证排序字段
        valid_fields = ['supplier', 'type', 'resources_type', 'batch', 
                       'received_date', 'imsi', 'iccid', 'msisdn', 
                       'created_at', 'updated_at']
        
        if sort_field not in valid_fields:
            sort_field = 'updated_at'
        
        # 应用排序
        if sort_order == 'asc':
            return query.order_by(asc(getattr(SimResource, sort_field)))
        else:
            return query.order_by(desc(getattr(SimResource, sort_field)))
    
    @staticmethod
    def get_options():
        """获取所有选项数据"""
        # 从数据库获取实际存在的值
        try:
            existing_types = db.session.query(SimResource.type).distinct().all()
            existing_resources = db.session.query(SimResource.resources_type).distinct().all()
            
            return {
                'providers': SimResourceManager.PROVIDER_OPTIONS,
                'card_types': [t[0] for t in existing_types if t[0]] or SimResourceManager.CARD_TYPE_OPTIONS,
                'resources_types': [t[0] for t in existing_resources if t[0]] or SimResourceManager.RESOURCES_TYPE_OPTIONS
            }
        except Exception as e:
            print(f"Error getting options: {e}")
            return {
                'providers': SimResourceManager.PROVIDER_OPTIONS,
                'card_types': SimResourceManager.CARD_TYPE_OPTIONS,
                'resources_types': SimResourceManager.RESOURCES_TYPE_OPTIONS
            }
    
    @staticmethod
    def validate_resource_data(data, is_edit=False, resource_id=None):
        """验证资源数据"""
        errors = []
        
        # 必填字段验证
        required_fields = ['Provider', 'CardType', 'ResourcesType', 'Batch', 
                          'ReceivedDate', 'IMSI', 'ICCID', 'MSISDN']
        
        for field in required_fields:
            if not data.get(field) or str(data[field]).strip() == '':
                errors.append(f"{field} 必填")
        
        # 卡类型验证
        card_type = data.get('CardType', '')
        if card_type and card_type not in SimResourceManager.CARD_TYPE_OPTIONS:
            # 不再強制報錯，允許數據庫中已存在的舊類型，或者發出警告
            # 如果需要嚴格驗證，可以保留。這裡暫時保留但建議前端選項要同步
            pass 
        
        # 条件必填验证
        if card_type == 'Soft Profile':
            if not data.get('Ki', '').strip():
                errors.append("Soft Profile 必须填写 Ki")
            if not data.get('OPC', '').strip():
                errors.append("Soft Profile 必须填写 OPC")
        elif card_type == 'eSIM':
            if not data.get('LPA', '').strip():
                errors.append("eSIM 必须填写 LPA")
        
        # 移除對 ResourcesType 的嚴格集合驗證，允許自定義類型
        # resource_type = data.get('ResourcesType', '')
        # if resource_type not in SimResourceManager.RESOURCES_TYPE_OPTIONS:
        #     errors.append(f"无效的資源类型: {card_type}")        
        
        # 重复检查
        if not is_edit:
            # 僅在新增時檢查重複
            if data.get('IMSI'):
                existing = SimResource.query.filter_by(imsi=data['IMSI'].strip()).first()
                if existing:
                    errors.append("IMSI 已存在")
            
            if data.get('ICCID'):
                existing = SimResource.query.filter_by(iccid=data['ICCID'].strip()).first()
                if existing:
                    errors.append("ICCID 已存在")
        else:
            # 編輯時檢查是否與其他資源重複 (排除自己)
            if data.get('IMSI'):
                existing = SimResource.query.filter(SimResource.imsi == data['IMSI'].strip(), SimResource.id != resource_id).first()
                if existing:
                    errors.append("IMSI 已存在")
            
            if data.get('ICCID'):
                existing = SimResource.query.filter(SimResource.iccid == data['ICCID'].strip(), SimResource.id != resource_id).first()
                if existing:
                    errors.append("ICCID 已存在")
        
        return errors
    
    @staticmethod
    def create_resource(data):
        """创建新资源"""
        resource = SimResource(
            type=data['CardType'].strip(),
            supplier=data['Provider'].strip(),
            resources_type=data['ResourcesType'].strip(),
            batch=data['Batch'].strip(),
            received_date=data['ReceivedDate'].strip(),
            imsi=data['IMSI'].strip(),
            iccid=data['ICCID'].strip(),
            msisdn=data['MSISDN'].strip(),
            ki=data.get('Ki', '').strip() or None,
            opc=data.get('OPC', '').strip() or None,
            lpa=data.get('LPA', '').strip() or None,
            pin1=data.get('PIN1', '').strip() or None,
            puk1=data.get('PUK1', '').strip() or None,
            pin2=data.get('PIN2', '').strip() or None,
            puk2=data.get('PUK2', '').strip() or None
        )
        
        db.session.add(resource)
        db.session.commit()
        return resource
    
    @staticmethod
    def update_resource(resource_id, data):
        """更新资源"""
        resource = SimResource.query.get_or_404(resource_id)
        
        resource.type = data['CardType'].strip()
        resource.supplier = data['Provider'].strip()
        resource.resources_type = data['ResourcesType'].strip()
        resource.batch = data['Batch'].strip()
        resource.received_date = data['ReceivedDate'].strip()
        resource.imsi = data['IMSI'].strip()
        resource.iccid = data['ICCID'].strip()
        resource.msisdn = data['MSISDN'].strip()
        resource.ki = data.get('Ki', '').strip() or None
        resource.opc = data.get('OPC', '').strip() or None
        resource.lpa = data.get('LPA', '').strip() or None
        resource.pin1 = data.get('PIN1', '').strip() or None
        resource.puk1 = data.get('PUK1', '').strip() or None
        resource.pin2 = data.get('PIN2', '').strip() or None
        resource.puk2 = data.get('PUK2', '').strip() or None
        
        db.session.commit()
        return resource
    
    @staticmethod
    def get_low_stock_alerts():
        """获取低库存警告"""
        from sqlalchemy import func
        
        # 按 type 分组统计
        type_counts = db.session.query(
            SimResource.type,
            func.count(SimResource.id)
        ).group_by(SimResource.type).all()
        type_stats = {row[0]: row[1] for row in type_counts}
        
        # 低库存警告
        low_stock_alerts = []
        total_count = sum(type_stats.values())
        
        for typ, cnt in type_stats.items():
            if cnt < LOW_STOCK_THRESHOLD and cnt > 0:
                low_stock_alerts.append(f"{typ.capitalize()} 仅剩 {cnt} 张")
        if total_count < LOW_STOCK_THRESHOLD and total_count > 0:
            low_stock_alerts.append(f"总库存仅剩 {total_count} 张")
        
        return low_stock_alerts
    
    @staticmethod
    def calculate_assignment_options(provider, card_type, resources_type, quantity):
        """
        計算分配選項：
        1. 找出所有可用庫存，按 ReceivedDate ASC, Batch ASC 排序
        2. 計算方案 A (FIFO): 跨批次拼接
        3. 計算方案 B (Single Batch): 尋找單一批次滿足
        """
        # 1. 查詢該條件下的所有可用資源，按批次分組統計
        # 注意：這裡我們先撈出所有可用資源的摘要信息，而不是所有 row
        from sqlalchemy import func
        
        # 查詢各批次的可用數量
        # 按 received_date 排序確保先進先出
        batch_stats = db.session.query(
            SimResource.batch,
            SimResource.received_date,
            func.count(SimResource.id)
        ).filter(
            SimResource.supplier == provider,
            SimResource.type == card_type,
            SimResource.resources_type == resources_type,
            SimResource.status == 'Available'
        ).group_by(
            SimResource.batch, 
            SimResource.received_date
        ).order_by(
            SimResource.received_date.asc(),
            SimResource.batch.asc()
        ).all()

        total_available = sum(count for _, _, count in batch_stats)
        
        if total_available < quantity:
            return {
                "success": False,
                "message": f"庫存不足。需求: {quantity}, 總可用: {total_available}",
                "total_available": total_available
            }

        options = []

        # --- 方案 A: FIFO (跨批次拼接) ---
        fifo_plan = []
        remaining_qty = quantity
        
        for batch, r_date, count in batch_stats:
            if remaining_qty <= 0:
                break
            
            take = min(remaining_qty, count)
            fifo_plan.append({
                "batch": batch,
                "received_date": r_date,
                "take": take,
                "available": count
            })
            remaining_qty -= take
            
        options.append({
            "id": "fifo",
            "name": "方案 A (FIFO): 優先使用最早批次",
            "batches": fifo_plan
        })

        # --- 方案 B: Single Batch (單一批次滿足) ---
        # 尋找第一個數量足夠的單一批次
        single_batch_plan = None
        for batch, r_date, count in batch_stats:
            if count >= quantity:
                # 找到一個單一批次足夠
                single_batch_plan = [{
                    "batch": batch,
                    "received_date": r_date,
                    "take": quantity,
                    "available": count
                }]
                break
        
        # 只有當方案 B 存在，且方案 B 的批次構成與方案 A 不同時，才提供方案 B
        # (例如方案 A 已經就是只用了 Batch 1，那就不需要顯示重複的方案 B)
        if single_batch_plan:
            is_different = True
            if len(fifo_plan) == 1 and fifo_plan[0]['batch'] == single_batch_plan[0]['batch']:
                is_different = False
            
            if is_different:
                options.append({
                    "id": "single",
                    "name": f"方案 B (單一批次): 直接使用 {single_batch_plan[0]['batch']}",
                    "batches": single_batch_plan
                })

        return {
            "success": True,
            "options": options,
            "total_available": total_available
        }

    @staticmethod
    def confirm_assignment(plan, customer, assigned_date, provider, card_type, resources_type):
        """
        執行分配
        增加 provider, card_type, resources_type 參數以確保精確匹配
        """
        total_assigned = 0
        assigned_ranges = []

        try:
            for item in plan:
                batch_name = item['batch']
                take_qty = item['take']
                
                # 找出該批次中符合所有條件且 Available 的卡
                # 這裡必須嚴格篩選 provider, card_type, resources_type
                resources_to_update = SimResource.query.filter(
                    SimResource.batch == batch_name,
                    SimResource.status == 'Available',
                    SimResource.supplier == provider,          # 新增篩選
                    SimResource.type == card_type,             # 新增篩選
                    SimResource.resources_type == resources_type # 新增篩選
                ).order_by(
                    SimResource.imsi.asc()
                ).limit(take_qty).all()
                
                if len(resources_to_update) < take_qty:
                    raise Exception(f"批次 {batch_name} 中符合條件的庫存不足 (需求 {take_qty}, 實際 {len(resources_to_update)})，請刷新頁面重試")
                
                # 更新狀態
                first_imsi = resources_to_update[0].imsi
                last_imsi = resources_to_update[-1].imsi
                
                for res in resources_to_update:
                    res.status = 'Assigned'
                    res.customer = customer
                    res.assigned_date = assigned_date
                
                total_assigned += len(resources_to_update)
                assigned_ranges.append(f"{batch_name}: {first_imsi} ~ {last_imsi} ({len(resources_to_update)} pcs)")

            db.session.commit()
            return {
                "success": True, 
                "message": f"成功分配 {total_assigned} 張 SIM 卡",
                "details": assigned_ranges
            }
            
        except Exception as e:
            db.session.rollback()
            return {"success": False, "message": str(e)}

    @staticmethod
    def manual_assignment(start_imsi, end_imsi, customer, assigned_date):
        """
        手動分配：根據 IMSI 範圍
        """
        try:
            # 1. 驗證輸入
            if not start_imsi.isdigit() or not end_imsi.isdigit():
                return {"success": False, "message": "IMSI 必須為數字"}
            
            start = int(start_imsi)
            end = int(end_imsi)
            
            if start > end:
                return {"success": False, "message": "起始 IMSI 不能大於結束 IMSI"}
            
            count = end - start + 1
            if count > 10000: # 簡單防護
                 return {"success": False, "message": "單次操作數量過大 (上限 10000)"}

            # 2. 查詢範圍內的資源
            # 由於 IMSI 是字串存儲，直接使用 between 可能會有字典序問題
            # 但如果長度一致，字典序等於數值序。
            # 為保險起見，我們找出該範圍內的所有記錄進行檢查
            
            # 使用 cast 轉成數字比較會更準確，但在不同 DB 語法不同
            # 這裡簡化處理：假設 IMSI 長度相同，直接用字串比較
            target_resources = SimResource.query.filter(
                SimResource.imsi >= start_imsi,
                SimResource.imsi <= end_imsi
            ).all()
            
            # 3. 嚴格驗證
            if len(target_resources) == 0:
                return {"success": False, "message": f"範圍 {start_imsi} - {end_imsi} 內找不到任何資源"}
            
            # 檢查是否所有找到的資源都在請求範圍內 (再次確認，雖 SQL 已濾)
            valid_resources = []
            assigned_list = []
            
            for res in target_resources:
                # 再次確保數值在範圍內
                if not (start <= int(res.imsi) <= end):
                    continue
                    
                if res.status != 'Available':
                    assigned_list.append(res.imsi)
                else:
                    valid_resources.append(res)
            
            if assigned_list:
                # 顯示前 3 個重複的
                preview = ", ".join(assigned_list[:3])
                return {
                    "success": False, 
                    "message": f"範圍內有 {len(assigned_list)} 張卡已被分配或不可用。例如: {preview}..."
                }
            
            # 4. 執行更新
            for res in valid_resources:
                res.status = 'Assigned'
                res.customer = customer
                res.assigned_date = assigned_date
                
            db.session.commit()
            
            return {
                "success": True, 
                "message": f"手動分配成功！共 {len(valid_resources)} 張卡 (IMSI: {start_imsi} - {end_imsi})"
            }

        except Exception as e:
            db.session.rollback()
            return {"success": False, "message": f"系統錯誤: {str(e)}"}
        
    @staticmethod
    def unassign_resource(resource_id):
        """取消分配：將狀態重置為 Available 並清空客戶資訊"""
        resource = SimResource.query.get_or_404(resource_id)
        
        if resource.status == 'Available':
            return resource # 本來就是 Available，無需操作
            
        resource.status = 'Available'
        resource.customer = None
        resource.assigned_date = None
        # resource.order_id = None # 如果有這個欄位也清空
        
        db.session.commit()
        return resource