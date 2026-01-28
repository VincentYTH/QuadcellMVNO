from flask import Blueprint, render_template, request, jsonify, Response, send_file, url_for, send_from_directory, current_app
from datetime import datetime
import pandas as pd
import io
import zipfile
import qrcode
from io import StringIO
import csv
import os
from .manager import SimResourceManager
from models.sim_resource import SimResource, db
from .config_manager import SimConfigManager

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

# SIM Resource Import/Modify Excel
@sim_resources_bp.route('/api/import', methods=['POST'])
def import_resources():
    """
    導入資源接口 (支持 Add 新增 和 Modify 修改)
    """
    if 'file' not in request.files:
        return jsonify({'success': False, 'message': '未上傳文件'}), 400
    
    file = request.files['file']
    mode = request.form.get('mode', 'add') # 獲取導入模式，默認為新增
    
    try:
        # 1. 讀取 Excel 通用處理
        # dtype=str 強制所有內容讀取為字符串 (防止 IMSI/ICCID 前導零丟失)
        df = pd.read_excel(file, dtype=str)
        df = df.fillna('') # 將 NaN (空值) 轉換為空字符串
        df.columns = df.columns.str.strip() # 去除標題前後空格
        
        # ==========================================
        # 模式 A: 修改現有資源 (Modify)
        # ==========================================
        if mode == 'modify':
            # 1. 驗證必要列
            if 'IMSI' not in df.columns:
                 return jsonify({'success': False, 'message': '模板錯誤：必須包含 "IMSI" 列 (Column A)'}), 400
            
            # 2. 定義映射關係 (Excel標題 -> DB欄位名)
            # 僅允許修改這些與安全/卡片參數相關的欄位
            field_map = {
                'Ki': 'ki', 
                'OPC': 'opc', 
                'LPA': 'lpa',
                'PIN1': 'pin1', 
                'PUK1': 'puk1', 
                'PIN2': 'pin2', 
                'PUK2': 'puk2'
            }
            
            # 3. 提取 Excel 中的所有 IMSI (用於批量查詢，提升性能)
            excel_imsis = df['IMSI'].dropna().astype(str).str.strip().tolist()
            excel_imsis = [i for i in excel_imsis if i] # 過濾掉空字符串
            
            if not excel_imsis:
                return jsonify({'success': False, 'message': 'Excel 中沒有有效的 IMSI 數據'}), 400

            # 4. 批量查詢數據庫中存在的資源
            # 使用 in_ 查詢一次性撈出所有相關記錄，避免在迴圈中頻繁查庫
            existing_resources = SimResource.query.filter(SimResource.imsi.in_(excel_imsis)).all()
            
            # 建立 IMSI -> Resource 對象的映射字典，方便快速查找
            resource_map = {res.imsi: res for res in existing_resources}
            
            updated_count = 0
            not_found_count = 0
            ignored_count = 0
            
            # 5. 遍歷 Excel 每一行進行更新
            for _, row in df.iterrows():
                imsi = str(row['IMSI']).strip()
                if not imsi: continue
                
                if imsi in resource_map:
                    resource = resource_map[imsi]
                    has_change = False
                    
                    # 遍歷允許修改的欄位
                    for excel_col, db_col in field_map.items():
                        if excel_col in df.columns:
                            val = str(row[excel_col]).strip()
                            # 關鍵邏輯：只有當 Excel 裡填了值，才修改 DB (非覆蓋式更新)
                            if val: 
                                setattr(resource, db_col, val)
                                has_change = True
                    
                    if has_change:
                        updated_count += 1
                    else:
                        ignored_count += 1 # 找到了 IMSI，但該行其他欄位都是空的
                else:
                    not_found_count += 1 # 數據庫裡沒這個 IMSI

            # 6. 提交更改
            if updated_count > 0:
                db.session.commit()
                
            # 7. 構建返回訊息
            msg = f"修改處理完成。"
            details = []
            if updated_count > 0: details.append(f"• 成功更新: {updated_count} 筆")
            if not_found_count > 0: details.append(f"• 庫存未找到: {not_found_count} 筆 (IMSI 不存在)")
            if ignored_count > 0: details.append(f"• 未變更: {ignored_count} 筆 (未填寫修改內容)")
            
            full_msg = msg + "\n" + "\n".join(details)
                
            return jsonify({
                'success': True, 
                'message': full_msg,
                'updated_count': updated_count,
                'error_count': not_found_count
            })

        # ==========================================
        # 模式 B: 新增資源 (Add)
        # ==========================================
        else:
            # 1. 驗證必要列
            required_columns = ['Provider', 'CardType', 'ResourcesType', 'Batch', 'ReceivedDate', 'IMSI', 'ICCID', 'MSISDN']
            missing_cols = [col for col in required_columns if col not in df.columns]
            if missing_cols:
                return jsonify({'success': False, 'message': f'模板錯誤：缺少必要列 {", ".join(missing_cols)}'}), 400

            success_count = 0
            duplicate_count = 0
            errors = []

            # 2. 獲取所有 IMSI 和 ICCID 用於預先查重 (性能優化)
            imsis = df['IMSI'].dropna().astype(str).str.strip().tolist()
            iccids = df['ICCID'].dropna().astype(str).str.strip().tolist()
            
            # 查出數據庫中已存在的 IMSI 和 ICCID
            existing_imsis = set(r[0] for r in db.session.query(SimResource.imsi).filter(SimResource.imsi.in_(imsis)).all())
            existing_iccids = set(r[0] for r in db.session.query(SimResource.iccid).filter(SimResource.iccid.in_(iccids)).all())

            # 3. 遍歷插入
            new_resources = []
            for index, row in df.iterrows():
                try:
                    imsi = str(row['IMSI']).strip()
                    iccid = str(row['ICCID']).strip()
                    
                    # 跳過空行
                    if not imsi or not iccid: continue
                    
                    # 查重邏輯
                    if imsi in existing_imsis or iccid in existing_iccids:
                        duplicate_count += 1
                        continue
                        
                    # 構建對象
                    res = SimResource(
                        supplier=str(row['Provider']).strip(),
                        type=str(row['CardType']).strip(),
                        resources_type=str(row['ResourcesType']).strip(),
                        batch=str(row['Batch']).strip(),
                        received_date=str(row['ReceivedDate']).strip(),
                        imsi=imsi,
                        iccid=iccid,
                        msisdn=str(row['MSISDN']).strip(),
                        status='Available', # 默認狀態
                        
                        # 可選欄位
                        ki=str(row.get('Ki', '')).strip() or None,
                        opc=str(row.get('OPC', '')).strip() or None,
                        lpa=str(row.get('LPA', '')).strip() or None,
                        pin1=str(row.get('PIN1', '')).strip() or None,
                        puk1=str(row.get('PUK1', '')).strip() or None,
                        pin2=str(row.get('PIN2', '')).strip() or None,
                        puk2=str(row.get('PUK2', '')).strip() or None,
                        remark=str(row.get('Remark', '')).strip() or None
                    )
                    new_resources.append(res)
                    
                    # 簡單的防重機制：把剛加進列表的也算作已存在，防止 Excel 內部有重複
                    existing_imsis.add(imsi)
                    existing_iccids.add(iccid)
                    
                except Exception as row_err:
                    errors.append(f"Row {index+2}: {str(row_err)}")

            # 4. 批量寫入
            if new_resources:
                # 使用 bulk_save_objects 提升寫入速度
                db.session.bulk_save_objects(new_resources)
                db.session.commit()
                success_count = len(new_resources)

            # 5. 構建返回訊息
            msg = f"導入完成。"
            details = []
            if success_count > 0: details.append(f"• 成功新增: {success_count} 筆")
            if duplicate_count > 0: details.append(f"• 跳過重複: {duplicate_count} 筆 (IMSI/ICCID 已存在)")
            if len(errors) > 0: details.append(f"• 數據錯誤: {len(errors)} 筆")
            
            full_msg = msg + "\n" + "\n".join(details)
            
            if len(errors) > 0 and len(errors) < 5:
                full_msg += "\n\n錯誤詳情:\n" + "\n".join(errors)

            return jsonify({
                'success': True,
                'message': full_msg,
                'success_count': success_count,
                'duplicate_count': duplicate_count,
                'error_count': len(errors)
            })

    except Exception as e:
        db.session.rollback()
        # import traceback
        # traceback.print_exc()
        return jsonify({'success': False, 'message': f"文件處理失敗: {str(e)}"}), 500

# 用於下載修改模板的路由
@sim_resources_bp.route('/api/template/<filename>')
def download_template(filename):
    """下載 Excel 模板"""
    # 假設您的模板存放在 app 根目錄下的 ExcelTemplate 文件夾
    # 您可能需要根據實際目錄結構調整 directory 參數
    template_dir = os.path.join(current_app.root_path, 'ExcelTemplate')
    
    # 安全檢查，只允許下載特定的模板
    allowed_templates = ['SIM_Resource_Template.xlsx', 'SIM_Resource_Modify_Template.xlsx']
    if filename not in allowed_templates:
        return jsonify({'success': False, 'message': '文件不存在或不允許下載'}), 404
        
    try:
        return send_from_directory(directory=template_dir, path=filename, as_attachment=True)
    except FileNotFoundError:
        return jsonify({'success': False, 'message': '服務器上找不到模板文件'}), 404

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
    """
    自定義導出接口
    功能: 
    1. 導出 Excel (支持自定義欄位、搜索範圍)
    2. 可選: 同步生成 eSIM LPA 的 QR Code 圖片並打包為 ZIP
    """
    try:
        # 1. 獲取請求參數
        data = request.json
        scope = data.get('scope') # 'selected' or 'search'
        selected_ids = data.get('selected_ids')
        search_params = data.get('search_params')
        selected_columns = data.get('columns', []) # 用戶勾選的導出欄位
        filter_customer = data.get('filter_customer')
        filter_assigned_date = data.get('filter_assigned_date')
        
        # 是否包含 QR Code
        include_qrcode = data.get('include_qrcode', False)
        
        # 2. 構建查詢 (復用 Manager 的過濾邏輯)
        query = SimResource.query
        
        if scope == 'selected' and selected_ids:
            query = query.filter(SimResource.id.in_(selected_ids))
        elif scope == 'search' and search_params:
            query = SimResourceManager._apply_search_filters(query, search_params)
            query = SimResourceManager._apply_sorting(query, search_params)
            
        # 額外的 Modal 過濾器
        if filter_customer and filter_customer != 'ALL':
            query = query.filter(SimResource.customer == filter_customer)
        if filter_assigned_date and filter_assigned_date != 'ALL':
            query = query.filter(SimResource.assigned_date == filter_assigned_date)
            
        # 執行查詢
        resources = query.all()
        
        # 10,000 筆數量限制檢查
        if include_qrcode and len(resources) > 10000:
            return jsonify({
                'error': f'QR Code 生成數量限制為 10,000 筆。當前篩選結果共 {len(resources)} 筆，請縮小範圍。'
            }), 400
        
        if not resources:
            return jsonify({'error': '沒有符合條件的數據可導出'}), 400

        # 3. 準備 Excel 數據
        export_list = []
        for res in resources:
            # 建立完整的數據字典 (Mapping DB欄位 -> Excel標題)
            row = {
                'IMSI': res.imsi,
                'ICCID': res.iccid,
                'MSISDN': res.msisdn,
                'LPA': res.lpa,
                'Ki': res.ki,
                'OPC': res.opc,
                'Customer': res.customer,
                'Assign Date': res.assigned_date,
                'Provider': res.supplier,
                'CardType': res.type,
                'ResourcesType': res.resources_type,
                'Remark': res.remark,
                'Status': res.status,
                'Batch': res.batch,
                'ReceivedDate': res.received_date,
                'PIN1': res.pin1,
                'PUK1': res.puk1,
                'PIN2': res.pin2,
                'PUK2': res.puk2,
                'Created At': res.created_at,
                'Updated At': res.updated_at
            }
            
            # 過濾欄位：只保留用戶勾選的 columns
            # 注意：如果用戶沒勾選 IMSI 或 LPA，Excel 裡就不會顯示，
            # 但我們在後續生成 QR Code 時依然可以直接訪問 res 對象，不受影響。
            filtered_row = {k: v for k, v in row.items() if k in selected_columns}
            export_list.append(filtered_row)

        # 創建 DataFrame
        df = pd.DataFrame(export_list)
        
        # 4. 生成 Excel 字節流 (寫入內存)
        excel_io = io.BytesIO()
        with pd.ExcelWriter(excel_io, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False, sheet_name='Resources')
        excel_data = excel_io.getvalue()
        
        # ==========================================
        # 分支 A: 僅導出 Excel (無需 QR Code)
        # ==========================================
        if not include_qrcode:
            excel_io.seek(0)
            return send_file(
                excel_io,
                mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                as_attachment=True,
                download_name='sim_resources.xlsx'
            )

        # ==========================================
        # 分支 B: 導出 ZIP (Excel + QR Codes)
        # ==========================================
        zip_io = io.BytesIO()
        
        # 使用 ZIP_DEFLATED 壓縮算法減少體積
        with zipfile.ZipFile(zip_io, 'w', zipfile.ZIP_DEFLATED) as zf:
            # B1. 將 Excel 寫入 ZIP 根目錄
            zf.writestr('sim_resources.xlsx', excel_data)
            
            # B2. 遍歷生成 QR Code
            # 優化：預先初始化 QR 工廠配置，避免在迴圈中重複初始化，提升 2000+ 筆數據的處理速度
            # ERROR_CORRECT_L (7%) 對於純文本 LPA 足夠了，且生成的圖片體積最小
            qr_factory = qrcode.QRCode(
                version=1, 
                error_correction=qrcode.constants.ERROR_CORRECT_L, 
                box_size=10, 
                border=2
            )
            
            for res in resources:
                # 只有 eSIM 且 LPA 有值時才生成
                if res.type == 'eSIM' and res.lpa:
                    try:
                        qr_factory.clear() # 重置矩陣
                        qr_factory.add_data(res.lpa)
                        qr_factory.make(fit=True)
                        
                        # 生成圖片對象
                        img = qr_factory.make_image(fill_color="black", back_color="white")
                        
                        # 保存圖片到內存流
                        img_byte_arr = io.BytesIO()
                        img.save(img_byte_arr, format='PNG')
                        
                        # 定義文件名：優先使用 IMSI，如果沒有則用 ICCID 或 ID
                        # 這樣用戶解壓後能直接通過文件名對應到 Excel 裡的數據
                        if res.iccid:
                            fname = f"{res.iccid}.png"
                        elif res.imsi:
                            fname = f"{res.imsi}.png"
                        else:
                            fname = f"unknown_{res.id}.png"
                        
                        # 將圖片寫入 ZIP 的 QRCodes 文件夾下
                        zf.writestr(f"QRCodes/{fname}", img_byte_arr.getvalue())
                        
                    except Exception as e:
                        print(f"QR Gen Error Resource ID {res.id}: {e}")
                        # 出錯時跳過該張圖片，不中斷整體導出
                        continue
        
        # 指針歸位
        zip_io.seek(0)
        
        # 返回 ZIP 文件
        return send_file(
            zip_io,
            mimetype='application/zip',
            as_attachment=True,
            download_name='sim_resources_package.zip'
        )

    except Exception as e:
        # 打印錯誤日誌方便後端調試
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'導出處理失敗: {str(e)}'}), 500
    
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
    
    # 動態獲取閾值
    config = SimConfigManager.load_config()
    threshold = config.get('low_stock_threshold', 1000)
    
    return jsonify({
        'stats': stats,
        'threshold': threshold
    })  
    
@sim_resources_bp.route('/api/config/get', methods=['GET'])
def get_config():
    """獲取當前配置"""
    try:
        config = SimConfigManager.load_config()
        return jsonify(config)
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@sim_resources_bp.route('/api/config/save', methods=['POST'])
def save_config():
    """保存配置"""
    try:
        new_config = request.json
        SimConfigManager.save_config(new_config)
        return jsonify({'success': True, 'message': '配置已保存'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@sim_resources_bp.route('/api/config/check_usage', methods=['POST'])
def check_config_usage():
    """檢查配置項是否被使用"""
    try:
        data = request.json
        category = data.get('category')
        value = data.get('value')
        
        is_used = SimConfigManager.check_usage(category, value)
        return jsonify({'used': is_used})
    except Exception as e:
        return jsonify({'used': True, 'error': str(e)}), 500 # 出錯時默認當作被使用，防止誤刪    
    
# 批量操作: 按導入IMSI
@sim_resources_bp.route('/api/batch/resolve_imsis', methods=['POST'])
def resolve_imsis_for_batch():
    """解析批量操作導入的 IMSI Excel (性能優化版)"""
    if 'file' not in request.files:
        return jsonify({'success': False, 'message': '未上傳文件'}), 400
    
    file = request.files['file']
    try:
        # 1. 讀取 Excel (只讀取需要的數據)
        # header=None 先讀取所有內容，稍後判斷
        df = pd.read_excel(file, header=None, dtype=str)
        
        target_series = pd.Series(dtype=str)
        
        # 智能尋找數據列
        # 嘗試 A: 尋找包含 "IMSI" 字樣的行作為標題
        # 展平所有數據並轉為字符串，去除空格
        all_values = df.values.flatten().astype(str)
        all_values = [x.strip() for x in all_values if x.lower() != 'nan' and x.lower() != 'imsi']
        
        # 使用 Pandas 向量化操作進行過濾 (比 Python for loop 快很多)
        s_values = pd.Series(all_values)
        
        # 2. 格式驗證 (15位數字)
        # 使用正則表達式匹配 15 位數字
        valid_mask = s_values.str.match(r'^\d{15}$')
        
        # 提取有效 IMSI (去重)
        valid_imsis = s_values[valid_mask].unique().tolist()
        
        # 統計無效數據 (這裡簡單計算總數差，不一一列出以節省資源)
        total_count = len(s_values)
        valid_count = len(valid_imsis)
        invalid_count = total_count - valid_count
        
        if not valid_imsis:
             return jsonify({'success': False, 'message': f'未在文件中找到有效的 15 位 IMSI 號碼 (共掃描 {total_count} 個單元格)。'}), 400

        # 3. 數據庫查詢優化
        # 只查詢 id 和 imsi 欄位，不加載整個對象
        # 使用 yield_per 分批處理，防止內存溢出 (雖然這裡只查 ID 影響不大，但好習慣)
        found_records = db.session.query(SimResource.imsi, SimResource.id)\
            .filter(SimResource.imsi.in_(valid_imsis))\
            .all()
        
        # 4. 構建結果
        found_map = {rec.imsi: rec.id for rec in found_records}
        found_ids = list(found_map.values())
        
        # 計算未找到的 IMSI
        not_found_count = len(valid_imsis) - len(found_ids)
        
        # 構建訊息
        message = f"解析完成！"
        details = [f"• 成功匹配庫存: {len(found_ids)} 筆"]
        
        if invalid_count > 0:
            details.append(f"• 忽略格式不符: {invalid_count} 筆 (非15位數字或標題)")
        
        if not_found_count > 0:
            details.append(f"• 庫存未找到: {not_found_count} 筆")
            
        full_message = message + "\n" + "\n".join(details)
            
        return jsonify({
            'success': True,
            'ids': found_ids,
            'count': len(found_ids),
            'message': full_message,
            'invalid_count': invalid_count,
            'not_found_count': not_found_count
        })

    except Exception as e:
        # import traceback
        # traceback.print_exc()
        return jsonify({'success': False, 'message': f"解析失敗: {str(e)}"}), 500
    
# 用於即時查看單個資源 QR Code 的接口
@sim_resources_bp.route('/api/qrcode/view/<int:resource_id>')
def get_resource_qrcode(resource_id):
    """即時生成並返回單個資源的 QR Code 圖片流"""
    resource = SimResource.query.get_or_404(resource_id)
    
    if not resource.lpa:
        return jsonify({'success': False, 'message': '此資源沒有 LPA 數據'}), 404
        
    try:
        # 生成 QR Code
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L, # 使用低容錯率 (L) 以減小體積和加快生成速度
            box_size=10,
            border=2,
        )
        qr.add_data(resource.lpa)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        
        # 轉為字節流
        img_io = io.BytesIO()
        img.save(img_io, 'PNG')
        img_io.seek(0)
        
        return send_file(img_io, mimetype='image/png')
    except Exception as e:
        return jsonify({'success': False, 'message': f'生成失敗: {str(e)}'}), 500    