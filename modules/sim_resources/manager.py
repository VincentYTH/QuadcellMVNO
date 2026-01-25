from datetime import datetime
import pandas as pd
import re
import math
from sqlalchemy import asc, desc, func, case, text
from sqlalchemy.sql.expression import cast
from models.sim_resource import SimResource, db
from config.sim_resource import (
    PROVIDER_OPTIONS, 
    CARD_TYPE_OPTIONS, 
    RESOURCES_TYPE_OPTIONS,
    LOW_STOCK_THRESHOLD,
    PROVIDER_RESOURCES_MAPPING
)

class PaginationResult:
    """Helper class to mimic Flask-SQLAlchemy Pagination object for raw/grouped queries"""
    def __init__(self, items, page, per_page, total):
        self.items = items
        self.page = page
        self.per_page = per_page
        self.total = total
        self.pages = int(math.ceil(total / per_page)) if per_page else 0
        self.has_prev = page > 1
        self.has_next = page < self.pages
        self.prev_num = page - 1
        self.next_num = page + 1
        
    def iter_pages(self, left_edge=2, left_current=2, right_current=5, right_edge=2):
        last = 0
        for num in range(1, self.pages + 1):
            if num <= left_edge or \
               (num > self.page - left_current - 1 and \
                num < self.page + right_current) or \
               num > self.pages - right_edge:
                if last + 1 != num:
                    yield None
                yield num
                last = num

class SimResourceManager:
    
    PROVIDER_OPTIONS = PROVIDER_OPTIONS
    CARD_TYPE_OPTIONS = CARD_TYPE_OPTIONS
    RESOURCES_TYPE_OPTIONS = RESOURCES_TYPE_OPTIONS
    
    @staticmethod
    def get_all_resources(query_params, page=1, per_page=50):
        """獲取SIM資源列表（單條模式）"""
        query = SimResource.query
        
        # 應用所有過濾器 (屬性 + ID)
        query = SimResourceManager._apply_attribute_filters(query, query_params)
        query = SimResourceManager._apply_id_filters(query, query_params)
        
        # 應用排序
        query = SimResourceManager._apply_sorting(query, query_params)
        
        return query.paginate(page=page, per_page=per_page, error_out=False)

    @staticmethod
    def get_grouped_resources(query_params, page=1, per_page=50):
        """獲取分組後的資源列表 (按 IMSI 段落模式)"""
        
        # 1. 基礎查詢：只應用「屬性」過濾器 (Provider, Batch等)，不應用 ID 過濾器
        #    這是為了讓 ID 搜索能匹配到整個段落
        base_query = SimResource.query
        base_query = SimResourceManager._apply_attribute_filters(base_query, query_params)
        
        # 2. 定義分組屬性
        group_cols = [
            SimResource.supplier,
            SimResource.type,
            SimResource.resources_type,
            SimResource.batch,
            SimResource.status,
            SimResource.customer,
            SimResource.assigned_date,
            SimResource.remark
        ]
        
        # 3. Gaps-and-Islands 計算邏輯
        def safe_cast_diff(col, order_col):
             # 將字串轉數字進行連續性判斷
             return case(
                 (cast(col, db.Text).op("~")('^[0-9]+$'), 
                  cast(col, db.Numeric) - func.row_number().over(order_by=order_col)),
                 else_=0
             )

        # 排序基礎
        order_col = cast(SimResource.imsi, db.Numeric)
        
        # 4. 構建子查詢 (標記 grp_id)
        subquery = base_query.with_entities(
            SimResource.id,
            *group_cols,
            SimResource.imsi,
            SimResource.iccid,
            SimResource.msisdn,
            SimResource.created_at,
            SimResource.updated_at,
            safe_cast_diff(SimResource.imsi, order_col).label('imsi_grp'),
            safe_cast_diff(SimResource.iccid, order_col).label('iccid_grp'),
            safe_cast_diff(SimResource.msisdn, order_col).label('msisdn_grp')
        ).subquery()
        
        # 5. 構建聚合查詢
        group_by_args = [getattr(subquery.c, col.name) for col in group_cols] + \
                        [subquery.c.imsi_grp, subquery.c.iccid_grp, subquery.c.msisdn_grp]
        
        query = db.session.query(
            func.min(subquery.c.id).label('id'),
            *[getattr(subquery.c, col.name) for col in group_cols],
            func.count().label('count'),
            func.min(subquery.c.imsi).label('start_imsi'),
            func.max(subquery.c.imsi).label('end_imsi'),
            func.min(subquery.c.iccid).label('start_iccid'),
            func.max(subquery.c.iccid).label('end_iccid'),
            func.min(subquery.c.msisdn).label('start_msisdn'),
            func.max(subquery.c.msisdn).label('end_msisdn'),
            func.max(subquery.c.created_at).label('created_at'),
            func.max(subquery.c.updated_at).label('updated_at'),
            func.array_agg(subquery.c.id).label('ids_list')
        ).group_by(*group_by_args)
        
        # 6. [重點修改] 在聚合後應用 ID 過濾 (Overlap 邏輯)
        #    邏輯：段落範圍 (Min~Max) 與 搜索範圍 (Start~End) 是否有重疊
        #    Overlap 條件: Seg.Min <= Search.End AND Seg.Max >= Search.Start
        
        def apply_range_overlap_filter(q, col_min, col_max, search_val):
            if not search_val:
                return q
            
            val = search_val.strip()
            start_val, end_val = val, val
            
            if '-' in val:
                parts = val.split('-')
                if len(parts) == 2:
                    s, e = parts[0].strip(), parts[1].strip()
                    if s.isdigit() and e.isdigit():
                        start_val, end_val = s, e
            
            if start_val.isdigit() and end_val.isdigit():
                # 轉為數字進行比較
                s_num = int(start_val)
                e_num = int(end_val)
                return q.having(
                    (cast(col_min, db.Numeric) <= e_num) & 
                    (cast(col_max, db.Numeric) >= s_num)
                )
            else:
                # 非數字則使用模糊匹配 (fallback)
                return q.having(col_min.ilike(f'%{val}%'))

        query = apply_range_overlap_filter(query, func.min(subquery.c.imsi), func.max(subquery.c.imsi), query_params.get('imsi'))
        query = apply_range_overlap_filter(query, func.min(subquery.c.iccid), func.max(subquery.c.iccid), query_params.get('iccid'))
        query = apply_range_overlap_filter(query, func.min(subquery.c.msisdn), func.max(subquery.c.msisdn), query_params.get('msisdn'))
        
        # 7. 排序 (強制按 Start IMSI ASC)
        query = query.order_by(asc('start_imsi'))
        
        # 8. 分頁
        total_count = query.count()
        items = query.limit(per_page).offset((page - 1) * per_page).all()
        
        return PaginationResult(items, page, per_page, total_count)
    
    @staticmethod
    def _apply_attribute_filters(query, params):
        """應用非 ID 類屬性過濾器 (Provider, Type, Status 等)"""
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
            
        if params.get('status'):
            query = query.filter(SimResource.status == params['status'])
        if params.get('customer'):
            query = query.filter(SimResource.customer == params["customer"])
        if params.get('remark'):
            query = query.filter(SimResource.remark.ilike(f'%{params["remark"]}%'))    
            
        start_date = params.get('assigned_date_start')
        end_date = params.get('assigned_date_end')
        if start_date and end_date:
            query = query.filter(SimResource.assigned_date >= start_date, SimResource.assigned_date <= end_date)
        elif start_date:
            query = query.filter(SimResource.assigned_date >= start_date)
        elif end_date:
            query = query.filter(SimResource.assigned_date <= end_date)
            
        return query

    @staticmethod
    def _apply_id_filters(query, params):
        """應用 ID 類過濾器 (IMSI, ICCID, MSISDN) - 用於單條模式"""
        def apply_range_or_like(q, field, value):
            if not value: return q
            value = value.strip()
            if '-' in value:
                parts = value.split('-')
                if len(parts) == 2:
                    start, end = parts[0].strip(), parts[1].strip()
                    if start.isdigit() and end.isdigit():
                        return q.filter(field >= start, field <= end)
            return q.filter(field.ilike(f'%{value}%'))

        query = apply_range_or_like(query, SimResource.imsi, params.get('imsi'))
        query = apply_range_or_like(query, SimResource.iccid, params.get('iccid'))
        query = apply_range_or_like(query, SimResource.msisdn, params.get('msisdn'))
        return query

    @staticmethod
    def _apply_search_filters(query, params):
        """兼容舊代碼的入口 (如果還有其他地方調用)"""
        query = SimResourceManager._apply_attribute_filters(query, params)
        query = SimResourceManager._apply_id_filters(query, params)
        return query
    
    # ... (其他方法 _apply_sorting, get_options 等保持不變) ...
    # 請確保保留 validate_resource_data, create_resource 等所有現有方法
    @staticmethod
    def _apply_sorting(query, params):
        sort_field = params.get('sort', 'updated_at')
        sort_order = params.get('order', 'desc')
        valid_fields = ['supplier', 'type', 'resources_type', 'batch', 'received_date', 'imsi', 'iccid', 'msisdn', 'customer', 'assigned_date', 'status', 'created_at', 'updated_at']
        if sort_field not in valid_fields: sort_field = 'updated_at'
        if sort_order == 'asc': return query.order_by(asc(getattr(SimResource, sort_field)))
        else: return query.order_by(desc(getattr(SimResource, sort_field)))

    @staticmethod
    def get_options():
        """获取所有选项数据"""
        try:
            existing_types = db.session.query(SimResource.type).distinct().all()
            existing_resources = db.session.query(SimResource.resources_type).distinct().all()
            existing_customers = db.session.query(SimResource.customer).distinct().all()
            existing_batches = db.session.query(SimResource.batch).distinct().all()
            existing_dates = db.session.query(SimResource.received_date).distinct().all()
            existing_assigned_dates = db.session.query(SimResource.assigned_date).distinct().all()
            
            card_types_set = set([t[0] for t in existing_types if t[0]]) | set(SimResourceManager.CARD_TYPE_OPTIONS)
            resources_types_set = set([t[0] for t in existing_resources if t[0]]) | set(SimResourceManager.RESOURCES_TYPE_OPTIONS)
            
            def natural_keys(text):
                return [int(c) if c.isdigit() else c for c in re.split(r'(\d+)', str(text))]

            customers_list = sorted([c[0] for c in existing_customers if c[0] and c[0].strip()])
            raw_batches = [b[0] for b in existing_batches if b[0] and b[0].strip()]
            batches_list = sorted(raw_batches, key=natural_keys)
            dates_list = sorted([d[0] for d in existing_dates if d[0] and d[0].strip()], reverse=True)
            assigned_dates_list = sorted([d[0] for d in existing_assigned_dates if d[0] and d[0].strip()], reverse=True)
            
            return {
                'providers': SimResourceManager.PROVIDER_OPTIONS,
                'card_types': sorted(list(card_types_set)),
                'resources_types': sorted(list(resources_types_set)),
                'provider_mapping': PROVIDER_RESOURCES_MAPPING,
                'customers': customers_list,
                'batches': batches_list,
                'received_dates': dates_list,
                'assigned_dates': assigned_dates_list 
            }
        except Exception as e:
            print(f"Error getting options: {e}")
            return {
                'providers': SimResourceManager.PROVIDER_OPTIONS,
                'card_types': SimResourceManager.CARD_TYPE_OPTIONS,
                'resources_types': list(SimResourceManager.RESOURCES_TYPE_OPTIONS),
                'customers': [],
                'batches': [],
                'received_dates': [],
                'assigned_dates': []
            }
    
    @staticmethod
    def get_distinct_filters(params, extra_filters=None):
        """
        獲取當前搜索條件下的唯一 Customer 和 Assigned Date
        params: 頁面上的主要搜索條件
        extra_filters: Modal 內部的額外篩選 (例如選了 Customer 後要篩選 Date)
        """
        # 1. 基礎查詢 (基於頁面搜索條件)
        base_query = SimResource.query
        base_query = SimResourceManager._apply_search_filters(base_query, params)
        
        # 2. 獲取 Customer 清單 
        # (Customer 清單永遠只受頁面搜索影響，不受 Modal 內 Date 選擇影響，否則會變成都選不到)
        customers = base_query.with_entities(SimResource.customer)\
            .filter(SimResource.customer != None, SimResource.customer != '')\
            .distinct().order_by(SimResource.customer).all()
        
        # 3. 獲取 Assigned Date 清單
        # (Date 清單受頁面搜索 + Modal 內選擇的 Customer 影響)
        date_query = base_query
        
        if extra_filters and extra_filters.get('customer') and extra_filters['customer'] != 'ALL':
            date_query = date_query.filter(SimResource.customer == extra_filters['customer'])

        dates = date_query.with_entities(SimResource.assigned_date)\
            .filter(SimResource.assigned_date != None, SimResource.assigned_date != '')\
            .distinct().order_by(SimResource.assigned_date.desc()).all()
            
        return {
            'customers': [c[0] for c in customers],
            'assigned_dates': [d[0] for d in dates]
        }
    
    @staticmethod
    def get_resources_for_export(scope, selected_ids=None, search_params=None, extra_filters=None):
        """
        獲取導出數據
        scope: 'search' (當前搜索結果) 或 'selected' (已選項目)
        selected_ids: ID列表 (當 scope='selected' 時使用)
        search_params: 搜索參數 (當 scope='search' 時使用)
        extra_filters: 額外過濾器 (Customer, AssignedDate)
        """
        query = SimResource.query
        
        # 1. 確定基礎範圍
        if scope == 'selected' and selected_ids:
            query = query.filter(SimResource.id.in_(selected_ids))
        elif scope == 'search' and search_params:
            # 重用搜索邏輯
            query = SimResourceManager._apply_search_filters(query, search_params)
            # 應用排序以保持一致性
            query = SimResourceManager._apply_sorting(query, search_params)
        
        # 2. 應用額外過濾器 (Customer 和 Assign Date)
        if extra_filters:
            customer = extra_filters.get('customer')
            assigned_date = extra_filters.get('assigned_date')
            
            if customer and customer != 'ALL':
                query = query.filter(SimResource.customer == customer)
            
            if assigned_date and assigned_date != 'ALL':
                query = query.filter(SimResource.assigned_date == assigned_date)
        
        return query.all()

    # ... (其餘 validate_resource_data, create, update 等方法保持不變) ...
    # 為了節省篇幅，這裡只列出有修改的部分，實際文件中請保留其他現有方法
    
    @staticmethod
    def validate_resource_data(data, is_edit=False, resource_id=None):
        """验证资源数据"""
        errors = []
        
        required_fields = ['Provider', 'CardType', 'ResourcesType', 'Batch', 
                          'ReceivedDate', 'IMSI', 'ICCID', 'MSISDN']
        
        for field in required_fields:
            if not data.get(field) or str(data[field]).strip() == '':
                errors.append(f"{field} 必填")
        
        card_type = data.get('CardType', '')
        
        if card_type == 'Soft Profile':
            if not data.get('Ki', '').strip():
                errors.append("Soft Profile 必须填写 Ki")
            if not data.get('OPC', '').strip():
                errors.append("Soft Profile 必须填写 OPC")
        elif card_type == 'eSIM':
            if not data.get('LPA', '').strip():
                errors.append("eSIM 必须填写 LPA")
        
        if not is_edit:
            if data.get('IMSI'):
                existing = SimResource.query.filter_by(imsi=data['IMSI'].strip()).first()
                if existing:
                    errors.append("IMSI 已存在")
            
            if data.get('ICCID'):
                existing = SimResource.query.filter_by(iccid=data['ICCID'].strip()).first()
                if existing:
                    errors.append("ICCID 已存在")
        else:
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
        
        # 判斷狀態
        customer = data.get('Customer', '').strip() or None
        status = 'Assigned' if customer else 'Available'        
        
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
            puk2=data.get('PUK2', '').strip() or None,
            status=status,
            customer=customer,
            assigned_date=data.get('Assign Date', '').strip() or None,
            remark=data.get('Remark', '').strip() or None         
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
        
        # 更新客戶資訊
        if 'Customer' in data: # 只有當數據中包含 Customer 時才更新 (如果是從簡單編輯表格來)
            customer = data.get('Customer', '').strip() or None
            resource.customer = customer
            # 自動更新狀態邏輯 (可選)
            # if customer: resource.status = 'Assigned'
            
        if 'Assign Date' in data:
            resource.assigned_date = data.get('Assign Date', '').strip() or None   
            
        if 'Remark' in data:
            resource.remark = data.get('Remark', '').strip() or None     
        
        db.session.commit()
        return resource
    
    @staticmethod
    def get_low_stock_alerts():
        """获取低库存警告"""
        from sqlalchemy import func
        
        type_counts = db.session.query(
            SimResource.type,
            func.count(SimResource.id)
        ).group_by(SimResource.type).all()
        type_stats = {row[0]: row[1] for row in type_counts}
        
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
        """計算分配選項"""
        from sqlalchemy import func
        
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

        # --- 方案 A: FIFO ---
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

        # --- 方案 B: Single Batch ---
        single_batch_plan = None
        for batch, r_date, count in batch_stats:
            if count >= quantity:
                single_batch_plan = [{
                    "batch": batch,
                    "received_date": r_date,
                    "take": quantity,
                    "available": count
                }]
                break
        
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
    def confirm_assignment(plan, customer, assigned_date, provider, card_type, resources_type, remark=None):
        """執行分配"""
        total_assigned = 0
        assigned_ranges = []

        try:
            for item in plan:
                batch_name = item['batch']
                take_qty = item['take']
                
                resources_to_update = SimResource.query.filter(
                    SimResource.batch == batch_name,
                    SimResource.status == 'Available',
                    SimResource.supplier == provider,
                    SimResource.type == card_type,
                    SimResource.resources_type == resources_type
                ).order_by(
                    SimResource.imsi.asc()
                ).limit(take_qty).all()
                
                if len(resources_to_update) < take_qty:
                    raise Exception(f"批次 {batch_name} 中符合條件的庫存不足 (需求 {take_qty}, 實際 {len(resources_to_update)})，請刷新頁面重試")
                
                first_imsi = resources_to_update[0].imsi
                last_imsi = resources_to_update[-1].imsi
                
                for res in resources_to_update:
                    res.status = 'Assigned'
                    res.customer = customer
                    res.assigned_date = assigned_date
                    # 如果提供了 remark 則更新
                    if remark is not None and str(remark).strip():
                        res.remark = str(remark).strip()
                
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
    def manual_assignment(scope, ids, start_imsi, end_imsi, customer, assigned_date, remark=None):
        """手動分配：支持 按IMSI範圍 或 按已選項目"""
        try:
            # 1. 獲取查詢對象
            query, error = SimResourceManager._get_batch_targets(scope, ids, start_imsi, end_imsi)
            if error: return {"success": False, "message": error}
            
            resources = query.all()
            target_resources = []
            
            # 2. 過濾與驗證
            if scope == 'range':
                # 範圍模式：嚴格數字驗證與範圍匹配
                if not start_imsi.isdigit() or not end_imsi.isdigit():
                    return {"success": False, "message": "IMSI 必須為純數字"}
                s_int, e_int = int(start_imsi), int(end_imsi)
                if s_int > e_int: return {"success": False, "message": "起始 IMSI 不能大於結束 IMSI"}
                
                # 範圍模式下的數量檢查
                count_expected = e_int - s_int + 1
                if count_expected > 10000: return {"success": False, "message": "單次操作數量過大 (上限 10000)"}

                for res in resources:
                    if res.imsi and res.imsi.isdigit():
                        if s_int <= int(res.imsi) <= e_int:
                            target_resources.append(res)
            else:
                # 已選模式
                target_resources = resources

            if not target_resources:
                return {"success": False, "message": "未找到符合條件的資源"}

            # 3. 檢查狀態 (必須為 Available)
            unavailable = []
            for res in target_resources:
                if res.status != 'Available':
                    unavailable.append(res.imsi)
            
            if unavailable:
                return {"success": False, "message": f"以下 IMSI 已被分配或不可用: {', '.join(unavailable[:3])}..."}

            # 4. 執行分配
            for res in target_resources:
                res.status = 'Assigned'
                res.customer = customer
                res.assigned_date = assigned_date
                # 如果提供了 remark 則更新
                if remark is not None and str(remark).strip():
                    res.remark = str(remark).strip()
            
            db.session.commit()
            return {"success": True, "message": f"成功分配 {len(target_resources)} 張卡"}

        except Exception as e:
            db.session.rollback()
            return {"success": False, "message": f"系統錯誤: {str(e)}"}

    @staticmethod
    def batch_cancel_assignment(scope, ids, start_imsi, end_imsi, remark=None):
        """批量取消分配：支持 按IMSI範圍 或 按已選項目"""
        try:
            query, error = SimResourceManager._get_batch_targets(scope, ids, start_imsi, end_imsi)
            if error: return {"success": False, "message": error}
            
            resources = query.all()
            target_resources = []
            
            if scope == 'range':
                if not start_imsi.isdigit() or not end_imsi.isdigit():
                    return {"success": False, "message": "IMSI 必須為純數字"}
                s_int, e_int = int(start_imsi), int(end_imsi)
                
                for res in resources:
                    if res.imsi and res.imsi.isdigit():
                        if s_int <= int(res.imsi) <= e_int:
                            target_resources.append(res)
            else:
                target_resources = resources

            if not target_resources:
                return {"success": False, "message": "未找到符合條件的資源"}
            
            # 只處理狀態為 Assigned 的資源
            changed_count = 0
            for res in target_resources:
                if res.status == 'Assigned':
                    res.status = 'Available'
                    res.customer = None
                    res.assigned_date = None
                    # 如果用戶在 Cancel 時輸入了 Remark，則更新它
                    if remark is not None and str(remark).strip():
                        res.remark = str(remark).strip()
                    changed_count += 1
            
            if changed_count == 0:
                return {"success": False, "message": "選定範圍內沒有 'Assigned' 狀態的資源，無需取消。"}

            db.session.commit()
            return {"success": True, "message": f"成功取消分配 {changed_count} 張卡"}

        except Exception as e:
            db.session.rollback()
            return {"success": False, "message": f"系統錯誤: {str(e)}"}
    
    @staticmethod
    def unassign_resource(resource_id):
        """取消分配：將狀態重置為 Available 並清空客戶資訊"""
        resource = SimResource.query.get_or_404(resource_id)
        
        if resource.status == 'Available':
            return resource
            
        resource.status = 'Available'
        resource.customer = None
        resource.assigned_date = None
        
        db.session.commit()
        return resource
    
    @staticmethod
    def delete_batch_resources(resource_ids):
        """批量刪除資源"""
        try:
            if not resource_ids:
                return {"success": False, "message": "未選擇任何資源"}
            
            # 使用 SQLAlchemy 的 in_ 操作符進行批量刪除
            # synchronize_session=False 對於批量刪除更高效
            deleted_count = SimResource.query.filter(SimResource.id.in_(resource_ids)).delete(synchronize_session=False)
            db.session.commit()
            
            return {
                "success": True, 
                "message": f"成功刪除 {deleted_count} 個資源"
            }
        except Exception as e:
            db.session.rollback()
            return {"success": False, "message": f"刪除失敗: {str(e)}"}
        
    @staticmethod
    def _get_batch_targets(scope, ids=None, start_imsi=None, end_imsi=None):
        """批量操作輔助方法：獲取目標資源查詢對象"""
        if scope == 'selected':
            if not ids:
                return None, "未選擇任何項目"
            return SimResource.query.filter(SimResource.id.in_(ids)), None
            
        elif scope == 'range':
            if not start_imsi or not end_imsi:
                return None, "請輸入起始和結束 IMSI"
            
            # 初步使用字串比較過濾 (利用 SQL 索引)
            query = SimResource.query.filter(
                SimResource.imsi >= start_imsi,
                SimResource.imsi <= end_imsi
            )
            return query, None
            
        return None, "無效的操作範圍"

    @staticmethod
    def batch_update_resources(scope, ids, start_imsi, end_imsi, update_data):
        """批量更新資源 (Provider, CardType, ResourcesType, Batch, ReceivedDate)"""
        try:
            query, error = SimResourceManager._get_batch_targets(scope, ids, start_imsi, end_imsi)
            if error: return {"success": False, "message": error}
            
            resources = query.all()
            target_ids = []
            
            # 如果是範圍模式，進行二次嚴格數字驗證
            if scope == 'range':
                if not start_imsi.isdigit() or not end_imsi.isdigit():
                    return {"success": False, "message": "IMSI 必須為純數字"}
                    
                s_int, e_int = int(start_imsi), int(end_imsi)
                for res in resources:
                    if res.imsi and res.imsi.isdigit():
                        imsi_int = int(res.imsi)
                        if s_int <= imsi_int <= e_int:
                            target_ids.append(res.id)
            else:
                target_ids = [r.id for r in resources]
            
            if not target_ids:
                return {"success": False, "message": "未找到符合條件的資源"}

            # 構建更新字典，過濾掉空值
            fields_to_update = {}
            allowed_fields = {
                'Provider': 'supplier',
                'CardType': 'type',
                'ResourcesType': 'resources_type',
                'Batch': 'batch',
                'ReceivedDate': 'received_date',
                'Remark': 'remark'
            }
            
            for key, db_col in allowed_fields.items():
                if update_data.get(key):
                    fields_to_update[db_col] = update_data[key].strip()
            
            if not fields_to_update:
                return {"success": False, "message": "未輸入任何需要更新的欄位"}

            # 批量更新
            updated_count = SimResource.query.filter(SimResource.id.in_(target_ids)).update(fields_to_update, synchronize_session=False)
            db.session.commit()
            
            return {"success": True, "message": f"成功更新 {updated_count} 筆資源"}

        except Exception as e:
            db.session.rollback()
            return {"success": False, "message": f"更新失敗: {str(e)}"}

    @staticmethod
    def batch_delete_resources(scope, ids, start_imsi, end_imsi):
        """批量刪除資源"""
        try:
            query, error = SimResourceManager._get_batch_targets(scope, ids, start_imsi, end_imsi)
            if error: return {"success": False, "message": error}
            
            # 確定要刪除的 ID 列表
            target_ids = []
            
            if scope == 'range':
                if not start_imsi.isdigit() or not end_imsi.isdigit():
                    return {"success": False, "message": "IMSI 必須為純數字"}
                
                s_int = int(start_imsi)
                e_int = int(end_imsi)
                
                if s_int > e_int:
                    return {"success": False, "message": "起始 IMSI 不能大於結束 IMSI"}
                
                # 計算該段落應有的總數量
                expected_count = e_int - s_int + 1
                
                # 為了安全，設置一個上限（例如一次最多刪除 10000 條，防止誤操作過大範圍）
                if expected_count > 10000:
                    return {"success": False, "message": f"單次操作範圍過大 ({expected_count} 條)，請縮小範圍 (上限 10000)"}

                # 獲取初步篩選的資源 (String 比較)
                resources = query.all()
                
                # 在 Python 中進行嚴格的數字過濾，並統計實際存在的唯一 IMSI
                found_imsis = set()
                target_ids = []
                
                for res in resources:
                    if res.imsi and res.imsi.isdigit():
                        imsi_int = int(res.imsi)
                        # 嚴格確認在數字範圍內
                        if s_int <= imsi_int <= e_int:
                            target_ids.append(res.id)
                            found_imsis.add(imsi_int)
                
                # 核心檢查邏輯：實際找到的唯一 IMSI 數量必須等於範圍長度
                if len(found_imsis) < expected_count:
                    missing_count = expected_count - len(found_imsis)
                    return {
                        "success": False, 
                        "message": f"驗證失敗：無法執行刪除。\n\n您選擇的段落 ({start_imsi} - {end_imsi}) 共有 {expected_count} 個號碼，但數據庫中只找到了 {len(found_imsis)} 個。\n\n缺失 {missing_count} 個號碼。請確保該段落內的所有 IMSI 都存在。"
                    }
                    
            else:
                # 'selected' 模式 (按勾選項目)
                resources = query.all()
                target_ids = [r.id for r in resources]

            if not target_ids:
                return {"success": False, "message": "未找到符合條件的資源"}
            
            # 執行刪除
            deleted_count = SimResource.query.filter(SimResource.id.in_(target_ids)).delete(synchronize_session=False)
            db.session.commit()
            
            return {"success": True, "message": f"成功刪除 {deleted_count} 筆資源"}
            
        except Exception as e:
            db.session.rollback()
            return {"success": False, "message": f"刪除失敗: {str(e)}"}     
        
    @staticmethod
    def get_inventory_stats():
        """獲取庫存統計數據 (統計 Available 狀態，並包含 0 庫存的 Batch)"""
        
        # 1. 獲取所有已知的分類組合 (Provider, CardType, ResourcesType)
        all_combinations = db.session.query(
            SimResource.supplier,
            SimResource.type,
            SimResource.resources_type
        ).distinct().all()
        
        # 初始化數據結構
        inventory_data = {}
        for supplier, card_type, res_type in all_combinations:
            if not supplier: supplier = "Unknown"
            if not res_type: res_type = "N/A" 
            
            if supplier not in inventory_data:
                inventory_data[supplier] = {}
            if card_type not in inventory_data[supplier]:
                inventory_data[supplier][card_type] = {}
            
            # 初始化 total 為 0，batches 為空列表
            inventory_data[supplier][card_type][res_type] = {
                'total': 0,
                'batches': []
            }

        # 2. [修改] 查詢邏輯：不使用 filter 過濾 Available，而是用 sum+case 統計
        inventory_counts = db.session.query(
            SimResource.supplier,
            SimResource.type,
            SimResource.resources_type,
            SimResource.batch,
            SimResource.received_date,
            func.sum(case((SimResource.status == 'Available', 1), else_=0)) # 統計 Available 的數量
        ).group_by(
            SimResource.supplier, 
            SimResource.type, 
            SimResource.resources_type,
            SimResource.batch,
            SimResource.received_date
        ).order_by(
            SimResource.received_date.asc(), # [修改] 從小到大 (舊到新)
            SimResource.batch.asc()          # [修改] 從小到大
        ).all()
        
        # 3. 填入實際數量和 Batch 細節
        for supplier, card_type, res_type, batch, rec_date, count in inventory_counts:
            if not supplier: supplier = "Unknown"
            if not res_type: res_type = "N/A"
            if not batch: batch = "Unknown"
            if not rec_date: rec_date = "-"
            
            # 轉換 count 為 int (sum 可能返回 Decimal 或 None)
            count = int(count) if count is not None else 0
            
            # 確保鍵存在
            if supplier not in inventory_data: inventory_data[supplier] = {}
            if card_type not in inventory_data[supplier]: inventory_data[supplier][card_type] = {}
            if res_type not in inventory_data[supplier][card_type]:
                inventory_data[supplier][card_type][res_type] = {'total': 0, 'batches': []}
            
            # 累加總數
            inventory_data[supplier][card_type][res_type]['total'] += count
            
            # 添加 Batch 細節 (現在即使 count 為 0 也會被加入)
            inventory_data[supplier][card_type][res_type]['batches'].append({
                'batch': batch,
                'received_date': rec_date,
                'count': count
            })
            
        # 4. 排序：Supplier -> CardType -> ResourcesType
        sorted_data = {}
        for supplier in sorted(inventory_data.keys()):
            sorted_data[supplier] = {}
            for card_type in sorted(inventory_data[supplier].keys()):
                sorted_data[supplier][card_type] = dict(sorted(inventory_data[supplier][card_type].items()))
                
        return sorted_data