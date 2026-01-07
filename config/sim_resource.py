# 预设选项数据
PROVIDER_OPTIONS = ['Quadcell', 'Montnet']

CARD_TYPE_OPTIONS = ['Physical SIM', 'eSIM', 'Soft Profile']

# 根据供应商预设资源类型选项
RESOURCES_TYPE_OPTIONS = {'MNT002', 'MNT001', 'MNT000'}

# 数据库配置
SQLALCHEMY_DATABASE_URI = 'postgresql://postgres:123456@localhost:5432/sim_management_db'
SQLALCHEMY_TRACK_MODIFICATIONS = False

# 应用配置
SECRET_KEY = 'QB($67:;P2G-h4qGo|f?'
UPLOAD_FOLDER = 'uploads'
MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB
CALLBACK_LOG_DIR = "CallbackLogs"

# 其他 SIM 相关配置
LOW_STOCK_THRESHOLD = 1000  # 低库存阈值