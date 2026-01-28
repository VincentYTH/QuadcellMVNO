from datetime import datetime
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class SimResource(db.Model):
    __tablename__ = 'sim_resources'
    
    id = db.Column(db.Integer, primary_key=True)
    type = db.Column(db.String(50), nullable=False)
    supplier = db.Column(db.String(50), nullable=False)
    resources_type = db.Column(db.String(255), index=True)
    batch = db.Column(db.String(255), index=True)
    received_date = db.Column(db.String(255))
    imsi = db.Column(db.String(255), index=True)
    iccid = db.Column(db.String(255), index=True)
    msisdn = db.Column(db.String(255), index=True)
    ki = db.Column(db.String(255))
    opc = db.Column(db.String(255))
    lpa = db.Column(db.String(255))
    pin1 = db.Column(db.String(255))
    puk1 = db.Column(db.String(255))
    pin2 = db.Column(db.String(255))
    puk2 = db.Column(db.String(255))
    
    # === 新增欄位 ===
    # 狀態: Available / Assigned，預設 Available
    status = db.Column(db.String(20), default='Available', index=True)
    # 客戶名稱
    customer = db.Column(db.String(100), nullable=True)
    # 分配日期 (格式 YYYY-MM-DD)
    assigned_date = db.Column(db.String(20), nullable=True)
    # 備注
    remark = db.Column(db.String(255), nullable=True)
    # ================
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f'<SimResource {self.id} - {self.type}>'
    
    def to_dict(self):
        return {
            'id': self.id,
            'type': self.type,
            'supplier': self.supplier,
            'resources_type': self.resources_type,
            'batch': self.batch,
            'received_date': self.received_date,
            'imsi': self.imsi,
            'iccid': self.iccid,
            'msisdn': self.msisdn,
            'status': self.status,
            'customer': self.customer,
            'assigned_date': self.assigned_date,
            'remark': self.remark,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }