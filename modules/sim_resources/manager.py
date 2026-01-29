from datetime import datetime
import pandas as pd
import re
import math
from sqlalchemy import asc, desc, func, case, text, or_, and_
from sqlalchemy.sql.expression import cast
from models.sim_resource import SimResource, db
from .config_manager import SimConfigManager

class PaginationResult:
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
    
    @staticmethod
    def get_all_resources(query_params, page=1, per_page=50):
        """獲取SIM資源列表（單條模式）"""
        query = SimResource.query
        query = SimResourceManager._apply_attribute_filters(query, query_params)
        query = SimResourceManager._apply_id_filters(query, query_params)
        query = SimResourceManager._apply_sorting(query, query_params)
        return query.paginate(page=page, per_page=per_page, error_out=False)

    @staticmethod
    def get_grouped_resources(query_params, page=1, per_page=50):
        """獲取分組後的資源列表 (Range Mode 優化版)"""
        base_query = SimResource.query
        base_query = SimResourceManager._apply_attribute_filters(base_query, query_params)
        
        group_cols = [
            SimResource.supplier, SimResource.type, SimResource.resources_type,
            SimResource.batch, SimResource.status, SimResource.customer,
            SimResource.assigned_date, SimResource.remark
        ]
        
        # 優先使用 imsi_num 進行排序
        order_col = case((SimResource.imsi_num != None, SimResource.imsi_num), else_=cast(SimResource.imsi, db.Numeric))
        
        # Gaps-and-Islands 計算
        diff_val = order_col - func.row_number().over(order_by=order_col)

        subquery = base_query.with_entities(
            SimResource.id,
            *group_cols,
            SimResource.imsi,
            SimResource.imsi_num,
            SimResource.iccid,
            SimResource.iccid_num,  # 確保這兩個欄位在數據庫已存在
            SimResource.msisdn,
            SimResource.msisdn_num, # 確保這兩個欄位在數據庫已存在
            SimResource.created_at,
            SimResource.updated_at,
            diff_val.label('imsi_grp')
        ).subquery()
        
        group_by_args = [getattr(subquery.c, col.name) for col in group_cols] + [subquery.c.imsi_grp]
        
        # 聚合查詢
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
            
            # [Optimize Bug 2] 聚合數字欄位用於過濾
            func.min(subquery.c.iccid_num).label('min_iccid_num'),
            func.max(subquery.c.iccid_num).label('max_iccid_num'),
            func.min(subquery.c.msisdn_num).label('min_msisdn_num'),
            func.max(subquery.c.msisdn_num).label('max_msisdn_num')
        ).group_by(*group_by_args)
        
        # [Optimize Bug 2] 範圍重疊過濾器 (Range Overlap Filter)
        def apply_range_filter(q, col_min_num, col_max_num, search_val):
            if not search_val: return q
            val = search_val.strip()
            
            # 1. 範圍搜索 (Start - End)
            if '-' in val:
                try:
                    parts = val.split('-')
                    if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                        s, e = int(parts[0]), int(parts[1])
                        # 檢查兩個範圍是否有交集: max >= search_start AND min <= search_end
                        return q.having((col_max_num >= s) & (col_min_num <= e))
                except: pass
            
            # 2. 單個值搜索 (檢查是否包含在該段落內)
            if val.isdigit():
                # 兼容 20 位 ICCID (超出普通 Int 範圍，Python int 自動處理大數)
                v = int(val)
                # 檢查: min <= search_val <= max
                return q.having((col_min_num <= v) & (col_max_num >= v))
            
            # 3. 模糊搜索 (Fallback)
            # 注意：在 Range Mode 下，這裡只能對聚合結果過濾，可能不準確，建議用戶搜索數字
            return q 

        # 應用 IMSI 過濾
        if query_params.get('imsi'):
            imsi_min = func.min(subquery.c.imsi_num)
            imsi_max = func.max(subquery.c.imsi_num)
            query = apply_range_filter(query, imsi_min, imsi_max, query_params.get('imsi'))
            
        # [Fix Bug 2] 應用 ICCID 過濾 (使用新的 num 聚合)
        if query_params.get('iccid'):
            query = apply_range_filter(query, func.min(subquery.c.iccid_num), func.max(subquery.c.iccid_num), query_params.get('iccid'))

        # [Fix Bug 2] 應用 MSISDN 過濾 (使用新的 num 聚合)
        if query_params.get('msisdn'):
            query = apply_range_filter(query, func.min(subquery.c.msisdn_num), func.max(subquery.c.msisdn_num), query_params.get('msisdn'))
        
        query = query.order_by(desc('assigned_date').nullslast(), desc('updated_at').nullslast(), asc('start_imsi'))
        
        total_count = query.count()
        items = query.limit(per_page).offset((page - 1) * per_page).all()
        
        return PaginationResult(items, page, per_page, total_count)

    @staticmethod
    def _apply_attribute_filters(query, params):
        if params.get('provider'): query = query.filter(SimResource.supplier == params["provider"])
        if params.get('card_type'): query = query.filter(SimResource.type == params["card_type"])
        if params.get('resources_type'): query = query.filter(SimResource.resources_type == params["resources_type"])
        if params.get('status'): query = query.filter(SimResource.status == params['status'])
        if params.get('customer'): query = query.filter(SimResource.customer == params["customer"])
        if params.get('received_date'): query = query.filter(SimResource.received_date == params["received_date"])
        if params.get('batch'): query = query.filter(SimResource.batch.ilike(f'%{params["batch"]}%'))
        if params.get('remark'): query = query.filter(SimResource.remark.ilike(f'%{params["remark"]}%'))    
        start_date, end_date = params.get('assigned_date_start'), params.get('assigned_date_end')
        if start_date and end_date: query = query.filter(SimResource.assigned_date >= start_date, SimResource.assigned_date <= end_date)
        elif start_date: query = query.filter(SimResource.assigned_date >= start_date)
        elif end_date: query = query.filter(SimResource.assigned_date <= end_date)
        return query

    @staticmethod
    def _apply_id_filters(query, params):
        def apply_filter(q, field_num, field_str, value):
            if not value: return q
            val = value.strip()
            if '-' in val:
                try:
                    parts = val.split('-')
                    if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                        if field_num is not None:
                            return q.filter(field_num >= int(parts[0]), field_num <= int(parts[1]))
                        return q.filter(field_str >= parts[0], field_str <= parts[1])
                except: pass
            
            # 精確搜索 (長數字)
            if val.isdigit() and len(val) > 5:
                if field_num is not None:
                    # 使用數字欄位精確匹配，性能遠高於字符串匹配
                    return q.filter(field_num == int(val))
                return q.filter(field_str == val)
            
            return q.filter(field_str.ilike(f'%{val}%'))

        query = apply_filter(query, SimResource.imsi_num, SimResource.imsi, params.get('imsi'))
        # [Optimize] 這裡假設 SimResource 已經有了 iccid_num 和 msisdn_num 屬性
        # 如果用戶還沒更新 models.py 並重啟，這裡會報錯，導致 'Load Failed'
        if hasattr(SimResource, 'iccid_num'):
            query = apply_filter(query, SimResource.iccid_num, SimResource.iccid, params.get('iccid'))
        else:
            query = apply_filter(query, None, SimResource.iccid, params.get('iccid'))
            
        if hasattr(SimResource, 'msisdn_num'):
            query = apply_filter(query, SimResource.msisdn_num, SimResource.msisdn, params.get('msisdn'))
        else:
            query = apply_filter(query, None, SimResource.msisdn, params.get('msisdn'))
            
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
        # 獲取過濾器選項，用於下拉選單
        base_query = SimResource.query
        base_query = SimResourceManager._apply_search_filters(base_query, params)
        
        customers = base_query.with_entities(SimResource.customer)\
            .filter(SimResource.customer != None, SimResource.customer != '')\
            .distinct().order_by(SimResource.customer).all()
        
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
        query = SimResource.query
        
        if scope == 'selected' and selected_ids:
            # 這裡原本直接用 in_(ids)，現在改用通用方法處理 Range Objects
            q, err = SimResourceManager._get_batch_targets('selected', selected_ids)
            if not err:
                query = q
            else:
                # 如果出錯（例如空列表），返回空查詢
                return []
                
        elif scope == 'search' and search_params:
            query = SimResourceManager._apply_search_filters(query, search_params)
            query = SimResourceManager._apply_sorting(query, search_params)
        
        if extra_filters:
            customer = extra_filters.get('customer')
            assigned_date = extra_filters.get('assigned_date')
            if customer and customer != 'ALL':
                query = query.filter(SimResource.customer == customer)
            if assigned_date and assigned_date != 'ALL':
                query = query.filter(SimResource.assigned_date == assigned_date)
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
                resources_to_update = SimResource.query.filter(
                    SimResource.batch == batch_name,
                    SimResource.status == 'Available',
                    SimResource.supplier == provider,
                    SimResource.type == card_type,
                    SimResource.resources_type == resources_type
                ).order_by(SimResource.imsi_num.asc()).limit(take_qty).all() # 使用 imsi_num 排序
                
                if len(resources_to_update) < take_qty:
                    raise Exception(f"批次 {batch_name} 中符合條件的庫存不足")
                
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
    
    @staticmethod
    def _get_batch_targets(scope, ids=None, start_imsi=None, end_imsi=None):
        if scope == 'selected':
            if not ids: return None, "未選擇任何項目"
            if len(ids) > 0 and isinstance(ids[0], dict):
                conditions = []
                for item in ids:
                    start = item.get('start')
                    end = item.get('end')
                    batch = item.get('batch')
                    if start and end:
                        if str(start).isdigit() and str(end).isdigit():
                             s_int, e_int = int(start), int(end)
                             cond = and_(SimResource.imsi_num >= s_int, SimResource.imsi_num <= e_int, SimResource.batch == batch)
                        else:
                             cond = and_(SimResource.imsi >= start, SimResource.imsi <= end, SimResource.batch == batch)
                        conditions.append(cond)
                if not conditions: return None, "無效的選擇範圍數據"
                return SimResource.query.filter(or_(*conditions)), None
            else:
                return SimResource.query.filter(SimResource.id.in_(ids)), None
        elif scope == 'range':
            if not start_imsi or not end_imsi: return None, "請輸入起始和結束 IMSI"
            if str(start_imsi).isdigit() and str(end_imsi).isdigit():
                 s_int, e_int = int(start_imsi), int(end_imsi)
                 return SimResource.query.filter(SimResource.imsi_num >= s_int, SimResource.imsi_num <= e_int), None
            else:
                 return SimResource.query.filter(SimResource.imsi >= start_imsi, SimResource.imsi <= end_imsi), None
        return None, "無效的操作範圍"

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