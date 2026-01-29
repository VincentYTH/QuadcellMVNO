from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import Index

db = SQLAlchemy()

class SimResource(db.Model):
    __tablename__ = 'sim_resources'
    
    id = db.Column(db.Integer, primary_key=True)
    type = db.Column(db.String(50), nullable=False)
    supplier = db.Column(db.String(50), nullable=False)
    resources_type = db.Column(db.String(255), index=True)
    batch = db.Column(db.String(255), index=True)
    received_date = db.Column(db.String(255))
    
    # 原始字符串欄位
    imsi = db.Column(db.String(255), index=True)
    iccid = db.Column(db.String(255), index=True)
    msisdn = db.Column(db.String(255), index=True)
    
    # [Optimize] 純數字欄位優化 (Range Mode 專用)
    imsi_num = db.Column(db.BigInteger, index=True)
    msisdn_num = db.Column(db.BigInteger, index=True)
    iccid_num = db.Column(db.Numeric(22, 0), index=True)
    
    ki = db.Column(db.String(255))
    opc = db.Column(db.String(255))
    lpa = db.Column(db.String(255))
    pin1 = db.Column(db.String(255))
    puk1 = db.Column(db.String(255))
    pin2 = db.Column(db.String(255))
    puk2 = db.Column(db.String(255))
    
    status = db.Column(db.String(20), default='Available', index=True)
    customer = db.Column(db.String(100), nullable=True)
    assigned_date = db.Column(db.String(20), nullable=True)
    remark = db.Column(db.String(255), nullable=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # 複合索引優化
    __table_args__ = (
        Index('idx_supplier_type_status', 'supplier', 'type', 'status'),
        Index('idx_batch_status', 'batch', 'status'),
        Index('idx_imsi_num_status', 'imsi_num', 'status'),
    )

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
            'imsi_num': self.imsi_num,
            'iccid_num': str(self.iccid_num) if self.iccid_num else None,
            'status': self.status,
            'customer': self.customer,
            'assigned_date': self.assigned_date,
            'remark': self.remark,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }