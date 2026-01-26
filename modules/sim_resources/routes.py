from flask import Blueprint, render_template, request, jsonify, Response, send_file
from datetime import datetime
import pandas as pd
from io import StringIO
import csv
import os
from .manager import SimResourceManager
from models.sim_resource import SimResource, db
from flask import current_app
from config.sim_resource import LOW_STOCK_THRESHOLD

sim_resources_bp = Blueprint('sim_resources', __name__, url_prefix='/resources')

# SIM資源管理頁面 - 使用全寬模式
@sim_resources_bp.route('')
def resources_page():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    view_mode = request.args.get('view_mode', 'single')  # 'single' or 'range'
    default_sort = 'assigned_date' if view_mode == 'range' else 'updated_at'
    
    # 獲取搜索參數
    search_params = {
        'provider': request.args.get('provider', '').strip(),
        'card_type': request.args.get('card_type', '').strip(),
        'resources_type': request.args.get('resources_type', '').strip(),
        'batch': request.args.get('batch', '').strip(),
        'received_date': request.args.get('received_date', '').strip(),
        'imsi': request.args.get('imsi', '').strip(),
        'iccid': request.args.get('iccid', '').strip(),
        'msisdn': request.args.get('msisdn', '').strip(),
        
        # 新增參數
        'status': request.args.get('status', '').strip(),
        'customer': request.args.get('customer', '').strip(),
        'assigned_date_start': request.args.get('assigned_date_start', '').strip(),
        'assigned_date_end': request.args.get('assigned_date_end', '').strip(),
        'remark': request.args.get('remark', '').strip(),
        
        'sort': request.args.get('sort', default_sort),
        'order': request.args.get('order', 'desc'),
        'per_page': per_page
    }
    
    # 根據 view_mode 調用不同的查詢方法
    if view_mode == 'range':
        resources = SimResourceManager.get_grouped_resources(search_params, page, per_page)
    else:
        resources = SimResourceManager.get_all_resources(search_params, page, per_page)
        
    options = SimResourceManager.get_options()
    
    return render_template('resources.html', 
                          resources=resources.items, 
                          pagination=resources,
                          options=options,
                          search_params=search_params,
                          view_mode=view_mode,
                          full_width=True)

# 编辑资源路由
@sim_resources_bp.route('/api/edit/<int:resource_id>', methods=['POST'])
def edit_resource(resource_id):
    """编辑资源"""
    try:
        data = request.json
        
        # 验证数据
        errors = SimResourceManager.validate_resource_data(data, is_edit=True, resource_id=resource_id)
        if errors:
            return jsonify({'error': '; '.join(errors)}), 400
        
        # 更新资源
        resource = SimResourceManager.update_resource(resource_id, data)
        return jsonify({'success': True, 'resource': resource.to_dict()})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

# 新增资源路由
@sim_resources_bp.route('/api/add', methods=['POST'])
def add_resource():
    """新增资源"""
    try:
        data = request.json
        
        # 验证数据
        errors = SimResourceManager.validate_resource_data(data)
        if errors:
            return jsonify({'error': '; '.join(errors)}), 400
        
        # 创建资源
        resource = SimResourceManager.create_resource(data)
        return jsonify({'success': True, 'resource': resource.to_dict()})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

# 添加获取选项的API
@sim_resources_bp.route('/api/options')
def get_resource_options():
    """获取资源选项"""
    options = SimResourceManager.get_options()
    return jsonify(options)

# 删除资源
@sim_resources_bp.route('/api/delete/<int:resource_id>', methods=['POST'])
def delete_resource(resource_id):
    try:
        resource = SimResource.query.get_or_404(resource_id)
        db.session.delete(resource)
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

# 獲取導出的動態篩選選項
@sim_resources_bp.route('/api/export/options', methods=['POST'])
def get_export_filter_options():
    try:
        data = request.json
        # 從前端接收當前的搜索參數
        search_params = data.get('search_params', {})
        # 接收 Modal 內部的過濾器 (例如已選的 Customer)
        modal_filters = data.get('modal_filters', {})
        
        options = SimResourceManager.get_distinct_filters(search_params, modal_filters)
        return jsonify(options)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# 导出CSV
@sim_resources_bp.route('/api/export')
def export_resources():
    try:
        resources = SimResource.query.all()
        output = []
        for res in resources:
            row = {
                'id': res.id,
                'type': res.type,
                'supplier': res.supplier,
                'created_at': res.created_at.isoformat(),
                'updated_at': res.updated_at.isoformat()
            }
            # 展开其他字段
            row.update({
                'resources_type': res.resources_type,
                'batch': res.batch,
                'received_date': res.received_date,
                'imsi': res.imsi,
                'iccid': res.iccid,
                'msisdn': res.msisdn,
                'ki': res.ki,
                'opc': res.opc,
                'lpa': res.lpa,
                'pin1': res.pin1,
                'puk1': res.puk1,
                'pin2': res.pin2,
                'puk2': res.puk2,
                'remark': res.remark
            })
            output.append(row)
        
        # 生成CSV
        si = StringIO()
        cw = csv.DictWriter(si, fieldnames=output[0].keys() if output else [])
        cw.writeheader()
        cw.writerows(output)
        return Response(si.getvalue(), mimetype='text/csv', headers={"Content-disposition": "attachment; filename=sim_resources.csv"})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# SIM Resource Import Excel
@sim_resources_bp.route('/api/import', methods=['POST'])
def import_resources():
    """匯入 SIM 資源 Excel，嚴格按照欄位規則 + 條件必填驗證，支持 Customer 和 Assign Date"""
    try:
        if 'file' not in request.files:
            return jsonify({'error': '沒有上傳檔案'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': '沒有選擇檔案'}), 400
        
        if not file.filename.lower().endswith(('.xlsx', '.xls')):
            return jsonify({'error': '僅支援 Excel 檔案 (.xlsx 或 .xls)'}), 400

        # [修改] 使用 dtype=str 強制所有數據讀取為字符串，防止 '0031' 變成 31.0
        # keep_default_na=False 會將空單元格讀取為空字符串 '' 而不是 NaN，這樣處理更方便
        df = pd.read_excel(file, sheet_name=0, dtype=str, keep_default_na=False)
        
        if df.empty:
            return jsonify({'error': '第一張 Sheet 為空'}), 400
        
        # 處理 Excel 標題前後可能的空格 (例如 'PIN2 ' -> 'PIN2')
        df.columns = df.columns.str.strip()
        
        required_columns = ['Provider', 'CardType', 'ResourcesType', 'Batch', 'ReceivedDate', 'IMSI', 'ICCID', 'MSISDN']
        missing_cols = [col for col in required_columns if col not in df.columns]
        if missing_cols:
            return jsonify({'error': f'缺少必填欄位: {", ".join(missing_cols)}'}), 400
        
        new_count = 0
        error_rows = []
        duplicate_count = 0
        duplicates_details = []
        
        existing = db.session.query(SimResource.imsi, SimResource.iccid).all()
        existing_imsi = {r.imsi for r in existing if r.imsi}
        existing_iccid = {r.iccid for r in existing if r.iccid}
        
        # 定義日期清洗函數
        def clean_date_str(val):
            if not val or val.lower() == 'nan':
                return None
            # 如果是 "2025-03-31 00:00:00" 這種格式，只取空格前的部分
            val = val.strip()
            if ' ' in val:
                val = val.split(' ')[0]
            return val

        for idx, row in df.iterrows():
            row_num = idx + 2
            
            missing_required = [col for col in required_columns if str(row.get(col, '')).strip() == '']
            if missing_required:
                error_rows.append(f"第 {row_num} 行：缺少必填欄位 {', '.join(missing_required)}")
                continue
            
            # 構建數據字典，去除內容前後空格
            data = {}
            for col in df.columns:
                val = row[col]
                data[col] = str(val).strip()
            
            card_type = data.get('CardType', '')
            
            validation_error = []
            if card_type == 'Soft Profile':
                if not data.get('Ki'): validation_error.append('Ki 必填')
                if not data.get('OPC'): validation_error.append('OPC 必填')
            elif card_type == 'eSIM':
                if not data.get('LPA'): validation_error.append('LPA 必填')
            elif card_type != 'Physical SIM':
                validation_error.append(f'CardType 必須是 Physical SIM / eSIM / Soft Profile')
            
            if validation_error:
                error_rows.append(f"第 {row_num} 行（{card_type}）：{', '.join(validation_error)}")
                continue
            
            current_imsi = data.get('IMSI')
            current_iccid = data.get('ICCID')
            is_duplicate = False
            reason = []
            if current_imsi and current_imsi in existing_imsi:
                is_duplicate = True
                reason.append(f"IMSI 重複")
            if current_iccid and current_iccid in existing_iccid:
                is_duplicate = True
                reason.append(f"ICCID 重複")
            
            if is_duplicate:
                duplicate_count += 1
                duplicates_details.append({
                    'row': row_num,
                    'CardType': card_type,
                    'IMSI': current_imsi,
                    'ICCID': current_iccid,
                    'reason': '，'.join(reason)
                })
                continue
            
            customer = data.get('Customer')
            
            # 處理日期格式，確保去掉時間部分
            raw_assign_date = data.get('Assign Date') or data.get('AssignDate') or data.get('AssignedDate')
            assign_date = clean_date_str(raw_assign_date)
            
            raw_received_date = data.get('ReceivedDate')
            received_date = clean_date_str(raw_received_date)

            remark = data.get('Remark')
            
            status = 'Available'
            if customer: 
                status = 'Assigned'
            
            new_resource = SimResource(
                type=card_type,
                supplier=data['Provider'],
                resources_type=data.get('ResourcesType'),
                batch=data.get('Batch'),
                received_date=received_date,
                imsi=data.get('IMSI'),
                iccid=data.get('ICCID'),
                msisdn=data.get('MSISDN'),
                ki=data.get('Ki') or None,
                opc=data.get('OPC') or None,
                lpa=data.get('LPA') or None,
                pin1=data.get('PIN1') or None,
                puk1=data.get('PUK1') or None,
                pin2=data.get('PIN2') or None,
                puk2=data.get('PUK2') or None,
                status=status,
                customer=customer,
                assigned_date=assign_date,
                remark=remark
            )
            
            db.session.add(new_resource)
            new_count += 1
            
            if current_imsi: existing_imsi.add(current_imsi)
            if current_iccid: existing_iccid.add(current_iccid)
        
        db.session.commit()
        
        message = f'匯入完成！成功新增 {new_count} 筆'
        if duplicate_count > 0: message += f'，{duplicate_count} 筆因重複跳過'
        if error_rows: message += f'，{len(error_rows)} 筆因格式錯誤未匯入'
        
        return jsonify({
            'success': True,
            'new_count': new_count,
            'duplicate_count': duplicate_count,
            'error_count': len(error_rows),
            'message': message,
            'errors': error_rows[:50],
            'duplicates': duplicates_details[:50]
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'匯入失敗: {str(e)}'}), 500

@sim_resources_bp.route('/api/assign/calculate', methods=['POST'])
def calculate_assignment():
    """計算分配選項"""
    data = request.json
    result = SimResourceManager.calculate_assignment_options(
        provider=data.get('provider'),
        card_type=data.get('card_type'),
        resources_type=data.get('resources_type'),
        quantity=int(data.get('quantity', 0))
    )
    return jsonify(result)

@sim_resources_bp.route('/api/assign/confirm', methods=['POST'])
def confirm_assignment():
    """確認並執行自動分配"""
    data = request.json
    result = SimResourceManager.confirm_assignment(
        plan=data.get('batches'),
        customer=data.get('customer'),
        assigned_date=data.get('assigned_date'),
        remark=data.get('remark'),
        provider=data.get('provider'),
        card_type=data.get('card_type'),
        resources_type=data.get('resources_type')
    )
    return jsonify(result)

@sim_resources_bp.route('/api/assign/manual', methods=['POST'])
def manual_assignment():
    """執行手動分配 (支持範圍或已選)"""
    data = request.json
    result = SimResourceManager.manual_assignment(
        scope=data.get('scope'),
        ids=data.get('ids'),
        start_imsi=data.get('start_imsi'),
        end_imsi=data.get('end_imsi'),
        customer=data.get('customer'),
        assigned_date=data.get('assigned_date'),
        remark=data.get('remark')
    )
    return jsonify(result)

@sim_resources_bp.route('/api/assign/cancel', methods=['POST'])
def cancel_assignment():
    """執行批量取消分配 (支持範圍或已選)"""
    data = request.json
    # 注意：這裡改用新的 batch_cancel_assignment 方法
    result = SimResourceManager.batch_cancel_assignment(
        scope=data.get('scope'),
        ids=data.get('ids'),
        start_imsi=data.get('start_imsi'),
        end_imsi=data.get('end_imsi'),
        remark=data.get('remark')
    )
    return jsonify(result)

@sim_resources_bp.route('/api/export_custom', methods=['POST'])
def export_custom_resources():
    """自定義導出資源"""
    try:
        data = request.json
        scope = data.get('scope', 'search')  # 'search' or 'selected'
        selected_ids = data.get('selected_ids', [])
        search_params = data.get('search_params', {})
        
        # 額外過濾器 (Customer & Assign Date)
        extra_filters = {
            'customer': data.get('filter_customer'),
            'assigned_date': data.get('filter_assigned_date')
        }
        
        # 獲取導出欄位配置
        selected_columns = data.get('columns', [])
        
        # 查詢數據
        resources = SimResourceManager.get_resources_for_export(
            scope=scope,
            selected_ids=selected_ids,
            search_params=search_params,
            extra_filters=extra_filters
        )
        
        # 檢查 columns 中是否包含 'IMSI' (對應 field_mapping 中的 imsi) -> asc
        if 'IMSI' in selected_columns:
            # 使用 Python 排序，處理 None 值
            resources.sort(key=lambda x: str(x.imsi) if x.imsi else '')
        
        # 欄位映射 (DB Model屬性 -> 導出標題)
        field_mapping = {
            'imsi': 'IMSI',
            'iccid': 'ICCID',
            'msisdn': 'MSISDN',
            'customer': 'Customer',
            'assigned_date': 'Assign Date',
            'remark': 'Remark',                        
            'supplier': 'Provider',
            'type': 'CardType',
            'resources_type': 'ResourcesType',
            'batch': 'Batch',
            'received_date': 'ReceivedDate',
            'ki': 'Ki',
            'opc': 'OPC',
            'lpa': 'LPA',
            'pin1': 'PIN1',
            'puk1': 'PUK1',
            'pin2': 'PIN2',
            'puk2': 'PUK2',
            'status': 'Status',
            'created_at': 'Created At',
            'updated_at': 'Updated At'
        }
        
        # 準備導出數據
        output_data = []
        for res in resources:
            row = {}
            for col in selected_columns:
                # 根據列名獲取對應的屬性值
                db_field = next((k for k, v in field_mapping.items() if v == col), None)
                if db_field:
                    val = getattr(res, db_field)
                    # 處理日期時間對象
                    if isinstance(val, datetime):
                        val = val.strftime('%Y-%m-%d %H:%M:%S')
                    # 確保所有值轉為字符串，防止科學計數法
                    row[col] = str(val) if val is not None else ''
            output_data.append(row)
            
        # 創建 DataFrame
        df = pd.DataFrame(output_data)
        
        # 如果沒有數據，創建空 DataFrame 但保留列頭
        if df.empty and selected_columns:
            df = pd.DataFrame(columns=selected_columns)
            
        # 寫入 Excel (使用 BytesIO)
        output = StringIO()
        # 對於 Excel，我們需要使用 BytesIO
        from io import BytesIO
        excel_output = BytesIO()
        
        with pd.ExcelWriter(excel_output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False)
            
        excel_output.seek(0)
        
        return Response(
            excel_output.getvalue(),
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            headers={"Content-disposition": f"attachment; filename=sim_resources_export_{datetime.now().strftime('%Y%m%d%H%M%S')}.xlsx"}
        )
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    
@sim_resources_bp.route('/api/batch/operation', methods=['POST'])
def batch_operation():
    """執行批量操作 (編輯/刪除)"""
    try:
        data = request.json
        action = data.get('action') # 'edit' 或 'delete'
        scope = data.get('scope')   # 'selected' 或 'range'
        ids = data.get('ids', [])
        start_imsi = data.get('start_imsi')
        end_imsi = data.get('end_imsi')
        
        if action == 'edit':
            update_data = data.get('data', {})
            result = SimResourceManager.batch_update_resources(scope, ids, start_imsi, end_imsi, update_data)
        elif action == 'delete':
            result = SimResourceManager.batch_delete_resources(scope, ids, start_imsi, end_imsi)
        else:
            return jsonify({"success": False, "message": "無效的操作類型"}), 400
            
        return jsonify(result)
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500
    
@sim_resources_bp.route('/api/inventory_stats')
def get_inventory_stats():
    """獲取庫存統計 API"""
    stats = SimResourceManager.get_inventory_stats()
    return jsonify({
        'stats': stats,
        'threshold': LOW_STOCK_THRESHOLD
    })    