from flask import Blueprint, render_template, request, jsonify, Response, send_file
from datetime import datetime
import pandas as pd
from io import StringIO
import csv
import os
from .manager import SimResourceManager
from models.sim_resource import SimResource, db
from flask import current_app

sim_resources_bp = Blueprint('sim_resources', __name__, url_prefix='/resources')

# SIM資源管理頁面 - 使用全寬模式
@sim_resources_bp.route('')
def resources_page():
    """SIM資源管理頁面 - 支持多欄位搜索 + 每頁50筆 + 排序"""
    page = request.args.get('page', 1, type=int)
    
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
        'sort': request.args.get('sort', 'updated_at'),
        'order': request.args.get('order', 'desc')
    }
    
    # 獲取資源列表
    resources = SimResourceManager.get_all_resources(search_params, page, 50)
    
    # 獲取選項數據
    options = SimResourceManager.get_options()
    
    # 傳遞 full_width=True 表示使用全寬模式
    return render_template('resources.html', 
                          resources=resources.items, 
                          pagination=resources,
                          options=options,
                          search_params=search_params,
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
                'puk2': res.puk2
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
    """匯入 SIM 資源 Excel，嚴格按照欄位規則 + 條件必填驗證"""
    try:
        if 'file' not in request.files:
            return jsonify({'error': '沒有上傳檔案'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': '沒有選擇檔案'}), 400
        
        if not file.filename.lower().endswith(('.xlsx', '.xls')):
            return jsonify({'error': '僅支援 Excel 檔案 (.xlsx 或 .xls)'}), 400

        # 只讀第一張 Sheet
        df = pd.read_excel(file, sheet_name=0)
        
        if df.empty:
            return jsonify({'error': '第一張 Sheet 為空'}), 400
        
        # 定義必填欄位（對應 Column A:H）
        required_columns = ['Provider', 'CardType', 'ResourcesType', 'Batch', 'ReceivedDate', 'IMSI', 'ICCID', 'MSISDN']
        missing_cols = [col for col in required_columns if col not in df.columns]
        if missing_cols:
            return jsonify({'error': f'缺少必填欄位: {", ".join(missing_cols)}'}), 400
        
        new_count = 0
        error_rows = []
        duplicate_count = 0
        duplicates_details = []
        
        # 取得現有 IMSI / ICCID 集合（防重複）
        existing = db.session.query(SimResource.imsi, SimResource.iccid).all()
        existing_imsi = {r.imsi for r in existing if r.imsi}
        existing_iccid = {r.iccid for r in existing if r.iccid}
        
        for idx, row in df.iterrows():
            row_num = idx + 2  # Excel 行號從 2 開始
            
            # 檢查必填欄位是否為空
            missing_required = [col for col in required_columns if pd.isna(row[col]) or str(row[col]).strip() == '']
            if missing_required:
                error_rows.append(f"第 {row_num} 行：缺少必填欄位 {', '.join(missing_required)}")
                continue
            
            # 轉成字串並清理
            data = {}
            for col in df.columns:
                val = row[col]
                if pd.notna(val):
                    data[col] = str(val).strip()
            
            card_type = data.get('CardType', '')
            
            # 條件必填驗證
            validation_error = []
            if card_type == 'Soft Profile':
                if not data.get('Ki'):
                    validation_error.append('Ki 必填')
                if not data.get('OPC'):
                    validation_error.append('OPC 必填')
            elif card_type == 'eSIM':
                if not data.get('LPA'):
                    validation_error.append('LPA 必填')
            elif card_type != 'Physical SIM':
                validation_error.append(f'CardType 必須是 Physical SIM / eSIM / Soft Profile，目前為: {card_type}')
            
            if validation_error:
                error_rows.append(f"第 {row_num} 行（{card_type}）：{', '.join(validation_error)}")
                continue
            
            # 重複檢查（IMSI 或 ICCID）
            current_imsi = data.get('IMSI')
            current_iccid = data.get('ICCID')
            is_duplicate = False
            reason = []
            if current_imsi and current_imsi in existing_imsi:
                is_duplicate = True
                reason.append(f"IMSI 重複: {current_imsi}")
            if current_iccid and current_iccid in existing_iccid:
                is_duplicate = True
                reason.append(f"ICCID 重複: {current_iccid}")
            
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
            
            # 直接建立新資源，使用獨立欄位
            new_resource = SimResource(
                type=card_type,
                supplier=data['Provider'],
                resources_type=data.get('ResourcesType'),
                batch=data.get('Batch'),
                received_date=data.get('ReceivedDate'),
                imsi=data.get('IMSI'),
                iccid=data.get('ICCID'),
                msisdn=data.get('MSISDN'),
                ki=data.get('Ki') or None,
                opc=data.get('OPC') or None,
                lpa=data.get('LPA') or None,
                pin1=data.get('PIN1') or None,
                puk1=data.get('PUK1') or None,
                pin2=data.get('PIN2') or None,
                puk2=data.get('PUK2') or None
            )
            
            db.session.add(new_resource)
            new_count += 1
            
            # 更新重複檢查集合
            if current_imsi:
                existing_imsi.add(current_imsi)
            if current_iccid:
                existing_iccid.add(current_iccid)
        
        db.session.commit()
        
        message = f'匯入完成！成功新增 {new_count} 筆'
        if duplicate_count > 0:
            message += f'，{duplicate_count} 筆因重複跳過'
        if error_rows:
            message += f'，{len(error_rows)} 筆因格式錯誤未匯入'
        
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