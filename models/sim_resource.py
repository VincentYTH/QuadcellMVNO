from datetime import datetime
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class SimResource(db.Model):
    __tablename__ = 'sim_resources'
    
    id = db.Column(db.Integer, primary_key=True)
    type = db.Column(db.String(50), nullable=False)
    supplier = db.Column(db.String(50), nullable=False)
    resources_type = db.Column(db.String(255))
    batch = db.Column(db.String(255))
    received_date = db.Column(db.String(255))
    imsi = db.Column(db.String(255))
    iccid = db.Column(db.String(255))
    msisdn = db.Column(db.String(255))
    ki = db.Column(db.String(255))
    opc = db.Column(db.String(255))
    lpa = db.Column(db.String(255))
    pin1 = db.Column(db.String(255))
    puk1 = db.Column(db.String(255))
    pin2 = db.Column(db.String(255))
    puk2 = db.Column(db.String(255))
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
            'ki': self.ki,
            'opc': self.opc,
            'lpa': self.lpa,
            'pin1': self.pin1,
            'puk1': self.puk1,
            'pin2': self.pin2,
            'puk2': self.puk2,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }