from datetime import datetime
import pandas as pd
import re
import math
from sqlalchemy import asc, desc, func, case, text, or_, and_
from sqlalchemy.sql.expression import cast
from models.sim_resource import SimResource, db
from .config_manager import SimConfigManager

class PaginationResult:
    def __init__(self, items, page, per_page, total, total_records=None):
        self.items = items
        self.page = page
        self.per_page = per_page
        self.total = total
        self.total_records = total_records if total_records is not None else total
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
    
    @staticmethod
    def get_all_resources(query_params, page=1, per_page=50):
        query = SimResource.query
        query = SimResourceManager._apply_search_filters(query, query_params)
        query = SimResourceManager._apply_sorting(query, query_params)
        return query.paginate(page=page, per_page=per_page, error_out=False)

    @staticmethod
    def get_grouped_resources(query_params, page=1, per_page=50):
        # 1. 基礎過濾
        base_query = SimResource.query
        base_query = SimResourceManager._apply_attribute_filters(base_query, query_params)
        
        group_cols = [
            SimResource.supplier, SimResource.type, SimResource.resources_type,
            SimResource.batch, SimResource.status, SimResource.customer,
            SimResource.assigned_date, SimResource.remark
        ]
        
        order_col = case((SimResource.imsi_num != None, SimResource.imsi_num), else_=cast(SimResource.imsi, db.Numeric))
        diff_val = order_col - func.row_number().over(order_by=order_col)

        subquery = base_query.with_entities(
            SimResource.id, *group_cols, 
            SimResource.imsi, SimResource.imsi_num, 
            SimResource.iccid, SimResource.iccid_num, 
            SimResource.msisdn, SimResource.msisdn_num, 
            SimResource.created_at, SimResource.updated_at,
            diff_val.label('imsi_grp')
        ).subquery()
        
        group_by_args = [getattr(subquery.c, col.name) for col in group_cols] + [subquery.c.imsi_grp]
        
        # 2. 構建聚合查詢
        query = db.session.query(
            func.min(subquery.c.id).label('id'),
            *[getattr(subquery.c, col.name) for col in group_cols],
            func.count().label('count'),
            func.min(subquery.c.imsi).label('start_imsi'), func.max(subquery.c.imsi).label('end_imsi'),
            func.min(subquery.c.iccid).label('start_iccid'), func.max(subquery.c.iccid).label('end_iccid'),
            func.min(subquery.c.msisdn).label('start_msisdn'), func.max(subquery.c.msisdn).label('end_msisdn'),
            func.max(subquery.c.created_at).label('created_at'), func.max(subquery.c.updated_at).label('updated_at'),
            func.min(subquery.c.imsi_num).label('min_imsi_num'), func.max(subquery.c.imsi_num).label('max_imsi_num'),
            func.min(subquery.c.iccid_num).label('min_iccid_num'), func.max(subquery.c.iccid_num).label('max_iccid_num'),
            func.min(subquery.c.msisdn_num).label('min_msisdn_num'), func.max(subquery.c.msisdn_num).label('max_msisdn_num')
        ).group_by(*group_by_args)
        
        # 3. 應用範圍過濾 (HAVING)
        def apply_range_filter(q, col_min_num, col_max_num, search_val):
            if not search_val: return q
            val = search_val.strip()
            
            # 批量搜索支持 (Batch Search in Range Mode)
            # 邏輯：如果段落範圍 (Min ~ Max) 包含列表中的任意一個數字，則顯示該段落
            if ',' in val or ' ' in val or '\n' in val:
                # 1. 提取所有有效數字
                nums = [int(x) for x in re.split(r'[,\s\n]+', val) if x.strip().isdigit()]
                
                if nums:
                    # 2. 構建 OR 條件: (Min <= v1 <= Max) OR (Min <= v2 <= Max) ...
                    # 這會檢查段落是否包含這些特定的號碼
                    conditions = []
                    for v in nums:
                        conditions.append((col_min_num <= v) & (col_max_num >= v))
                    
                    if conditions:
                        return q.having(or_(*conditions))
            
            # 範圍搜索 (Start - End)
            # 邏輯：兩個範圍是否有重疊 (Overlap)
            if '-' in val:
                try:
                    parts = val.split('-')
                    if len(parts) == 2 and parts[0].strip().isdigit() and parts[1].strip().isdigit():
                        s, e = int(parts[0].strip()), int(parts[1].strip())
                        return q.having((col_max_num >= s) & (col_min_num <= e))
                except: pass
            
            # 單個值搜索
            # 邏輯：值是否在範圍內
            if val.isdigit():
                v = int(val)
                return q.having((col_min_num <= v) & (col_max_num >= v))
            
            # 模糊搜索 (僅作為最後手段，對聚合後的字符串進行匹配，性能較差)
            # 注意：這裡無法對數字列做 ilike，如果前面都沒命中，這裡通常不會執行或無效
            return q

        has_range_filter = False
        if query_params.get('imsi'):
            query = apply_range_filter(query, func.min(subquery.c.imsi_num), func.max(subquery.c.imsi_num), query_params.get('imsi'))
            has_range_filter = True
        if query_params.get('iccid'):
            query = apply_range_filter(query, func.min(subquery.c.iccid_num), func.max(subquery.c.iccid_num), query_params.get('iccid'))
            has_range_filter = True
        if query_params.get('msisdn'):
            query = apply_range_filter(query, func.min(subquery.c.msisdn_num), func.max(subquery.c.msisdn_num), query_params.get('msisdn'))
            has_range_filter = True
        
        query = query.order_by(desc('assigned_date').nullslast(), desc('updated_at').nullslast(), asc('start_imsi'))
        
        total_groups = query.count()
        
        if not has_range_filter:
            total_records = base_query.count()
        else:
            count_subquery = query.subquery()
            total_records = db.session.query(func.sum(count_subquery.c.count)).scalar() or 0

        items = query.limit(per_page).offset((page - 1) * per_page).all()
        return PaginationResult(items, page, per_page, total_groups, total_records)
    
    @staticmethod
    def _apply_search_filters(query, params):
        query = SimResourceManager._apply_attribute_filters(query, params)
        query = SimResourceManager._apply_id_filters(query, params)
        return query

    @staticmethod
    def _apply_attribute_filters(query, params):
        for field in ['provider', 'card_type', 'resources_type', 'status', 'customer', 'received_date']:
            if params.get(field): 
                db_field = 'supplier' if field == 'provider' else 'type' if field == 'card_type' else field
                query = query.filter(getattr(SimResource, db_field) == params[field])
        
        if params.get('batch'): query = query.filter(SimResource.batch.ilike(f'%{params["batch"]}%'))
        if params.get('remark'): query = query.filter(SimResource.remark.ilike(f'%{params["remark"]}%'))
        
        s_date, e_date = params.get('assigned_date_start'), params.get('assigned_date_end')
        if s_date: query = query.filter(SimResource.assigned_date >= s_date)
        if e_date: query = query.filter(SimResource.assigned_date <= e_date)
        return query

    @staticmethod
    def _apply_id_filters(query, params):
        # [Optimize] 批量搜索與數字索引優化
        def filter_id(q, num_col, str_col, value):
            if not value: return q
            val = value.strip()
            
            # 1. [Feature] 批量搜索 (Batch Search)
            # 檢查是否包含分隔符 (逗號、空格、換行)
            if ',' in val or ' ' in val or '\n' in val:
                # 使用正則分割，過濾掉空字符串
                raw_items = [x.strip() for x in re.split(r'[,\s\n]+', val) if x.strip()]
                
                if raw_items:
                    # 嘗試將所有項目轉為數字 (用於數字索引查詢)
                    # 注意：如果用戶混合輸入數字和非數字，只提取數字部分用於 num_col 查詢
                    num_items = [int(x) for x in raw_items if x.isdigit()]
                    
                    if num_col is not None and len(num_items) > 0:
                        # 優先使用數字列 IN 查詢 (極快)
                        # 如果輸入的全部是數字，直接走這條路
                        if len(num_items) == len(raw_items):
                            return q.filter(num_col.in_(num_items))
                    
                    # 如果包含非數字或無數字列，退回字符串 IN 查詢
                    return q.filter(str_col.in_(raw_items))

            # 2. 範圍搜索
            if '-' in val: 
                try:
                    parts = val.split('-')
                    if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                        if num_col is not None:
                            return q.filter(num_col >= int(parts[0]), num_col <= int(parts[1]))
                        return q.filter(str_col >= parts[0], str_col <= parts[1])
                except: pass
            
            # 3. 精確數字搜索
            if val.isdigit() and len(val) > 5 and num_col is not None: 
                return q.filter(num_col == int(val))
            
            # 4. 模糊搜索 (Fallback)
            return q.filter(str_col.ilike(f'%{val}%'))

        query = filter_id(query, SimResource.imsi_num, SimResource.imsi, params.get('imsi'))
        
        # 安全獲取 iccid_num/msisdn_num，兼容舊 DB 結構
        query = filter_id(query, getattr(SimResource, 'iccid_num', None), SimResource.iccid, params.get('iccid'))
        query = filter_id(query, getattr(SimResource, 'msisdn_num', None), SimResource.msisdn, params.get('msisdn'))
        return query

    @staticmethod
    def _apply_sorting(query, params):
        sort_field = params.get('sort', 'updated_at')
        sort_order = params.get('order', 'desc')
        
        col_attr = None
        if sort_field == 'imsi': col_attr = SimResource.imsi_num
        elif sort_field == 'iccid' and hasattr(SimResource, 'iccid_num'): col_attr = SimResource.iccid_num
        elif sort_field == 'msisdn' and hasattr(SimResource, 'msisdn_num'): col_attr = SimResource.msisdn_num
        elif hasattr(SimResource, sort_field): col_attr = getattr(SimResource, sort_field)
        else: col_attr = SimResource.updated_at

        primary_sort = asc(col_attr).nullslast() if sort_order == 'asc' else desc(col_attr).nullslast()
        return query.order_by(primary_sort, asc(SimResource.imsi_num))

    @staticmethod
    def get_options():
        try:
            config = SimConfigManager.load_config()
            existing_customers = db.session.query(SimResource.customer).distinct().all()
            existing_batches = db.session.query(SimResource.batch).distinct().all()
            existing_dates = db.session.query(SimResource.received_date).distinct().all()
            existing_assigned_dates = db.session.query(SimResource.assigned_date).distinct().all()
            
            def natural_keys(text):
                return [int(c) if c.isdigit() else c for c in re.split(r'(\d+)', str(text))]

            customers_list = sorted([c[0] for c in existing_customers if c[0] and c[0].strip()])
            raw_batches = [b[0] for b in existing_batches if b[0] and b[0].strip()]
            batches_list = sorted(raw_batches, key=natural_keys)
            dates_list = sorted([d[0] for d in existing_dates if d[0] and d[0].strip()], reverse=True)
            assigned_dates_list = sorted([d[0] for d in existing_assigned_dates if d[0] and d[0].strip()], reverse=True)
            
            return {
                'providers': config.get('providers', []), 
                'card_types': config.get('card_types', []), 
                'resources_types': config.get('resources_types', []), 
                'provider_mapping': config.get('provider_mapping', {}),
                'customers': customers_list,
                'batches': batches_list,
                'received_dates': dates_list,
                'assigned_dates': assigned_dates_list,
                'low_stock_threshold': config.get('low_stock_threshold', 1000)
            }
        except Exception as e:
            print(f"Error getting options: {e}")
            return {
                'providers': [], 'card_types': [], 'resources_types': [],
                'customers': [], 'batches': [], 'received_dates': [], 'assigned_dates': []
            }
    
    @staticmethod
    def get_distinct_filters(params, extra_filters=None):
        base_query = SimResource.query
        # 這裡調用 _apply_search_filters，如果該方法未定義或報錯，就會導致 Load Failed
        base_query = SimResourceManager._apply_search_filters(base_query, params)
        
        customers = base_query.with_entities(SimResource.customer).filter(SimResource.customer != None, SimResource.customer != '').distinct().order_by(SimResource.customer).all()
        
        date_query = base_query
        if extra_filters and extra_filters.get('customer') and extra_filters['customer'] != 'ALL':
            date_query = date_query.filter(SimResource.customer == extra_filters['customer'])
            
        dates = date_query.with_entities(SimResource.assigned_date).filter(SimResource.assigned_date != None, SimResource.assigned_date != '').distinct().order_by(SimResource.assigned_date.desc()).all()
        
        return {'customers': [c[0] for c in customers], 'assigned_dates': [d[0] for d in dates]}
    
    # 導出邏輯 - 使用 _get_batch_targets 處理字典
    @staticmethod
    def get_resources_for_export(scope, selected_ids=None, search_params=None, extra_filters=None):
        query = SimResource.query
        
        if scope == 'selected' and selected_ids:
            # 這裡調用 _get_batch_targets 來解析混合了 ID 和 Range Object 的列表
            q, err = SimResourceManager._get_batch_targets('selected', selected_ids)
            if not err:
                query = q
            else:
                return [] # 選擇無效
        
        elif scope == 'search' and search_params:
            query = SimResourceManager._apply_search_filters(query, search_params)
            query = SimResourceManager._apply_sorting(query, search_params)
        
        if extra_filters:
            if extra_filters.get('customer') and extra_filters['customer'] != 'ALL':
                query = query.filter(SimResource.customer == extra_filters['customer'])
            if extra_filters.get('assigned_date') and extra_filters['assigned_date'] != 'ALL':
                query = query.filter(SimResource.assigned_date == extra_filters['assigned_date'])
                
        return query.all()

    @staticmethod
    def validate_resource_data(data, is_edit=False, resource_id=None):
        errors = []
        required_fields = ['Provider', 'CardType', 'Batch', 'ReceivedDate', 'IMSI', 'ICCID', 'MSISDN']
        for field in required_fields:
            if not data.get(field) or str(data[field]).strip() == '':
                errors.append(f"{field} 必填")
        
        card_type = data.get('CardType', '')
        if card_type == 'Soft Profile':
            if not data.get('Ki', '').strip(): errors.append("Soft Profile 必須還填寫 Ki")
            if not data.get('OPC', '').strip(): errors.append("Soft Profile 必須還填寫 OPC")
        elif card_type == 'eSIM':
            if not data.get('LPA', '').strip(): errors.append("eSIM 必須還填寫 LPA")
        
        if not is_edit:
            if data.get('IMSI'):
                existing = SimResource.query.filter_by(imsi=data['IMSI'].strip()).first()
                if existing: errors.append("IMSI 已存在")
            if data.get('ICCID'):
                existing = SimResource.query.filter_by(iccid=data['ICCID'].strip()).first()
                if existing: errors.append("ICCID 已存在")
        else:
            if data.get('IMSI'):
                existing = SimResource.query.filter(SimResource.imsi == data['IMSI'].strip(), SimResource.id != resource_id).first()
                if existing: errors.append("IMSI 已存在")
            if data.get('ICCID'):
                existing = SimResource.query.filter(SimResource.iccid == data['ICCID'].strip(), SimResource.id != resource_id).first()
                if existing: errors.append("ICCID 已存在")
        return errors
    
    @staticmethod
    def create_resource(data):
        # 這裡需要確保傳入的數據能正確轉換為 num
        imsi = data['IMSI'].strip()
        iccid = data['ICCID'].strip()
        msisdn = data['MSISDN'].strip()
        
        imsi_num = int(imsi) if imsi.isdigit() else None
        msisdn_num = int(msisdn) if msisdn.isdigit() else None
        iccid_num = int(iccid) if iccid.isdigit() else None

        customer = data.get('Customer', '').strip() or None
        status = 'Assigned' if customer else 'Available'
        
        resource = SimResource(
            type=data['CardType'].strip(),
            supplier=data['Provider'].strip(),
            resources_type=data['ResourcesType'].strip(),
            batch=data['Batch'].strip(),
            received_date=data['ReceivedDate'].strip(),
            imsi=imsi,
            imsi_num=imsi_num,
            iccid=iccid,
            iccid_num=iccid_num,
            msisdn=msisdn,
            msisdn_num=msisdn_num,
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
        resource = SimResource.query.get_or_404(resource_id)
        # ... 基礎欄位更新 ...
        resource.type = data['CardType'].strip()
        resource.supplier = data['Provider'].strip()
        resource.resources_type = data['ResourcesType'].strip()
        resource.batch = data['Batch'].strip()
        resource.received_date = data['ReceivedDate'].strip()
        
        # 更新並同步 num
        resource.imsi = data['IMSI'].strip()
        resource.imsi_num = int(resource.imsi) if resource.imsi.isdigit() else None
        
        resource.iccid = data['ICCID'].strip()
        resource.iccid_num = int(resource.iccid) if resource.iccid.isdigit() else None
        
        resource.msisdn = data['MSISDN'].strip()
        resource.msisdn_num = int(resource.msisdn) if resource.msisdn.isdigit() else None
        
        resource.ki = data.get('Ki', '').strip() or None
        resource.opc = data.get('OPC', '').strip() or None
        resource.lpa = data.get('LPA', '').strip() or None
        resource.pin1 = data.get('PIN1', '').strip() or None
        resource.puk1 = data.get('PUK1', '').strip() or None
        resource.pin2 = data.get('PIN2', '').strip() or None
        resource.puk2 = data.get('PUK2', '').strip() or None
        
        if 'Customer' in data: 
            resource.customer = data.get('Customer', '').strip() or None
        if 'Assign Date' in data:
            resource.assigned_date = data.get('Assign Date', '').strip() or None   
        if 'Remark' in data:
            resource.remark = data.get('Remark', '').strip() or None     
            
        db.session.commit()
        return resource
    
    @staticmethod
    def get_inventory_stats():
        all_combinations = db.session.query(
            SimResource.supplier,
            SimResource.type,
            SimResource.resources_type
        ).distinct().all()
        
        inventory_data = {}
        for supplier, card_type, res_type in all_combinations:
            if not supplier: supplier = "Unknown"
            if not res_type: res_type = "N/A" 
            if supplier not in inventory_data:
                inventory_data[supplier] = {}
            if card_type not in inventory_data[supplier]:
                inventory_data[supplier][card_type] = {}
            inventory_data[supplier][card_type][res_type] = {'total': 0, 'batches': []}

        inventory_counts = db.session.query(
            SimResource.supplier,
            SimResource.type,
            SimResource.resources_type,
            SimResource.batch,
            SimResource.received_date,
            func.sum(case((SimResource.status == 'Available', 1), else_=0)) 
        ).group_by(
            SimResource.supplier, 
            SimResource.type, 
            SimResource.resources_type,
            SimResource.batch,
            SimResource.received_date
        ).order_by(
            SimResource.received_date.asc(), 
            SimResource.batch.asc()          
        ).all()
        
        for supplier, card_type, res_type, batch, rec_date, count in inventory_counts:
            if not supplier: supplier = "Unknown"
            if not res_type: res_type = "N/A"
            if not batch: batch = "Unknown"
            if not rec_date: rec_date = "-"
            count = int(count) if count is not None else 0
            
            if supplier not in inventory_data: inventory_data[supplier] = {}
            if card_type not in inventory_data[supplier]: inventory_data[supplier][card_type] = {}
            if res_type not in inventory_data[supplier][card_type]:
                inventory_data[supplier][card_type][res_type] = {'total': 0, 'batches': []}
            
            inventory_data[supplier][card_type][res_type]['total'] += count
            inventory_data[supplier][card_type][res_type]['batches'].append({
                'batch': batch,
                'received_date': rec_date,
                'count': count
            })
            
        sorted_data = {}
        for supplier in sorted(inventory_data.keys()):
            sorted_data[supplier] = {}
            for card_type in sorted(inventory_data[supplier].keys()):
                sorted_data[supplier][card_type] = dict(sorted(inventory_data[supplier][card_type].items()))
        return sorted_data

    @staticmethod
    def calculate_assignment_options(provider, card_type, resources_type, quantity):
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
        fifo_plan = []
        remaining_qty = quantity
        for batch, r_date, count in batch_stats:
            if remaining_qty <= 0: break
            take = min(remaining_qty, count)
            fifo_plan.append({"batch": batch, "received_date": r_date, "take": take, "available": count})
            remaining_qty -= take
        options.append({"id": "fifo", "name": "方案 A (FIFO): 優先使用最早批次", "batches": fifo_plan})

        single_batch_plan = None
        for batch, r_date, count in batch_stats:
            if count >= quantity:
                single_batch_plan = [{"batch": batch, "received_date": r_date, "take": quantity, "available": count}]
                break
        
        if single_batch_plan:
            is_different = True
            if len(fifo_plan) == 1 and fifo_plan[0]['batch'] == single_batch_plan[0]['batch']:
                is_different = False
            if is_different:
                options.append({"id": "single", "name": f"方案 B (單一批次): 直接使用 {single_batch_plan[0]['batch']}", "batches": single_batch_plan})

        return {"success": True, "options": options, "total_available": total_available}

    @staticmethod
    def confirm_assignment(plan, customer, assigned_date, provider, card_type, resources_type, remark=None):
        total_assigned = 0
        assigned_ranges = []
        try:
            for item in plan:
                batch_name = item['batch']
                take_qty = item['take']
                
                # [Feature] 並發控制 (Race Condition Handling)
                # 使用 with_for_update(skip_locked=True)
                # 作用：鎖定選中的行，如果有其他事務已經鎖定了某些行，直接跳過這些行選取下一批。
                # 這能保證在高並發下，多個請求不會互相阻塞，也不會選到同一張卡。
                resources_to_update = SimResource.query.filter(
                    SimResource.batch == batch_name,
                    SimResource.status == 'Available',
                    SimResource.supplier == provider,
                    SimResource.type == card_type,
                    SimResource.resources_type == resources_type
                ).order_by(SimResource.imsi_num.asc())\
                 .with_for_update(skip_locked=True)\
                 .limit(take_qty).all()
                
                # 再次檢查數量 (因為 skip_locked 可能導致獲取到的數量少於預期)
                if len(resources_to_update) < take_qty:
                    raise Exception(f"批次 {batch_name} 庫存不足或正被其他用戶操作 (請求: {take_qty}, 實際鎖定: {len(resources_to_update)})")
                
                first_imsi = resources_to_update[0].imsi
                last_imsi = resources_to_update[-1].imsi
                
                for res in resources_to_update:
                    res.status = 'Assigned'
                    res.customer = customer
                    res.assigned_date = assigned_date
                    if remark is not None and str(remark).strip():
                        res.remark = str(remark).strip()
                
                total_assigned += len(resources_to_update)
                assigned_ranges.append(f"{batch_name}: {first_imsi} ~ {last_imsi} ({len(resources_to_update)} pcs)")

            db.session.commit()
            return {"success": True, "message": f"成功分配 {total_assigned} 張 SIM 卡", "details": assigned_ranges}
        except Exception as e:
            db.session.rollback()
            return {"success": False, "message": str(e)}

    @staticmethod
    def manual_assignment(scope, ids, start_imsi, end_imsi, customer, assigned_date, remark=None):
        try:
            # 獲取目標 (支援新的 Range Object 格式)
            query, error = SimResourceManager._get_batch_targets(scope, ids, start_imsi, end_imsi)
            if error: return {"success": False, "message": error}
            
            # 直接執行更新，避免先查詢再循環更新，提升性能
            update_values = {
                SimResource.status: 'Assigned',
                SimResource.customer: customer,
                SimResource.assigned_date: assigned_date
            }
            if remark is not None and str(remark).strip():
                update_values[SimResource.remark] = str(remark).strip()
                
            updated_count = query.update(update_values, synchronize_session=False)
            
            db.session.commit()
            return {"success": True, "message": f"成功分配 {updated_count} 張卡"}
        except Exception as e:
            db.session.rollback()
            return {"success": False, "message": f"系統錯誤: {str(e)}"}

    @staticmethod
    def batch_cancel_assignment(scope, ids, start_imsi, end_imsi, remark=None):
        try:
            query, error = SimResourceManager._get_batch_targets(scope, ids, start_imsi, end_imsi)
            if error: return {"success": False, "message": error}
            
            # 僅更新狀態為 Assigned 的
            query = query.filter(SimResource.status == 'Assigned')
            
            update_values = {
                SimResource.status: 'Available',
                SimResource.customer: None,
                SimResource.assigned_date: None
            }
            if remark is not None and str(remark).strip():
                update_values[SimResource.remark] = str(remark).strip()
                
            changed_count = query.update(update_values, synchronize_session=False)
            
            if changed_count == 0: return {"success": False, "message": "選定範圍內沒有 'Assigned' 狀態的資源，無需取消。"}

            db.session.commit()
            return {"success": True, "message": f"成功取消分配 {changed_count} 張卡"}
        except Exception as e:
            db.session.rollback()
            return {"success": False, "message": f"系統錯誤: {str(e)}"}
    
    # 分離 ID 列表和 Range 對象列表，防止 "can't adapt type 'dict'" 錯誤
    @staticmethod
    def _get_batch_targets(scope, ids=None, start_imsi=None, end_imsi=None):
        if scope == 'selected':
            if not ids: return None, "未選擇項目"
            
            range_conds = []
            simple_ids = []
            
            for item in ids:
                if isinstance(item, dict):
                    # 處理 Range Object {'start':..., 'end':..., 'batch':...}
                    s, e, batch = item.get('start'), item.get('end'), item.get('batch')
                    if s and e:
                        if str(s).isdigit() and str(e).isdigit():
                            range_conds.append(and_(
                                SimResource.imsi_num >= int(s), 
                                SimResource.imsi_num <= int(e),
                                SimResource.batch == batch
                            ))
                        else:
                            range_conds.append(and_(
                                SimResource.imsi >= s, 
                                SimResource.imsi <= e,
                                SimResource.batch == batch
                            ))
                else:
                    # 處理普通 ID
                    simple_ids.append(item)
            
            # 組合條件
            final_conds = []
            if range_conds: final_conds.extend(range_conds)
            if simple_ids: final_conds.append(SimResource.id.in_(simple_ids))
            
            if not final_conds: return None, "無效選擇"
            return SimResource.query.filter(or_(*final_conds)), None
            
        elif scope == 'range':
            # 手動輸入範圍
            if not start_imsi or not end_imsi: return None, "請輸入範圍"
            if str(start_imsi).isdigit() and str(end_imsi).isdigit():
                return SimResource.query.filter(SimResource.imsi_num >= int(start_imsi), SimResource.imsi_num <= int(end_imsi)), None
            return SimResource.query.filter(SimResource.imsi >= start_imsi, SimResource.imsi <= end_imsi), None
            
        return None, "未知範圍類型"

    @staticmethod
    def batch_update_resources(scope, ids, start_imsi, end_imsi, update_data):
        try:
            query, error = SimResourceManager._get_batch_targets(scope, ids, start_imsi, end_imsi)
            if error: return {"success": False, "message": error}
            
            fields_to_update = {}
            allowed_fields = {'Provider': 'supplier', 'CardType': 'type', 'ResourcesType': 'resources_type', 'Batch': 'batch', 'ReceivedDate': 'received_date', 'Remark': 'remark'}
            
            for key, db_col in allowed_fields.items():
                if update_data.get(key): fields_to_update[db_col] = update_data[key].strip()
            
            if not fields_to_update: return {"success": False, "message": "未輸入任何需要更新的欄位"}

            updated_count = query.update(fields_to_update, synchronize_session=False)
            db.session.commit()
            return {"success": True, "message": f"成功更新 {updated_count} 筆資源"}
        except Exception as e:
            db.session.rollback()
            return {"success": False, "message": f"更新失敗: {str(e)}"}

    @staticmethod
    def batch_delete_resources(scope, ids, start_imsi, end_imsi):
        try:
            query, error = SimResourceManager._get_batch_targets(scope, ids, start_imsi, end_imsi)
            if error: return {"success": False, "message": error}
            
            # 對於 range 刪除，做一個安全檢查，防止誤刪太多
            if scope == 'range':
                 if not start_imsi.isdigit() or not end_imsi.isdigit(): return {"success": False, "message": "IMSI 必須為純數字"}
                 s_int, e_int = int(start_imsi), int(end_imsi)
                 expected_count = e_int - s_int + 1
                 if expected_count > 10000: return {"success": False, "message": f"單次操作範圍過大，上限 10000"}

            deleted_count = query.delete(synchronize_session=False)
            db.session.commit()
            return {"success": True, "message": f"成功刪除 {deleted_count} 筆資源"}
        except Exception as e:
            db.session.rollback()
            return {"success": False, "message": f"刪除失敗: {str(e)}"}