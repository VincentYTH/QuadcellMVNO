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
        """应用搜索过滤器"""
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
        if params.get('imsi'):
            query = query.filter(SimResource.imsi.ilike(f'%{params["imsi"]}%'))
        if params.get('iccid'):
            query = query.filter(SimResource.iccid.ilike(f'%{params["iccid"]}%'))
        if params.get('msisdn'):
            query = query.filter(SimResource.msisdn.ilike(f'%{params["msisdn"]}%'))
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